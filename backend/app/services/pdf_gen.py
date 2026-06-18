"""Render an appeal letter to a simple, multi-page PDF.

Dependency-free on purpose: the letter is plain text with no formatting needs
for the MVP, so we emit a minimal-but-valid PDF by hand (same approach as
scripts/make_fixtures.py) rather than pull in reportlab/weasyprint. If richer
formatting is ever needed, swap this for a real PDF library.
"""

# Letter (US) page geometry, in PDF points (1/72 inch).
_PAGE_W = 612
_PAGE_H = 792
_MARGIN = 72
_FONT_SIZE = 11
_LEADING = 15
_TOP = _PAGE_H - _MARGIN
# Conservative character budget per line for 11pt Helvetica within the margins.
_WRAP = 92
_LINES_PER_PAGE = (_TOP - _MARGIN) // _LEADING


def _wrap_lines(body: str) -> list[str]:
    """Split on explicit newlines, then word-wrap each paragraph to the page
    width. Blank lines are preserved so the letter keeps its spacing."""
    out: list[str] = []
    for raw in body.replace("\r\n", "\n").split("\n"):
        if not raw.strip():
            out.append("")
            continue
        line = ""
        for word in raw.split(" "):
            candidate = f"{line} {word}".strip()
            if len(candidate) > _WRAP and line:
                out.append(line)
                line = word
            else:
                line = candidate
        out.append(line)
    return out


def _paginate(lines: list[str]) -> list[list[str]]:
    pages = [lines[i : i + _LINES_PER_PAGE] for i in range(0, len(lines), _LINES_PER_PAGE)]
    return pages or [[]]


def _escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _content_stream(lines: list[str]) -> bytes:
    body = f"BT /F1 {_FONT_SIZE} Tf {_MARGIN} {_TOP} Td {_LEADING} TL\n"
    body += "".join(f"({_escape(line)}) Tj T*\n" for line in lines)
    body += "ET"
    # latin-1 keeps the byte offsets in the xref table exact (one byte per char).
    return body.encode("latin-1", errors="replace")


def render_letter_pdf(body: str) -> bytes:
    """Return PDF bytes for the given letter text, paginated across as many
    Letter-size pages as needed."""
    pages = _paginate(_wrap_lines(body))

    # Object numbering: 1=Catalog, 2=Pages, 3=Font, then (Page, Contents) pairs.
    page_obj_nums = [4 + 2 * i for i in range(len(pages))]
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids ["
        + b" ".join(f"{n} 0 R".encode() for n in page_obj_nums)
        + b"] /Count "
        + str(len(pages)).encode()
        + b" >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for i, page_lines in enumerate(pages):
        content = _content_stream(page_lines)
        content_obj_num = page_obj_nums[i] + 1
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 "
            + f"{_PAGE_W} {_PAGE_H}".encode()
            + b"] /Resources << /Font << /F1 3 0 R >> >> /Contents "
            + f"{content_obj_num} 0 R".encode()
            + b" >>"
        )
        objects.append(
            b"<< /Length "
            + str(len(content)).encode()
            + b" >>\nstream\n"
            + content
            + b"\nendstream"
        )

    pdf = b"%PDF-1.4\n"
    offsets: list[int] = []
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += str(index).encode() + b" 0 obj\n" + obj + b"\nendobj\n"

    xref_at = len(pdf)
    pdf += b"xref\n0 " + str(len(objects) + 1).encode() + b"\n"
    pdf += b"0000000000 65535 f \n"
    for offset in offsets:
        pdf += f"{offset:010d} 00000 n \n".encode()
    pdf += b"trailer\n<< /Size " + str(len(objects) + 1).encode() + b" /Root 1 0 R >>\n"
    pdf += b"startxref\n" + str(xref_at).encode() + b"\n%%EOF"
    return pdf
