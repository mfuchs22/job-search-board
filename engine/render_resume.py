"""Render a tailored resume from markdown to a compact one-page PDF.

Usage:
    py engine/render_resume.py <path/to/resume.md> [--out resume.pdf] [--pages 1]

The markdown file stays the single source of truth; this script only lays it
out. It builds the PDF directly with fpdf2 using the PDF base-14 fonts
(Times for body, Helvetica for section labels), which every reader ships
with and which are never embedded. A one-page resume comes out around
10 to 15 KB, small enough to attach through an email connector inline.
(The first version printed HTML through Chrome headless; that embedded the
full Georgia and Arial font programs and produced a 120 KB file.)

Markdown subset understood:
    # Title                   -> name
    first paragraph after it  -> contact line
    ## Heading                -> section label with rule
    ### Heading               -> employer line
    paragraph                 -> body text (italic when it follows an employer line)
    **Bold line**             -> role line (whole paragraph bold)
    - bullet                  -> bullet
    ---                       -> ignored
    inline **bold**           -> bold

Exit code 2 if the PDF has more pages than --pages (default 1), so a caller
can tell the resume needs a cut rather than shipping a two-page file that
was meant to be one.
"""

import argparse
import re
import sys
from pathlib import Path

from fpdf import FPDF

BODY = "Times"
LABEL = "Helvetica"
BODY_PT = 9.9
LEAD = 4.0  # mm per body line
MARGIN_SIDE = 12  # mm
MARGIN_TOP = 9  # mm


def blocks(md_text):
    """Yield (kind, text) blocks from the markdown subset."""
    lines = md_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line or line == "---":
            i += 1
            continue
        if line.startswith("### "):
            yield "h3", line[4:]
        elif line.startswith("## "):
            yield "h2", line[3:]
        elif line.startswith("# "):
            yield "h1", line[2:]
        elif line.startswith("- "):
            text = line[2:]
            while i + 1 < len(lines) and lines[i + 1].startswith("  ") and lines[i + 1].strip():
                i += 1
                text += " " + lines[i].strip()
            yield "li", text
        else:
            text = line
            while i + 1 < len(lines) and lines[i + 1].strip() and not re.match(r"^(#|- |---)", lines[i + 1]):
                i += 1
                text += " " + lines[i].strip()
            if re.fullmatch(r"\*\*[^*]+\*\*", text):
                yield "role", text[2:-2]
            else:
                yield "p", text
        i += 1


def latin(text):
    """Base-14 fonts are Latin-1; swap the few characters that are not."""
    return (
        text.replace("’", "'").replace("‘", "'")
        .replace("“", '"').replace("”", '"')
        .replace("–", "-").replace("—", "-")
        .replace("…", "...")
    )


class Resume(FPDF):
    def __init__(self):
        super().__init__(orientation="P", unit="mm", format="Letter")
        self.set_margins(MARGIN_SIDE, MARGIN_TOP, MARGIN_SIDE)
        self.set_auto_page_break(auto=True, margin=MARGIN_TOP)
        self.add_page()

    def width(self):
        return self.w - 2 * MARGIN_SIDE

    def h1(self, text):
        self.set_font(BODY, "B", 19)
        self.cell(0, 8, latin(text), new_x="LMARGIN", new_y="NEXT")

    def contact(self, text):
        self.set_font(LABEL, "", 8.6)
        self.set_text_color(60, 60, 60)
        self.cell(0, 4.5, latin(text), new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)
        self.ln(1.5)

    def h2(self, text):
        self.ln(2.2)
        self.set_font(LABEL, "B", 8.6)
        self.cell(0, 4.5, latin(text).upper(), new_x="LMARGIN", new_y="NEXT")
        y = self.get_y()
        self.set_draw_color(140, 140, 140)
        self.line(MARGIN_SIDE, y, self.w - MARGIN_SIDE, y)
        self.ln(1.6)

    def h3(self, text):
        self.ln(1.2)
        self.set_font(BODY, "B", 11)
        self.cell(0, 5, latin(text), new_x="LMARGIN", new_y="NEXT")

    def role(self, text):
        self.ln(0.8)
        self.set_font(BODY, "B", BODY_PT)
        self.cell(0, LEAD, latin(text), new_x="LMARGIN", new_y="NEXT")

    def p(self, text, italic=False):
        self.set_font(BODY, "I" if italic else "", BODY_PT)
        self.multi_cell(0, LEAD, latin(text), markdown=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(0.8)

    def li(self, text):
        self.set_font(BODY, "", BODY_PT)
        # Base-14 fonts have no bullet glyph; draw one.
        self.set_fill_color(0, 0, 0)
        self.ellipse(self.get_x() + 1.0, self.get_y() + LEAD / 2 - 0.65, 1.3, 1.3, style="F")
        self.set_x(self.get_x() + 4)
        self.multi_cell(self.width() - 4, LEAD, latin(text), markdown=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(0.6)


def render(md_text):
    pdf = Resume()
    prev = None
    for kind, text in blocks(md_text):
        if kind == "h1":
            pdf.h1(text)
        elif kind == "p" and prev == "h1":
            pdf.contact(text)
        elif kind == "h2":
            pdf.h2(text)
        elif kind == "h3":
            pdf.h3(text)
        elif kind == "role":
            pdf.role(text)
        elif kind == "p":
            pdf.p(text, italic=(prev == "h3"))
        elif kind == "li":
            pdf.li(text)
        prev = kind
    return pdf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", help="markdown resume")
    ap.add_argument("--out", help="pdf path (default: next to the source)")
    ap.add_argument("--pages", type=int, default=1, help="max pages allowed")
    args = ap.parse_args()

    src = Path(args.source).resolve()
    out = Path(args.out).resolve() if args.out else src.with_suffix(".pdf")
    md_text = src.read_text(encoding="utf-8")
    pdf = render(md_text)
    pdf.set_title(md_text.splitlines()[0].lstrip("# ").strip())
    pdf.output(str(out))

    pages = pdf.page_no()
    size = out.stat().st_size
    print(f"wrote {out} ({pages} page{'s' if pages != 1 else ''}, {size // 1024} KB)")
    if pages > args.pages:
        print(f"over the {args.pages}-page limit; cut before sending", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
