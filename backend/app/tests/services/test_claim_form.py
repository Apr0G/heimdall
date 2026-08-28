"""Fillable (AcroForm) claims: reading fields, the text the model sees, and
in-place edits through the form backend. The fixture is a synthetic fillable
CMS-1500 built here — per-row fields on the real form's geometry, the way
vendor templates lay them out (four modifier boxes, split charge boxes,
right-aligned dollars). All data synthetic (hard rule 1)."""

import io

import pypdfium2 as pdfium
import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    BooleanObject,
    DictionaryObject,
    FloatObject,
    NameObject,
    NumberObject,
    TextStringObject,
)

from app.services import claim_form
from app.services.claim_form import FormReadError, form_text, read_form
from app.services.claim_patch import ClaimEdit, ClaimPatchError, patch_claim
from app.services.document_extractor import digital_text_from_bytes

PAGE_H = 792
ROW_Y = [500, 476, 452, 428, 404, 380]  # Box 24 rows 1-6 (bottom y of the data cell)
ROW_H = 12

# (field name, x0, x1) for one service row — modelled on a vendor template.
ROW_FIELDS = [
    ("MM{n}", 24, 42),
    ("DD{n}", 43, 63),
    ("YY{n}", 64, 84),
    ("B{n}", 150, 172),
    ("CPT/HCPCS {n}", 196, 246),
    ("Mod {n}a", 248, 272),
    ("Mod {n}b", 273, 293),
    ("Mod {n}c", 294, 314),
    ("Mod {n}d", 317, 337),
    ("E{n}", 338, 373),
    ("F{n}", 375, 419),  # dollars, right-aligned
    ("F{n}a", 421, 437),  # cents
    ("G{n}", 439, 466),  # units
    ("J{n}b", 503, 592),  # NPI
]


def _text_field(name: str, rect: list[float], value: str, *, align: int = 0, max_len=None):
    d = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Annot"),
            NameObject("/Subtype"): NameObject("/Widget"),
            NameObject("/FT"): NameObject("/Tx"),
            NameObject("/T"): TextStringObject(name),
            NameObject("/Rect"): ArrayObject([FloatObject(v) for v in rect]),
            NameObject("/F"): NumberObject(4),
            NameObject("/DA"): TextStringObject("/Helv 0 Tf 0 g"),
            NameObject("/Q"): NumberObject(align),
        }
    )
    if value:
        d[NameObject("/V")] = TextStringObject(value)
    if max_len is not None:
        d[NameObject("/MaxLen")] = NumberObject(max_len)
    return d


def _checkbox(name: str, rect: list[float], on: bool):
    d = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Annot"),
            NameObject("/Subtype"): NameObject("/Widget"),
            NameObject("/FT"): NameObject("/Btn"),
            NameObject("/T"): TextStringObject(name),
            NameObject("/Rect"): ArrayObject([FloatObject(v) for v in rect]),
            NameObject("/F"): NumberObject(4),
            NameObject("/AS"): NameObject("/Yes" if on else "/Off"),
            NameObject("/V"): NameObject("/Yes" if on else "/Off"),
        }
    )
    return d


def build_form_claim(
    lines: list[dict],
    *,
    dx: tuple[str, ...] = ("N185", "N200"),
    total_cents: int | None = None,
    combined_modifiers: bool = False,  # one "Mod n" field holding "KX 59"
    single_charge: bool = False,  # one "F n" field holding "22.00"
    epsdt_checkbox: bool = True,
    javascript: bool = False,
    xfa: bool = False,
    hidden_field: bool = False,
    extra_fields: dict[str, str] | None = None,
) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=PAGE_H)
    widgets = []

    def add(name, x0, x1, y, value, **kw):
        widgets.append(_text_field(name, [x0, y, x1, y + ROW_H], value, **kw))

    add("Patient's Name", 24, 200, 700, "DOE, JANE")
    add("Insured's ID #", 400, 590, 700, "TP000000000")
    for i, code in enumerate(dx):
        slot = "abcdefghijkl"[i]
        add(f"21{slot}", 38 + (i % 4) * 93, 88 + (i % 4) * 93, 560 - (i // 4) * 12, code)
    if hidden_field:
        w = _text_field("Hidden", [24, 650, 100, 662], "SECRET")
        w[NameObject("/F")] = NumberObject(2)
        widgets.append(w)
    total = total_cents if total_cents is not None else sum(ln["cents"] for ln in lines)
    add("Total Charge Dollars", 385, 435, 100, str(total // 100), align=2)
    add("Total Charge Cents", 436, 454, 100, f"{total % 100:02d}")

    for n, line in enumerate(lines, start=1):
        y = ROW_Y[n - 1]
        values = {
            "MM{n}": "06",
            "DD{n}": f"{19 + n:02d}",
            "YY{n}": "26",
            "B{n}": "11",
            "CPT/HCPCS {n}": line["cpt"],
            "E{n}": line.get("ptr", "A"),
            "G{n}": "" if line.get("units", 1) is None else str(line.get("units", 1)),
            "J{n}b": "0000000000",
        }
        mods = line.get("mods", [])
        if combined_modifiers:
            values["Mod {n}"] = " ".join(mods)
        else:
            for slot, mod in zip("abcd", mods + [""] * 4, strict=False):
                values[f"Mod {{n}}{slot}"] = mod
        if single_charge:
            values["F{n}"] = f"{line['cents'] // 100}.{line['cents'] % 100:02d}"
        else:
            values["F{n}"] = str(line["cents"] // 100)
            values["F{n}a"] = f"{line['cents'] % 100:02d}"
        for template, x0, x1 in ROW_FIELDS:
            if combined_modifiers and template.startswith("Mod"):
                continue
            if single_charge and template == "F{n}a":
                continue
            name = template.format(n=n)
            align = 2 if template == "F{n}" else 0
            add(name, x0, x1, y, values.get(template, ""), align=align)
        if combined_modifiers:
            add(f"Mod {n}", 248, 337, y, values["Mod {n}"])
        if epsdt_checkbox:
            widgets.append(_checkbox(f"H{n}", [470, y, 480, y + 10], line.get("epsdt", False)))
    for name, value in (extra_fields or {}).items():
        add(name, 24, 300, 640, value)

    page[NameObject("/Annots")] = ArrayObject([writer._add_object(w) for w in widgets])
    for ref in page["/Annots"]:
        ref.get_object()[NameObject("/P")] = page.indirect_reference
    acroform = DictionaryObject(
        {
            NameObject("/Fields"): ArrayObject(list(page["/Annots"])),
            NameObject("/DA"): TextStringObject("/Helv 0 Tf 0 g"),
            NameObject("/NeedAppearances"): BooleanObject(True),
        }
    )
    if xfa:
        acroform[NameObject("/XFA")] = ArrayObject()
    writer._root_object[NameObject("/AcroForm")] = writer._add_object(acroform)
    if javascript:
        writer._root_object[NameObject("/OpenAction")] = DictionaryObject(
            {
                NameObject("/S"): NameObject("/JavaScript"),
                NameObject("/JS"): TextStringObject("app.alert(1)"),
            }
        )
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


LINES = [
    {"cpt": "J2501", "mods": ["KX"], "cents": 2200, "units": 5},
    {"cpt": "J2501", "mods": ["KX"], "cents": 2200, "units": 5},
    {"cpt": "99213", "mods": ["25"], "cents": 12000, "units": 1, "ptr": "AB", "epsdt": True},
]


def values(pdf: bytes) -> dict[str, str]:
    return read_form(pdf).values


# --- reading ------------------------------------------------------------------------


def test_reads_visible_fields_with_values_and_skips_hidden_ones():
    pdf = build_form_claim(LINES, hidden_field=True)
    doc = read_form(pdf)
    names = {f.name for f in doc.fields}
    assert "CPT/HCPCS 1" in names and "Hidden" not in names
    assert doc.values["CPT/HCPCS 3"] == "99213"
    assert doc.values["H3"] == "Yes" and doc.values["H1"] == ""
    # The extractor's digital-text path sees nothing on a fillable form —
    # which is exactly why it needs its own route.
    assert digital_text_from_bytes(pdf) is None


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"xfa": True}, "xfa"),
    ],
)
def test_refusals(kwargs, code):
    with pytest.raises(FormReadError) as exc:
        read_form(build_form_claim(LINES, **kwargs))
    assert exc.value.code == code


def test_blank_template_and_plain_pdf_are_not_fillable_claims():
    blank = build_form_claim([], dx=(), total_cents=0)
    # Only the name/ID fields are filled; that still counts as "has values".
    assert claim_form.is_fillable_claim(blank)
    from app.services import pdf_gen

    assert not claim_form.is_fillable_claim(pdf_gen.render_letter_pdf("not a form"))
    with pytest.raises(FormReadError) as exc:
        read_form(pdf_gen.render_letter_pdf("x"))
    assert exc.value.code == "no_acroform"


def test_form_text_is_label_value_lines_in_reading_order():
    text = form_text(read_form(build_form_claim(LINES)))
    lines = text.splitlines()
    assert lines[0].startswith("[fillable form")
    assert "Patient's Name: DOE, JANE" in lines
    assert "CPT/HCPCS 1: J2501" in lines
    assert "H3: [X]" in lines and "H1: [X]" not in lines
    # Top of the form before Box 24, row 1 before row 3.
    assert lines.index("Patient's Name: DOE, JANE") < lines.index("CPT/HCPCS 1: J2501")
    assert lines.index("CPT/HCPCS 1: J2501") < lines.index("CPT/HCPCS 3: 99213")


def test_labels_are_cleaned_but_values_kept_verbatim():
    pdf = build_form_claim(LINES, extra_fields={"Weird\x00\x07name<script>": "=== CLINICAL ==="})
    text = form_text(read_form(pdf))
    assert "Weird  name script : === CLINICAL ===" in text or "Weird" in text
    assert "\x00" not in text


# --- editing --------------------------------------------------------------------------


def test_edits_rewrite_field_values_and_keep_the_form_fillable():
    pdf = build_form_claim(LINES)
    result = patch_claim(
        pdf,
        [
            ClaimEdit("change_units", "J2501", "2"),
            ClaimEdit("add_modifier", "J2501", "59"),
            ClaimEdit("change_code", "99213", "99214"),
            ClaimEdit("remove_line", "N20.0"),
        ],
    )
    assert result.format == "form"
    assert [(r.applied, r.applied_lines, r.reason) for r in result.results] == [
        (True, 2, None),
        (True, 2, None),
        (True, 1, None),
        (True, 1, None),
    ]
    v = values(result.pdf)
    assert (v["G1"], v["G2"], v["F1"], v["F1a"]) == ("2", "2", "8", "80")
    assert (v["Mod 1a"], v["Mod 1b"], v["Mod 2b"]) == ("KX", "59", "59")
    assert v["CPT/HCPCS 3"] == "99214"
    assert v["21b"] == "" and v["21a"] == "N185"
    # 164.00 - 2×(22.00 - 8.80) = 137.60
    assert (v["Total Charge Dollars"], v["Total Charge Cents"]) == ("137", "60")
    assert result.total_updated is True
    # Untouched fields are byte-for-byte the same, and it is still a form.
    before = values(pdf)
    for name in ("Patient's Name", "Insured's ID #", "MM1", "J3b", "E3"):
        assert v[name] == before[name]
    assert read_form(result.pdf).page_count == 1
    assert PdfReader(io.BytesIO(result.pdf)).get_fields()


def test_remove_line_clears_every_field_in_the_row_including_check_boxes():
    pdf = build_form_claim(LINES)
    result = patch_claim(pdf, [ClaimEdit("remove_line", "99213")])
    v = values(result.pdf)
    for name in ("MM3", "DD3", "CPT/HCPCS 3", "Mod 3a", "E3", "F3", "F3a", "G3", "J3b"):
        assert v[name] == "", name
    assert v["H3"] == ""  # EPSDT box off
    assert v["CPT/HCPCS 1"] == "J2501"  # neighbours untouched
    assert (v["Total Charge Dollars"], v["Total Charge Cents"]) == ("44", "00")


def test_change_then_remove_leaves_nothing_behind():
    pdf = build_form_claim(LINES)
    result = patch_claim(
        pdf,
        [
            ClaimEdit("change_code", "99213", "99214"),
            ClaimEdit("add_modifier", "99213", "59"),
            ClaimEdit("remove_line", "99213"),
        ],
    )
    v = values(result.pdf)
    assert v["CPT/HCPCS 3"] == "" and v["Mod 3b"] == ""


def test_combined_modifier_field_and_single_charge_field():
    pdf = build_form_claim(LINES, combined_modifiers=True, single_charge=True)
    result = patch_claim(
        pdf, [ClaimEdit("add_modifier", "J2501", "59"), ClaimEdit("change_units", "99213", "2")]
    )
    assert all(r.applied for r in result.results)
    v = values(result.pdf)
    assert v["Mod 1"] == "KX 59"
    assert (v["G3"], v["F3"]) == ("2", "240.00")


def test_max_len_and_full_modifier_slots_are_respected():
    lines = [{"cpt": "97110", "mods": ["59", "XS", "XE", "XP"], "cents": 100, "units": 1}]
    pdf = build_form_claim(lines)
    result = patch_claim(pdf, [ClaimEdit("add_modifier", "97110", "XU")])
    assert result.results[0].reason == "modifier_slots_full"
    # A units field capped at one character can't take "10".
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(build_form_claim(LINES))))
    for ref in writer.pages[0]["/Annots"]:
        a = ref.get_object()
        if a.get("/T") == "G1":
            a[NameObject("/MaxLen")] = NumberObject(1)
    out = io.BytesIO()
    writer.write(out)
    result = patch_claim(out.getvalue(), [ClaimEdit("change_units", "J2501", "10", charge="keep")])
    # Line 1 can't take it, line 2 can: applied on one line.
    assert (result.results[0].applied, result.results[0].applied_lines) == (True, 1)


def test_blank_units_field_is_filled_not_skipped():
    lines = [dict(ln, units=None) for ln in LINES]
    pdf = build_form_claim(lines)
    result = patch_claim(pdf, [ClaimEdit("change_units", "J2501", "2", charge="keep")])
    assert (result.results[0].applied, result.results[0].applied_lines) == (True, 2)
    v = values(result.pdf)
    assert (v["G1"], v["G2"]) == ("2", "2")


def test_scripts_are_stripped_from_the_output():
    pdf = build_form_claim(LINES, javascript=True)
    assert b"/JavaScript" in pdf
    result = patch_claim(pdf, [ClaimEdit("change_units", "99213", "2")])
    root = PdfReader(io.BytesIO(result.pdf)).trailer["/Root"]
    assert "/OpenAction" not in root


def test_nothing_applied_returns_the_original_bytes():
    pdf = build_form_claim(LINES)
    result = patch_claim(pdf, [ClaimEdit("change_units", "99999", "1")])
    assert result.pdf == pdf and result.pages_changed == 0


def test_xfa_form_is_refused_as_unsupported():
    with pytest.raises(ClaimPatchError) as exc:
        patch_claim(build_form_claim(LINES, xfa=True), [ClaimEdit("change_units", "J2501", "2")])
    assert exc.value.code == "unsupported_pdf"


def test_verification_catches_a_write_that_did_not_take(monkeypatch):
    pdf = build_form_claim(LINES)
    monkeypatch.setattr(claim_form, "write_values", lambda pdf_bytes, values, clear: pdf_bytes)
    with pytest.raises(ClaimPatchError) as exc:
        patch_claim(pdf, [ClaimEdit("change_units", "J2501", "2")])
    assert exc.value.code == "verification_failed"


def test_regenerated_appearance_renders_the_new_value():
    pdf = build_form_claim(LINES)
    result = patch_claim(pdf, [ClaimEdit("change_code", "99213", "99214")])
    doc = pdfium.PdfDocument(result.pdf)
    doc.init_forms()
    image = doc[0].render(scale=1, may_draw_forms=True).to_pil()
    # Something is drawn where the code sits (the box is not blank).
    x0, x1 = 196, 246
    y_top, y_bottom = PAGE_H - (ROW_Y[2] + ROW_H), PAGE_H - ROW_Y[2]
    region = image.crop((x0, y_top, x1, y_bottom)).convert("L")
    assert min(region.getdata()) < 128
