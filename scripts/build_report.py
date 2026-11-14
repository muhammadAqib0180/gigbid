"""Render report/REPORT.md to report/GigBid_RD_Report.pdf (Markdown -> HTML -> fpdf2).

    python -m scripts.build_report
"""

from __future__ import annotations

import re
from pathlib import Path

import markdown
from fpdf import FPDF

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "report" / "REPORT.md"
OUT = ROOT / "report" / "GigBid_RD_Report.pdf"

REPL = {"—": "-", "–": "-", "’": "'", "‘": "'", "“": '"', "”": '"', "→": "->", "≤": "<=",
        "≥": ">=", "≈": "~", "×": "x", "…": "...", "•": "-", "‖": "||", "✓": "yes", "✗": "no",
        "·": "|", "−": "-", "κ": "kappa", " ": " ", "←": "<-", "│": "|", "─": "-", "►": ">"}


class PDF(FPDF):
    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 8, f"GigBid - AI-4016 R&D report - page {self.page_no()}", align="C")


def clean(s: str) -> str:
    for k, v in REPL.items():
        s = s.replace(k, v)
    return s.encode("latin-1", "replace").decode("latin-1")


def main() -> None:
    md = clean(SRC.read_text(encoding="utf-8"))
    html = markdown.markdown(md, extensions=["tables", "fenced_code"])
    html = re.sub(r"<table>", '<table border="1" width="100%">', html)
    html = re.sub(r"<code>(.*?)</code>", r"<font face='Courier'>\1</font>", html, flags=re.S)
    pdf = PDF(format="A4")
    pdf.set_margins(16, 14, 16)
    pdf.set_auto_page_break(True, 14)
    pdf.add_page()
    pdf.set_font("Helvetica", size=9.5)
    pdf.write_html(html, table_line_separators=True, tag_styles=None)
    pdf.output(str(OUT))
    print(f"wrote {OUT} ({pdf.page_no()} pages)")


if __name__ == "__main__":
    main()
