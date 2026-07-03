import pytest

from app.prompts import analysis_prompt, extraction_prompt, letter_prompt
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
    for system in (extraction_prompt.SYSTEM, analysis_prompt.SYSTEM, letter_prompt.SYSTEM):
        assert "UNTRUSTED" in system
