"""Minimal PDFs assembled byte by byte, with coordinates we chose.

No binary fixtures in the repository: a committed PDF is opaque, cannot be
diffed, and nobody can tell what it is supposed to contain. Building the file
here means the expected geometry is written next to the assertion that checks it.

PDF space is bottom-up, so a rectangle drawn at y=600 in a 792pt page has its top
edge at 792 - 650 = 142 once converted. That conversion is exactly what the
extractor is being tested on.
"""

from __future__ import annotations

PAGE_WIDTH = 612.0
PAGE_HEIGHT = 792.0


def build_pdf(
    content: str,
    *,
    width: float = PAGE_WIDTH,
    height: float = PAGE_HEIGHT,
    pages: int = 1,
    font_name: str = "Helvetica",
) -> bytes:
    """Assemble a valid single-font PDF whose pages all share one content stream.

    `font_name` is the raw `/BaseFont` value — e.g. `"Helvetica-Bold"` to
    exercise the PostScript-style-suffix regression, unstripped and
    unvalidated, exactly as a real embedded font name would arrive.
    """
    stream = content.encode("ascii")

    objects: list[bytes] = []
    kid_ids = [4 + i for i in range(pages)]

    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{i} 0 R" for i in kid_ids).encode("ascii")
    objects.append(b"<< /Type /Pages /Kids [" + kids + b"] /Count %d >>" % pages)
    objects.append(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /" + font_name.encode("ascii") + b" >>"
    )

    content_id = 4 + pages
    for _ in range(pages):
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %s %s] "
            b"/Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>"
            % (_num(width), _num(height), content_id)
        )

    objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []

    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"

    xref_at = len(out)
    out += b"xref\n0 %d\n" % (len(objects) + 1)
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset

    out += b"trailer\n<< /Size %d /Root 1 0 R >>\n" % (len(objects) + 1)
    out += b"startxref\n%d\n%%%%EOF\n" % xref_at

    return bytes(out)


def _num(value: float) -> bytes:
    return f"{value:g}".encode("ascii")


# A filled red rectangle: bottom-left (100, 600), 200 wide, 50 tall.
# Converted to top-left origin that is x=100, y=792-650=142, w=200, h=50.
RECT = "1 0 0 rg 100 600 200 50 re f"
RECT_EXPECTED = {"x": 100.0, "y": 142.0, "w": 200.0, "h": 50.0, "hex": "#ff0000"}

# A stroked horizontal line from (50, 500) to (250, 500).
LINE = "0 0 1 RG 2 w 50 500 m 250 500 l S"

# Text in a known place. The baseline sits at y=700; the box around it is
# derived from font metrics, so tests assert a range rather than a point.
TEXT = "BT /F1 12 Tf 0 0.5 0 rg 72 700 Td (Hello) Tj ET"
TEXT_EXPECTED = {"text": "Hello", "size": 12.0, "family": "Helvetica", "hex": "#008000"}

# Two words far enough apart that they must not merge into one run.
TWO_RUNS = "BT /F1 10 Tf 72 400 Td (Left) Tj 300 0 Td (Right) Tj ET"
