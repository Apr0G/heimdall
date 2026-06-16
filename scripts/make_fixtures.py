"""Generate synthetic PDF fixtures for testing document upload.

Dependency-free, minimal-but-valid single-page PDFs with a little text.
Synthetic data only (Jane Doe, CLM-TEST-...). Run from the repo root:

    python scripts/make_fixtures.py   ->  fixtures/{denial,claim,clinical}.pdf
"""

from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def _pdf(lines: list[str]) -> bytes:
    def esc(text: str) -> str:
        return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")

    body = "BT /F1 12 Tf 72 740 Td 16 TL\n"
    body += "".join(f"({esc(line)}) Tj T*\n" for line in lines)
    body += "ET"
    content = body.encode("latin-1")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length "
        + str(len(content)).encode()
        + b" >>\nstream\n"
        + content
        + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

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


DOCS = {
    "denial": [
        "EXPLANATION OF BENEFITS (SYNTHETIC TEST DATA)",
        "Payer: Aetna    Claim #: CLM-TEST-0001",
        "Patient: Jane Doe    DOS: 2026-05-04",
        "Denial: CARC CO-50 - not deemed a medical necessity.",
        "Denied amount: $450.00",
    ],
    "claim": [
        "CMS-1500 PROFESSIONAL CLAIM (SYNTHETIC TEST DATA)",
        "Billing provider NPI: 0000000000",
        "Box 21 ICD-10: M54.50    Box 24 CPT: 73721",
        "Patient: Jane Doe    Claim #: CLM-TEST-0001",
    ],
    "clinical": [
        "CLINICAL NOTE (SYNTHETIC TEST DATA)",
        "Patient: Jane Doe",
        "MRI of the knee ordered for persistent pain after six weeks of",
        "conservative therapy; medically necessary per exam findings.",
    ],
}


def main() -> None:
    FIXTURES_DIR.mkdir(exist_ok=True)
    for name, lines in DOCS.items():
        path = FIXTURES_DIR / f"{name}.pdf"
        path.write_bytes(_pdf(lines))
        print(f"wrote {path} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
