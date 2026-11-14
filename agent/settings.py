"""Configuration loading: agent/config.yaml (with ${VAR:-default} expansion) + environment."""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = Path(os.getenv("GIGBID_CONFIG", ROOT / "agent" / "config.yaml"))

load_dotenv(ROOT / ".env", override=False)

_ENV_RE = re.compile(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?\}")


def _expand(value: Any) -> Any:
    if isinstance(value, str):
        def repl(m: re.Match[str]) -> str:
            return os.getenv(m.group(1), m.group(2) if m.group(2) is not None else "")

        out = _ENV_RE.sub(repl, value)
        return out
    if isinstance(value, dict):
        return {k: _expand(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand(v) for v in value]
    return value


@lru_cache(maxsize=1)
def config() -> dict[str, Any]:
    with open(CONFIG_PATH, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return _expand(raw)


def reload_config() -> dict[str, Any]:
    config.cache_clear()
    return config()


def cfg(path: str, default: Any = None) -> Any:
    """Dotted lookup, e.g. cfg("budgets.max_graph_steps")."""
    node: Any = config()
    for part in path.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return default
    return node


def env(name: str, default: str | None = None) -> str | None:
    return os.getenv(name, default)


def data_dir() -> Path:
    return Path(env("GIGBID_DATA_DIR", str(ROOT / "data")) or ROOT / "data")


def processed_dir() -> Path:
    p = data_dir() / "processed"
    p.mkdir(parents=True, exist_ok=True)
    return p


def database_url() -> str:
    url = env("DATABASE_URL") or f"sqlite+aiosqlite:///{(processed_dir() / 'gigbid.db').as_posix()}"
    return url


def is_postgres() -> bool:
    return database_url().startswith("postgresql")
