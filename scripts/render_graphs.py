"""Render both LangGraph graphs from code: docs/images/{bid,conversation}_graph.mmd (Mermaid source, from
graph.get_graph().draw_mermaid()) and .png (drawn by Mermaid in a headless Edge/Chromium via scripts/mermaid_png.mjs).

    python -m scripts.render_graphs            # .mmd + .png
    python -m scripts.render_graphs --check    # fail if the committed .mmd no longer matches the code
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMG = ROOT / "docs" / "images"


def mermaid_sources() -> dict[str, str]:
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.store.memory import InMemoryStore

    from agent.graphs.bid_graph import build_bid_graph
    from agent.graphs.conversation_graph import build_conversation_graph

    return {"bid_graph": build_bid_graph(InMemorySaver(), InMemoryStore()).get_graph().draw_mermaid(),
            "conversation_graph": build_conversation_graph(InMemorySaver(), InMemoryStore()).get_graph().draw_mermaid()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    srcs = mermaid_sources()
    if args.check:
        stale = [n for n, s in srcs.items() if (IMG / f"{n}.mmd").read_text(encoding="utf-8") != s]
        if stale:
            sys.exit(f"graph renders are stale: {stale} (run python -m scripts.render_graphs)")
        print("graph renders match the code")
        return
    IMG.mkdir(parents=True, exist_ok=True)
    for name, src in srcs.items():
        (IMG / f"{name}.mmd").write_text(src, encoding="utf-8")
        print("wrote", IMG / f"{name}.mmd")
    node = shutil.which("node")
    if not node:
        print("node not found: skipped PNG rendering")
        return
    for name in srcs:
        subprocess.run([node, str(ROOT / "scripts" / "mermaid_png.mjs"), str(IMG / f"{name}.mmd"), str(IMG / f"{name}.png")],
                       cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
