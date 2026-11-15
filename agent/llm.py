"""Model router: every node's model comes from agent/config.yaml (profile -> node -> provider/model).

* `structured()` returns a validated Pydantic object; `text()` returns a string.
* Fallback chain: primary -> configured fallback -> optional deterministic heuristic.
* Usage (tokens, USD, latency) is returned per node so graphs can enforce token budgets (C4)
  and report cost per job / per proposal (R8).
* Provider `fake` (profile `test`) runs the node's deterministic heuristic: CI and the offline
  demo run end to end with no API key.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, ValidationError

from agent.prompting import load_prompt
from agent.settings import cfg

log = logging.getLogger("gigbid.llm")
T = TypeVar("T", bound=BaseModel)

_SEMAPHORES: dict[str, asyncio.Semaphore] = {}
_MODEL_CACHE: dict[tuple, BaseChatModel] = {}
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class LLMError(RuntimeError):
    pass


@dataclass
class LLMResult:
    value: Any
    usage: dict[str, dict[str, float]] = field(default_factory=dict)
    model: str = ""
    prompt_ref: str = ""
    fallback_used: str | None = None


def active_profile() -> str:
    return os.getenv("MODEL_PROFILE") or cfg("models.profile", "open") or "open"


def node_spec(node: str, profile: str | None = None) -> dict[str, Any]:
    prof = cfg(f"models.profiles.{profile or active_profile()}", {}) or {}
    spec = dict(prof.get("default", {}))
    spec.update((prof.get("nodes") or {}).get(node, {}) or {})
    return spec


def _chain(node: str, profile: str | None) -> list[dict[str, Any]]:
    spec = node_spec(node, profile)
    chain = [spec]
    fb = spec.get("fallback")
    if fb:
        merged = {k: v for k, v in spec.items() if k not in {"fallback", "provider", "model", "extra"}}
        merged.update(fb)
        chain.append(merged)
    return chain


def _price(model: str, tokens_in: int, tokens_out: int) -> float:
    table = cfg("models.pricing_usd_per_1m", {}) or {}
    pin, pout = table.get(model, [0.0, 0.0])
    return (tokens_in * float(pin) + tokens_out * float(pout)) / 1_000_000


def _build(spec: dict[str, Any], structured: bool) -> BaseChatModel:
    provider = spec["provider"]
    pconf = cfg(f"models.providers.{provider}", {}) or {}
    kind = pconf.get("kind")
    key = (provider, spec["model"], structured, spec.get("temperature"))
    if key in _MODEL_CACHE:
        return _MODEL_CACHE[key]
    timeout = float(cfg("budgets.node_timeout_s", 120))
    if kind == "openai_compatible":
        api_key = os.getenv(pconf.get("api_key_env", ""), "")
        if not api_key:
            raise LLMError(f"{pconf.get('api_key_env')} not set for provider {provider}")
        from langchain_openai import ChatOpenAI

        extra = dict(spec.get("extra") or {})
        model: BaseChatModel = ChatOpenAI(
            model=spec["model"],
            base_url=pconf["base_url"],
            api_key=api_key,
            temperature=spec.get("temperature", 0.2),
            timeout=timeout,
            max_retries=1,
            **extra,
        )
        if structured:
            model = model.bind(response_format={"type": "json_object"})  # type: ignore[assignment]
    elif kind == "ollama":
        from langchain_ollama import ChatOllama

        model = ChatOllama(
            model=spec["model"],
            base_url=pconf.get("base_url") or "http://localhost:11434",
            temperature=spec.get("temperature", 0.2),
            reasoning=False,
            num_ctx=int(spec.get("num_ctx", 8192)),
            format="json" if structured else None,
        )
    else:
        raise LLMError(f"provider kind {kind!r} cannot build a chat model")
    _MODEL_CACHE[key] = model
    return model


def _sem(provider: str) -> asyncio.Semaphore:
    if provider not in _SEMAPHORES:
        _SEMAPHORES[provider] = asyncio.Semaphore(1 if provider == "ollama" else 4)
    return _SEMAPHORES[provider]


def _parse_json(text: str) -> Any:
    text = _THINK.sub("", text).strip()
    text = _FENCE.sub("", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


def _schema_hint(schema: type[BaseModel]) -> str:
    return json.dumps(schema.model_json_schema(), separators=(",", ":"))


def _usage_entry(node: str, msg: AIMessage | None, model: str, latency: float) -> dict[str, dict[str, float]]:
    um = getattr(msg, "usage_metadata", None) or {}
    tin, tout = int(um.get("input_tokens", 0)), int(um.get("output_tokens", 0))
    return {
        node: {
            "calls": 1,
            "tokens_in": tin,
            "tokens_out": tout,
            "usd": _price(model, tin, tout),
            "latency_s": latency,
            "latency_max_s": latency,
        }
    }


def _heuristic_usage(node: str, latency: float) -> dict[str, dict[str, float]]:
    return {node: {"calls": 1, "tokens_in": 0, "tokens_out": 0, "usd": 0.0, "latency_s": latency, "latency_max_s": latency}}


async def _invoke(spec: dict, structured: bool, system: str, user: str) -> tuple[AIMessage, float]:
    model = _build(spec, structured)
    t0 = time.perf_counter()
    async with _sem(spec["provider"]):
        msg = await asyncio.wait_for(
            model.ainvoke([SystemMessage(system), HumanMessage(user)]),
            timeout=float(cfg("budgets.node_timeout_s", 120)),
        )
    return msg, time.perf_counter() - t0  # type: ignore[return-value]


async def structured(
    node: str,
    prompt: str,
    schema: type[T],
    variables: dict[str, Any],
    heuristic: Callable[[], T] | None = None,
    profile: str | None = None,
) -> LLMResult:
    p = load_prompt(prompt)
    system, user = p.render(**variables)
    system = f"{system}\n\nReturn ONLY a JSON object that validates against this JSON schema:\n{_schema_hint(schema)}"
    errors: list[str] = []
    usage: dict[str, dict[str, float]] = {}
    chain = _chain(node, profile)
    for spec in chain:
        if spec.get("provider") == "fake":
            break
        try:
            msg, latency = await _invoke(spec, True, system, user)
            for k, v in _usage_entry(node, msg, spec["model"], latency).items():
                usage[k] = v
            try:
                value = schema.model_validate(_parse_json(str(msg.content)))
            except (ValidationError, json.JSONDecodeError, ValueError) as exc:
                # one repair round
                repair = f"{user}\n\nYour previous output was invalid ({str(exc)[:300]}). Return only valid JSON."
                msg2, lat2 = await _invoke(spec, True, system, repair)
                u2 = _usage_entry(node, msg2, spec["model"], lat2)[node]
                for key in ("calls", "tokens_in", "tokens_out", "usd", "latency_s"):
                    usage[node][key] += u2[key]
                value = schema.model_validate(_parse_json(str(msg2.content)))
            return LLMResult(value, usage, spec["model"], p.ref, None if spec is chain[0] else "fallback_model")
        except Exception as exc:  # noqa: BLE001 - try next model in the chain
            errors.append(f"{spec.get('provider')}/{spec.get('model')}: {type(exc).__name__}: {str(exc)[:200]}")
            log.warning("node %s model failed: %s", node, errors[-1])
    if heuristic is not None:
        t0 = time.perf_counter()
        value = heuristic()
        used = None if (node_spec(node, profile).get("provider") == "fake") else "heuristic"
        return LLMResult(value, _heuristic_usage(node, time.perf_counter() - t0), "heuristic-v1", p.ref, used)
    raise LLMError(f"all models failed for node {node}: {errors}")


async def text(
    node: str,
    prompt: str,
    variables: dict[str, Any],
    heuristic: Callable[[], str] | None = None,
    profile: str | None = None,
) -> LLMResult:
    p = load_prompt(prompt)
    system, user = p.render(**variables)
    errors: list[str] = []
    chain = _chain(node, profile)
    for spec in chain:
        if spec.get("provider") == "fake":
            break
        try:
            msg, latency = await _invoke(spec, False, system, user)
            out = _THINK.sub("", str(msg.content)).strip()
            return LLMResult(out, _usage_entry(node, msg, spec["model"], latency), spec["model"], p.ref,
                             None if spec is chain[0] else "fallback_model")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{spec.get('provider')}/{spec.get('model')}: {type(exc).__name__}: {str(exc)[:200]}")
            log.warning("node %s model failed: %s", node, errors[-1])
    if heuristic is not None:
        t0 = time.perf_counter()
        value = heuristic()
        used = None if (node_spec(node, profile).get("provider") == "fake") else "heuristic"
        return LLMResult(value, _heuristic_usage(node, time.perf_counter() - t0), "heuristic-v1", p.ref, used)
    raise LLMError(f"all models failed for node {node}: {errors}")


def total_tokens(usage: dict[str, dict[str, float]]) -> int:
    return int(sum(u.get("tokens_in", 0) + u.get("tokens_out", 0) for u in usage.values()))


def total_usd(usage: dict[str, dict[str, float]]) -> float:
    return float(sum(u.get("usd", 0.0) for u in usage.values()))


def chat_model_for(node: str, profile: str | None = None) -> BaseChatModel:
    """Raw chat model for tool-calling agents (baselines in R&D A/C)."""
    for spec in _chain(node, profile):
        try:
            return _build(spec, structured=False)
        except LLMError:
            continue
    raise LLMError(f"no usable model for node {node}")
