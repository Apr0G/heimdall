"""In-place CMS-1500 patching. The fixtures are synthetic claims (hard rule 1)
built three ways billing systems actually print them — one text operator per
cell, a whole row in one string, and kerned TJ arrays — with and without the
form's own labels, so the parser is exercised on layout, not coordinates."""

import io
import zlib

import pdfplumber
import pytest
from pypdf import PdfReader

from app.services import claim_patch
from app.services.claim_patch import ClaimEdit, ClaimPatchError, patch_claim

PAGE_W, PAGE_H = 612, 792
STYLES = ("cells", "row", "tj")


def _esc(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


_SPACING = ""  # set per build_claim call; keeps the cell helpers' signatures small


def _tj(text: str, x: float, y: float, size: int = 9) -> str:
    return f"BT /F1 {size} Tf {_SPACING} 1 0 0 1 {x} {y} Tm ({_esc(text)}) Tj ET\n"


def _tj_array(parts: list, x: float, y: float, size: int = 9) -> str:
    items = " ".join(f"({_esc(p)})" if isinstance(p, str) else str(p) for p in parts)
    return f"BT /F1 {size} Tf 1 0 0 1 {x} {y} Tm [{items}] TJ ET\n"


# Box 24 cell x positions (data-only print of a 02/12 form, roughly to scale).
X = {
    "dos": 40,
    "dos_to": 100,
    "pos": 160,
    "emg": 180,
    "cpt": 200,
    "mods": (240, 262, 284, 306),
    "ptr": 330,
    "charge": 360,
    "cents": 385,
    "units": 420,
    "epsdt": 445,
    "npi": 470,
}
ROW_Y0 = 500
ROW_STEP = 24


def build_claim(
    lines: list[dict],
    *,
    style: str = "cells",
    form: bool = True,
    money: str = "split",  # split ("150" "00") | single ("150.00") | dollar ("$1,150.00")
    dx: tuple[str, ...] = ("M17.11", "M25.561"),
    dx_dots: bool = True,  # the paper form prints Box 21 without decimals ("D509")
    total_label: str = "TOTAL CHARGE",
    pages: int = 1,
    xobject: bool = False,
    background: bool = False,  # drawn form background as a text-free form XObject
    spacing: str = "",  # extra text-state ops, e.g. "0.3 Tc 95 Tz 1 Tw"
    compress: bool = False,
) -> bytes:
    """Synthetic claim: every value is fake (CPT/HCPCS are real code *formats*,
    the NPI is all zeros)."""

    global _SPACING
    _SPACING = spacing

    def money_words(cents: int) -> list[str]:
        dollars, rem = divmod(cents, 100)
        if money == "split":
            return [str(dollars), f"{rem:02d}"]
        if money == "dollar":
            return [f"${dollars:,}.{rem:02d}"]
        return [f"{dollars}.{rem:02d}"]

    def page_content(page_lines: list[dict], total_cents: int) -> str:
        c = ""
        if form:
            c += _tj("HEALTH INSURANCE CLAIM FORM (SYNTHETIC TEST DATA)", 40, 750, 11)
            c += _tj(
                "24. A. DATE(S) OF SERVICE  B. POS  C. EMG  D. PROCEDURES  E. DX  "
                "F. $ CHARGES  G. UNITS",
                40,
                ROW_Y0 + 30,
                6,
            )
            slots = "  ".join(
                f"{letter}. {code if dx_dots else code.replace('.', '')}"
                for letter, code in zip("ABCDEFGHIJKL", dx, strict=False)
            )
            c += _tj(f"21. DIAGNOSIS  {slots}", 40, ROW_Y0 + 60, 8)
            c += _tj("1a. INSURED ID  000000000  ZIP 90210", 40, ROW_Y0 + 90, 8)
        for i, line in enumerate(page_lines):
            y = ROW_Y0 - ROW_STEP * i
            if form:
                # The shaded upper half of each service line carries the NPI label.
                c += _tj("NPI", X["npi"] - 22, y + 11, 6)
            cells: list[tuple[str, float]] = [("01 15 26", X["dos"]), ("01 15 26", X["dos_to"])]
            cells.append(("11", X["pos"]))
            cells.append((line["cpt"], X["cpt"]))
            for m, mx in zip(line.get("mods", []), X["mods"], strict=False):
                cells.append((m, mx))
            cells.append((line.get("ptr", "A"), X["ptr"]))
            mw = money_words(line["cents"])
            cells.append((mw[0], X["charge"]))
            if len(mw) == 2:
                cells.append((mw[1], X["cents"]))
            cells.append((str(line.get("units", 1)), X["units"]))
            cells.append(("0000000000", X["npi"]))
            if style == "cells":
                for text, x in cells:
                    c += _tj(text, x, y)
            elif style == "row":
                c += _tj("   ".join(t for t, _ in cells), X["dos"], y)
            else:  # kerned arrays, code split mid-token
                for text, x in cells:
                    if text == line["cpt"]:
                        c += _tj_array([text[:3], 15, text[3:]], x, y)
                    else:
                        c += _tj_array([text[:1], -8, text[1:]] if len(text) > 1 else [text], x, y)
        if form:
            c += _tj("28. " + total_label, 250, 200, 7)
            c += _tj("29. AMOUNT PAID", 440, 200, 7)
            c += _tj("0", 520, 200)
            c += _tj("00", 545, 200)
        tw = money_words(total_cents)
        c += _tj(tw[0], X["charge"], 200)
        if len(tw) == 2:
            c += _tj(tw[1], X["cents"], 200)
        return c

    per_page = [lines[i::pages] for i in range(pages)] if pages > 1 else [lines]
    grand = sum(ln["cents"] for ln in lines)

    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"",  # Pages, filled after we know the page object numbers
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    page_nums: list[int] = []
    for page_lines in per_page:
        content = page_content(page_lines, grand).encode("latin-1")
        if xobject:
            xobj = (
                b"<< /Type /XObject /Subtype /Form /BBox [0 0 612 792] "
                b"/Resources << /Font << /F1 3 0 R >> >> /Length "
                + str(len(content)).encode()
                + b" >>\nstream\n"
                + content
                + b"\nendstream"
            )
            objects.append(xobj)
            xobj_num = len(objects)
            content = b"/X1 Do"
            resources = (
                b"/Resources << /Font << /F1 3 0 R >> /XObject << /X1 "
                + str(xobj_num).encode()
                + b" 0 R >> >>"
            )
        elif background:
            # A vector form background (boxes, no text) drawn before the data,
            # the way "with form" exports from billing systems are built.
            bg = (
                b"0.8 0 0 RG 40 180 530 380 re S 40 "
                + str(ROW_Y0 - 10).encode()
                + b" m 570 "
                + str(ROW_Y0 - 10).encode()
                + b" l S"
            )
            objects.append(
                b"<< /Type /XObject /Subtype /Form /BBox [0 0 612 792] /Length "
                + str(len(bg)).encode()
                + b" >>\nstream\n"
                + bg
                + b"\nendstream"
            )
            bg_num = len(objects)
            content = b"q /Bg Do Q\n" + content
            resources = (
                b"/Resources << /Font << /F1 3 0 R >> /XObject << /Bg "
                + str(bg_num).encode()
                + b" 0 R >> >>"
            )
        else:
            resources = b"/Resources << /Font << /F1 3 0 R >> >>"
        page_num = len(objects) + 1
        content_num = page_num + 1
        page_nums.append(page_num)
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            + resources
            + b" /Contents "
            + str(content_num).encode()
            + b" 0 R >>"
        )
        if compress:
            data = zlib.compress(content)
            objects.append(
                b"<< /Length "
                + str(len(data)).encode()
                + b" /Filter /FlateDecode >>\nstream\n"
                + data
                + b"\nendstream"
            )
        else:
            objects.append(
                b"<< /Length "
                + str(len(content)).encode()
                + b" >>\nstream\n"
                + content
                + b"\nendstream"
            )
    objects[1] = (
        b"<< /Type /Pages /Kids ["
        + b" ".join(f"{n} 0 R".encode() for n in page_nums)
        + b"] /Count "
        + str(len(page_nums)).encode()
        + b" >>"
    )

    pdf = b"%PDF-1.4\n"
    offsets = []
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += str(index).encode() + b" 0 obj\n" + obj + b"\nendobj\n"
    xref_at = len(pdf)
    pdf += b"xref\n0 " + str(len(objects) + 1).encode() + b"\n0000000000 65535 f \n"
    for off in offsets:
        pdf += f"{off:010d} 00000 n \n".encode()
    pdf += b"trailer\n<< /Size " + str(len(objects) + 1).encode() + b" /Root 1 0 R >>\n"
    pdf += b"startxref\n" + str(xref_at).encode() + b"\n%%EOF"
    return pdf


LINES = [
    {"cpt": "99213", "mods": ["25"], "cents": 12000, "units": 1},
    {"cpt": "20610", "mods": [], "cents": 15000, "units": 3},
    {"cpt": "J3301", "mods": ["RT"], "cents": 4500, "units": 2, "ptr": "AB"},
]


def words(pdf: bytes, page: int = 0) -> list[dict]:
    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        return doc.pages[page].extract_words()


def words_at_row(pdf: bytes, row: int) -> list[str]:
    """Text of the words on service line `row`, left to right."""
    y_top = PAGE_H - (ROW_Y0 - ROW_STEP * row) - 9
    return [
        w["text"] for w in sorted(words(pdf), key=lambda w: w["x0"]) if abs(w["top"] - y_top) < 3
    ]


def service_lines(pdf: bytes):
    pages = claim_patch._load_pages(pdf)
    return [ln for p in pages for ln in claim_patch._find_service_lines(p.words)]


# --- parsing ------------------------------------------------------------------


@pytest.mark.parametrize("style", STYLES)
@pytest.mark.parametrize("form", [True, False])
@pytest.mark.parametrize("money", ["split", "single", "dollar"])
def test_finds_every_service_line_regardless_of_print_style(style, form, money):
    pdf = build_claim(LINES, style=style, form=form, money=money)
    lines = service_lines(pdf)
    assert [ln.cpt.text for ln in lines] == ["99213", "20610", "J3301"]
    assert [[m.text for m in ln.modifiers] for ln in lines] == [["25"], [], ["RT"]]
    assert [ln.pointer.text for ln in lines] == ["A", "A", "AB"]
    assert [ln.charge.cents for ln in lines] == [12000, 15000, 4500]
    assert [ln.units.text for ln in lines] == ["1", "3", "2"]


def test_zip_and_id_numbers_are_not_service_lines():
    # "90210" in the address block looks like a CPT but has no charge/units after it.
    pdf = build_claim(LINES[:1], form=True)
    assert [ln.cpt.text for ln in service_lines(pdf)] == ["99213"]


def test_shaded_half_row_label_is_not_data():
    pdf = build_claim(LINES, form=True)
    for ln in service_lines(pdf):
        assert all(w.text != "NPI" for w in ln.shaded_words)


# --- edits --------------------------------------------------------------------


@pytest.mark.parametrize("style", STYLES)
def test_change_units_replaces_only_that_cell(style):
    pdf = build_claim(LINES, style=style)
    before = words_at_row(pdf, 1)
    result = patch_claim(pdf, [ClaimEdit("change_units", "20610", "1")])
    assert result.results[0].applied
    after = words_at_row(result.pdf, 1)
    assert before.index("3") == after.index("1")
    assert after == [("1" if w == "3" else w) for w in before]
    # The other rows are untouched, and the old value is gone from the text
    # layer, not hidden under a white box.
    assert words_at_row(result.pdf, 0) == words_at_row(pdf, 0)
    assert words_at_row(result.pdf, 2) == words_at_row(pdf, 2)
    assert "3" not in PdfReader(io.BytesIO(result.pdf)).pages[0].extract_text().split()
    assert service_lines(result.pdf)[1].units.text == "1"


@pytest.mark.parametrize("style", ["cells", "tj"])
def test_add_modifier(style):
    pdf = build_claim(LINES, style=style)
    result = patch_claim(pdf, [ClaimEdit("add_modifier", "20610", "59")])
    assert result.results[0].applied
    lines = service_lines(result.pdf)
    assert [m.text for m in lines[1].modifiers] == ["59"]
    # Existing modifier lines get the new one appended after the last.
    result2 = patch_claim(pdf, [ClaimEdit("add_modifier", "99213", "XS")])
    assert [m.text for m in service_lines(result2.pdf)[0].modifiers] == ["25", "XS"]


def test_add_modifier_refuses_when_the_row_has_no_gap_for_it():
    # A whole-row string leaves three spaces between cells: inserting there
    # would push every cell to the right out of its box. Skip, don't shift.
    pdf = build_claim(LINES, style="row")
    result = patch_claim(pdf, [ClaimEdit("add_modifier", "20610", "59")])
    assert result.results[0].reason == "no_room"
    assert result.pdf == pdf


@pytest.mark.parametrize("style", STYLES)
def test_change_code(style):
    pdf = build_claim(LINES, style=style)
    result = patch_claim(pdf, [ClaimEdit("change_code", "99213", "99212")])
    assert result.results[0].applied
    assert [ln.cpt.text for ln in service_lines(result.pdf)] == ["99212", "20610", "J3301"]


@pytest.mark.parametrize("style", STYLES)
@pytest.mark.parametrize("money", ["split", "single", "dollar"])
def test_remove_line_clears_the_row_and_recomputes_the_total(style, money):
    pdf = build_claim(LINES, style=style, money=money)
    result = patch_claim(pdf, [ClaimEdit("remove_line", "20610")])
    assert result.results[0].applied
    assert result.total_updated is True
    assert words_at_row(result.pdf, 1) == []
    assert [ln.cpt.text for ln in service_lines(result.pdf)] == ["99213", "J3301"]
    # 315.00 - 150.00 = 165.00, in the document's own money format.
    texts = [w["text"] for w in words(result.pdf)]
    expected = {"split": ["165", "00"], "single": ["165.00"], "dollar": ["$165.00"]}[money]
    for token in expected:
        assert token in texts
    assert "315" not in texts and "315.00" not in texts and "$315.00" not in texts


def test_remove_line_keeps_the_forms_own_labels():
    pdf = build_claim(LINES, form=True)
    result = patch_claim(pdf, [ClaimEdit("remove_line", "20610")])
    texts = [w["text"] for w in words(result.pdf)]
    assert texts.count("NPI") == 3
    assert "DIAGNOSIS" in texts and "TOTAL" in texts


def test_several_edits_in_one_pass():
    pdf = build_claim(LINES)
    result = patch_claim(
        pdf,
        [
            ClaimEdit("remove_line", "J3301"),
            ClaimEdit("change_units", "20610", "1"),
            ClaimEdit("add_modifier", "20610", "XS"),
            ClaimEdit("change_code", "99213", "99214"),
        ],
    )
    assert all(r.applied for r in result.results)
    lines = service_lines(result.pdf)
    assert [(ln.cpt.text, [m.text for m in ln.modifiers], ln.units.text) for ln in lines] == [
        ("99214", ["25"], "1"),
        ("20610", ["XS"], "1"),
    ]
    assert result.total_updated is True
    assert result.pages_changed == 1


def test_no_edits_applied_returns_the_original_bytes():
    pdf = build_claim(LINES)
    result = patch_claim(pdf, [ClaimEdit("change_units", "99999", "1")])
    assert result.pdf == pdf
    assert result.pages_changed == 0
    assert result.results[0].reason == "line_not_found"


def test_compressed_content_streams():
    pdf = build_claim(LINES, compress=True)
    result = patch_claim(pdf, [ClaimEdit("change_units", "20610", "1")])
    assert service_lines(result.pdf)[1].units.text == "1"


def test_multi_page_claim_edits_lines_but_leaves_the_total_alone():
    six = LINES + [
        {"cpt": "97110", "cents": 8000, "units": 4},
        {"cpt": "97140", "cents": 6000, "units": 1},
    ]
    pdf = build_claim(six, pages=2)
    assert len(PdfReader(io.BytesIO(pdf)).pages) == 2
    result = patch_claim(
        pdf, [ClaimEdit("remove_line", "97110"), ClaimEdit("change_units", "20610", "2")]
    )
    assert [r.applied for r in result.results] == [True, True]
    assert result.total_updated is False
    assert "97110" not in {ln.cpt.text for ln in service_lines(result.pdf)}


# --- per-edit refusals --------------------------------------------------------


def test_skip_reasons():
    pdf = build_claim(LINES + [{"cpt": "97110", "mods": ["59", "XS", "XE", "XP"], "cents": 100}])
    result = patch_claim(
        pdf,
        [
            ClaimEdit("change_units", "20610", "3"),  # already 3
            ClaimEdit("documentation", "99213", None),
            ClaimEdit("change_units", "99213", "1"),  # already 1
            ClaimEdit("change_units", "99213", "0"),
            ClaimEdit("add_modifier", "99213", "5"),
            ClaimEdit("add_modifier", "99213", "25"),
            ClaimEdit("add_modifier", "97110", "XU"),
            ClaimEdit("change_code", "J3301", "abc"),
        ],
    )
    assert [r.reason for r in result.results] == [
        "already_present",
        "unsupported_kind",
        "already_present",
        "bad_value",
        "bad_value",
        "already_present",
        "modifier_slots_full",
        "bad_value",
    ]
    assert result.pdf == pdf


def test_values_are_normalised_but_not_trusted():
    pdf = build_claim(LINES)
    result = patch_claim(pdf, [ClaimEdit("add_modifier", "20610", " xs ")])
    assert result.results[0].applied
    assert [m.text for m in service_lines(result.pdf)[1].modifiers] == ["XS"]


# --- document-level refusals --------------------------------------------------


def test_text_inside_a_form_xobject_is_refused():
    pdf = build_claim(LINES, xobject=True)
    with pytest.raises(ClaimPatchError) as exc:
        patch_claim(pdf, [ClaimEdit("change_units", "20610", "1")])
    assert exc.value.code == "unsupported_pdf"


def test_document_without_service_lines_is_refused():
    from app.services import pdf_gen

    pdf = pdf_gen.render_letter_pdf("Dear Payer, this is not a claim.")
    with pytest.raises(ClaimPatchError) as exc:
        patch_claim(pdf, [ClaimEdit("change_units", "20610", "1")])
    assert exc.value.code == "no_service_lines"


def test_garbage_bytes_are_refused_without_quoting_them():
    with pytest.raises(ClaimPatchError) as exc:
        patch_claim(b"not a pdf at all", [ClaimEdit("change_units", "20610", "1")])
    assert exc.value.code == "unsupported_pdf"
    assert "not a pdf" not in str(exc.value)


def test_verification_catches_a_rewrite_that_did_not_take(monkeypatch):
    pdf = build_claim(LINES)
    monkeypatch.setattr(claim_patch, "_rewrite", lambda pdf_bytes, pages, per_page: pdf_bytes)
    with pytest.raises(ClaimPatchError) as exc:
        patch_claim(pdf, [ClaimEdit("change_units", "20610", "1")])
    assert exc.value.code == "verification_failed"


# --- a code on several lines ----------------------------------------------------

MULTI = [
    {"cpt": "J2501", "mods": ["KX"], "cents": 2200, "units": 5},
    {"cpt": "J2501", "mods": ["KX"], "cents": 2200, "units": 5},
    {"cpt": "J3370", "mods": ["KX"], "cents": 1095, "units": 10},
    {"cpt": "J3370", "mods": ["KX"], "cents": 1095, "units": 2},
]


def test_edits_apply_to_every_line_carrying_the_code():
    # Drug codes are billed one line per date; the edit is about the code.
    pdf = build_claim(MULTI, money="single")
    result = patch_claim(
        pdf,
        [
            ClaimEdit("change_units", "J2501", "2"),
            ClaimEdit("add_modifier", "J2501", "59"),
            ClaimEdit("change_units", "J3370", "2"),  # only the line over 2
            ClaimEdit("change_code", "J3370", "J3371"),
        ],
    )
    assert [(r.applied, r.applied_lines, r.reason) for r in result.results] == [
        (True, 2, None),
        (True, 2, None),
        (True, 1, None),
        (True, 2, None),
    ]
    lines = service_lines(result.pdf)
    assert [(ln.cpt.text, [m.text for m in ln.modifiers], ln.units.text) for ln in lines] == [
        ("J2501", ["KX", "59"], "2"),
        ("J2501", ["KX", "59"], "2"),
        ("J3371", ["KX"], "2"),
        ("J3371", ["KX"], "2"),
    ]


def test_remove_line_takes_every_line_of_the_code_and_fixes_the_total():
    pdf = build_claim(MULTI, money="single")
    result = patch_claim(pdf, [ClaimEdit("remove_line", "J2501")])
    assert result.results[0].applied_lines == 2
    assert result.total_updated is True
    assert [ln.cpt.text for ln in service_lines(result.pdf)] == ["J3370", "J3370"]
    assert "21.90" in [w["text"] for w in words(result.pdf)]


def test_modifier_only_lands_on_lines_that_lack_it():
    pdf = build_claim(
        [
            {"cpt": "J2501", "mods": ["KX", "59"], "cents": 100, "units": 1},
            {"cpt": "J2501", "mods": ["KX"], "cents": 100, "units": 1},
        ]
    )
    result = patch_claim(pdf, [ClaimEdit("add_modifier", "J2501", "59")])
    assert (result.results[0].applied, result.results[0].applied_lines) == (True, 1)
    assert [[m.text for m in ln.modifiers] for ln in service_lines(result.pdf)] == [
        ["KX", "59"],
        ["KX", "59"],
    ]


# --- Box 21 diagnosis codes -------------------------------------------------------


@pytest.mark.parametrize("dx_dots", [True, False])
def test_diagnosis_code_can_be_removed_or_replaced(dx_dots):
    pdf = build_claim(LINES, dx=("N18.5", "N20.0", "D50.9"), dx_dots=dx_dots)
    result = patch_claim(
        pdf,
        [
            ClaimEdit("remove_line", "D50.9"),
            ClaimEdit("change_code", "N20.0", "N20.1"),
            ClaimEdit("add_modifier", "N18.5", "59"),  # modifiers are for service lines
        ],
    )
    assert [(r.applied, r.reason, r.note) for r in result.results] == [
        (True, None, "check_dx_pointers"),
        (True, None, None),
        (False, "not_a_service_line", None),
    ]
    texts = [w["text"] for w in words(result.pdf)]
    gone, was, now = ("D50.9", "N20.0", "N20.1") if dx_dots else ("D509", "N200", "N201")
    assert gone not in texts and was not in texts and now in texts
    # Service lines untouched; the form's own slot labels stay.
    assert [ln.cpt.text for ln in service_lines(result.pdf)] == ["99213", "20610", "J3301"]
    assert "C." in texts


def test_diagnosis_lookup_never_touches_a_service_row_or_an_unknown_code():
    pdf = build_claim(LINES, dx=("N18.5",))
    result = patch_claim(
        pdf, [ClaimEdit("remove_line", "N18.9"), ClaimEdit("change_code", "N18.5", "abc")]
    )
    assert [r.reason for r in result.results] == ["line_not_found", "bad_value"]
    assert result.pdf == pdf


# --- real-export traits -----------------------------------------------------------


def test_text_free_form_background_is_fine():
    # "With form" exports draw the red CMS-1500 as a form XObject with no text;
    # only text inside an XObject would throw the char numbering off.
    pdf = build_claim(LINES, background=True)
    result = patch_claim(pdf, [ClaimEdit("change_units", "20610", "1")])
    assert result.results[0].applied
    assert service_lines(result.pdf)[1].units.text == "1"


@pytest.mark.parametrize("spacing", ["0.4 Tc", "2 Tw", "90 Tz", "0.3 Tc 1.5 Tw 110 Tz"])
def test_character_and_word_spacing_are_reproduced_exactly(spacing):
    # Billing systems set Tc/Tw/Tz; the TJ adjustment for a removed glyph has
    # to include them or the rest of the row shifts (caught by verification).
    pdf = build_claim(LINES, style="row", spacing=spacing)
    result = patch_claim(
        pdf, [ClaimEdit("change_units", "20610", "1"), ClaimEdit("change_code", "J3301", "J3302")]
    )
    assert all(r.applied for r in result.results)
    assert words_at_row(result.pdf, 1) == [("1" if w == "3" else w) for w in words_at_row(pdf, 1)]
    assert service_lines(result.pdf)[2].cpt.text == "J3302"


def test_rewritten_streams_are_compressed():
    pdf = build_claim(LINES, compress=True)
    result = patch_claim(pdf, [ClaimEdit("change_units", "20610", "1")])
    assert b"/FlateDecode" in result.pdf
