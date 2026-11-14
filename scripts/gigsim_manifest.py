"""Freeze / verify gigsim/ (CI rule: nothing under gigsim/ changes).

    python -m scripts.gigsim_manifest --write    # once, when the simulator is frozen
    python -m scripts.gigsim_manifest --check    # CI
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "gigsim"
MANIFEST = ROOT / "MANIFEST.sha256"


def digest() -> dict[str, str]:
    out = {}
    for f in sorted(ROOT.rglob("*")):
        if f.is_file() and f != MANIFEST and "__pycache__" not in f.parts:
            data = f.read_bytes().replace(b"\r\n", b"\n")
            out[f.relative_to(ROOT).as_posix()] = hashlib.sha256(data).hexdigest()
    return out


def main() -> int:
    if "--write" in sys.argv:
        MANIFEST.write_text("".join(f"{h}  {p}\n" for p, h in digest().items()), encoding="utf-8")
        print(f"wrote {MANIFEST}")
        return 0
    expected = dict(line.split("  ", 1)[::-1] for line in MANIFEST.read_text(encoding="utf-8").splitlines() if line.strip())
    expected = {k.strip(): v for k, v in expected.items()}
    current = digest()
    bad = sorted(set(expected) ^ set(current)) + sorted(p for p in current if p in expected and current[p] != expected[p])
    if bad:
        print("gigsim/ changed:", bad)
        return 1
    print(f"gigsim/ unchanged ({len(current)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
