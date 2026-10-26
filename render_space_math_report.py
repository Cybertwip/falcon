from __future__ import annotations

import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape

from bs4 import BeautifulSoup, NavigableString, Tag
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


ASCII_REPLACEMENTS = {
    "\u00a0": " ",
    "\u03bc": "mu",
    "\u03bd": "nu",
    "\u03a9": "Omega",
    "\u03c9": "omega",
    "\u03d6": "varpi",
    "\u03c0": "pi",
    "\u0394": "Delta",
    "\u03c1": "rho",
    "\u2013": "-",
    "\u2014": "-",
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2022": "-",
    "\u2264": "<=",
    "\u2265": ">=",
    "\u2248": "approximately",
}


def clean_text(text: str) -> str:
    for old, new in ASCII_REPLACEMENTS.items():
        text = text.replace(old, new)
    text = text.replace("\r", "")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def inline_text(node: Tag | NavigableString) -> str:
    chunks: list[str] = []

    def walk(current: Tag | NavigableString) -> None:
        if isinstance(current, NavigableString):
            chunks.append(str(current))
            return

        if current.name == "br":
            chunks.append("\n")
            return

        if current.name in {"li", "p", "div", "section", "tr"} and chunks and not chunks[-1].endswith((" ", "\n")):
            chunks.append(" ")

        for child in current.children:
            walk(child)

        if current.name in {"p", "li", "div", "tr"}:
            chunks.append(" ")

    walk(node)
    text = "".join(chunks)
    text = clean_text(text)
    return text


def multiline_text(node: Tag | NavigableString) -> str:
    chunks: list[str] = []

    def walk(current: Tag | NavigableString) -> None:
        if isinstance(current, NavigableString):
            chunks.append(str(current))
            return

        if current.name == "br":
            chunks.append("\n")
            return

        if current.name in {"div", "p", "li", "tr", "td", "th"} and chunks and not chunks[-1].endswith("\n"):
            chunks.append("\n")

        for child in current.children:
            walk(child)

        if current.name in {"div", "p", "li", "tr"} and chunks and not chunks[-1].endswith("\n"):
            chunks.append("\n")

    walk(node)
    text = "".join(chunks)
    text = clean_text(text)
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def paragraph(text: str, style: ParagraphStyle) -> Paragraph:
    safe = escape(clean_text(text)).replace("\n", "<br/>")
    return Paragraph(safe, style)


def boxed_paragraph(text: str, style: ParagraphStyle, background: colors.Color, border: colors.Color, width: float) -> Table:
    box = Table([[paragraph(text, style)]], colWidths=[width])
    box.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), background),
                ("BOX", (0, 0), (-1, -1), 0.8, border),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return box


def table_flowable(node: Tag, styles: dict[str, ParagraphStyle], width: float) -> Table:
    rows: list[list[Paragraph]] = []
    all_rows = node.find_all("tr")
    max_cols = 0
    header_rows = 0

    for tr in all_rows:
        cells = tr.find_all(["th", "td"], recursive=False)
        if not cells:
            cells = tr.find_all(["th", "td"])
        if not cells:
            continue
        row: list[Paragraph] = []
        is_header = any(cell.name == "th" for cell in cells)
        style = styles["table_header"] if is_header else styles["table_cell"]
        for cell in cells:
          row.append(paragraph(inline_text(cell), style))
        max_cols = max(max_cols, len(row))
        if is_header:
            header_rows += 1
        rows.append(row)

    if not rows:
        return boxed_paragraph("", styles["body"], colors.white, colors.white, width)

    for row in rows:
        while len(row) < max_cols:
            row.append(paragraph("", styles["table_cell"]))

    col_width = width / max_cols
    flow = Table(rows, colWidths=[col_width] * max_cols, repeatRows=1 if header_rows else 0)
    flow.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#c8d4de")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d9e8ef")),
            ]
        )
    )
    return flow


def build_styles() -> dict[str, ParagraphStyle]:
    sheet = getSampleStyleSheet()
    return {
        "eyebrow": ParagraphStyle(
            "Eyebrow",
            parent=sheet["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=10,
            textColor=colors.HexColor("#4e6275"),
            alignment=TA_LEFT,
            spaceAfter=8,
        ),
        "title": ParagraphStyle(
            "TitleLarge",
            parent=sheet["Title"],
            fontName="Times-Bold",
            fontSize=24,
            leading=28,
            textColor=colors.HexColor("#123a52"),
            alignment=TA_LEFT,
            spaceAfter=10,
        ),
        "subtitle": ParagraphStyle(
            "Subtitle",
            parent=sheet["BodyText"],
            fontName="Times-Roman",
            fontSize=12.5,
            leading=16,
            textColor=colors.HexColor("#4e6275"),
            alignment=TA_LEFT,
            spaceAfter=10,
        ),
        "h2": ParagraphStyle(
            "SectionHeading",
            parent=sheet["Heading1"],
            fontName="Times-Bold",
            fontSize=16,
            leading=20,
            textColor=colors.HexColor("#123a52"),
            spaceBefore=10,
            spaceAfter=6,
        ),
        "h3": ParagraphStyle(
            "SubHeading",
            parent=sheet["Heading2"],
            fontName="Times-Bold",
            fontSize=12,
            leading=15,
            textColor=colors.HexColor("#1d3446"),
            spaceBefore=8,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=sheet["BodyText"],
            fontName="Times-Roman",
            fontSize=10.4,
            leading=13.6,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#15202b"),
            spaceAfter=5,
        ),
        "small": ParagraphStyle(
            "Small",
            parent=sheet["BodyText"],
            fontName="Times-Italic",
            fontSize=8.8,
            leading=11,
            textColor=colors.HexColor("#4e6275"),
            spaceAfter=5,
        ),
        "equation": ParagraphStyle(
            "Equation",
            parent=sheet["BodyText"],
            fontName="Courier",
            fontSize=8.9,
            leading=11.2,
            textColor=colors.HexColor("#15202b"),
            spaceAfter=0,
        ),
        "box": ParagraphStyle(
            "Box",
            parent=sheet["BodyText"],
            fontName="Times-Roman",
            fontSize=10,
            leading=13,
            textColor=colors.HexColor("#15202b"),
            spaceAfter=0,
        ),
        "table_header": ParagraphStyle(
            "TableHeader",
            parent=sheet["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=8.8,
            leading=10.5,
            textColor=colors.HexColor("#17364c"),
        ),
        "table_cell": ParagraphStyle(
            "TableCell",
            parent=sheet["BodyText"],
            fontName="Times-Roman",
            fontSize=8.7,
            leading=10.6,
            textColor=colors.HexColor("#15202b"),
        ),
        "bullet": ParagraphStyle(
            "Bullet",
            parent=sheet["BodyText"],
            fontName="Times-Roman",
            fontSize=10.2,
            leading=13.2,
            leftIndent=12,
            firstLineIndent=-9,
            spaceAfter=3,
        ),
        "signoff": ParagraphStyle(
            "Signoff",
            parent=sheet["BodyText"],
            fontName="Times-Italic",
            fontSize=11,
            leading=14,
            spaceBefore=8,
        ),
    }


def add_page_number(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#4e6275"))
    canvas.drawRightString(A4[0] - doc.rightMargin, 8 * mm, f"Page {canvas.getPageNumber()}")
    canvas.restoreState()


def process_children(parent: Tag, story: list, styles: dict[str, ParagraphStyle], width: float) -> None:
    for child in parent.children:
        if isinstance(child, NavigableString):
            continue

        classes = set(child.get("class", []))
        tag = child.name

        if tag == "h1":
            story.append(paragraph(inline_text(child), styles["title"]))
            continue
        if tag == "h2":
            story.append(paragraph(inline_text(child), styles["h2"]))
            continue
        if tag == "h3":
            story.append(paragraph(inline_text(child), styles["h3"]))
            continue
        if tag == "p":
            style = styles["small"] if "small" in classes or "source" in classes else styles["body"]
            story.append(paragraph(inline_text(child), style))
            continue
        if tag == "ul":
            for li in child.find_all("li", recursive=False):
                story.append(paragraph(f"- {inline_text(li)}", styles["bullet"]))
            story.append(Spacer(1, 3))
            continue
        if tag == "table":
            story.append(table_flowable(child, styles, width))
            story.append(Spacer(1, 7))
            continue
        if tag == "div" and "eq" in classes:
            story.append(boxed_paragraph(multiline_text(child), styles["equation"], colors.HexColor("#f7fafc"), colors.HexColor("#dfe7ec"), width))
            story.append(Spacer(1, 5))
            continue
        if tag == "div" and ("note" in classes or "warning" in classes or "card" in classes or "cover-note" in classes):
            bg = colors.HexColor("#fbf7ef") if "warning" in classes else colors.HexColor("#f8fbfd")
            border = colors.HexColor("#d8c8a6") if "warning" in classes else colors.HexColor("#c8d4de")
            story.append(boxed_paragraph(multiline_text(child), styles["box"], bg, border, width))
            story.append(Spacer(1, 6))
            continue
        if tag == "div" and ("eq-grid" in classes or "cover-grid" in classes):
            process_children(child, story, styles, width)
            continue
        if tag == "div" and child.get("class") == ["eyebrow"]:
            story.append(paragraph(inline_text(child), styles["eyebrow"]))
            continue
        if tag == "div" and child.get("class") == ["footer-signoff"]:
            story.append(paragraph(inline_text(child), styles["signoff"]))
            continue
        if tag == "section":
            if "section-break" in classes and story:
                story.append(PageBreak())
            process_children(child, story, styles, width)
            continue

        process_children(child, story, styles, width)


def render_report(html_path: Path, pdf_path: Path) -> None:
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
    main = soup.find("main")
    if main is None:
        raise RuntimeError("HTML report does not contain a <main> element")

    styles = build_styles()
    story: list = []

    top_sections = [child for child in main.children if isinstance(child, Tag)]
    for index, section in enumerate(top_sections):
        classes = set(section.get("class", []))
        if "cover" in classes:
            process_children(section, story, styles, A4[0] - 30 * mm)
            story.append(PageBreak())
            continue
        if "section-break" in classes and story:
            story.append(PageBreak())
        process_children(section, story, styles, A4[0] - 30 * mm)
        if index != len(top_sections) - 1:
            story.append(Spacer(1, 4))

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=16 * mm,
        bottomMargin=15 * mm,
        title="Space Plugin and Scripted Falcon Guidance",
        author="Lieutenant Lopez",
        subject="Mathematical reconstruction of the Space plugin and scripts",
    )
    doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)


def main(argv: list[str]) -> int:
    report_dir = Path(__file__).resolve().parent
    html_path = report_dir / "space_math_report_elon_musk.html"
    pdf_path = report_dir / "space_math_report_elon_musk.pdf"

    if len(argv) >= 2:
        html_path = Path(argv[1]).resolve()
    if len(argv) >= 3:
        pdf_path = Path(argv[2]).resolve()

    render_report(html_path, pdf_path)
    print(pdf_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))