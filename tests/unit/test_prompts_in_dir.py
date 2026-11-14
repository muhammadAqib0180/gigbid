"""CI rule: every prompt lives in agent/prompts/ (no inline prompts in node code)."""

import ast
import re
from pathlib import Path

from agent.prompting import PROMPT_DIR, list_prompts, load_prompt

ROOT = Path(__file__).resolve().parents[2]
SCAN = [ROOT / "agent", ROOT / "rag", ROOT / "apps" / "api", ROOT / "evals" / "runners"]
PROMPTY = re.compile(r"^\s*(you are|your task|you will|act as|system:|instructions:)", re.I)


def test_every_referenced_prompt_exists():
    names = set(list_prompts())
    used: set[str] = set()
    for base in SCAN:
        for f in base.rglob("*.py"):
            src = f.read_text(encoding="utf-8")
            used |= set(re.findall(r"llm\.(?:structured|text)\(\s*\"[a-z_]+\",\s*\"([a-z_]+)\"", src))
    assert used, "no prompt usages found"
    missing = used - names
    assert not missing, f"prompts referenced but not in {PROMPT_DIR}: {missing}"


def test_no_inline_prompts_in_code():
    offenders = []
    for base in SCAN:
        for f in base.rglob("*.py"):
            tree = ast.parse(f.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", "")) in {
                        "SystemMessage", "ChatPromptTemplate", "PromptTemplate"}:
                    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                        offenders.append(f"{f}:{node.lineno}")
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and len(node.value) > 160 and PROMPTY.match(node.value):
                    offenders.append(f"{f}:{node.lineno}")
    assert not offenders, f"inline prompts found: {offenders}"


def test_prompts_are_versioned():
    for name in list_prompts():
        p = load_prompt(name)
        assert p.version and p.system, name
