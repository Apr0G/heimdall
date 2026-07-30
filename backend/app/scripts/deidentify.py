"""PHI redaction for the training-corpus export — implements HIPAA Safe Harbor
(§164.514(b)(2)) in code across the 18 identifier categories:

  names ............... Presidio NER (PERSON) + letter-slot cues + captured values
  geography < state ... Presidio NER (LOCATION) + street-address + ZIP regex
  all dates (yr only).. dates generalized to year (structured) / regex (free text)
  ages > 89 ........... aggregated to "90+"
  phone / fax ......... regex          email ............... regex
  SSN ................. regex          MRN/account/plan #s . 6+-digit run + captured
  certificate/license . captured (NPI) + Presidio           URL / IP ... regex
  vehicle/device/bio/photo ............ N/A for text; long-number run catches serials

Formatted identifiers are handled by precise regex (so 5-digit CPT codes and
ICD codes survive as training signal); names/places by NER (recall). Every run
also emits a residual scan (scan_residual) for the validation report.

Safe Harbor also requires "no actual knowledge" that the residual data could
identify someone — that is a documented human review, which the export's
validation report is built to support. Treat the output as PHI until that review
is signed off.
"""

import os
import re
from datetime import date

from app.core import hashing

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

_MONTHS = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?"

_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_URL = re.compile(r"\bhttps?://\S+|\bwww\.[^\s,;]+")
_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_PHONE = re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)")
_ZIP4 = re.compile(r"\b\d{5}-\d{4}\b")
# "CA 90210" -> keep the state (allowed at state level), drop the ZIP.
_STATE_ZIP = re.compile(r"\b([A-Z]{2})\s+\d{5}(?:-\d{4})?\b")
_STREET = re.compile(
    r"\b\d{1,6}\s+(?:[A-Z][A-Za-z.'-]+\s+){0,4}"
    r"(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct"
    r"|Way|Place|Pl|Terrace|Ter|Circle|Cir|Highway|Hwy|Parkway|Pkwy)\.?"
    r"(?:\s+(?:Suite|Ste|Apt|Unit|Floor|Fl|#)\.?\s*\w+)?",
    re.IGNORECASE,
)
_DATE = re.compile(
    r"\b(?:"
    r"\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}"  # 03/15/1980
    r"|\d{4}-\d{1,2}-\d{1,2}"  # 1980-03-15
    rf"|{_MONTHS}\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}"  # March 15, 1980
    rf"|\d{{1,2}}(?:st|nd|rd|th)?\s+(?:of\s+)?{_MONTHS},?\s+\d{{4}}"  # 15 March 1980
    r")\b",
    re.IGNORECASE,
)
_LONGNUM = re.compile(r"(?<!\d)\d{6,}(?!\d)")  # member ids / MRNs / claim / account
# Medicare Beneficiary Identifier (MBI): 11 chars, position-constrained, optionally
# dash-separated as 4-3-4 — e.g. 1EG4-TE5-MK73. Never all-numeric, so it slips past
# _LONGNUM entirely.
_MBI = re.compile(
    r"\b[1-9][A-Z][A-Y0-9]\d-?[A-Z][A-Y0-9]\d-?[A-Z]{2}\d{2}\b",
    re.IGNORECASE,
)
# Commercial payer member IDs: a mixed alphanumeric run of 8+ characters containing
# at least one letter AND at least one digit (W1A2B3C4D, ABC123456789). Deliberately
# 8+ and mixed so CPT (5 digits), ICD-10 (A00.0), HCPCS (J1234), CARC (CO-197) and
# NPIs (caught by _LONGNUM) all survive as training signal.
_MEMBER_ALNUM = re.compile(
    r"\b(?=[A-Z0-9]{8,20}\b)(?=[A-Z0-9]*[A-Z])(?=[A-Z0-9]*\d)[A-Z0-9]{8,20}\b"
)
# Authorization / reference numbers (AUTH-555, CASE-1234). 4+ letter prefix so
# 2-3 letter form/adjustment codes survive (CO-197, UB-04, CMS-1500).
_AUTH = re.compile(r"\b[A-Z]{4,}-\d{2,}[A-Z0-9-]*\b")
# Ages: capture the number, aggregate to "90+" only when >= 90 (Safe Harbor).
_AGE = re.compile(
    r"\b(\d{2,3})(\s*-?\s*(?:years?|yrs?|y[/.]?o|yo)\b(?:\s*old)?)"
    r"|(\baged?\s*[:=]?\s*)(\d{2,3})\b",
    re.IGNORECASE,
)
# Names that follow a standard letter cue (not "Re:", which is a subject line).
# (?i:...) scopes case-insensitivity to the CUE only; the captured name must still
# start uppercase, so we don't redact a lowercase continuation like "Dear sir".
_NAME_SLOT = re.compile(
    r"(?P<cue>(?i:\b(?:Dear|Attn|Attention|Sincerely|Regards|Patient(?:'s)?(?:\s+name)?"
    r"|Member(?:\s+name)?|Name|Insured|Subscriber)\b)[:,]?\s+)"
    r"(?P<name>[A-Z][a-zA-Z'.-]+(?:\s+[A-Z][a-zA-Z'.-]+){0,3})"
)
# Capitalized bigram — a candidate name that may have slipped through, for QA only.
# [ \t] (not \s) so a candidate never spans a line break.
_CANDIDATE_NAME = re.compile(r"\b[A-Z][a-z]{1,}[ \t]+[A-Z][a-z]{1,}\b")
# Billing/diagnosis code shapes. NER sometimes mis-tags these as a PERSON (e.g.
# ICD-10 "I48.91"); we keep them — they're training signal, not PHI, and a code
# never contains a real name. Used to filter NER detections.
_CODE = re.compile(
    r"[A-Z]\d[0-9A-Z](?:\.[A-Z0-9]{1,4})?"  # ICD-10-CM: I48.91, M23.205, S72.001A
    r"|\d{5}"  # CPT: 93306
    r"|[A-Z]\d{4}"  # HCPCS Level II: J1234
    r"|[A-Z]{1,3}-\d{1,3}"  # CARC / group code: CO-197
    r"|(?:MA|[MN])\d{1,3}"  # RARC: N115, M76, MA13
)


def hash_ref(value: str) -> str:
    """Stable, non-reversible reference so records stay linkable without the id.

    HMAC-keyed, not a bare digest. §164.514(c) requires a re-identification code
    that is NOT derived from information about the individual; an unsalted
    sha256(claim_number) is derived from precisely that, so anyone holding an EOB
    could compute the digest and confirm the case is in the corpus, or enumerate a
    payer's claim-number format offline.

    Fails closed when no pepper is configured. The export is an operator-run job,
    so a loud failure is correct — silently emitting a brute-forceable reference
    into a corpus with no lifecycle expiry is not.
    """
    return "ref_" + hashing.keyed_hash(value, purpose=hashing.CLAIM_REF)[:24]


def deid_year(value: date | None) -> int | None:
    return value.year if value else None


def _age_sub(m: re.Match) -> str:
    if m.group(1) is not None:  # "<n> years old"
        return ("90+" if int(m.group(1)) >= 90 else m.group(1)) + m.group(2)
    return m.group(3) + ("90+" if int(m.group(4)) >= 90 else m.group(4))  # "age <n>"


# --- NER layer (Presidio) ----------------------------------------------------
# NER handles ONLY names/places (what regex can't). Formatted PHI is left to the
# regex above so Presidio's over-eager DATE_TIME/number recognizers don't clobber
# billing codes. Lazy + optional; installed at runtime in the export task, never
# baked into the app image. Prefers the accurate model, falls back to whatever is
# installed (large > medium > small).
_NER_ENTITIES = ["PERSON", "LOCATION"]
_NER_TOKEN = {"PERSON": "[NAME]", "LOCATION": "[LOCATION]"}
_SPACY_MODELS = ["en_core_web_lg", "en_core_web_md", "en_core_web_sm"]
# None = not tried; () = tried but unavailable; (analyzer, anonymizer) = ready.
_ner_engines: object = None


def _ner_engines_or_none():
    global _ner_engines
    if _ner_engines is not None:
        return _ner_engines or None
    try:
        import spacy
        from presidio_analyzer import AnalyzerEngine
        from presidio_analyzer.nlp_engine import NlpEngineProvider
        from presidio_anonymizer import AnonymizerEngine
    except ImportError:
        _ner_engines = ()
        return None
    wanted = [os.environ.get("DEID_SPACY_MODEL"), *_SPACY_MODELS]
    model = next((m for m in wanted if m and spacy.util.is_package(m)), None)
    if model is None:
        _ner_engines = ()
        return None
    nlp_engine = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "en", "model_name": model}],
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
    # Keep billing/diagnosis codes NER mis-tagged as a PERSON/LOCATION.
    results = [r for r in results if not _CODE.fullmatch(text[r.start : r.end].strip(" \t().,;:"))]
    if not results:
        return text
    operators = {
        ent: OperatorConfig("replace", {"new_value": tok}) for ent, tok in _NER_TOKEN.items()
    }
    operators["DEFAULT"] = OperatorConfig("replace", {"new_value": "[REDACTED]"})
    return anonymizer.anonymize(text=text, analyzer_results=results, operators=operators).text


def redact_text(text: str | None, known: list, use_ner: bool = False) -> str | None:
    """Redact PHI from free text: NER names/places (optional) + captured identifiers
    + the Safe Harbor formatted-identifier passes + letter-slot names + age 90+."""
    if not text:
        return text
    out = text
    if use_ner:
        out = _ner_redact(out)
    # Exact captured identifiers first — longest first; word-boundary lookarounds
    # avoid clipping inside real words.
    seen = {str(k).strip() for k in known if k and len(str(k).strip()) >= 2}
    for val in sorted(seen, key=len, reverse=True):
        out = re.sub(rf"(?<!\w){re.escape(val)}(?!\w)", "[REDACTED]", out, flags=re.IGNORECASE)
    # Formatted identifiers (precise — bare CPT/ICD codes are not matched).
    out = _EMAIL.sub("[EMAIL]", out)
    out = _URL.sub("[URL]", out)
    out = _SSN.sub("[SSN]", out)
    out = _IPV4.sub("[IP]", out)
    out = _STREET.sub("[ADDRESS]", out)
    out = _ZIP4.sub("[ZIP]", out)
    out = _STATE_ZIP.sub(r"\1 [ZIP]", out)
    out = _PHONE.sub("[PHONE]", out)
    out = _DATE.sub("[DATE]", out)
    out = _AGE.sub(_age_sub, out)
    out = _AUTH.sub("[ID]", out)
    # Member-ID shapes BEFORE the plain long-number pass. These are the identifiers
    # the exact-match key-set used to miss entirely: `extracted_json` is written
    # with exclude={"member_id"} per hard rule 5, so raw.get("member_id") was always
    # None and the member ID was never in the redaction set at all. Structural
    # coverage does not depend on having captured the value.
    out = _MBI.sub("[MEMBER_ID]", out)
    out = _MEMBER_ALNUM.sub("[MEMBER_ID]", out)
    out = _LONGNUM.sub("[ID]", out)
    # Names in standard letter slots (belt-and-suspenders over NER).
    out = _NAME_SLOT.sub(lambda m: m.group("cue") + "[NAME]", out)
    return out


def scan_residual(text: str | None) -> dict:
    """Flag anything that still looks like PHI after redaction — for the validation
    report. Formatted leaks are bugs to fix; candidate names are a human review
    list (mostly benign terms like payer names, but a missed patient name shows
    here too)."""
    if not text:
        return {}
    flags: dict = {}
    for label, pat in (
        ("email", _EMAIL),
        ("ssn", _SSN),
        ("phone", _PHONE),
        ("ip", _IPV4),
        ("long_number", _LONGNUM),
        ("auth_ref", _AUTH),
        ("mbi", _MBI),
        ("member_alnum", _MEMBER_ALNUM),
    ):
        count = len(pat.findall(text))
        if count:
            flags[label] = count
    candidates = sorted({m.group(0) for m in _CANDIDATE_NAME.finditer(text)})
    if candidates:
        flags["candidate_names"] = candidates
    return flags
