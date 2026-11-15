"""Assemble report/REPORT.md from the section files, then build the PDF (scripts/build_report.py).

    python -m scripts.assemble_report
"""

from __future__ import annotations

import re
from pathlib import Path

R = Path(__file__).resolve().parents[1] / "report"


def section(text: str, start: str, end: str | None) -> str:
    i = text.index(start)
    j = text.index(end, i) if end else len(text)
    return text[i:j].strip()


def main() -> None:
    static = (R / "sections_static.md").read_text(encoding="utf-8")
    parts = {
        "{{STATIC_1_2}}": section(static, "## 1.", "## 9."),
        "{{STATIC_9}}": section(static, "## 9.", None),
        "{{SECTION_3}}": (R / "s3.md").read_text(encoding="utf-8").strip(),
        "{{SECTION_4}}": (R / "s4.md").read_text(encoding="utf-8").strip(),
        "{{SECTION_5}}": (R / "s5.md").read_text(encoding="utf-8").strip(),
        "{{SECTION_6}}": section((R / "s6_7_8.md").read_text(encoding="utf-8"), "## 6.", "## 7."),
        "{{SECTION_7}}": section((R / "s6_7_8.md").read_text(encoding="utf-8"), "## 7.", "## 8."),
        "{{SECTION_8}}": section((R / "s6_7_8.md").read_text(encoding="utf-8"), "## 8.", None),
        "{{SECTION_10}}": (R / "s10.md").read_text(encoding="utf-8").strip(),
    }
    tmpl = (R / "REPORT_TEMPLATE.md").read_text(encoding="utf-8")
    for k, v in parts.items():
        tmpl = tmpl.replace(k, v)
    left = re.findall(r"\{\{[A-Z0-9_]+\}\}", tmpl)
    if left:
        raise SystemExit(f"unfilled placeholders: {left}")
    (R / "REPORT.md").write_text(tmpl, encoding="utf-8")
    print("wrote report/REPORT.md", len(tmpl.split()), "words")


if __name__ == "__main__":
    main()
