import pytest

from app.api.cases import case_status_after_outcome
from app.services import pdf_gen


def test_render_letter_pdf_is_valid_pdf():
    pdf = pdf_gen.render_letter_pdf("Dear Payer,\n\nWe appeal this denial.\n\nSincerely,")
    assert pdf.startswith(b"%PDF-1.4")
    assert pdf.rstrip().endswith(b"%%EOF")
    assert b"/Type /Catalog" in pdf
    assert b"xref" in pdf


def test_render_letter_pdf_paginates_long_body():
    # Far more lines than fit on one page -> multiple Page objects.
    body = "\n".join(f"Line number {i} of a very long appeal letter." for i in range(200))
    pdf = pdf_gen.render_letter_pdf(body)
    assert pdf.count(b"/Type /Page ") >= 2
    # Count in the Pages node matches the number of Page objects emitted.
    assert b"/Count " in pdf


def test_render_letter_pdf_handles_empty_body():
    pdf = pdf_gen.render_letter_pdf("")
    assert pdf.startswith(b"%PDF")
    assert b"/Count 1" in pdf


def test_wrap_lines_respects_width():
    long_word_line = "word " * 60  # ~300 chars, must wrap
    wrapped = pdf_gen._wrap_lines(long_word_line.strip())
    assert len(wrapped) > 1
    assert all(len(line) <= pdf_gen._WRAP for line in wrapped)


def test_case_status_after_outcome():
    assert case_status_after_outcome("overturned") == "resolved"
    assert case_status_after_outcome("upheld") == "resolved"
    assert case_status_after_outcome("partial") == "resolved"
    assert case_status_after_outcome("withdrawn") == "resolved"
    assert case_status_after_outcome("pending") == "submitted"


def test_outcome_amount_rejects_dollar_valued_float():
    # 450.0 must not be silently truncated into 450 cents (LOW-10).
    from pydantic import ValidationError

    from app.schemas.case import OutcomeRequest

    with pytest.raises(ValidationError):
        OutcomeRequest.model_validate({"result": "overturned", "amount_recovered_cents": 450.0})
    assert (
        OutcomeRequest.model_validate(
            {"result": "overturned", "amount_recovered_cents": 45000}
        ).amount_recovered_cents
        == 45000
    )
