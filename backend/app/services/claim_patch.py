"""Apply pre-check edits to a born-digital CMS-1500 PDF, in place.

The doctor's draft claim comes back as *their* PDF with the chosen changes
made, not a re-typed summary. Three properties this module guarantees:

* **No model in the loop.** The review pipeline decides *what* to change
  (``risk_reports.proposed_edits``); this code makes the change. A patched
  claim is a deterministic function of the PDF and the selected edits.
* **Old values are gone, not covered.** A white box drawn over a cell leaves
  the original glyphs in the content stream, where any text extractor (a PDF
  viewer's select-all, a payer's intake tool, our own re-check) still reads
  them. So the original glyph codes are removed from the text-showing
  operator and replaced by an equivalent advance, which keeps every other
  glyph on the page exactly where it was; the new value is drawn on top in
  Helvetica at the old origin and size.
* **Verified before it leaves.** The patched PDF is re-read and every word
  compared against the expected outcome (original words, minus removals, plus
  insertions, at the same positions ± a point). Any discrepancy raises rather
  than returning a subtly wrong claim (hard rule 9).

Service lines are located by *content*, never by coordinates: the CMS-1500
(02/12) fixes the *order* of Box 24 cells (DOS · POS · EMG · CPT + modifiers ·
dx pointer · charge · units · …) but billing systems print them with their own
fonts, offsets and grouping, and "data only" prints for pre-printed red stock
have no form at all. Anything this parser cannot read with confidence is
refused (``ClaimPatchError``) or skipped per edit with a reason code; the
caller falls back to the edits-only view. Never PHI in exceptions or reasons —
codes and counts only (hard rule 2).
"""

from __future__ import annotations

import io
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

import pdfplumber
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    ByteStringObject,
    ContentStream,
    DictionaryObject,
    FloatObject,
    NameObject,
    NumberObject,
)

# --- vocabulary --------------------------------------------------------------

EDIT_KINDS = ("remove_line", "add_modifier", "change_units", "change_code")
MAX_MODIFIERS = 4  # Box 24D has four modifier positions

# CPT (5 digits, or 4 digits + F/T/U category suffix) or HCPCS level II (letter + 4 digits).
_CODE_RE = re.compile(r"^(?:\d{5}|\d{4}[FTU]|[A-Z]\d{4})$")
_MODIFIER_RE = re.compile(r"^[A-Z0-9]{2}$")
# ICD-10-CM as printed in Box 21 — with or without the decimal (the paper form
# omits it: "D509"). U is excluded (reserved chapter), same as CMS's own list.
_ICD10_RE = re.compile(r"^[A-TV-Z]\d{2}(?:\.?\d{1,4})?$")
# Box 24E: letters A–L on the 02/12 form (printed "AB", "A,B"), digits 1–4 on
# the older 08/05 form some payers' samples still show.
_DX_POINTER_RE = re.compile(r"^(?:[A-L](?:,?[A-L]){0,3}|[1-4](?:,?[1-4]){0,3})$")
# Box 24G as printed: whole units, or decimals for time/drug units ("1.5").
_UNITS_RE = re.compile(r"^\d{1,3}(?:\.\d{1,2})?$")
_MONEY_SINGLE_RE = re.compile(r"^\$?\d{1,3}(?:,\d{3})*\.\d{2}$|^\$?\d{1,7}\.\d{2}$")
_MONEY_DOLLARS_RE = re.compile(r"^\$?\d{1,7}$")
_MONEY_CENTS_RE = re.compile(r"^\d{2}$")
# Loose "looks like claim data, not a form label" test for the shaded half-row.
_DATA_TOKEN_RE = re.compile(r"^[A-Z0-9.,$/-]{1,12}$")
_LABEL_RE = re.compile(r"^[A-Z]{2,}$")

# Helvetica AFM advance widths (thousandths of em) for the characters an edit
# can draw: digits, uppercase, and the few punctuation marks money uses.
_HELVETICA_WIDTHS = {
    **{c: 556 for c in "0123456789"},
    **dict(
        zip(
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
            map(
                int,
                "667 667 722 722 667 611 778 722 278 500 667 556 833 "
                "722 778 667 778 722 667 611 722 667 944 667 667 611".split(),
            ),
            strict=True,
        )
    ),
    ".": 278,
    ",": 278,
    "$": 556,
    " ": 278,
}
_OVERLAY_FONT_KEY = "/HdClaimPatchHelv"
_OVERLAY_ITALIC_FONT_KEY = "/HdClaimPatchHelvOb"
_COLOR_OPERATOR = {1: b"g", 3: b"rg", 4: b"k"}
_POSITION_TOLERANCE = 1.5  # points; pdfminer float noise is far below this


class ClaimPatchError(RuntimeError):
    """Document-level refusal. ``code`` is one of: unsupported_pdf,
    no_service_lines, verification_failed. Deliberately carries no document
    text (hard rule 2)."""

    def __init__(self, code: str, detail: str | None = None) -> None:
        self.code = code
        super().__init__(code if detail is None else f"{code}: {detail}")


@dataclass(frozen=True)
class ClaimEdit:
    kind: str
    target: str  # the CPT/HCPCS on the line the edit applies to
    value: str | None = None  # new modifier / units / code; unused for remove_line


@dataclass(frozen=True)
class EditResult:
    edit: ClaimEdit
    applied: bool
    # Reason codes for a skipped edit: unsupported_kind, line_not_found,
    # ambiguous_line, modifier_slots_full, already_present, no_room, bad_value,
    # not_a_service_line (a modifier/units edit aimed at a diagnosis code),
    # no_units_cell (blank 24G and no sibling line shows where the column is).
    reason: str | None = None
    # A code can sit on several service lines (one per date); the edit applies
    # to each line it fits, and this says how many it reached.
    applied_lines: int = 0
    # Advisory for an applied edit, e.g. check_dx_pointers after a Box 21 removal.
    note: str | None = None


@dataclass
class PatchResult:
    pdf: bytes
    results: list[EditResult]
    # None when no charge changed; False when it changed but the Box 28 total
    # could not be located unambiguously (caller tells the user to fix it).
    total_updated: bool | None
    pages_changed: int


# --- page model -------------------------------------------------------------


@dataclass
class _Word:
    page: int
    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    size: float
    origin_x: float  # glyph origin of the first char, PDF user space
    origin_y: float
    chars: list[int]  # indices into the page's char list, stream order
    # Fill colour as the content stream set it (gray / RGB / CMYK tuple) and
    # whether the face is italic — so a drawn value matches its neighbours.
    color: tuple[float, ...] = (0.0,)
    italic: bool = False

    @property
    def upright(self) -> bool:
        return self.top < self.bottom


@dataclass
class _PageText:
    words: list[_Word]
    # Per char (stream order, spaces included): glyph advance in thousandths
    # of text space — what a TJ adjustment needs to reproduce it exactly.
    advances: list[float]


@dataclass
class _Charge:
    words: list[_Word]
    cents: int
    split: bool  # "150" "00" as two words vs "150.00" as one


@dataclass
class _ServiceLine:
    page: int
    cpt: _Word
    modifiers: list[_Word]
    pointer: _Word
    charge: _Charge
    units: _Word | None  # a blank 24G means one unit
    row_words: list[_Word]  # everything in the data band, sorted by x
    shaded_words: list[_Word]  # data tokens in the half-row above (24J qualifier etc.)


@dataclass
class _Overlay:
    page: int
    x: float
    y: float  # baseline, PDF user space
    size: float
    text: str
    line: object = None  # the service line it was drawn on, if any
    color: tuple[float, ...] = (0.0,)
    italic: bool = False


@dataclass
class _PageEdits:
    remove: set[int] = field(default_factory=set)  # char indices
    overlays: list[_Overlay] = field(default_factory=list)


# --- public entry point -----------------------------------------------------


def patch_claim(pdf_bytes: bytes, edits: Sequence[ClaimEdit]) -> PatchResult:
    """Apply ``edits`` to the CMS-1500 in ``pdf_bytes``. Raises ClaimPatchError
    when the document as a whole can't be handled; individual edits that can't
    be applied come back as EditResult(applied=False, reason=...)."""
    pages = _load_pages(pdf_bytes)
    pages_words = [page.words for page in pages]
    lines = [line for page_words in pages_words for line in _find_service_lines(page_words)]
    if not lines:
        raise ClaimPatchError("no_service_lines")

    per_page: dict[int, _PageEdits] = {}
    results: list[EditResult] = []
    removed_lines: list[_ServiceLine] = []
    expected_removed: list[_Word] = []
    expected_added: list[tuple[int, str, float, float]] = []  # page, text, x0, baseline

    def page_edits(page: int) -> _PageEdits:
        return per_page.setdefault(page, _PageEdits())

    ctx = _ApplyContext(page_edits, expected_removed, expected_added, removed_lines, lines)

    for edit in edits:
        if edit.kind not in EDIT_KINDS:
            results.append(EditResult(edit, False, "unsupported_kind"))
            continue
        target = edit.target.strip().upper()
        matches = [line for line in lines if line.cpt.text == target and line not in removed_lines]
        if matches:
            results.append(_apply_to_lines(edit, matches, ctx))
            continue
        dx_words = _find_dx(pages_words, lines, target)
        if dx_words is None or not dx_words:
            results.append(EditResult(edit, False, "line_not_found"))
        elif len(dx_words) > 1:
            results.append(EditResult(edit, False, "ambiguous_line"))
        else:
            results.append(_apply_to_dx(edit, dx_words[0], pages_words, ctx))

    total_updated: bool | None = None
    if removed_lines:
        total_updated = _update_total(
            pages_words, lines, removed_lines, per_page, expected_removed, expected_added
        )

    # A page whose every edit was skipped has an empty entry; don't rewrite it.
    per_page = {k: v for k, v in per_page.items() if v.remove or v.overlays}
    if not per_page:
        return PatchResult(pdf=pdf_bytes, results=results, total_updated=None, pages_changed=0)

    patched = _rewrite(pdf_bytes, pages, per_page)
    _verify(patched, pages_words, expected_removed, expected_added)
    return PatchResult(
        pdf=patched, results=results, total_updated=total_updated, pages_changed=len(per_page)
    )


@dataclass
class _ApplyContext:
    page_edits: object  # callable page -> _PageEdits
    expected_removed: list[_Word]
    expected_added: list[tuple[int, str, float, float]]
    removed_lines: list[_ServiceLine]
    lines: list[_ServiceLine] = field(default_factory=list)

    def units_column_x(self, page: int) -> float | None:
        xs = [ln.units.origin_x for ln in self.lines if ln.page == page and ln.units is not None]
        return min(xs) if xs else None

    def remove_word(self, word: _Word) -> None:
        self.page_edits(word.page).remove.update(word.chars)
        self.expected_removed.append(word)

    def draw(
        self,
        page: int,
        x: float,
        y: float,
        size: float,
        text: str,
        *,
        like: _Word,
        line: _ServiceLine | None = None,
    ) -> None:
        """Draw `text` at (x, y) styled like the word it replaces or sits next to."""
        overlay = _Overlay(page, x, y, size, text, line=line, color=like.color, italic=like.italic)
        self.page_edits(page).overlays.append(overlay)
        self.expected_added.append((page, text, x, y))

    def remove_line(self, line: _ServiceLine) -> None:
        """Take every word of the line — and anything an earlier edit drew on
        it, or a changed code / added modifier would float on the blank row."""
        for word in line.row_words + line.shaded_words:
            self.remove_word(word)
        pe = self.page_edits(line.page)
        dropped = [o for o in pe.overlays if o.line is line]
        pe.overlays = [o for o in pe.overlays if o.line is not line]
        for o in dropped:
            self.expected_added.remove((o.page, o.text, o.x, o.y))
        self.removed_lines.append(line)


def _apply_to_lines(edit: ClaimEdit, lines: list[_ServiceLine], ctx: _ApplyContext) -> EditResult:
    """Apply one edit to every service line carrying its code. A modifier or a
    code correction belongs on each line of that code; a unit cut lands on the
    lines that exceed the new count; a removal takes every line. Per-line
    failures (no room, slots full) don't block the other lines."""
    if edit.kind == "remove_line":
        for line in lines:
            ctx.remove_line(line)
        return EditResult(edit, True, applied_lines=len(lines))

    value = _validated_value(edit)
    if value is None:
        return EditResult(edit, False, "bad_value")

    if edit.kind == "change_units":
        current = [line for line in lines if _units_value(line) != float(value)]
        if not current:
            return EditResult(edit, False, "already_present")
        over = [line for line in current if _units_value(line) > int(value)]
        candidates = over or current
    elif edit.kind == "add_modifier":
        candidates = [line for line in lines if all(m.text != value for m in line.modifiers)]
        if not candidates:
            return EditResult(edit, False, "already_present")
    else:  # change_code
        candidates = lines

    applied = 0
    reasons: list[str] = []
    for line in candidates:
        reason = _apply_to_line(edit, value, line, ctx)
        if reason is None:
            applied += 1
        else:
            reasons.append(reason)
    if applied == 0:
        return EditResult(edit, False, reasons[0] if reasons else "line_not_found")
    return EditResult(edit, True, applied_lines=applied)


def _apply_to_line(
    edit: ClaimEdit, value: str, line: _ServiceLine, ctx: _ApplyContext
) -> str | None:
    """Apply to one line; return a skip reason or None when applied."""
    if edit.kind == "add_modifier":
        if len(line.modifiers) >= MAX_MODIFIERS:
            return "modifier_slots_full"
        anchor = line.modifiers[-1] if line.modifiers else line.cpt
        # Modifier boxes are ~3 characters apart on the form; reuse the gap the
        # printer left between the code and its first modifier when we have
        # one, else three digit-widths.
        gap = (
            (line.modifiers[0].x0 - line.cpt.x1)
            if line.modifiers
            else 3 * anchor.size * _HELVETICA_WIDTHS["0"] / 1000
        )
        x = anchor.x1 + gap
        if x + _text_width(value, anchor.size) > line.pointer.x0 - 1:
            return "no_room"
        ctx.draw(line.page, x, anchor.origin_y, anchor.size, value, like=anchor, line=line)
        return None

    if edit.kind == "change_units" and line.units is None:
        # Blank 24G (one unit implied): write the new count where the units
        # column is on this page, learned from a sibling line that has one.
        column_x = ctx.units_column_x(line.page)
        if column_x is None:
            return "no_units_cell"
        anchor = line.cpt
        after = [w for w in line.row_words if w.x0 > column_x]
        limit = after[0].x0 - 1 if after else column_x + _text_width(value, anchor.size)
        if column_x + _text_width(value, anchor.size) > limit:
            return "no_room"
        ctx.draw(line.page, column_x, anchor.origin_y, anchor.size, value, like=anchor, line=line)
        return None

    old = line.units if edit.kind == "change_units" else line.cpt
    assert old is not None
    if old.text == value:
        return "already_present"
    width = _text_width(value, old.size)
    right_neighbour = _next_word_right(line.row_words, old)
    limit = right_neighbour.x0 - 1 if right_neighbour else old.x1 + width
    if old.origin_x + width > limit:
        return "no_room"
    ctx.remove_word(old)
    ctx.draw(line.page, old.origin_x, old.origin_y, old.size, value, like=old, line=line)
    return None


def _find_dx(
    pages_words: list[list[_Word]], lines: list[_ServiceLine], target: str
) -> list[_Word] | None:
    """Box 21 candidates for an ICD-10 target: words off the service rows whose
    text equals the target with decimals ignored ("D50.9" matches "D509").
    None when the target isn't shaped like an ICD-10 code at all."""
    if not _ICD10_RE.match(target):
        return None
    key = target.replace(".", "")
    in_rows = {idx for line in lines for w in line.row_words + line.shaded_words for idx in w.chars}
    return [
        w
        for page_words in pages_words
        for w in page_words
        if w.upright and w.chars[0] not in in_rows and w.text.upper().replace(".", "") == key
    ]


def _apply_to_dx(
    edit: ClaimEdit, word: _Word, pages_words: list[list[_Word]], ctx: _ApplyContext
) -> EditResult:
    """A diagnosis code in Box 21: it can be removed or replaced. Modifiers and
    units are service-line concepts and don't apply."""
    if edit.kind in ("add_modifier", "change_units"):
        return EditResult(edit, False, "not_a_service_line")
    if edit.kind == "remove_line":
        ctx.remove_word(word)
        # Lines pointing at this slot (Box 24E) now reference nothing; the
        # form's own A–L labels stay, so only the pointers need a look.
        return EditResult(edit, True, applied_lines=1, note="check_dx_pointers")
    value = (edit.value or "").strip().upper()
    if not _ICD10_RE.match(value):
        return EditResult(edit, False, "bad_value")
    # Match the print style of the slot: no decimal if the form omits it.
    if "." not in word.text:
        value = value.replace(".", "")
    if value == word.text.upper():
        return EditResult(edit, False, "already_present")
    row = sorted(
        (
            w
            for w in pages_words[word.page]
            if w.upright and abs(w.top - word.top) <= max(2.0, 0.45 * word.size)
        ),
        key=lambda w: w.x0,
    )
    width = _text_width(value, word.size)
    right_neighbour = _next_word_right(row, word)
    limit = right_neighbour.x0 - 1 if right_neighbour else word.x1 + width
    if word.origin_x + width > limit:
        return EditResult(edit, False, "no_room")
    ctx.remove_word(word)
    ctx.draw(word.page, word.origin_x, word.origin_y, word.size, value, like=word)
    return EditResult(edit, True, applied_lines=1)


def _tj_units(
    advance: float, *, font_size: float, hscale: float, char_spacing: float, word_spacing: float
) -> float:
    """The TJ number that moves the cursor exactly as far as one removed glyph
    did. Per the PDF text-space equations a glyph displaces
    (w0·Tfs + Tc + Tw)·Th and a TJ number n displaces −n/1000·Tfs·Th, so
    n = 1000·w0 + 1000·(Tc + Tw)/Tfs. `advance` is pdfminer's glyph width,
    which already carries Th (1000·w0·Th)."""
    th = hscale / 100.0
    if th <= 0 or font_size <= 0:
        raise ClaimPatchError("unsupported_pdf", "text scaling state")
    return advance / th + 1000.0 * (char_spacing + word_spacing) / font_size


# --- reading ----------------------------------------------------------------


def _load_pages(pdf_bytes: bytes) -> list[_PageText]:
    pages: list[_PageText] = []
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as doc:
            for page_index, page in enumerate(doc.pages):
                if (page.rotation or 0) % 360 != 0:
                    raise ClaimPatchError("unsupported_pdf", "rotated page")
                index_of = {id(c): i for i, c in enumerate(page.chars)}
                words: list[_Word] = []
                for raw in page.extract_words(
                    use_text_flow=True, return_chars=True, extra_attrs=["size"]
                ):
                    chars = raw["chars"]
                    first = chars[0]
                    matrix = first["matrix"]
                    words.append(
                        _Word(
                            page=page_index,
                            text=raw["text"],
                            x0=raw["x0"],
                            x1=raw["x1"],
                            top=raw["top"],
                            bottom=raw["bottom"],
                            size=raw["size"],
                            origin_x=float(matrix[4]),
                            origin_y=float(matrix[5]),
                            chars=[index_of[id(c)] for c in chars],
                            color=_fill_color(first),
                            italic=_is_italic(str(first.get("fontname") or "")),
                        )
                    )
                advances = [
                    (c["x1"] - c["x0"]) / c["size"] * 1000 if c["size"] else 0.0 for c in page.chars
                ]
                pages.append(_PageText(words=words, advances=advances))
    except ClaimPatchError:
        raise
    except Exception as exc:  # noqa: BLE001 — parser messages can quote document text
        raise ClaimPatchError("unsupported_pdf", type(exc).__name__) from None
    return pages


def _fill_color(char: dict) -> tuple[float, ...]:
    """The glyph's non-stroking colour as a 1/3/4-tuple (gray/RGB/CMYK), or
    black when it's anything more exotic (pattern, separation)."""
    raw = char.get("non_stroking_color")
    if isinstance(raw, int | float):
        raw = (raw,)
    if isinstance(raw, list | tuple) and len(raw) in (1, 3, 4):
        try:
            return tuple(min(1.0, max(0.0, float(v))) for v in raw)
        except (TypeError, ValueError):
            pass
    return (0.0,)


def _is_italic(fontname: str) -> bool:
    lowered = fontname.lower()
    return "italic" in lowered or "oblique" in lowered


def _find_service_lines(words: list[_Word]) -> list[_ServiceLine]:
    lines: list[_ServiceLine] = []
    claimed: set[int] = set()  # char indices already part of a parsed line
    for cpt in sorted(words, key=lambda w: (w.top, w.x0)):
        if not _CODE_RE.match(cpt.text) or cpt.chars[0] in claimed:
            continue
        tol = max(2.0, 0.45 * cpt.size)
        row = sorted(
            (w for w in words if abs(w.top - cpt.top) <= tol and w.upright),
            key=lambda w: w.x0,
        )
        right = [w for w in row if w.x0 > cpt.x1]
        parsed = _parse_right_of_code(right)
        if parsed is None:
            continue
        modifiers, pointer, charge, units = parsed
        row_height = cpt.bottom - cpt.top
        shaded = [
            w
            for w in words
            if w.upright
            and cpt.top - 1.6 * row_height <= w.top < cpt.top - tol
            and _DATA_TOKEN_RE.match(w.text)
            and not _LABEL_RE.match(w.text)
            and row[0].x0 - 1 <= w.x0 <= row[-1].x1 + 1
        ]
        line = _ServiceLine(
            page=cpt.page,
            cpt=cpt,
            modifiers=modifiers,
            pointer=pointer,
            charge=charge,
            units=units,
            row_words=row,
            shaded_words=shaded,
        )
        lines.append(line)
        for w in row + shaded:
            claimed.update(w.chars)
    return lines


def _parse_right_of_code(
    right: list[_Word],
) -> tuple[list[_Word], _Word, _Charge, _Word | None] | None:
    """Box 24 cells after the code: 0–4 modifiers, dx pointer, charge, units.
    Modifiers and pointers overlap lexically ("AB" is a valid instance of
    both), so try each modifier count and keep the first full parse."""
    for count in range(0, MAX_MODIFIERS + 1):
        if len(right) < count + 2:
            break
        modifiers = right[:count]
        if not all(_MODIFIER_RE.match(m.text) for m in modifiers):
            break
        pointer = right[count]
        if not _DX_POINTER_RE.match(pointer.text):
            continue
        charge, consumed = _parse_charge(right[count + 1 :])
        if charge is None:
            continue
        rest = right[count + 1 + consumed :]
        # A blank units cell is common ("1" implied); anything else there
        # (EPSDT flag, NPI) is not a units value.
        units = rest[0] if rest and _UNITS_RE.match(rest[0].text) else None
        return modifiers, pointer, charge, units
    return None


def _parse_charge(words: list[_Word]) -> tuple[_Charge | None, int]:
    if not words:
        return None, 0
    head = words[0]
    if _MONEY_SINGLE_RE.match(head.text):
        return _Charge([head], _money_to_cents(head.text), split=False), 1
    if len(words) >= 2 and _MONEY_DOLLARS_RE.match(head.text):
        cents_word = words[1]
        if _MONEY_CENTS_RE.match(cents_word.text) and _adjacent(head, cents_word):
            return (
                _Charge(
                    [head, cents_word],
                    int(head.text.replace("$", "")) * 100 + int(cents_word.text),
                    True,
                ),
                2,
            )
    return None, 0


def _adjacent(a: _Word, b: _Word) -> bool:
    # Dollars and cents sit in neighbouring boxes; a units cell is further away.
    return 0 <= b.x0 - a.x1 <= 3 * a.size


def _money_to_cents(text: str) -> int:
    dollars, cents = text.replace("$", "").replace(",", "").split(".")
    return int(dollars) * 100 + int(cents)


def _units_value(line: _ServiceLine) -> float:
    return float(line.units.text) if line.units is not None else 1.0


def _next_word_right(row: list[_Word], word: _Word) -> _Word | None:
    candidates = [w for w in row if w.x0 > word.x1 - 0.1 and w is not word]
    return min(candidates, key=lambda w: w.x0) if candidates else None


def _validated_value(edit: ClaimEdit) -> str | None:
    """Server-side whitelist for the values that end up drawn on the claim —
    the client picks them, so nothing outside the vocabulary gets through."""
    value = (edit.value or "").strip().upper()
    if edit.kind == "add_modifier":
        return value if _MODIFIER_RE.match(value) else None
    if edit.kind == "change_units":
        return value if _UNITS_RE.match(value) and int(value) >= 1 else None
    if edit.kind == "change_code":
        return value if _CODE_RE.match(value) or _ICD10_RE.match(value) else None
    return None


def _text_width(text: str, size: float) -> float:
    return sum(_HELVETICA_WIDTHS.get(ch, 600) for ch in text) * size / 1000


# --- total (Box 28) ---------------------------------------------------------


def _format_money(cents: int, like: _Charge) -> list[str]:
    dollars, rem = divmod(cents, 100)
    if like.split:
        prefix = "$" if like.words[0].text.startswith("$") else ""
        return [f"{prefix}{dollars}", f"{rem:02d}"]
    sample = like.words[0].text
    body = f"{dollars:,}.{rem:02d}" if "," in sample else f"{dollars}.{rem:02d}"
    return [("$" + body) if sample.startswith("$") else body]


def _update_total(
    pages_words: list[list[_Word]],
    lines: list[_ServiceLine],
    removed: list[_ServiceLine],
    per_page: dict[int, _PageEdits],
    expected_removed: list[_Word],
    expected_added: list[tuple[int, str, float, float]],
) -> bool:
    """Recompute Box 28 after line removals. Only attempted on single-page
    claims (multi-page claims carry per-page or cumulative totals — ambiguous),
    and only when exactly one money token off the service rows equals the old
    total; otherwise the caller tells the user to fix the total by hand."""
    if len(pages_words) != 1:
        return False
    page = 0
    old_total = sum(line.charge.cents for line in lines)
    new_total = old_total - sum(line.charge.cents for line in removed)
    in_rows = {idx for line in lines for w in line.row_words for idx in w.chars}
    words = sorted(
        (w for w in pages_words[page] if w.upright and w.chars[0] not in in_rows),
        key=lambda w: (w.top, w.x0),
    )
    candidates: list[_Charge] = []
    for i in range(len(words)):
        charge, _ = _parse_charge(words[i : i + 2])
        if charge is not None and charge.cents == old_total:
            candidates.append(charge)
    if len(candidates) != 1:
        return False
    total = candidates[0]
    new_text = _format_money(new_total, like=total)
    pe = per_page.setdefault(page, _PageEdits())
    for old_word, text in zip(total.words, new_text, strict=True):
        pe.remove.update(old_word.chars)
        expected_removed.append(old_word)
        # Money is right-aligned in its box: keep the right edge where it was.
        width = _text_width(text, old_word.size)
        x = old_word.x1 - width
        pe.overlays.append(
            _Overlay(
                page,
                x,
                old_word.origin_y,
                old_word.size,
                text,
                color=old_word.color,
                italic=old_word.italic,
            )
        )
        expected_added.append((page, text, x, old_word.origin_y))
    return True


# --- writing ----------------------------------------------------------------

_TEXT_SHOWING = {b"Tj", b"'", b'"', b"TJ"}


def _rewrite(pdf_bytes: bytes, pages: list[_PageText], per_page: dict[int, _PageEdits]) -> bytes:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter(clone_from=reader)
    for page_index, pe in per_page.items():
        page = writer.pages[page_index]
        content = ContentStream(page.get_contents(), writer)
        resources = _resources(page)
        ops = _strip_glyphs(
            content.operations,
            _fonts_in(resources),
            _xobjects_in(resources),
            pe.remove,
            pages[page_index].advances,
        )
        ops = [([], b"q")] + ops + [([], b"Q")] + _overlay_ops(pe.overlays)
        _ensure_overlay_font(page, writer)
        new_content = ContentStream(None, writer)
        new_content.operations = ops
        page.replace_contents(new_content)
        # The rewritten stream is emitted raw; a form export is tens of
        # thousands of operators, so re-compress or the file triples in size.
        page.compress_content_streams()
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def _resources(obj) -> dict:
    res = obj.get("/Resources")
    return res.get_object() if res is not None else {}


def _xobjects_in(resources: dict) -> dict:
    xobjects = resources.get("/XObject")
    return xobjects.get_object() if xobjects is not None else {}


def _fonts_in(resources: dict, inherited: dict[str, int] | None = None) -> dict[str, int]:
    """Font resource name -> bytes per character code. Composite fonts with a
    non-Identity CMap would need the CMap to count codes; refuse those. A form
    XObject may lean on its parent's fonts (non-conforming but common), so the
    parent's map is the fallback."""
    fonts = resources.get("/Font") or {}
    out: dict[str, int] = dict(inherited or {})
    for name, ref in fonts.items():
        font = ref.get_object()
        subtype = font.get("/Subtype")
        if subtype == "/Type0":
            encoding = font.get("/Encoding")
            enc_name = encoding if isinstance(encoding, str) else None
            if enc_name not in ("/Identity-H", "/Identity-V"):
                raise ClaimPatchError("unsupported_pdf", "composite font with CMap encoding")
            out[str(name)] = 2
        else:
            out[str(name)] = 1
    return out


def _form_text_codes(xobject, fonts: dict[str, int], depth: int = 0) -> int:
    """How many character codes pdfminer sees inside a form XObject (and any it
    nests) — text drawn there shifts the page's char numbering by that much."""
    if depth > 8:
        raise ClaimPatchError("unsupported_pdf", "xobject nesting")
    resources = _resources(xobject)
    own_fonts = _fonts_in(resources, inherited=fonts)
    nested = _xobjects_in(resources)
    bytes_per_code = 1
    saved: list[int] = []
    total = 0
    for operands, operator in ContentStream(xobject, None).operations:
        if operator == b"Tf":
            bytes_per_code = own_fonts.get(str(operands[0]), 1)
        elif operator == b"q":
            saved.append(bytes_per_code)
        elif operator == b"Q" and saved:
            bytes_per_code = saved.pop()
        elif operator == b"Do":
            child = nested.get(str(operands[0]))
            child = child.get_object() if child is not None else None
            if child is not None and child.get("/Subtype") == "/Form":
                total += _form_text_codes(child, own_fonts, depth + 1)
        elif operator in _TEXT_SHOWING:
            strings = list(operands[0]) if operator == b"TJ" else [operands[-1]]
            for item in strings:
                if isinstance(item, bytes | str):
                    total += -(-len(_raw_bytes(item)) // bytes_per_code)
    return total


def _strip_glyphs(
    operations,
    fonts: dict[str, int],
    xobjects: dict,
    remove: set[int],
    advances: list[float],
) -> list:
    """Walk the content stream in order, numbering character codes the way
    pdfminer numbers chars, and drop the codes in ``remove`` — each dropped run
    becomes a TJ adjustment of the same advance so nothing else moves. The
    walk must account for exactly the chars pdfminer saw, or the numbering is
    off and the wrong glyphs would go."""
    ops_out: list = []
    char_index = 0
    bytes_per_code = 1
    font_size = 0.0
    char_spacing = 0.0
    word_spacing = 0.0
    hscale = 100.0
    saved: list[tuple[int, float, float, float, float]] = []

    for operands, operator in operations:
        if operator == b"Tf":
            name = str(operands[0])
            if name not in fonts:
                raise ClaimPatchError("unsupported_pdf", "font outside page resources")
            bytes_per_code = fonts[name]
            font_size = float(operands[1])
        elif operator == b"Tc":
            char_spacing = float(operands[0])
        elif operator == b"Tw":
            word_spacing = float(operands[0])
        elif operator == b"Tz":
            hscale = float(operands[0])
        elif operator == b"q":
            saved.append((bytes_per_code, font_size, char_spacing, word_spacing, hscale))
        elif operator == b"Q" and saved:
            bytes_per_code, font_size, char_spacing, word_spacing, hscale = saved.pop()
        elif operator == b"Do":
            # Images carry no text. A form XObject (typically the drawn CMS-1500
            # background) may: pdfminer numbers any text inside it in sequence,
            # so account for those chars — but never edit them, they belong to
            # the form, not the claim data.
            xobject = xobjects.get(str(operands[0]))
            xobject = xobject.get_object() if xobject is not None else None
            if xobject is None:
                raise ClaimPatchError("unsupported_pdf", "xobject outside page resources")
            if xobject.get("/Subtype") == "/Form":
                inside = _form_text_codes(xobject, fonts)
                if any(char_index <= idx < char_index + inside for idx in remove):
                    raise ClaimPatchError("unsupported_pdf", "text inside form xobject")
                char_index += inside

        if operator not in _TEXT_SHOWING:
            ops_out.append((operands, operator))
            continue

        if operator == b'"':
            word_spacing = float(operands[0])
            char_spacing = float(operands[1])
            strings: list = [operands[2]]
        elif operator == b"TJ":
            strings = list(operands[0])
        else:
            strings = [operands[0]]

        touched = False
        new_array: list = []
        for item in strings:
            if not isinstance(item, bytes | str):
                new_array.append(item)  # kerning number inside a TJ array
                continue
            raw = _raw_bytes(item)
            codes = [raw[i : i + bytes_per_code] for i in range(0, len(raw), bytes_per_code)]
            keep = bytearray()
            drop_advance = 0.0
            for code in codes:
                if char_index >= len(advances):
                    raise ClaimPatchError("unsupported_pdf", "more codes than chars")
                if char_index in remove:
                    touched = True
                    if keep:
                        new_array.append(ByteStringObject(bytes(keep)))
                        keep = bytearray()
                    drop_advance += _tj_units(
                        advances[char_index],
                        font_size=font_size,
                        hscale=hscale,
                        char_spacing=char_spacing,
                        word_spacing=(
                            word_spacing if bytes_per_code == 1 and code == b" " else 0.0
                        ),
                    )
                else:
                    if drop_advance:
                        new_array.append(FloatObject(-drop_advance))
                        drop_advance = 0.0
                    keep += code
                char_index += 1
            if keep:
                new_array.append(ByteStringObject(bytes(keep)))
            if drop_advance:
                new_array.append(FloatObject(-drop_advance))

        if not touched:
            ops_out.append((operands, operator))
            continue
        if operator == b"'":
            ops_out.append(([], b"T*"))
        elif operator == b'"':
            ops_out.append(([operands[0]], b"Tw"))
            ops_out.append(([operands[1]], b"Tc"))
            ops_out.append(([], b"T*"))
        ops_out.append(([ArrayObject(new_array)], b"TJ"))

    if char_index != len(advances):
        raise ClaimPatchError("unsupported_pdf", "text outside content stream")
    return ops_out


def _raw_bytes(item) -> bytes:
    if isinstance(item, bytes):
        return bytes(item)
    original = getattr(item, "original_bytes", None)
    if original is not None:
        return bytes(original)
    return str(item).encode("latin-1", errors="strict")


def _overlay_ops(overlays: Iterable[_Overlay]) -> list:
    ops: list = []
    for ov in overlays:
        ops.append(([], b"BT"))
        ops.append(([FloatObject(v) for v in ov.color], _COLOR_OPERATOR[len(ov.color)]))
        font = _OVERLAY_ITALIC_FONT_KEY if ov.italic else _OVERLAY_FONT_KEY
        ops.append(([NameObject(font), FloatObject(ov.size)], b"Tf"))
        ops.append(
            (
                [
                    NumberObject(1),
                    NumberObject(0),
                    NumberObject(0),
                    NumberObject(1),
                    FloatObject(ov.x),
                    FloatObject(ov.y),
                ],
                b"Tm",
            )
        )
        ops.append(([ByteStringObject(ov.text.encode("latin-1"))], b"Tj"))
        ops.append(([], b"ET"))
    return ops


def _ensure_overlay_font(page, writer: PdfWriter) -> None:
    resources = page.get("/Resources")
    if resources is None:
        resources = DictionaryObject()
        page[NameObject("/Resources")] = resources
    resources = resources.get_object()
    fonts = resources.get("/Font")
    if fonts is None:
        fonts = DictionaryObject()
        resources[NameObject("/Font")] = fonts
    fonts = fonts.get_object()
    for key, base in (
        (_OVERLAY_FONT_KEY, "/Helvetica"),
        (_OVERLAY_ITALIC_FONT_KEY, "/Helvetica-Oblique"),
    ):
        if key in fonts:
            continue
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject(base),
                NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
            }
        )
        fonts[NameObject(key)] = writer._add_object(font)


# --- verification -----------------------------------------------------------


def _verify(
    patched: bytes,
    original_pages: list[list[_Word]],
    removed: list[_Word],
    added: list[tuple[int, str, float, float]],
) -> None:
    """Every original word survives at its position except the removed ones;
    every added word appears where we drew it; nothing else. Words are
    compared by (page, text, x0, baseline) with a small tolerance — the
    baseline, because that is what the overlay sets exactly; a glyph box top
    depends on the font's ascent and Helvetica's differs from the original's."""
    actual = [page.words for page in _load_pages(patched)]
    removed_ids = {(w.page, id(w)) for w in removed}
    expected: list[tuple[int, str, float, float]] = [
        (w.page, w.text, w.x0, w.origin_y)
        for page_words in original_pages
        for w in page_words
        if (w.page, id(w)) not in removed_ids
    ]
    expected.extend(added)
    pool = [(w.page, w.text, w.x0, w.origin_y) for page_words in actual for w in page_words]

    unmatched = 0
    for page, text, x0, base in expected:
        hit = None
        for i, (p, t, ax, abase) in enumerate(pool):
            if (
                p == page
                and t == text
                and abs(ax - x0) <= _POSITION_TOLERANCE
                and abs(abase - base) <= _POSITION_TOLERANCE
            ):
                hit = i
                break
        if hit is None:
            unmatched += 1
        else:
            pool.pop(hit)
    if unmatched or pool:
        raise ClaimPatchError("verification_failed", f"missing={unmatched} unexpected={len(pool)}")
