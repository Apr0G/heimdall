import pytest

from app.prompts import (
    analysis_prompt,
    extraction_prompt,
    letter_prompt,
    precheck_extraction_prompt,
    precheck_review_prompt,
)
from app.services.document_extractor import NotAPdfError, _assert_pdf


def test_assert_pdf_accepts_pdf():
    _assert_pdf(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj")  # no raise


def test_assert_pdf_allows_small_leading_bytes():
    _assert_pdf(b"\xef\xbb\xbf  %PDF-1.7 rest")  # BOM + whitespace still fine


def test_assert_pdf_rejects_non_pdf():
    with pytest.raises(NotAPdfError):
        _assert_pdf(b"<html>totally not a pdf</html>")
    with pytest.raises(NotAPdfError):
        _assert_pdf(b"GIF89a...")


def test_prompts_carry_injection_guard():
    # Uploaded document text is untrusted; each prompt must say so.
    prompts = (
        extraction_prompt.SYSTEM,
        analysis_prompt.SYSTEM,
        letter_prompt.SYSTEM,
        precheck_extraction_prompt.SYSTEM,
        precheck_review_prompt.SYSTEM,
    )
    for system in prompts:
        assert "UNTRUSTED" in system


def test_malformed_pdf_raises_phi_free_domain_error():
    # A PDF whose content stream is garbage: pypdf's own error would quote bytes
    # of the stream; ours must carry only the parser's exception type name.
    from app.services.document_extractor import DocumentParseError, digital_text_from_bytes

    bad = (
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/Contents 4 0 R>>endobj\n"
        b"4 0 obj<</Length 30>>stream\nBT (Jane Doe) Tj ) ) garbage\nendstream\nendobj\n"
        b"trailer<</Root 1 0 R>>"
    )
    with pytest.raises(DocumentParseError) as info:
        digital_text_from_bytes(bad)
    assert "Jane" not in str(info.value)
