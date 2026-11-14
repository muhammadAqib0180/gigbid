"""Prompt loading. Every prompt is a versioned Markdown file in agent/prompts/ (no inline prompts).

File format:
    ---
    name: writer
    version: 3
    ---
    ## system
    ...
    ## user
    ... {placeholders} ...
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
_SECTION = re.compile(r"^##\s+(system|user)\s*$", re.MULTILINE)


class _SafeDict(dict):
    def __missing__(self, key: str) -> str:  # leave unknown placeholders visible
        return "{" + key + "}"


@dataclass(frozen=True)
class Prompt:
    name: str
    version: str
    system: str
    user: str

    @property
    def ref(self) -> str:
        return f"{self.name}@v{self.version}"

    def render(self, **variables: object) -> tuple[str, str]:
        vals = _SafeDict({k: ("" if v is None else str(v)) for k, v in variables.items()})
        return self.system.format_map(vals), self.user.format_map(vals)


@lru_cache(maxsize=64)
def load_prompt(name: str) -> Prompt:
    path = PROMPT_DIR / f"{name}.md"
    text = path.read_text(encoding="utf-8")
    meta: dict = {}
    if text.startswith("---"):
        _, fm, text = text.split("---", 2)
        meta = yaml.safe_load(fm) or {}
    parts = _SECTION.split(text)
    sections: dict[str, str] = {}
    for i in range(1, len(parts) - 1, 2):
        sections[parts[i]] = parts[i + 1].strip()
    return Prompt(
        name=str(meta.get("name", name)),
        version=str(meta.get("version", "1")),
        system=sections.get("system", ""),
        user=sections.get("user", ""),
    )


def list_prompts() -> list[str]:
    return sorted(p.stem for p in PROMPT_DIR.glob("*.md") if p.stem.lower() != "readme")
