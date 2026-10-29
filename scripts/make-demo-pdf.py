#!/usr/bin/env python3
"""Generate docs/demo/demo.pdf — a one-page dashboard this repo fully owns.

The documents this pipeline was developed against can't be published, so the
demo needs its own input. It is shaped to exercise the same code paths those
documents did — rounded-corner cards that must not classify as ellipses, a
donut and rounded bars that only a geometry donor can rebuild, recurring
elements worth componentizing, live text over shapes — while its subject,
palette and layout are invented. All figures are made up.

Usage: .venv/bin/python scripts/make-demo-pdf.py [-o docs/demo/demo.pdf]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen.canvas import Canvas

INK = HexColor("#1f2933")
MUTED = HexColor("#64748b")
CARD = HexColor("#f1f5f9")
RULE = HexColor("#e2e8f0")
SERIES = [HexColor("#0f766e"), HexColor("#d97706"), HexColor("#7c3aed"), HexColor("#e11d48")]

PAGE_W, PAGE_H = letter
MARGIN = 36


def top(y: float) -> float:
    """Lay out top-down like the IR does; reportlab draws bottom-up."""
    return PAGE_H - y


def header(c: Canvas) -> None:
    c.setFillColor(SERIES[0])
    c.rect(0, top(72), PAGE_W, 72, stroke=0, fill=1)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(MARGIN, top(40), "Example Co. — Product Metrics")
    c.setFont("Helvetica", 10)
    c.drawString(MARGIN, top(58), "Quarterly overview · sample data")


def kpi_cards(c: Canvas) -> None:
    kpis = [
        ("Active users", "48,210", "+6.2% vs last quarter"),
        ("Conversion", "3.4%", "+0.3 pt"),
        ("Avg. order", "$62.10", "\N{MINUS SIGN}1.1%"),
        ("Churn", "1.8%", "\N{MINUS SIGN}0.4 pt"),
    ]
    gap = 12
    w = (PAGE_W - 2 * MARGIN - 3 * gap) / 4
    for i, (label, value, delta) in enumerate(kpis):
        x = MARGIN + i * (w + gap)
        c.setFillColor(CARD)
        c.roundRect(x, top(176), w, 84, 10, stroke=0, fill=1)
        c.setFillColor(SERIES[i])
        c.roundRect(x + 12, top(112), 24, 4, 2, stroke=0, fill=1)
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 9)
        c.drawString(x + 12, top(128), label)
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 18)
        c.drawString(x + 12, top(150), value)
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 8)
        c.drawString(x + 12, top(166), delta)


def section_title(c: Canvas, x: float, y: float, text: str) -> None:
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x, top(y), text)


def donut(c: Canvas) -> None:
    x, y, w, h = MARGIN, 196, 258, 220
    c.setFillColor(CARD)
    c.roundRect(x, top(y + h), w, h, 10, stroke=0, fill=1)
    section_title(c, x + 14, y + 24, "Traffic by channel")

    shares = [("Organic", 42), ("Paid", 23), ("Referral", 18), ("Email", 17)]
    cx, cy, r = x + 80, top(y + 128), 58
    start = 90.0
    for i, (_, share) in enumerate(shares):
        extent = -360 * share / 100
        c.setFillColor(SERIES[i])
        c.wedge(cx - r, cy - r, cx + r, cy + r, start, extent, stroke=0, fill=1)
        start += extent
    c.setFillColor(CARD)
    c.circle(cx, cy, r * 0.6, stroke=0, fill=1)
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(cx, cy - 5, "100%")

    for i, (name, share) in enumerate(shares):
        ly = y + 82 + i * 22
        c.setFillColor(SERIES[i])
        c.roundRect(x + 160, top(ly + 10), 10, 10, 2, stroke=0, fill=1)
        c.setFillColor(INK)
        c.setFont("Helvetica", 9)
        c.drawString(x + 176, top(ly + 8), f"{name}  {share}%")


def bars(c: Canvas) -> None:
    x, y, w, h = MARGIN + 270, 196, PAGE_W - 2 * MARGIN - 270, 220
    c.setFillColor(CARD)
    c.roundRect(x, top(y + h), w, h, 10, stroke=0, fill=1)
    section_title(c, x + 14, y + 24, "Monthly revenue, $k")

    months = [("Jan", 84), ("Feb", 91), ("Mar", 88), ("Apr", 102), ("May", 117), ("Jun", 124)]
    base = y + h - 28
    slot = (w - 28) / len(months)
    for i, (month, value) in enumerate(months):
        bx = x + 14 + i * slot + slot * 0.2
        bh = value * 1.15
        c.setFillColor(SERIES[0] if i < len(months) - 1 else SERIES[1])
        c.roundRect(bx, top(base), slot * 0.6, bh, 4, stroke=0, fill=1)
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 8)
        c.drawCentredString(bx + slot * 0.3, top(base + 12), month)
        c.drawCentredString(bx + slot * 0.3, top(base - bh - 4), str(value))


def table(c: Canvas) -> None:
    x, y, w = MARGIN, 432, PAGE_W - 2 * MARGIN
    section_title(c, x, y + 14, "Top products")
    cols = [("Product", 0), ("Units", 230), ("Revenue", 320), ("Goal", 420)]
    rows = [
        ("Starter plan", "1,240", "$37.2k", 0.82),
        ("Team plan", "610", "$54.9k", 0.64),
        ("Add-on: storage", "980", "$9.8k", 0.91),
        ("Add-on: analytics", "415", "$12.4k", 0.47),
        ("Enterprise", "38", "$71.3k", 0.73),
    ]
    head_y = y + 34
    c.setFillColor(MUTED)
    c.setFont("Helvetica-Bold", 8)
    for name, dx in cols:
        c.drawString(x + dx, top(head_y), name.upper())
    for i, (product, units, revenue, goal) in enumerate(rows):
        ry = head_y + 24 + i * 26
        c.setStrokeColor(RULE)
        c.setLineWidth(0.75)
        c.line(x, top(ry - 15), x + w, top(ry - 15))
        c.setFillColor(INK)
        c.setFont("Helvetica", 10)
        c.drawString(x, top(ry), product)
        c.drawString(x + 230, top(ry), units)
        c.drawString(x + 320, top(ry), revenue)
        track_w = w - 420 - 40
        c.setFillColor(RULE)
        c.roundRect(x + 420, top(ry - 1), track_w, 6, 3, stroke=0, fill=1)
        c.setFillColor(SERIES[2])
        c.roundRect(x + 420, top(ry - 1), track_w * goal, 6, 3, stroke=0, fill=1)
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 8)
        c.drawRightString(x + w, top(ry), f"{round(goal * 100)}%")


def footer(c: Canvas) -> None:
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 8)
    note = "Generated by scripts/make-demo-pdf.py · all figures invented"
    c.drawString(MARGIN, top(PAGE_H - 24), note)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-o", "--output", type=Path, default=Path("docs/demo/demo.pdf"))
    args = ap.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    # invariant=1 pins the creation date and document id, so re-running the
    # script produces a byte-identical file.
    c = Canvas(str(args.output), pagesize=letter, invariant=1)
    c.setTitle("pdf-to-figma demo")
    c.setAuthor("pdf-to-figma")
    header(c)
    kpi_cards(c)
    donut(c)
    bars(c)
    table(c)
    footer(c)
    c.showPage()
    c.save()
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
