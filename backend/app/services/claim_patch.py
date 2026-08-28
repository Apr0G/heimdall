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

from app.services import claim_form

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


CHARGE_CHOICES = ("scale", "keep")


@dataclass(frozen=True)
class ClaimEdit:
    kind: str
    target: str  # the CPT/HCPCS on the line the edit applies to
    value: str | None = None  # new modifier / units / code; unused for remove_line
    # change_units only: "scale" rewrites 24F as price-per-unit × new units
    # (how billing systems build the charge); "keep" leaves the charge when the
    # units were a data-entry slip. Only the practice knows which — see the UI.
    charge: str = "scale"


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
    # Advisory for an applied edit: check_dx_pointers after a Box 21 removal,
    # charge_not_scaled when the per-unit price didn't divide to the cent.
    note: str | None = None
    # change_units with charge="scale": the line charge before and after (cents).
    charge_before_cents: int | None = None
    charge_after_cents: int | None = None


@dataclass
class PatchResult:
    pdf: bytes
    results: list[EditResult]
    # None when no charge changed; False when it changed but the Box 28 total
    # could not be located unambiguously (caller tells the user to fix it).
    total_updated: bool | None
    pages_changed: int
    format: str = "text"  # "text" (glyph surgery) | "form" (field values)


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
    # Fillable forms: the field this token belongs to and its index among the
    # value's whitespace-separated tokens.
    field: object = None
    token: int = 0

    @property
    def upright(self) -> bool:
        return self.top < self.bottom


@dataclass
class _PageText:
    words: list[_Word]
    # Per char (stream order, spaces included): glyph advance in thousandths
    # of text space — what a TJ adjustment needs to reproduce it exactly.
    advances: list[float]
    # Per char: (text, x0, baseline) — what verification compares, so word
    # grouping (which depends on gaps the extractor sees) plays no part.
    chars: list[tuple[str, float, float]]


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
    word: object = None  # the word it replaced, if any (dropped if that word is removed)
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
    be applied come back as EditResult(applied=False, reason=...).

    A fillable form (values in AcroForm fields) is edited by rewriting field
    values; anything else by glyph surgery on the content stream. Both go
    through the same row parser and the same edit policy."""
    backend: _Backend
    try:
        form = claim_form.read_form(pdf_bytes)
    except claim_form.FormReadError as exc:
        if exc.code == "xfa":
            raise ClaimPatchError("unsupported_pdf", "xfa form") from None
        backend = _GlyphBackend(pdf_bytes)
    else:
        backend = _FormBackend(pdf_bytes, form)

    pages_words = backend.pages_words
    lines = [line for page_words in pages_words for line in _find_service_lines(page_words)]
    if not lines:
        raise ClaimPatchError("no_service_lines")
    backend.lines = lines

    results: list[EditResult] = []
    for edit in edits:
        if edit.kind not in EDIT_KINDS:
            results.append(EditResult(edit, False, "unsupported_kind"))
            continue
        target = edit.target.strip().upper()
        matches = [
            line for line in lines if line.cpt.text == target and line not in backend.removed_lines
        ]
        if matches:
            results.append(_apply_to_lines(edit, matches, backend))
            continue
        dx_words = _find_dx(pages_words, lines, target)
        if dx_words is None or not dx_words:
            results.append(EditResult(edit, False, "line_not_found"))
        elif len(dx_words) > 1:
            results.append(EditResult(edit, False, "ambiguous_line"))
        else:
            results.append(_apply_to_dx(edit, dx_words[0], pages_words, backend))

    total_updated: bool | None = None
    if backend.removed_lines or backend.charges:
        total_updated = _update_total(pages_words, lines, backend)

    if not backend.changed:
        return PatchResult(
            pdf=pdf_bytes,
            results=results,
            total_updated=None,
            pages_changed=0,
            format=backend.format,
        )
    patched = backend.finalize()
    return PatchResult(
        pdf=patched,
        results=results,
        total_updated=total_updated,
        pages_changed=backend.pages_changed,
        format=backend.format,
    )


# --- backends ---------------------------------------------------------------


class _Backend:
    """What an edit needs from the document: replace a token, add a modifier,
    fill a blank units cell, rewrite an amount, remove a line, and finally
    write + verify. Room checks and the mechanics differ per backend; the
    edit policy above does not."""

    format: str
    pages_words: list[list[_Word]]

    def __init__(self) -> None:
        self.lines: list[_ServiceLine] = []
        self.removed_lines: list[_ServiceLine] = []
        # Current charge per line (id(line) -> cents) after scaling, for Box 28.
        self.charges: dict[int, int] = {}

    def current_cents(self, line: _ServiceLine) -> int:
        return self.charges.get(id(line), line.charge.cents)

    # -- operations (return a skip reason, or None when done) --
    def replace(self, word: _Word, text: str, *, row: list[_Word], line: _ServiceLine | None):
        raise NotImplementedError

    def add_modifier(self, line: _ServiceLine, value: str) -> str | None:
        raise NotImplementedError

    def set_blank_units(self, line: _ServiceLine, value: str) -> str | None:
        raise NotImplementedError

    def set_money(self, charge: _Charge, texts: list[str], *, row: list[_Word], line) -> str | None:
        raise NotImplementedError

    def remove_word(self, word: _Word) -> None:
        raise NotImplementedError

    def remove_line(self, line: _ServiceLine) -> None:
        raise NotImplementedError

    @property
    def changed(self) -> bool:
        raise NotImplementedError

    @property
    def pages_changed(self) -> int:
        raise NotImplementedError

    def finalize(self) -> bytes:
        raise NotImplementedError


class _GlyphBackend(_Backend):
    """Born-digital text: remove the glyph codes of a token from the content
    stream (keeping every other glyph in place) and draw the replacement in
    Helvetica at the old origin, matching colour and slant."""

    format = "text"

    def __init__(self, pdf_bytes: bytes) -> None:
        super().__init__()
        self.pdf_bytes = pdf_bytes
        self.pages = _load_pages(pdf_bytes)
        self.pages_words = [page.words for page in self.pages]
        self.per_page: dict[int, _PageEdits] = {}

    def _page(self, page: int) -> _PageEdits:
        return self.per_page.setdefault(page, _PageEdits())

    def remove_word(self, word: _Word) -> None:
        pe = self._page(word.page)
        pe.remove.update(word.chars)
        # A value drawn in this word's place earlier goes with it: "change it,
        # then remove it" ends with nothing there, as on a form.
        pe.overlays = [o for o in pe.overlays if o.word is not word]

    def _draw(
        self,
        page: int,
        x: float,
        y: float,
        size: float,
        text: str,
        *,
        like: _Word,
        line=None,
        replacing: _Word | None = None,
    ):
        self._page(page).overlays.append(
            _Overlay(
                page,
                x,
                y,
                size,
                text,
                line=line,
                word=replacing,
                color=like.color,
                italic=like.italic,
            )
        )

    def replace(self, word: _Word, text: str, *, row: list[_Word], line=None) -> str | None:
        width = _text_width(text, word.size)
        right_neighbour = _next_word_right(row, word)
        limit = right_neighbour.x0 - 1 if right_neighbour else word.x1 + width
        if word.origin_x + width > limit:
            return "no_room"
        self.remove_word(word)
        self._draw(
            word.page,
            word.origin_x,
            word.origin_y,
            word.size,
            text,
            like=word,
            line=line,
            replacing=word,
        )
        return None

    def add_modifier(self, line: _ServiceLine, value: str) -> str | None:
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
        self._draw(line.page, x, anchor.origin_y, anchor.size, value, like=anchor, line=line)
        return None

    def set_blank_units(self, line: _ServiceLine, value: str) -> str | None:
        # Where 24G starts: from a sibling line that prints a count, else at
        # the fixed distance the form keeps between the charge box and the
        # units box (a blank 24G on every line is the common case).
        xs = [ln.units.origin_x for ln in self.lines if ln.page == line.page and ln.units]
        if xs:
            column_x = min(xs)
        else:
            last_charge = line.charge.words[-1]
            column_x = last_charge.x1 + 1.6 * last_charge.size
        anchor = line.cpt
        after = [w for w in line.row_words if w.x0 > column_x]
        limit = after[0].x0 - 1 if after else column_x + _text_width(value, anchor.size)
        if column_x + _text_width(value, anchor.size) > limit:
            return "no_room"
        self._draw(line.page, column_x, anchor.origin_y, anchor.size, value, like=anchor, line=line)
        return None

    def set_money(self, charge: _Charge, texts: list[str], *, row: list[_Word], line=None):
        dollars = charge.words[0]
        x = dollars.x1 - _text_width(texts[0], dollars.size)  # money is right-aligned
        tol = max(2.0, 0.45 * dollars.size)
        left = [w for w in row if w.x1 <= dollars.x0 + 0.1 and abs(w.top - dollars.top) <= tol]
        if left and x < max(w.x1 for w in left) + 1:
            return "no_room"
        for word in charge.words:
            self.remove_word(word)
        # Split money ("13" "45") is one printed string with a space glyph
        # between the halves; the extractor splits words on whitespace in
        # stream order, so the replacement carries a space too — dollars
        # right-aligned where they were, cents left-aligned where they were.
        self._draw(
            dollars.page, x, dollars.origin_y, dollars.size, texts[0], like=dollars, line=line
        )
        if charge.split:
            cents = charge.words[1]
            self._draw(
                dollars.page,
                dollars.x1,
                dollars.origin_y,
                dollars.size,
                " ",
                like=dollars,
                line=line,
            )
            self._draw(
                cents.page,
                cents.origin_x,
                cents.origin_y,
                cents.size,
                texts[1],
                like=cents,
                line=line,
            )
        return None

    def remove_line(self, line: _ServiceLine) -> None:
        """Take every word of the line — and anything an earlier edit drew on
        it, or a changed code / added modifier would float on the blank row."""
        for word in line.row_words + line.shaded_words:
            self.remove_word(word)
        pe = self._page(line.page)
        pe.overlays = [o for o in pe.overlays if o.line is not line]
        self.removed_lines.append(line)

    @property
    def changed(self) -> bool:
        return any(pe.remove or pe.overlays for pe in self.per_page.values())

    @property
    def pages_changed(self) -> int:
        return sum(1 for pe in self.per_page.values() if pe.remove or pe.overlays)

    def finalize(self) -> bytes:
        per_page = {k: v for k, v in self.per_page.items() if v.remove or v.overlays}
        patched = _rewrite(self.pdf_bytes, self.pages, per_page)
        _verify(patched, self.pages, per_page)
        return patched


class _FormBackend(_Backend):
    """Fillable form: every token is part of a field value; an edit rewrites
    that field's value (old value gone, appearance regenerated), a removal
    clears every field in the row, and the result is verified by reading the
    fields back."""

    format = "form"

    def __init__(self, pdf_bytes: bytes, form: claim_form.FormDocument) -> None:
        super().__init__()
        self.pdf_bytes = pdf_bytes
        self.form = form
        self.original: dict[str, str] = form.values
        self.values: dict[str, str] = {}  # pending field value changes
        self.clear_buttons: set[str] = set()
        self.touched_pages: set[int] = set()
        self.pages_words = self._words()
        for page_index in range(form.page_count):
            for f in form.fields:
                if f.page == page_index and f.kind == "text":
                    break

    # -- reading --
    def _words(self) -> list[list[_Word]]:
        pages: list[list[_Word]] = [[] for _ in range(self.form.page_count)]
        counter = 0
        for f in self.form.fields:
            if f.kind != "text" or not f.value:
                continue
            tokens = f.value.split()
            if not tokens:
                continue
            size = f.size
            char_w = size * 0.55
            est = sum(len(t) for t in tokens) * char_w + (len(tokens) - 1) * char_w
            box_w = f.x1 - f.x0
            if f.align == 2:
                cursor = max(f.x0, f.x1 - est - 1)
            elif f.align == 1:
                cursor = max(f.x0, f.x0 + (box_w - est) / 2)
            else:
                cursor = f.x0 + 1
            for token_index, token in enumerate(tokens):
                w = len(token) * char_w
                counter += 1
                pages[f.page].append(
                    _Word(
                        page=f.page,
                        text=token,
                        x0=cursor,
                        x1=min(cursor + w, f.x1),
                        top=f.top,
                        bottom=f.bottom,
                        size=size,
                        origin_x=cursor,
                        origin_y=f.y0 + 2,
                        chars=[counter],
                        field=f,
                        token=token_index,
                    )
                )
                cursor += w + char_w
        return pages

    # -- helpers --
    def _current(self, f: claim_form.FormField) -> str:
        return self.values.get(f.name, self.original.get(f.name, f.value))

    def _set(self, f: claim_form.FormField, text: str) -> str | None:
        if f.read_only:
            return "no_room"
        if f.max_len is not None and len(text) > f.max_len:
            return "no_room"
        self.values[f.name] = text
        self.touched_pages.add(f.page)
        return None

    def _set_token(self, word: _Word, text: str | None) -> str | None:
        """Rewrite one whitespace-separated token of a field's value; None
        deletes it."""
        f = word.field
        assert isinstance(f, claim_form.FormField)
        tokens = self._current(f).split()
        if word.token >= len(tokens):
            return "line_not_found"
        if text is None:
            del tokens[word.token]
        else:
            tokens[word.token] = text
        return self._set(f, " ".join(tokens))

    def _band(self, line: _ServiceLine) -> tuple[float, float]:
        row_h = max(line.cpt.bottom - line.cpt.top, 8.0)
        # The data row plus the shaded half-row above it (24J qualifier etc.).
        return line.cpt.top - 1.1 * row_h, line.cpt.bottom + 0.3 * row_h

    def _fields_in_band(self, line: _ServiceLine) -> list[claim_form.FormField]:
        lo, hi = self._band(line)
        out = []
        for f in self.form.fields:
            if f.page != line.page:
                continue
            centre = (f.top + f.bottom) / 2
            if lo <= centre <= hi:
                out.append(f)
        return sorted(out, key=lambda f: f.x0)

    def _empty_text_fields(self, line: _ServiceLine) -> list[claim_form.FormField]:
        return [
            f
            for f in self._fields_in_band(line)
            if f.kind == "text" and not self._current(f).strip() and not f.read_only
        ]

    # -- operations --
    def replace(self, word: _Word, text: str, *, row: list[_Word], line=None) -> str | None:
        return self._set_token(word, text)

    def add_modifier(self, line: _ServiceLine, value: str) -> str | None:
        lo_x = line.cpt.x1 - 0.1
        hi_x = line.pointer.x0 + 0.1
        slots = [f for f in self._empty_text_fields(line) if lo_x <= f.x0 and f.x1 <= hi_x]
        if line.modifiers:
            slots = [f for f in slots if f.x0 >= line.modifiers[-1].x1 - 0.1]
        if slots:
            return self._set(slots[0], value)
        if line.modifiers:
            # A template with one combined modifier field: append to it.
            last = line.modifiers[-1].field
            assert isinstance(last, claim_form.FormField)
            joined = " ".join([*self._current(last).split(), value])
            return self._set(last, joined)
        return "no_room"

    def set_blank_units(self, line: _ServiceLine, value: str) -> str | None:
        after_x = line.charge.words[-1].x1 - 0.1
        nxt = _next_word_right(line.row_words, line.charge.words[-1])
        slots = [
            f
            for f in self._empty_text_fields(line)
            if f.x0 >= after_x and (nxt is None or f.x1 <= nxt.x0 + 0.1)
        ]
        if not slots:
            return "no_units_cell"
        return self._set(slots[0], value)

    def set_money(self, charge: _Charge, texts: list[str], *, row: list[_Word], line=None):
        if charge.split and charge.words[0].field is charge.words[1].field:
            # Both halves live in one field ("22 00"): rewrite it whole.
            f = charge.words[0].field
            assert isinstance(f, claim_form.FormField)
            tokens = self._current(f).split()
            a, b = charge.words[0].token, charge.words[1].token
            if b >= len(tokens):
                return "line_not_found"
            tokens[a], tokens[b] = texts[0], texts[1]
            return self._set(f, " ".join(tokens))
        for word, text in zip(charge.words, texts, strict=True):
            reason = self._set_token(word, text)
            if reason is not None:
                return reason
        return None

    def remove_word(self, word: _Word) -> None:
        self._set_token(word, None)

    def remove_line(self, line: _ServiceLine) -> None:
        for f in self._fields_in_band(line):
            if f.kind == "text":
                self.values[f.name] = ""
            elif f.kind in ("checkbox", "radio"):
                self.clear_buttons.add(f.name)
            self.touched_pages.add(f.page)
        self.removed_lines.append(line)

    @property
    def changed(self) -> bool:
        return any(self.values.get(k) != self.original.get(k) for k in self.values) or bool(
            self.clear_buttons
        )

    @property
    def pages_changed(self) -> int:
        return len(self.touched_pages)

    def finalize(self) -> bytes:
        changes = {k: v for k, v in self.values.items() if v != self.original.get(k)}
        patched = claim_form.write_values(self.pdf_bytes, changes, self.clear_buttons)
        try:
            after = claim_form.read_form(patched)
        except claim_form.FormReadError as exc:
            raise ClaimPatchError("verification_failed", exc.code) from None
        expected = dict(self.original)
        expected.update(changes)
        for name in self.clear_buttons:
            expected[name] = ""
        actual = after.values
        if len(after.fields) != len(self.form.fields):
            raise ClaimPatchError("verification_failed", "field count")
        mismatched = sum(1 for name, value in expected.items() if actual.get(name, "") != value)
        still_on = sum(1 for name in self.clear_buttons if actual.get(name, ""))
        if mismatched or still_on:
            raise ClaimPatchError("verification_failed", f"fields={mismatched} buttons={still_on}")
        return patched


# --- edit policy (backend-agnostic) ------------------------------------------


def _apply_to_lines(edit: ClaimEdit, lines: list[_ServiceLine], ctx: _Backend) -> EditResult:
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
    note: str | None = None
    before_cents = after_cents = 0
    for line in candidates:
        reason = _apply_to_line(edit, value, line, ctx)
        if reason is not None:
            reasons.append(reason)
            continue
        applied += 1
        if edit.kind == "change_units" and edit.charge == "scale":
            scaled = _scale_charge(line, value, ctx)
            if scaled is None:
                note = "charge_not_scaled"
            else:
                before_cents += ctx.current_cents(line)
                after_cents += scaled
                ctx.charges[id(line)] = scaled
    if applied == 0:
        return EditResult(edit, False, reasons[0] if reasons else "line_not_found")
    if edit.kind == "change_units" and edit.charge == "scale" and note is None:
        return EditResult(
            edit,
            True,
            applied_lines=applied,
            charge_before_cents=before_cents,
            charge_after_cents=after_cents,
        )
    return EditResult(edit, True, applied_lines=applied, note=note)


def _scale_charge(line: _ServiceLine, new_units: str, ctx: _Backend) -> int | None:
    """Rewrite 24F as (charge ÷ old units) × new units. Only when the per-unit
    price is a whole number of cents — otherwise the charge was not built from
    these units and scaling would invent an amount. Returns the new cents."""
    old_units = _units_value(line)
    cents = ctx.current_cents(line)
    if old_units <= 0 or old_units != int(old_units) or cents * int(new_units) % int(old_units):
        return None
    new_cents = cents * int(new_units) // int(old_units)
    if new_cents == cents:
        return cents
    texts = _format_money(new_cents, like=line.charge)
    if ctx.set_money(line.charge, texts, row=line.row_words, line=line) is not None:
        return None
    return new_cents


def _apply_to_line(edit: ClaimEdit, value: str, line: _ServiceLine, ctx: _Backend) -> str | None:
    """Apply to one line; return a skip reason or None when applied."""
    if edit.kind == "add_modifier":
        if len(line.modifiers) >= MAX_MODIFIERS:
            return "modifier_slots_full"
        return ctx.add_modifier(line, value)
    if edit.kind == "change_units" and line.units is None:
        # Blank 24G (one unit implied): write the new count in the units column.
        return ctx.set_blank_units(line, value)
    old = line.units if edit.kind == "change_units" else line.cpt
    assert old is not None
    if old.text == value:
        return "already_present"
    return ctx.replace(old, value, row=line.row_words, line=line)


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
    edit: ClaimEdit, word: _Word, pages_words: list[list[_Word]], ctx: _Backend
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
    reason = ctx.replace(word, value, row=row, line=None)
    if reason is not None:
        return EditResult(edit, False, reason)
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
                chars = [(c["text"], float(c["x0"]), float(c["matrix"][5])) for c in page.chars]
                pages.append(_PageText(words=words, advances=advances, chars=chars))
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


def _update_total(pages_words: list[list[_Word]], lines: list[_ServiceLine], ctx: _Backend) -> bool:
    """Recompute Box 28 after removals or scaled charges. Only attempted on
    single-page claims (multi-page claims carry per-page or cumulative totals —
    ambiguous), and only when exactly one money token off the service rows
    equals the old total; otherwise the caller tells the user to fix it."""
    if len(pages_words) != 1:
        return False
    page = 0
    old_total = sum(line.charge.cents for line in lines)
    new_total = sum(ctx.current_cents(line) for line in lines if line not in ctx.removed_lines)
    if new_total == old_total:
        return True
    in_rows = {idx for line in lines for w in line.row_words for idx in w.chars}
    # Row-banded sort: dollars and cents boxes can differ by a fraction of a
    # point vertically, and a plain (top, x) sort would interleave neighbours.
    words = sorted(
        (w for w in pages_words[page] if w.upright and w.chars[0] not in in_rows),
        key=lambda w: (round(w.top / 3), w.x0),
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
    return ctx.set_money(total, new_text, row=words, line=None) is None


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


def _verify(patched: bytes, original: list[_PageText], per_page: dict[int, _PageEdits]) -> None:
    """Every original character survives at its position except the removed
    ones; every character we drew appears where we put it; nothing else.
    Compared per character by (page, text, x0, baseline) — the baseline
    because that is what the overlay sets exactly, and characters rather than
    words because word grouping depends on gaps the extractor happens to see."""
    actual = _load_pages(patched)
    if len(actual) != len(original):
        raise ClaimPatchError("verification_failed", "page count")
    unmatched = 0
    unexpected = 0
    for page_index, page in enumerate(original):
        pe = per_page.get(page_index)
        removed = pe.remove if pe else set()
        expected = [
            (text, x0, base)
            for idx, (text, x0, base) in enumerate(page.chars)
            if idx not in removed and text.strip()
        ]
        for ov in pe.overlays if pe else []:
            x = ov.x
            for ch in ov.text:
                if ch.strip():  # a drawn space is a separator, not a glyph to find
                    expected.append((ch, x, ov.y))
                x += _text_width(ch, ov.size)
        pool = [(text, x0, base) for text, x0, base in actual[page_index].chars if text.strip()]
        # Bucket by text so matching stays linear-ish on a 40k-char page.
        buckets: dict[str, list[tuple[float, float]]] = {}
        for text, x0, base in pool:
            buckets.setdefault(text, []).append((x0, base))
        for text, x0, base in expected:
            candidates = buckets.get(text, [])
            hit = next(
                (
                    i
                    for i, (ax, abase) in enumerate(candidates)
                    if abs(ax - x0) <= _POSITION_TOLERANCE
                    and abs(abase - base) <= _POSITION_TOLERANCE
                ),
                None,
            )
            if hit is None:
                unmatched += 1
            else:
                candidates.pop(hit)
        unexpected += sum(len(v) for v in buckets.values())
    if unmatched or unexpected:
        raise ClaimPatchError("verification_failed", f"missing={unmatched} unexpected={unexpected}")
