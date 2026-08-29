"""Selection resolution for the corrected-claim flow — the boundary where a
browser's choices meet the stored report. Pure function; codes are synthetic."""

from types import SimpleNamespace

import pytest

from app.services.corrected_claim import (
    InvalidSelection,
    Selection,
    claim_document_editable,
    resolve_selections,
)

EDITS = [
    {"kind": "add_modifier", "target": "20610", "value": "59", "source": "ncci"},
    {"kind": "remove_line", "target": "10002", "value": None, "source": "ncci"},
    {"kind": "change_units", "target": "20553", "value": "3", "source": "ncci"},
    {"kind": "documentation", "target": None, "value": None, "source": "model"},
    {"kind": "change_code", "target": "99214", "value": None, "source": "model"},
]


def test_kind_and_target_come_from_the_report_not_the_client():
    resolved = resolve_selections(EDITS, [Selection(0), Selection(1), Selection(2)])
    assert [(i, e.kind, e.target, e.value) for i, e in resolved] == [
        (0, "add_modifier", "20610", "59"),
        (1, "remove_line", "10002", None),
        (2, "change_units", "20553", "3"),
    ]


def test_client_value_overrides_the_default_and_is_normalised():
    ((_, edit),) = resolve_selections(EDITS, [Selection(0, " xs ")])
    assert edit.value == "XS"


@pytest.mark.parametrize(
    ("selections", "code"),
    [
        ([Selection(0), Selection(0)], "duplicate_index"),
        ([Selection(5)], "index_out_of_range"),
        ([Selection(-1)], "index_out_of_range"),
        ([Selection(3)], "kind_not_applicable"),  # documentation edits aren't claim edits
        ([Selection(4)], "value_required"),  # model edit without a value, none supplied
        ([Selection(4, "abc")], "bad_value"),
        ([Selection(2, "0")], "bad_value"),
        ([Selection(0, "5")], "bad_value"),
    ],
)
def test_rejections(selections, code):
    with pytest.raises(InvalidSelection) as exc:
        resolve_selections(EDITS, selections)
    assert exc.value.code == code


def test_remove_instead_turns_any_claim_edit_into_a_line_removal():
    ((_, edit),) = resolve_selections(EDITS, [Selection(0, "XS", remove=True)])
    assert (edit.kind, edit.target, edit.value) == ("remove_line", "20610", None)
    # ...but not a documentation edit, which has no line to remove.
    with pytest.raises(InvalidSelection):
        resolve_selections(EDITS, [Selection(3, remove=True)])


def test_removal_ignores_any_client_value():
    ((_, edit),) = resolve_selections(EDITS, [Selection(1, "junk")])
    assert edit.value is None


def test_claim_document_editable_requires_a_text_layer_on_the_claim():
    doc = SimpleNamespace
    assert claim_document_editable([doc(doc_type="claim", ocr_status="not_needed")])
    assert not claim_document_editable([doc(doc_type="claim", ocr_status="completed")])
    assert not claim_document_editable([doc(doc_type="clinical", ocr_status="not_needed")])
    assert not claim_document_editable([])


def test_an_ncci_unit_limit_stays_a_ceiling_whatever_the_client_sends():
    edits = [
        {"kind": "change_units", "target": "97110", "value": "4", "cap": "day", "source": "ncci"},
        {"kind": "change_units", "target": "97140", "value": "2", "cap": "line", "source": "ncci"},
        {"kind": "change_units", "target": "20553", "value": "3", "cap": "bogus", "source": "ncci"},
        {"kind": "change_units", "target": "99214", "value": "1", "source": "model"},
    ]
    resolved = resolve_selections(
        edits, [Selection(0, "3"), Selection(1), Selection(2), Selection(3)]
    )
    # The report decides the kind of limit; a doctor's own number for that
    # finding is still applied as a limit, never as a count to raise lines to.
    assert [(e.value, e.cap) for _, e in resolved] == [
        ("3", "day"),
        ("2", "line"),
        ("3", None),
        ("1", None),
    ]
    # "Remove the line instead" has nothing to cap.
    ((_, edit),) = resolve_selections(edits, [Selection(0, remove=True)])
    assert (edit.kind, edit.cap) == ("remove_line", None)
