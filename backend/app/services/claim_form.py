"""Fillable (AcroForm) PDFs: read field values with their positions, write new
values back, and produce the text the extraction model sees.

A claim typed into a fillable CMS-1500 template carries its data in widget
annotations, not in the page content stream — pypdf's text extraction sees
nothing, and Textract only sees whatever appearance streams the saving app
left behind. The fields themselves are the best possible input: every value
is labelled and positioned on the standard 612×792 form. So a form is read
here, fed to the row parser in ``claim_patch`` as positioned words, and
edited by rewriting field values (old value gone, appearance regenerated,
file stays fillable).

Field *names* are template-specific (NUCC publishes no fillable form; one
vendor's ``CPT/HCPCS 1`` is another's ``Text242``) and are never the source
of truth — geometry and content are. Names and values are attacker-controlled
strings like any document text: never logged, and fenced before they reach a
prompt (``prompts/text.py``).
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, NameObject, TextStringObject

# Widget /F flag bits (PDF 32000 §12.5.3): 2 = Hidden, 6 = NoView.
_FLAG_HIDDEN = 1 << 1
_FLAG_NOVIEW = 1 << 5
# Field /Ff bits (§12.7.4.3): 25 = Comb (text spread across MaxLen cells).
_FF_COMB = 1 << 24
# A template's field count is a few hundred; anything far beyond is not a claim.
MAX_FIELDS = 2000
_NAME_CLEAN_RE = re.compile(r"[^\w .,#/()'&+-]+")


class FormReadError(ValueError):
    """The PDF is not a usable fillable form. ``code``: no_acroform, xfa,
    no_values, too_many_fields, unreadable. No document content in the message."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass
class FormField:
    """One widget of one field. A field with several widgets (same value shown
    in two places) yields one FormField per widget, sharing ``name``."""

    name: str  # fully qualified field name (dotted)
    kind: str  # text | checkbox | radio | choice | other
    value: str  # "" when empty; checkbox/radio: the on-state name when checked
    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    page_height: float
    align: int = 0  # /Q: 0 left, 1 centre, 2 right
    max_len: int | None = None
    comb: bool = False
    font_size: float = 0.0  # from /DA; 0 = auto-size
    read_only: bool = False

    @property
    def top(self) -> float:
        return self.page_height - self.y1

    @property
    def bottom(self) -> float:
        return self.page_height - self.y0

    @property
    def size(self) -> float:
        """A plausible glyph size: the /DA size, else ~70% of the box height."""
        return self.font_size if self.font_size > 0 else max(4.0, (self.y1 - self.y0) * 0.7)


@dataclass
class FormDocument:
    fields: list[FormField]
    page_count: int
    page_sizes: list[tuple[float, float]] = field(default_factory=list)

    @property
    def values(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for f in self.fields:
            out.setdefault(f.name, f.value)
        return out

    def filled_text_fields(self) -> list[FormField]:
        return [f for f in self.fields if f.kind == "text" and f.value.strip()]


# --- reading ---------------------------------------------------------------


def _inherited(obj, key: str, depth: int = 0):
    """Field attributes inherit up the /Parent chain (§12.7.3.1)."""
    node = obj
    while node is not None and depth < 32:
        if key in node:
            return node[key]
        parent = node.get("/Parent")
        node = parent.get_object() if parent is not None else None
        depth += 1
    return None


def _full_name(obj) -> str:
    parts: list[str] = []
    node = obj
    depth = 0
    while node is not None and depth < 32:
        t = node.get("/T")
        if t is not None:
            parts.append(str(t))
        parent = node.get("/Parent")
        node = parent.get_object() if parent is not None else None
        depth += 1
    return ".".join(reversed(parts))


def _da_font_size(da) -> float:
    # "/Helv 9 Tf 0 g" → 9; "/Helv 0 Tf" → auto.
    if da is None:
        return 0.0
    m = re.search(r"(-?\d+(?:\.\d+)?)\s+Tf", str(da))
    try:
        return float(m.group(1)) if m else 0.0
    except ValueError:
        return 0.0


def _text_value(raw) -> str:
    if raw is None:
        return ""
    if isinstance(raw, list | ArrayObject):
        return " ".join(str(v) for v in raw)
    return str(raw)


def read_form(pdf_bytes: bytes) -> FormDocument:
    """Every visible widget with its resolved value. Raises FormReadError when
    there is no AcroForm, it is XFA, or nothing has been filled in."""
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        root = reader.trailer["/Root"]
        acroform = root.get("/AcroForm")
        acroform = acroform.get_object() if acroform is not None else None
    except Exception:  # noqa: BLE001 — parser messages can quote document bytes
        raise FormReadError("unreadable") from None
    if acroform is None:
        raise FormReadError("no_acroform")
    if "/XFA" in acroform:
        raise FormReadError("xfa")
    fields: list[FormField] = []
    try:
        page_sizes: list[tuple[float, float]] = []
        for page_index, page in enumerate(reader.pages):
            width = float(page.mediabox.width)
            height = float(page.mediabox.height)
            page_sizes.append((width, height))
            for ref in page.get("/Annots") or []:
                annot = ref.get_object()
                if annot.get("/Subtype") != "/Widget":
                    continue
                flags = int(annot.get("/F", 0) or 0)
                if flags & (_FLAG_HIDDEN | _FLAG_NOVIEW):
                    continue
                ft = _inherited(annot, "/FT")
                ff = int(_inherited(annot, "/Ff") or 0)
                raw_value = _inherited(annot, "/V")
                if ft == "/Tx":
                    kind = "text"
                    value = _text_value(raw_value).strip()
                elif ft == "/Btn":
                    kind = "radio" if ff & (1 << 15) else "checkbox"
                    state = annot.get("/AS")
                    value = "" if state is None or state == "/Off" else str(state).lstrip("/")
                elif ft == "/Ch":
                    kind = "choice"
                    value = _text_value(raw_value).strip()
                else:
                    kind = "other"
                    value = ""
                rect = [float(v) for v in annot["/Rect"]]
                x0, x1 = sorted((rect[0], rect[2]))
                y0, y1 = sorted((rect[1], rect[3]))
                max_len = _inherited(annot, "/MaxLen")
                fields.append(
                    FormField(
                        name=_full_name(annot),
                        kind=kind,
                        value=value,
                        page=page_index,
                        x0=x0,
                        y0=y0,
                        x1=x1,
                        y1=y1,
                        page_height=height,
                        align=int(_inherited(annot, "/Q") or 0),
                        max_len=int(max_len) if max_len is not None else None,
                        comb=bool(ff & _FF_COMB),
                        font_size=_da_font_size(_inherited(annot, "/DA") or acroform.get("/DA")),
                        read_only=bool(ff & 1),
                    )
                )
                if len(fields) > MAX_FIELDS:
                    raise FormReadError("too_many_fields")
    except FormReadError:
        raise
    except Exception:  # noqa: BLE001
        raise FormReadError("unreadable") from None
    doc = FormDocument(fields=fields, page_count=len(reader.pages), page_sizes=page_sizes)
    if not doc.filled_text_fields():
        raise FormReadError("no_values")
    return doc


def is_fillable_claim(pdf_bytes: bytes) -> bool:
    try:
        read_form(pdf_bytes)
        return True
    except FormReadError:
        return False


# --- extraction text ---------------------------------------------------------


def clean_label(name: str) -> str:
    """A field name as a label: printable, bounded, template junk left as-is
    (the model copes with "Text242: 99213" next to its neighbours)."""
    return _NAME_CLEAN_RE.sub(" ", name).strip()[:80] or "field"


def form_text(doc: FormDocument) -> str:
    """The filled form as ``label: value`` lines in reading order (top to
    bottom, left to right, page by page), checked boxes as ``label: [X]``.
    Positioned like the paper form, so neighbouring lines are neighbouring
    boxes — the extraction model reads it much like a printed claim."""
    lines: list[str] = [f"[fillable form: {doc.page_count} page(s), field values follow]"]
    ordered = sorted(doc.fields, key=lambda f: (f.page, round(f.top / 6), f.x0))
    for f in ordered:
        if f.kind == "text" and f.value:
            lines.append(f"{clean_label(f.name)}: {f.value}")
        elif f.kind in ("checkbox", "radio") and f.value:
            lines.append(f"{clean_label(f.name)}: [X]")
        elif f.kind == "choice" and f.value:
            lines.append(f"{clean_label(f.name)}: {f.value}")
    return "\n".join(lines)


# --- writing ---------------------------------------------------------------


def _strip_actions(writer: PdfWriter) -> None:
    """Drop JavaScript and automatic actions. Templates ship calculation
    scripts (auto totals); we set totals ourselves, and a script in a file we
    hand back is a risk with no upside."""
    root = writer._root_object
    for key in ("/OpenAction", "/AA"):
        if key in root:
            del root[NameObject(key)]
    names = root.get("/Names")
    if names is not None:
        names = names.get_object()
        if "/JavaScript" in names:
            del names[NameObject("/JavaScript")]
    for page in writer.pages:
        if "/AA" in page:
            del page[NameObject("/AA")]
        for ref in page.get("/Annots") or []:
            annot = ref.get_object()
            for key in ("/AA", "/A"):
                if key in annot:
                    del annot[NameObject(key)]
            parent = annot.get("/Parent")
            depth = 0
            while parent is not None and depth < 32:
                node = parent.get_object()
                if "/AA" in node:
                    del node[NameObject("/AA")]
                parent = node.get("/Parent")
                depth += 1


def _pin_auto_font_size(annot, default_da) -> None:
    """A field whose /DA says ``0 Tf`` leaves the size to the viewer; the
    appearance we regenerate would come out tiny. Pin a size that fits the
    box, the way viewers do, before the value is written."""
    da = _inherited(annot, "/DA") or default_da
    if da is None or _da_font_size(da) > 0:
        return
    rect = [float(v) for v in annot["/Rect"]]
    height = abs(rect[3] - rect[1])
    size = max(6.0, min(10.0, height * 0.62))
    annot[NameObject("/DA")] = TextStringObject(
        re.sub(r"(-?\d+(?:\.\d+)?)\s+Tf", f"{size:.1f} Tf", str(da), count=1)
    )


def write_values(pdf_bytes: bytes, values: dict[str, str], clear_buttons: set[str]) -> bytes:
    """Return the same PDF with the named text fields set to ``values`` and the
    named check boxes turned off. Appearances are regenerated so every viewer
    (and any re-read of ours) shows the new value; NeedAppearances asks the
    viewer to refresh the rest."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter(clone_from=reader)
    acroform = writer._root_object.get("/AcroForm")
    default_da = acroform.get_object().get("/DA") if acroform is not None else None
    for page in writer.pages:
        page_values = {}
        for ref in page.get("/Annots") or []:
            annot = ref.get_object()
            if annot.get("/Subtype") != "/Widget":
                continue
            name = _full_name(annot)
            if name in values:
                page_values[name] = values[name]
                _pin_auto_font_size(annot, default_da)
            if name in clear_buttons and _inherited(annot, "/FT") == "/Btn":
                annot[NameObject("/AS")] = NameObject("/Off")
                target = annot if "/T" in annot else annot.get("/Parent", annot).get_object()
                target[NameObject("/V")] = NameObject("/Off")
        if page_values:
            writer.update_page_form_field_values(page, page_values, auto_regenerate=True)
    writer.set_need_appearances_writer(True)
    _strip_actions(writer)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
