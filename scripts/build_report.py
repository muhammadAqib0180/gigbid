"""Render report/REPORT.md to report/GigBid_RD_Report.pdf.

    python -m scripts.build_report

Markdown -> styled HTML (report/REPORT.html) -> PDF printed by Chromium (scripts/html_to_pdf.mjs, using the browser the
web app's Playwright installs: `cd apps/web && npx playwright install chromium`). Falls back to fpdf2 if Node or
Chromium is missing (plainer tables).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "report" / "REPORT.md"
HTML = ROOT / "report" / "REPORT.html"
OUT = ROOT / "report" / "GigBid_RD_Report.pdf"

CSS = """
@page { size: A4; }
body { font-family: "Segoe UI", Helvetica, Arial, sans-serif; font-size: 9.6pt; line-height: 1.36; color: #1a1a1a; margin: 0; }
h1 { font-size: 17pt; margin: 0 0 4pt; }
h2 { font-size: 12.5pt; margin: 11pt 0 3pt; border-bottom: 1px solid #ccc; padding-bottom: 1pt; break-after: avoid; }
h3 { font-size: 10.5pt; margin: 8pt 0 2pt; break-after: avoid; }
p, li { margin: 3pt 0; text-align: left; }
ul, ol { padding-left: 16pt; margin: 3pt 0; }
code { font-family: Consolas, "Courier New", monospace; font-size: 8.6pt; background: #f3f3f3; padding: 0 2px; border-radius: 2px; }
pre { background: #f6f6f6; padding: 5pt; font-size: 8pt; white-space: pre-wrap; break-inside: avoid; }
pre code { background: none; padding: 0; }
table { border-collapse: collapse; width: 100%; margin: 4pt 0 6pt; font-size: 8.2pt; line-height: 1.25; break-inside: auto; }
tr { break-inside: avoid; }
th, td { border: 1px solid #bbb; padding: 2pt 4pt; vertical-align: top; text-align: left; }
th { background: #eef1f5; font-weight: 600; }
tbody tr:nth-child(even) td { background: #fafafa; }
img { max-width: 100%; max-height: 560px; display: block; margin: 4pt auto 0; }
p:has(img) { break-inside: avoid; }
"""


def build_html() -> str:
    md = SRC.read_text(encoding="utf-8")
    body = markdown.markdown(md, extensions=["tables", "fenced_code", "sane_lists"])
    html = f"<!doctype html><html><head><meta charset='utf-8'><title>GigBid R&D report</title><style>{CSS}</style></head><body>{body}</body></html>"
    HTML.write_text(html, encoding="utf-8")
    return html


def chromium_pdf() -> bool:
    node = shutil.which("node")
    if not node or not (ROOT / "apps" / "web" / "node_modules" / "playwright").exists():
        return False
    r = subprocess.run([node, "scripts/html_to_pdf.mjs", str(HTML), str(OUT)], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print((r.stderr or "")[-800:])
    return r.returncode == 0


def fpdf_pdf() -> None:
    from fpdf import FPDF

    repl = {"—": "-", "–": "-", "’": "'", "‘": "'", "“": '"', "”": '"', "→": "->", "≤": "<=", "≥": ">=", "≈": "~",
            "×": "x", "…": "...", "•": "-", "‖": "||", "·": "|", "−": "-", "κ": "kappa", " ": " "}
    md = SRC.read_text(encoding="utf-8")
    for k, v in repl.items():
        md = md.replace(k, v)
    md = md.encode("latin-1", "replace").decode("latin-1")
    html = markdown.markdown(md, extensions=["tables", "fenced_code"])
    html = html.replace("<table>", '<table border="1" width="100%">')
    # fpdf2 tables accept plain text cells only
    html = re.sub(r"<(td|th)(\s[^>]*)?>(.*?)</\1>",
                  lambda m: f"<{m[1]}{m[2] or ''}>{re.sub(r'<[^>]+>', '', m[3])}</{m[1]}>", html, flags=re.S)
    html = re.sub(r"<code>(.*?)</code>", r"<font face='Courier'>\1</font>", html, flags=re.S)
    pdf = FPDF(format="A4")
    pdf.set_margins(16, 14, 16)
    pdf.set_auto_page_break(True, 14)
    pdf.add_page()
    pdf.set_font("Helvetica", size=9.5)
    pdf.write_html(html, table_line_separators=True, tag_styles=None)
    pdf.output(str(OUT))


def page_count() -> int | None:
    try:
        from pypdf import PdfReader

        return len(PdfReader(str(OUT)).pages)
    except Exception:  # noqa: BLE001
        try:
            import pymupdf

            return len(pymupdf.open(str(OUT)))
        except Exception:  # noqa: BLE001
            return None


def main() -> None:
    build_html()
    if not chromium_pdf():
        print("Chromium not available; falling back to fpdf2")
        fpdf_pdf()
    print(f"wrote {OUT} ({page_count()} pages)")


if __name__ == "__main__":
    main()
