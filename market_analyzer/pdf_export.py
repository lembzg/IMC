"""
pdf_export.py
-------------
Combine the market_analyzer outputs for a single (round, day) into one PDF:
cross-product summary + each product's report.md + all plots.

Pure-Python: uses ReportLab only (no pandoc, no WeasyPrint/Cairo).

Usage:
    python -m market_analyzer.pdf_export --round round_0 --day 0
    python -m market_analyzer.pdf_export --round round_0 --day 0 \
        --outputs-dir outputs --out custom.pdf
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Iterable, List

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.lib.utils import ImageReader

from .plot_explanations import explain as explain_plot


PAGE_W, PAGE_H = LETTER
MARGIN = 0.6 * inch
CONTENT_W = PAGE_W - 2 * MARGIN


# --------------------------------------------------------------------------- #
# Styles
# --------------------------------------------------------------------------- #
def _styles():
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle(
            "title", parent=base["Title"], fontSize=22, spaceAfter=14
        ),
        "h1": ParagraphStyle(
            "h1", parent=base["Heading1"], fontSize=18, spaceBefore=14, spaceAfter=8
        ),
        "h2": ParagraphStyle(
            "h2", parent=base["Heading2"], fontSize=14, spaceBefore=10, spaceAfter=6
        ),
        "h3": ParagraphStyle(
            "h3", parent=base["Heading3"], fontSize=12, spaceBefore=8, spaceAfter=4
        ),
        "body": ParagraphStyle(
            "body", parent=base["BodyText"], fontSize=9.5, leading=13
        ),
        "bullet": ParagraphStyle(
            "bullet",
            parent=base["BodyText"],
            fontSize=9.5,
            leading=13,
            leftIndent=14,
            bulletIndent=2,
        ),
        "mono": ParagraphStyle(
            "mono",
            parent=base["BodyText"],
            fontName="Courier",
            fontSize=8.5,
            leading=11,
        ),
        "caption": ParagraphStyle(
            "caption",
            parent=base["BodyText"],
            fontSize=8,
            textColor=colors.grey,
            spaceAfter=6,
        ),
        "explain_title": ParagraphStyle(
            "explain_title",
            parent=base["BodyText"],
            fontSize=9.5,
            leading=12,
            spaceBefore=2,
            spaceAfter=1,
        ),
        "explain_body": ParagraphStyle(
            "explain_body",
            parent=base["BodyText"],
            fontSize=8.5,
            leading=11,
            leftIndent=10,
            spaceAfter=1,
        ),
    }
    return styles


# --------------------------------------------------------------------------- #
# Minimal markdown -> flowables
# --------------------------------------------------------------------------- #
_INLINE_BOLD = re.compile(r"\*\*(.+?)\*\*")
_INLINE_ITALIC = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")
_INLINE_UNDERSCORE_ITALIC = re.compile(r"(?<!_)_([^_]+)_(?!_)")
_INLINE_CODE = re.compile(r"`([^`]+)`")


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _inline(text: str) -> str:
    """Convert a subset of markdown inline syntax to ReportLab mini-HTML.

    Uses placeholder tokens so that substitutions inside code/bold/italic
    spans don't get re-processed (e.g. underscores inside backticks).
    """
    tokens: List[str] = []

    def _store(html: str) -> str:
        tokens.append(html)
        return f"\x00{len(tokens) - 1}\x00"

    def _sub_code(m):
        return _store(f"<font name='Courier'>{_esc(m.group(1))}</font>")

    def _sub_bold(m):
        return _store(f"<b>{_esc(m.group(1))}</b>")

    def _sub_italic(m):
        return _store(f"<i>{_esc(m.group(1))}</i>")

    text = _INLINE_CODE.sub(_sub_code, text)
    text = _INLINE_BOLD.sub(_sub_bold, text)
    text = _INLINE_ITALIC.sub(_sub_italic, text)
    text = _INLINE_UNDERSCORE_ITALIC.sub(_sub_italic, text)
    text = _esc(text)
    # Restore placeholders (they were inserted *before* escaping, so the
    # NUL markers survived; the escaped body contains no NULs).
    text = re.sub(r"\x00(\d+)\x00", lambda m: tokens[int(m.group(1))], text)
    return text


def _parse_table(lines: List[str], start: int):
    """Parse a markdown pipe table starting at `start`. Returns (rows, next_i)."""
    header = lines[start]
    sep = lines[start + 1] if start + 1 < len(lines) else ""
    if not re.match(r"^\s*\|?\s*[-: ]+\s*(\|\s*[-: ]+\s*)+\|?\s*$", sep):
        return None, start
    rows = [_split_row(header)]
    i = start + 2
    while i < len(lines) and "|" in lines[i] and lines[i].strip():
        rows.append(_split_row(lines[i]))
        i += 1
    return rows, i


def _split_row(line: str) -> List[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def _table_flowable(rows: List[List[str]], styles) -> Table:
    n_cols = max(len(r) for r in rows)
    norm = [r + [""] * (n_cols - len(r)) for r in rows]
    # Wrap each cell in a Paragraph for wrapping.
    data = [
        [Paragraph(_inline(c), styles["body"]) for c in row] for row in norm
    ]
    col_w = CONTENT_W / n_cols
    t = Table(data, colWidths=[col_w] * n_cols, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    return t


def markdown_to_flowables(md: str, styles) -> List:
    flow: List = []
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            flow.append(Spacer(1, 4))
            i += 1
            continue

        # Tables
        if "|" in stripped and i + 1 < len(lines) and re.match(
            r"^\s*\|?\s*[-: ]+\s*(\|\s*[-: ]+\s*)+\|?\s*$", lines[i + 1]
        ):
            rows, i = _parse_table(lines, i)
            if rows:
                flow.append(_table_flowable(rows, styles))
                flow.append(Spacer(1, 6))
                continue

        # Headings
        if stripped.startswith("### "):
            flow.append(Paragraph(_inline(stripped[4:]), styles["h3"]))
        elif stripped.startswith("## "):
            flow.append(Paragraph(_inline(stripped[3:]), styles["h2"]))
        elif stripped.startswith("# "):
            flow.append(Paragraph(_inline(stripped[2:]), styles["h1"]))
        elif stripped.startswith("- ") or stripped.startswith("* "):
            flow.append(
                Paragraph(
                    _inline(stripped[2:]),
                    styles["bullet"],
                    bulletText="•",
                )
            )
        else:
            flow.append(Paragraph(_inline(stripped), styles["body"]))
        i += 1
    return flow


# --------------------------------------------------------------------------- #
# Image handling
# --------------------------------------------------------------------------- #
def _image_flowable(path: Path, styles, max_h: float = 4.5 * inch,
                    caption_prefix: str = "", folder_hint: str = ""):
    """Load an image, scale it, and follow with a caption + explanation block."""
    label = f"{caption_prefix} / {path.name}" if caption_prefix else path.name
    try:
        ir = ImageReader(str(path))
        iw, ih = ir.getSize()
    except Exception as e:
        return [Paragraph(f"<i>[could not load image {label}: {e}]</i>",
                          styles["caption"])]
    if iw <= 0 or ih <= 0:
        return [Paragraph(f"<i>[empty image {label}]</i>", styles["caption"])]
    scale = min(CONTENT_W / iw, max_h / ih, 1.0)
    w, h = iw * scale, ih * scale
    img = Image(str(path), width=w, height=h)

    flow: List = [img, Paragraph(label, styles["caption"])]
    exp = explain_plot(path.name, folder_hint=folder_hint)
    if exp is not None:
        flow.append(Paragraph(f"<b>{_esc(exp.title)}</b>", styles["explain_title"]))
        flow.append(
            Paragraph(f"<b>Definition:</b> {_esc(exp.definition)}", styles["explain_body"])
        )
        flow.append(
            Paragraph(f"<b>Why it matters:</b> {_esc(exp.why)}", styles["explain_body"])
        )
        if exp.look_for:
            flow.append(
                Paragraph(f"<b>What to look for:</b> {_esc(exp.look_for)}",
                          styles["explain_body"])
            )
    return flow


def _collect_images(folder: Path) -> List[Path]:
    if not folder.exists():
        return []
    exts = {".png", ".jpg", ".jpeg"}
    return sorted(p for p in folder.iterdir() if p.suffix.lower() in exts)


# --------------------------------------------------------------------------- #
# Section builders
# --------------------------------------------------------------------------- #
def _cross_product_section(day_dir: Path, styles) -> List:
    cp_dir = day_dir / "cross_product"
    flow: List = [Paragraph("Cross-product summary", styles["h1"])]
    if not cp_dir.exists():
        flow.append(
            Paragraph("<i>No cross_product folder present.</i>", styles["body"])
        )
        return flow

    # Any CSV tables — render the first few rows as a preview.
    for csv_path in sorted(cp_dir.glob("*.csv")):
        flow.append(Paragraph(csv_path.stem, styles["h2"]))
        try:
            import pandas as pd  # local import; analyzer already depends on it

            df = pd.read_csv(csv_path, index_col=0)
            preview = df.head(20)
            rows = [[""] + [str(c) for c in preview.columns]]
            for idx, row in preview.iterrows():
                cells = []
                for v in row.values:
                    if isinstance(v, float):
                        cells.append(f"{v:.4f}")
                    else:
                        cells.append(str(v))
                rows.append([str(idx)] + cells)
            flow.append(_table_flowable(rows, styles))
            flow.append(Spacer(1, 6))
        except Exception as e:
            flow.append(
                Paragraph(f"<i>Could not render {csv_path.name}: {e}</i>",
                          styles["caption"])
            )

    for img in _collect_images(cp_dir):
        flow.extend(_image_flowable(img, styles,
                                    caption_prefix="cross_product",
                                    folder_hint="cross_product"))
        flow.append(Spacer(1, 6))
    return flow


def _product_section(prod_dir: Path, styles) -> List:
    flow: List = [PageBreak(), Paragraph(prod_dir.name, styles["h1"])]

    report_md = prod_dir / "report.md"
    if report_md.exists():
        flow.extend(markdown_to_flowables(report_md.read_text(), styles))
    else:
        flow.append(Paragraph("<i>No report.md found.</i>", styles["body"]))

    summary_json = prod_dir / "summary.json"
    if summary_json.exists():
        try:
            data = json.loads(summary_json.read_text())
            fp = data.get("fingerprint", {})
            if fp:
                flow.append(Paragraph("Summary JSON — fingerprint", styles["h3"]))
                for k, v in fp.items():
                    flow.append(
                        Paragraph(
                            f"<b>{k}</b>: {v}", styles["bullet"], bulletText="•"
                        )
                    )
        except Exception:
            pass

    images = _collect_images(prod_dir / "plots")
    if images:
        flow.append(PageBreak())
        flow.append(Paragraph(f"{prod_dir.name} — plots", styles["h2"]))
        for img in images:
            flow.extend(_image_flowable(img, styles,
                                        caption_prefix=prod_dir.name,
                                        folder_hint="product"))
            flow.append(Spacer(1, 8))
    return flow


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def build_pdf(day_dir: Path, out_path: Path) -> Path:
    if not day_dir.is_dir():
        raise FileNotFoundError(f"day_dir does not exist: {day_dir}")

    styles = _styles()
    flow: List = [
        Paragraph("Market Analyzer — Combined Report", styles["title"]),
        Paragraph(f"Source: <font name='Courier'>{day_dir}</font>",
                  styles["caption"]),
        Spacer(1, 12),
    ]

    flow.extend(_cross_product_section(day_dir, styles))

    product_dirs = sorted(
        p for p in day_dir.iterdir()
        if p.is_dir() and p.name not in {"cross_product"}
    )
    for prod in product_dirs:
        flow.extend(_product_section(prod, styles))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=LETTER,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
        title=f"Market Analyzer — {day_dir.name}",
    )
    doc.build(flow)
    return out_path


def _resolve_day_dir(outputs_dir: Path, round_label: str, day: str) -> Path:
    # Accept "0", "day_0", etc.
    round_dir = outputs_dir / round_label
    name = day if day.startswith("day_") else f"day_{day}"
    return round_dir / name


def main(argv: Iterable[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="market_analyzer.pdf_export",
        description="Combine a (round, day) analyzer output folder into a single PDF.",
    )
    p.add_argument("--outputs-dir", type=Path, default=Path("outputs"),
                   help="Root analyzer outputs directory (default: outputs)")
    p.add_argument("--round", dest="round_label", required=True,
                   help="Round label, e.g. round_0")
    p.add_argument("--day", required=True,
                   help="Day number or day_<n> (e.g. 0 or day_0)")
    p.add_argument("--out", type=Path, default=None,
                   help="Output PDF path (default: <day_dir>/combined_report.pdf)")
    args = p.parse_args(list(argv) if argv is not None else None)

    day_dir = _resolve_day_dir(args.outputs_dir, args.round_label, args.day)
    out_path = args.out or (day_dir / "combined_report.pdf")
    out = build_pdf(day_dir, out_path)
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
