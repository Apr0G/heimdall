from app.prompts import analysis_prompt, letter_prompt
from app.services.analysis import SUPPLEMENTAL_DOC_TYPES


def test_supplemental_doc_types():
    assert "prior_auth" in SUPPLEMENTAL_DOC_TYPES
    assert "prior_treatment" in SUPPLEMENTAL_DOC_TYPES


def test_analysis_prompt_includes_supplemental_only_when_present():
    without = analysis_prompt.build_user_prompt({"a": 1}, "notes")
    assert "SUPPLEMENTAL DOCUMENTS" not in without
    with_supp = analysis_prompt.build_user_prompt({"a": 1}, "notes", "AUTH-555 approved")
    assert "SUPPLEMENTAL DOCUMENTS" in with_supp
    assert "AUTH-555 approved" in with_supp


def test_letter_prompt_includes_supplemental_only_when_present():
    args = ({"p": 1}, {"c": 2}, {"a": 3}, "notes")
    assert "SUPPLEMENTAL DOCUMENTS" not in letter_prompt.build_user_prompt(*args)
    with_supp = letter_prompt.build_user_prompt(*args, "AUTH-555 approved")
    assert "SUPPLEMENTAL DOCUMENTS" in with_supp
    assert "AUTH-555 approved" in with_supp
