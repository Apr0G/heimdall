"""Best-effort PHI redaction for the training-corpus export.

Removes what can be done reliably in code, with no ML dependency:
  1. every identifier we already captured for the case (initials, member id,
     claim number, provider name/NPI, prior-auth) — exact-string redaction;
  2. formatted PHI — email, SSN, phone, dates, ZIP+4, 6+-digit id runs, URLs;
  3. names in the standard appeal-letter slots (Dear …, Patient/Member Name: …,
     Sincerely, …).
Dates elsewhere are generalized to the year; claim numbers become a salted hash.

IMPORTANT — this is BEST-EFFORT, not a certified HIPAA Safe Harbor / Expert
Determination de-identification. We only stored patient *initials*, so a full
patient name that appears free-floating in the letter text (not in a known slot)
can still slip through. Before treating the output as non-PHI outside your BAA
boundary, run it through a dedicated PHI NER tool (e.g. Microsoft Presidio) or an
expert review.
"""

import hashlib
import re
from datetime import date

# Extraction fields that carry no patient identifier — safe to export verbatim.
SAFE_EXTRACTION_FIELDS = {
    "payer_name",
    "plan_type",
    "billed_amount_cents",
    "denied_amount_cents",
    "carc_codes",
    "rarc_codes",
    "group_codes",
    "cpt_codes",
    "icd10_codes",
    "modifiers",
    "pos_codes",
    "confidence",
}

_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_URL = re.compile(r"https?://\S+")
_ZIP4 = re.compile(r"\b\d{5}-\d{4}\b")
_PHONE = re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)")
_DATE = re.compile(
    r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"
    r"|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4})\b",
    re.IGNORECASE,
)
_LONGNUM = re.compile(r"(?<!\d)\d{6,}(?!\d)")  # member ids / MRNs / claim numbers
# Names that follow a standard letter cue (not "Re:", which is a subject line).
# (?i:...) scopes case-insensitivity to the CUE only; the captured name must still
# start uppercase, so we don't redact a lowercase continuation like "Dear sir".
_NAME_SLOT = re.compile(
    r"(?P<cue>(?i:\b(?:Dear|Attn|Attention|Sincerely|Regards|Patient(?:'s)?(?:\s+name)?"
    r"|Member(?:\s+name)?|Name|Insured|Subscriber)\b)[:,]?\s+)"
    r"(?P<name>[A-Z][a-zA-Z'.-]+(?:\s+[A-Z][a-zA-Z'.-]+){0,3})"
)


def hash_ref(value: str) -> str:
    """Stable, non-reversible reference so records stay linkable without the id."""
    return "ref_" + hashlib.sha256(value.strip().lower().encode()).hexdigest()[:12]


def deid_year(value: date | None) -> int | None:
    return value.year if value else None


# --- Optional NER layer (Presidio) -------------------------------------------
# Catches names/locations that appear free-floating in prose (not in a known slot
# and never captured structurally) — the residual gap the regex passes can't close.
# Lazy + optional: if Presidio isn't importable we fall back to regex-only. It is
# installed at runtime in the export task (export-corpus workflow), never baked
# into the app image.
# NER handles ONLY what regex can't — names and places. Formatted PHI (SSN, phone,
# email, dates, id runs) is left to the precise regex passes below; Presidio's
# DATE_TIME/number recognizers over-match and would clobber billing codes
# (e.g. CPT 99213 -> [DATE], ICD J45 -> [REDACTED]).
_NER_ENTITIES = ["PERSON", "LOCATION"]
_NER_TOKEN = {
    "PERSON": "[NAME]",
    "LOCATION": "[LOCATION]",
}
# None = not yet tried; () = tried but unavailable; (analyzer, anonymizer) = ready.
_ner_engines: object = None


def _ner_engines_or_none():
    global _ner_engines
    if _ner_engines is not None:
        return _ner_engines or None
    try:
        from presidio_analyzer import AnalyzerEngine
        from presidio_analyzer.nlp_engine import NlpEngineProvider
        from presidio_anonymizer import AnonymizerEngine
    except ImportError:
        _ner_engines = ()
        return None
    nlp_engine = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
        }
    ).create_engine()
    _ner_engines = (
        AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"]),
        AnonymizerEngine(),
    )
    return _ner_engines


def _ner_redact(text: str) -> str:
    engines = _ner_engines_or_none()
    if not engines:
        return text
    from presidio_anonymizer.entities import OperatorConfig

    analyzer, anonymizer = engines
    results = analyzer.analyze(text=text, language="en", entities=_NER_ENTITIES)
    if not results:
        return text
    operators = {
        ent: OperatorConfig("replace", {"new_value": tok}) for ent, tok in _NER_TOKEN.items()
    }
    operators["DEFAULT"] = OperatorConfig("replace", {"new_value": "[REDACTED]"})
    return anonymizer.anonymize(text=text, analyzer_results=results, operators=operators).text


def redact_text(text: str | None, known: list, use_ner: bool = False) -> str | None:
    """Redact captured identifiers + formatted PHI + letter-slot names from text.

    With use_ner=True, first run a Presidio NER pass (names/locations anywhere in
    the prose), then the deterministic passes below as belt-and-suspenders.
    """
    if not text:
        return text
    out = text
    if use_ner:
        out = _ner_redact(out)
    # 1) Exact known values first — longest first so a substring can't pre-empt a
    #    longer match; word-boundary lookarounds avoid clipping inside real words.
    seen = {str(k).strip() for k in known if k and len(str(k).strip()) >= 2}
    for val in sorted(seen, key=len, reverse=True):
        out = re.sub(rf"(?<!\w){re.escape(val)}(?!\w)", "[REDACTED]", out, flags=re.IGNORECASE)
    # 2) Formatted identifiers.
    out = _EMAIL.sub("[EMAIL]", out)
    out = _SSN.sub("[SSN]", out)
    out = _URL.sub("[URL]", out)
    out = _ZIP4.sub("[ZIP]", out)
    out = _PHONE.sub("[PHONE]", out)
    out = _DATE.sub("[DATE]", out)
    out = _LONGNUM.sub("[ID]", out)
    # 3) Names in standard letter slots.
    out = _NAME_SLOT.sub(lambda m: m.group("cue") + "[NAME]", out)
    return out
