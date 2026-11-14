"""Local model throughput (Models rule: report hardware + tokens/s for local models).

    python -m evals.runners.model_speed --models qwen3:1.7b,qwen3:4b --calls 2
"""

from __future__ import annotations

import argparse
import asyncio
import os
import platform
import time

from evals.runners.common import save, setup_env


async def main_async(args) -> None:
    setup_env("open_small")
    from langchain_core.messages import HumanMessage
    from langchain_ollama import ChatOllama

    out = {"hardware": {"machine": platform.machine(), "processor": platform.processor(), "cpu_count": os.cpu_count(),
                        "os": platform.platform(), "gpu": "none (Intel UHD 620 integrated, unused)"}, "models": {}}
    prompt = "In three sentences, describe how you would build a churn prediction model with scikit-learn and evaluate it."
    for m in args.models.split(","):
        llm = ChatOllama(model=m, base_url=os.environ["OLLAMA_BASE_URL"], reasoning=False, num_predict=160, temperature=0)
        runs = []
        for i in range(args.calls):
            t0 = time.perf_counter()
            try:
                msg = await asyncio.wait_for(llm.ainvoke([HumanMessage(prompt)]), timeout=args.timeout)
                dt = time.perf_counter() - t0
                um = msg.usage_metadata or {}
                meta = msg.response_metadata or {}
                ev, evd = meta.get("eval_count"), meta.get("eval_duration")
                runs.append({"call": i + 1, "wall_s": round(dt, 2), "tokens_in": um.get("input_tokens"), "tokens_out": um.get("output_tokens"),
                             "gen_tok_per_s": round(ev / (evd / 1e9), 2) if ev and evd else None,
                             "load_s": round(meta.get("load_duration", 0) / 1e9, 2)})
            except Exception as exc:  # noqa: BLE001
                runs.append({"call": i + 1, "error": f"{type(exc).__name__} after {time.perf_counter() - t0:.0f}s"})
            print(m, runs[-1])
        out["models"][m] = runs
    save("model_speed", out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="qwen3:1.7b,qwen3:4b")
    ap.add_argument("--calls", type=int, default=2)
    ap.add_argument("--timeout", type=float, default=900)
    asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    main()
