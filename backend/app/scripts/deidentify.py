"""Rule layer of the training-corpus de-identification — HIPAA Safe Harbor,
45 CFR §164.514(b)(2), implemented as deterministic patterns.

This module is ONE of three layers the export runs on every free-text field, in
this order (see export_corpus.py):

  1. rules      — this file: exact captured values, formatted identifiers, dates,
                  ages, labeled numbers, letter-slot names, geography, employers.
  2. detector B — Presidio + a clinical transformer (deid_detectors.PresidioDetector)
  3. detector A — Amazon Comprehend Medical DetectPHI (deid_detectors.ComprehendDetector)

Anything any layer finds is removed. `scan_residual` then re-checks the result
with detectors that are deliberately BROADER than the redaction patterns, and the
export refuses to write if a precise residual survives.

Safe Harbor identifier classes (§164.514(b)(2)(i)) and where each is handled:

  (A) names ................ `known` exact match, `_NAME_SLOT`, `_INITIALS`, NER (B), NAME (A)
  (B) geography < state .... `_STREET`, `_PO_BOX`, `_CITY_STATE`, `_COUNTY`, `_ZIP*`, NER
  (C) dates (all but year) . `_DATE` (year-bearing), `_PARTIAL_DATE` (no year), OCR shapes,
      ages > 89 ............ `_AGE`, `_AGE_WORDS`, `_BIRTH_YEAR` (year implying age > 89)
  (D)(E) phone / fax ....... `_PHONE`, `_PHONE_LOCAL` (7-digit with a cue)
  (F) email ................ `_EMAIL`
  (G) SSN .................. `_SSN` (dashed, spaced, bare 9 digits via `_LONGNUM`)
  (H) MRN .................. `_LABELED_ID` (cue-driven, any length), `_LONGNUM`
  (I) plan beneficiary # ... `_MBI`, `_MEMBER_ALNUM`, `_LABELED_ID`, archived member id
  (J) account # ............ `_LABELED_ID`, `_LONGNUM`
  (K) certificate/license .. `_LABELED_ID` (lic/DEA/NPI cues), `_TAX_ID`, `_LONGNUM`
  (L) vehicle ids .......... `_LABELED_ID` (plate/VIN cues), `_MEMBER_ALNUM` (VIN shape)
  (M) device serials ....... `_LABELED_ID` (serial/SN/device cues)
  (N) URLs ................. `_URL`
  (O) IP addresses ......... `_IPV4`, `_IPV6`
  (P)(Q) biometrics/photos . not representable in text
  (R) any other code ....... `_AUTH`, `_LABELED_ID`, `_FIVE_DIGIT` (non-CPT 5-digit runs),
                             employer/occupation cues (`_EMPLOYER`, `_OCCUPATION`)

Guidance §3.2: patient INITIALS are a name derivative and are not permitted —
the export passes every spelling of `case.patient_initials` in `known`, and
`_INITIALS` catches the letter subject-line shape structurally.

Guidance §3.3: a birth year that, with any other year in the record, implies an
age over 89 must go — `redact_text` takes `latest_year` for that comparison.

Guidance §3.8: provider / practice / payer names are NOT required to be removed.
The export removes practice and provider identifiers anyway (customer
confidentiality; "small practice + rare code + state" is the actual-knowledge
risk) and keeps payer names, which are training signal.

The second Safe Harbor prong — §164.514(b)(2)(ii), no actual knowledge — is a
human determination. Nothing this module produces is de-identified until the
promote step records a reviewer's attestation (promote_corpus.py).

RULESET_VERSION is recorded in every export report. Bump it on ANY pattern
change, exactly like a prompt VERSION.
"""

import re
from collections.abc import Iterable
from datetime import date

RULESET_VERSION = "deid_v2"

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

# --- formatted identifiers ------------------------------------------------------

_MONTHS = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?"
_MONTH_FULL = (
    r"(?:January|February|March|April|May|June|July|August|September|October|November"
    r"|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept?|Oct|Nov|Dec)\.?"
)

_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
# Dashed, spaced or dotted SSN. A bare 9-digit run is caught by _LONGNUM.
_SSN = re.compile(r"\b\d{3}[-. ]\d{2}[-. ]\d{4}\b")
_URL = re.compile(r"\bhttps?://\S+|\bwww\.[^\s,;]+")
_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_IPV6 = re.compile(r"(?<![\w:])(?:[0-9a-f]{0,4}:){2,7}[0-9a-f]{1,4}(?![\w:])", re.IGNORECASE)
_PHONE = re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)")
# 7-digit local number only when a telephone cue precedes it (a bare NNN-NNNN
# is also a CARC-adjacent / claim-line shape).
_PHONE_LOCAL = re.compile(
    r"(?P<cue>\b(?:phone|tel|telephone|fax|call|cell|mobile|pager)\b\.?\s*(?:no\.?|#|:)?\s*)"
    r"(?P<num>\d{3}[-.\s]\d{4})(?!\d)",
    re.IGNORECASE,
)
_ZIP4 = re.compile(r"\b\d{5}-\d{4}\b")
# "CA 90210" -> keep the state (allowed at state level), drop the ZIP.
_STATE_ZIP = re.compile(r"\b([A-Z]{2})\s+\d{5}(?:-\d{4})?\b")
# "ZIP: 90210" / "postal code 90210".
_BARE_ZIP = re.compile(
    r"(?P<cue>\b(?:zip(?:\s*code)?|postal(?:\s*code)?)\b\s*[:#]?\s*)(?P<zip>\d{5}(?:-\d{4})?)\b",
    re.IGNORECASE,
)
_STREET = re.compile(
    r"\b\d{1,6}\s+(?:[A-Z][A-Za-z.'-]+\s+){0,4}"
    r"(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct"
    r"|Way|Place|Pl|Terrace|Ter|Circle|Cir|Highway|Hwy|Parkway|Pkwy)\.?"
    r"(?:\s+(?:Suite|Ste|Apt|Unit|Floor|Fl|#)\.?\s*\w+)?",
    re.IGNORECASE,
)
_PO_BOX = re.compile(r"\bP\.?\s*O\.?\s*Box\s+\d+\b", re.IGNORECASE)
# US state and territory postal abbreviations — the one geographic level Safe
# Harbor permits. Used to recognise "City, ST" and to keep the state token.
US_STATES = frozenset(
    """AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE
    NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC PR VI GU AS
    MP""".split()
)
# "Springfield, IL" -> "[LOCATION], IL". Cities are geography below the state.
_CITY_STATE = re.compile(
    r"\b(?P<city>[A-Z][a-zA-Z.'-]+(?:\s+[A-Z][a-zA-Z.'-]+){0,3}),\s*(?P<state>[A-Z]{2})\b"
)
_COUNTY = re.compile(r"\b[A-Z][a-zA-Z.'-]+(?:\s+[A-Z][a-zA-Z.'-]+){0,2}\s+County\b")

# --- dates and ages ---------------------------------------------------------------

_DATE = re.compile(
    r"\b(?:"
    r"\d{1,2}\s?[/.-]\s?\d{1,2}\s?[/.-]\s?\d{2,4}"  # 03/15/1980, OCR "03 /15/ 1980"
    r"|\d{4}\s?-\s?\d{1,2}\s?-\s?\d{1,2}"  # 1980-03-15
    rf"|{_MONTHS}\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}"  # March 15, 1980
    rf"|\d{{1,2}}(?:st|nd|rd|th)?\s+(?:of\s+)?{_MONTHS},?\s+\d{{4}}"  # 15 March 1980
    rf"|\d{{1,2}}-{_MONTHS}-\d{{2,4}}"  # 15-Mar-2026
    rf"|{_MONTHS}-\d{{1,2}}-\d{{2,4}}"  # Mar-15-2026
    rf"|\d{{1,2}}{_MONTHS}\d{{2,4}}"  # 15MAR2026
    r"|\d{1,2}/\d{4}"  # 03/2026 (month/year — still a date element)
    rf"|{_MONTHS},?\s+\d{{4}}"  # May 2026
    r")\b",
    re.IGNORECASE,
)
# Month + day with NO year. Guidance §3.3: "the day, month, and any other
# information that is more specific than the year" must go, so "DOS 03/15" and
# "March 15" are date elements even without a year. The numeric shape is bounded
# to real month/day ranges so "120/80" (blood pressure) and "1/2 tablet" do not
# match... except 1/2 does, and that over-redaction is accepted (principle: a
# missed DOS is a leak, a lost fraction is noise).
_PARTIAL_DATE = re.compile(
    r"\b(?:"
    r"(?:0?[1-9]|1[0-2])\s?[/-]\s?(?:0?[1-9]|[12]\d|3[01])(?!\s?[/-]\s?\d)"  # 03/15, 3-15
    rf"|{_MONTH_FULL}\s+\d{{1,2}}(?:st|nd|rd|th)?(?!\s?[/-]?\s?,?\s*\d{{4}})(?![\d:])"  # March 15
    rf"|\d{{1,2}}(?:st|nd|rd|th)?\s+(?:of\s+)?{_MONTH_FULL}(?!,?\s+\d{{4}})"  # 15th of March
    rf"|(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|eleventh"
    rf"|twelfth|thirteenth|fourteenth|fifteenth|sixteenth|seventeenth|eighteenth"
    rf"|nineteenth|twentieth|twenty-\w+|thirtieth|thirty-first)\s+(?:of\s+)?{_MONTH_FULL}"
    r")\b",
    re.IGNORECASE,
)
# Ages: capture the number, aggregate to "90+" only when >= 90 (Safe Harbor).
_AGE = re.compile(
    r"\b(\d{2,3})(\s*-?\s*(?:years?|yrs?|y[/.]?o|yo)\b(?:\s*-?\s*old)?)"
    r"|(\baged?\s*[:=]?\s*)(\d{2,3})\b",
    re.IGNORECASE,
)
# Spelled-out ages at or past the boundary ("ninety-two years old", "one hundred").
_AGE_WORDS = re.compile(
    r"\b(?:ninety(?:[\s-]\w+)?|one\s+hundred(?:\s+(?:and\s+)?\w+)?)"
    r"(?=[\s-]*(?:years?|yrs?|y/?o)\b)",
    re.IGNORECASE,
)
# A year attached to a birth cue. Guidance §3.3 example: birth year 1910 with a
# service year of 2010 tells the reader the patient is ~100 — the year must go
# when it implies age > 89 against the latest year anywhere in the record.
_BIRTH_YEAR = re.compile(
    r"(?P<cue>\b(?:born|birth(?:\s*date|day)?|d\.?o\.?b\.?)\b\W{0,12}?(?:in\s+|on\s+)?)"
    r"(?P<year>(?:18|19|20)\d{2})\b",
    re.IGNORECASE,
)
_YEAR = re.compile(r"\b(?:18|19|20)\d{2}\b")

# --- numbers and codes ------------------------------------------------------------

_LONGNUM = re.compile(r"(?<!\d)\d{6,}(?!\d)")  # member ids / MRNs / claim / account
# Provider Tax ID (EIN) shape "12-3456789". Not a patient identifier under the
# rule, removed as a practice identifier (see module docstring).
_TAX_ID = re.compile(r"\b\d{2}-\d{7}\b")
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
    r"\b(?=[A-Z0-9]{8,20}\b)(?=[A-Z0-9]*[A-Z])(?=[A-Z0-9]*\d)[A-Z0-9]{8,20}\b",
    re.IGNORECASE,
)
# Authorization / reference numbers (AUTH-555, CASE-1234). 4+ letter prefix so
# 2-3 letter form/adjustment codes survive (CO-197, UB-04, CMS-1500).
_AUTH = re.compile(r"\b[A-Z]{4,}-\d{2,}[A-Z0-9-]*\b", re.IGNORECASE)
# The gap the length floors leave open: a SHORT identifier is still an identifier
# when it is labeled. "MRN: 48213", "Acct # 9921", "Lic. A12345", "Plate ABC1234",
# "SN-88213-Q", "Group 5521", "Policy 77A" — items (H)(I)(J)(K)(L)(M)(R). The value
# must contain a digit so "member of", "account manager" and other prose survive.
_LABELED_ID = re.compile(
    r"(?P<cue>\b(?:MRN|medical\s+record|chart|acct|account|patient\s+id|pt\s+id|member(?:\s+id)?"
    r"|subscriber(?:\s+id)?|policy|group|plan\s+id|lic(?:ense|ence)?|DEA|NPI|plate|VIN|serial"
    r"|S/?N|device(?:\s+id)?|ref(?:erence)?|auth(?:orization)?|case|claim|invoice|encounter"
    r"|visit|accession|specimen|badge|employee(?:\s+id)?)\b\.?\s*(?:no\.?|number|num\.?|#|:|id[:#]?)?\s*[:#]?\s*)"
    r"(?P<value>(?=[A-Z0-9][A-Z0-9-]*\d)[A-Z0-9][A-Z0-9-]{2,})",
    re.IGNORECASE,
)
# Employer and occupation of the patient. Employers are enumerated in the rule
# ("relatives, employers, or household members"); occupation is the guidance's
# own actual-knowledge example (§3.6 ex. 1, "former president of the State
# University"). Capitalised span after an employment cue.
_EMPLOYER = re.compile(
    r"(?P<cue>\b(?:employer|employed\s+(?:by|at|with)|works\s+(?:at|for)|working\s+(?:at|for)"
    r"|employment\s+(?:with|at))\b\W{0,3})"
    r"(?P<value>[A-Z][\w&.'-]*(?:\s+(?:[A-Z][\w&.'-]*|of|and|the|&)){0,5})"
)
_OCCUPATION = re.compile(
    r"(?P<cue>\b(?:occupation|profession|job\s+title|works\s+as|employed\s+as|is\s+employed\s+as)"
    r"\b\W{0,3}(?:an?\s+|the\s+)?)"
    r"(?P<value>[A-Za-z][\w-]*(?:\s+[A-Za-z][\w-]*){0,3})",
    re.IGNORECASE,
)

# --- names ------------------------------------------------------------------------

# Names that follow a standard letter cue (not "Re:", which is a subject line).
# (?i:...) scopes case-insensitivity to the CUE only; the captured name must still
# start uppercase, so we don't redact a lowercase continuation like "Dear sir".
_NAME_SLOT = re.compile(
    r"(?P<cue>(?i:\b(?:Dear|Attn|Attention|Sincerely|Regards|Patient(?:'s)?(?:\s+name)?"
    r"|Member(?:\s+name)?|Name|Insured|Subscriber|Beneficiary|Guarantor|Claimant"
    r"|Mr|Mrs|Ms|Mx|Dr)\b)\.?[:,]?\s+)"
    # Accept Title-case AND ALL-CAPS names in the slot: OCR'd EOB/CMS-1500 text is
    # frequently all-caps ("PATIENT: JANE DOE"), which a Title-case-only pattern
    # would miss entirely.
    # "LAST, FIRST" (claim forms) as well as "First Last" / "FIRST LAST".
    r"(?P<name>[A-Z][a-zA-Z'.-]+,\s+[A-Z][a-zA-Z'.-]+(?:\s+[A-Z]\.?)?"
    r"|[A-Z]{2,},\s+[A-Z]{2,}(?:\s+[A-Z]\.?)?"
    r"|[A-Z][a-zA-Z'.-]+(?:\s+[A-Z][a-zA-Z'.-]+){0,3}|[A-Z]{2,}(?:\s+[A-Z]{2,}){0,3})"
)
# Patient initials in the letter shapes the letter prompt produces:
# "Re: Appeal of Denied Claim #… for J.D., DOS …" and "Patient: J.D.". Dotted or
# spaced initials anywhere after a patient cue; bare two-letter initials only in
# the "for XX," subject shape, so "for CT scan" and "for MRI" survive.
_INITIALS = re.compile(
    r"(?P<cue>\b(?:patient|member|beneficiary|insured|subscriber|re)\b:?\s+(?:\w+\s+){0,6}?)"
    r"(?P<init>(?-i:[A-Z]\.\s?[A-Z]\.(?:\s?[A-Z]\.)?|[A-Z]\s[A-Z](?:\s[A-Z])?(?![a-z])))"
    r"|(?P<cue2>\bfor\s+)(?P<init2>(?-i:[A-Z]\.?\s?[A-Z]\.?(?:\s?[A-Z]\.?)?))(?P<tail>,\s*DOS\b)",
    re.IGNORECASE,
)
# Candidate-name bigrams that may have slipped through, for the fail-closed QA
# gate only (over-matching is fine — the review list is what it feeds). Both
# Title-case and ALL-CAPS, since scanned claim text is dominated by the latter.
# [ \t] (not \s) so a candidate never spans a line break.
_CANDIDATE_NAME = re.compile(r"\b[A-Z][a-z]{1,}[ \t]+[A-Z][a-z]{1,}\b|\b[A-Z]{2,}[ \t]+[A-Z]{2,}\b")

# Billing/diagnosis code shapes. Detectors sometimes tag these as a PERSON (e.g.
# ICD-10 "I48.91"); we keep them — they're training signal, not PHI, and a code
# never contains a real name. Used to carve codes out of detector spans.
_CODE = re.compile(
    r"[A-Z]\d[0-9A-Z](?:\.[A-Z0-9]{1,4})?"  # ICD-10-CM: I48.91, M23.205, S72.001A
    r"|\d{5}"  # CPT: 93306
    r"|[A-Z]\d{4}"  # HCPCS Level II: J1234
    r"|[A-Z]{1,3}-\d{1,3}"  # CARC / group code: CO-197
    r"|(?:MA|[MN])\d{1,3}"  # RARC: N115, M76, MA13
)
CODE_TOKEN = re.compile(rf"\b(?:{_CODE.pattern})\b")

# A bare five-digit run is a CPT code OR a ZIP code, and nothing in the shape
# tells them apart. It is kept only when the export can vouch for it: it is in
# the NCCI code set, or a code cue precedes it, or it is a dollar figure.
_FIVE_DIGIT = re.compile(r"(?<![\d$.,])\d{5}(?![\d,]|\.\d)")
_CODE_CUE = re.compile(
    r"\b(?:CPT|HCPCS|codes?|procedures?|proc\.?|E/M|services?|bill(?:ed|ing)?|line|modifier)\b"
    r"\W{0,3}(?:\d{5}(?:\s*(?:,|/|and|&|\s)\s*))*$",
    re.IGNORECASE,
)

REDACTED = "[REDACTED]"


def deid_year(value: date | None) -> int | None:
    return value.year if value else None


def initials_variants(initials: str | None) -> list[str]:
    """Every spelling of a patient's initials the letter or summary might carry:
    "J.D.", "JD", "J D", "J. D.", "j.d.". Guidance §3.2 — initials are names."""
    if not initials:
        return []
    letters = [c for c in initials.upper() if c.isalpha()]
    if not letters:
        return []
    return [
        "".join(letters),
        " ".join(letters),
        ".".join(letters) + ".",
        ". ".join(letters) + ".",
        initials.strip(),
    ]


def _age_sub(m: re.Match) -> str:
    if m.group(1) is not None:  # "<n> years old"
        return ("90+" if int(m.group(1)) >= 90 else m.group(1)) + m.group(2)
    return m.group(3) + ("90+" if int(m.group(4)) >= 90 else m.group(4))  # "age <n>"


def latest_year_in(texts: Iterable[str | None], *years: int | None) -> int:
    """The most recent year present in a record — the reference point for the
    birth-year rule. Falls back to today so a record with no years at all is
    still checked against the present."""
    found = [y for y in years if y]
    for text in texts:
        if text:
            found.extend(int(y) for y in _YEAR.findall(text))
    return max(found, default=date.today().year)


def _city_state_sub(m: re.Match) -> str:
    if m.group("state") not in US_STATES:
        return m.group(0)
    return f"[LOCATION], {m.group('state')}"


def _birth_year_sub(latest_year: int):
    def _sub(m: re.Match) -> str:
        year = int(m.group("year"))
        if latest_year - year > 89:
            return m.group("cue") + "[DATE]"
        return m.group(0)

    return _sub


def _five_digit_sub(known_codes: frozenset[str] | None):
    """Keep a five-digit run only when it is vouched for as a billing code."""

    def _sub(m: re.Match) -> str:
        value = m.group(0)
        if known_codes is not None and value in known_codes:
            return value
        prefix = m.string[max(0, m.start() - 40) : m.start()]
        if _CODE_CUE.search(prefix):
            return value
        return "[ID]"

    return _sub


def _initials_sub(m: re.Match) -> str:
    if m.group("init") is not None:
        return m.group("cue") + "[NAME]"
    return m.group("cue2") + "[NAME]" + m.group("tail")


def redact_text(
    text: str | None,
    known: list,
    *,
    latest_year: int | None = None,
    known_codes: frozenset[str] | None = None,
) -> str | None:
    """The rule layer. Removes every Safe Harbor identifier class that has a
    deterministic shape, plus the exact `known` values captured for the case.

    `latest_year` drives the age-over-89 birth-year rule (§3.3). `known_codes`
    is the NCCI CPT/HCPCS set, used to keep five-digit billing codes while
    removing five-digit runs that are not codes (ZIPs, short account numbers).
    Without it every un-cued five-digit run is removed — safe, and lossy.
    """
    if not text:
        return text
    out = text
    # Exact captured identifiers first — longest first; word-boundary lookarounds
    # avoid clipping inside real words.
    # Email and URL first: a captured value that is also a mailbox local part
    # ("JD" inside jd@example.com) would otherwise split the address so the
    # email pattern no longer recognises it.
    out = _EMAIL.sub("[EMAIL]", out)
    out = _URL.sub("[URL]", out)
    seen = {str(k).strip() for k in known if k and len(str(k).strip()) >= 2}
    for val in sorted(seen, key=len, reverse=True):
        out = re.sub(rf"(?<!\w){re.escape(val)}(?!\w)", REDACTED, out, flags=re.IGNORECASE)
    # Formatted identifiers (precise — bare CPT/ICD codes are not matched).
    out = _SSN.sub("[SSN]", out)
    out = _IPV4.sub("[IP]", out)
    out = _IPV6.sub("[IP]", out)
    out = _STREET.sub("[ADDRESS]", out)
    out = _PO_BOX.sub("[ADDRESS]", out)
    out = _ZIP4.sub("[ZIP]", out)
    out = _STATE_ZIP.sub(r"\1 [ZIP]", out)
    out = _BARE_ZIP.sub(lambda m: m.group("cue") + "[ZIP]", out)
    out = _CITY_STATE.sub(_city_state_sub, out)
    out = _COUNTY.sub("[LOCATION]", out)
    out = _TAX_ID.sub("[ID]", out)
    # Labeled identifiers BEFORE the phone and date passes: "NPI 1234567890" is
    # an identifier, not a phone number, and "Acct # 03/15" is not a date.
    out = _LABELED_ID.sub(lambda m: m.group("cue") + "[ID]", out)
    out = _PHONE.sub("[PHONE]", out)
    out = _PHONE_LOCAL.sub(lambda m: m.group("cue") + "[PHONE]", out)
    out = _BIRTH_YEAR.sub(_birth_year_sub(latest_year or date.today().year), out)
    out = _DATE.sub("[DATE]", out)
    out = _PARTIAL_DATE.sub("[DATE]", out)
    out = _AGE.sub(_age_sub, out)
    out = _AGE_WORDS.sub("90+", out)
    out = _AUTH.sub("[ID]", out)
    # Member-ID shapes BEFORE the plain long-number pass. These are the identifiers
    # the exact-match key-set used to miss entirely: `extracted_json` is written
    # with exclude={"member_id"} per hard rule 5, so the member ID is only in the
    # redaction set while the model_runs archive (30-day lifecycle) still holds
    # it. Structural coverage does not depend on having captured the value.
    out = _MBI.sub("[MEMBER_ID]", out)
    out = _MEMBER_ALNUM.sub("[MEMBER_ID]", out)
    out = _LONGNUM.sub("[ID]", out)
    out = _FIVE_DIGIT.sub(_five_digit_sub(known_codes), out)
    # Names in standard letter slots, initials, employers, occupations.
    out = _NAME_SLOT.sub(lambda m: m.group("cue") + "[NAME]", out)
    out = _INITIALS.sub(_initials_sub, out)
    out = _EMPLOYER.sub(lambda m: m.group("cue") + "[EMPLOYER]", out)
    out = _OCCUPATION.sub(lambda m: m.group("cue") + "[OCCUPATION]", out)
    return out


def carve_codes(spans: list[tuple[int, int]], text: str) -> list[tuple[int, int]]:
    """Cut billing/diagnosis codes OUT of detector spans instead of dropping or
    keeping a span whole. A NER model tags "Dx I48.91" as one PERSON; a whole-span
    test kept the code only when the span WAS the code, so the code was replaced
    by [NAME]. Dropping such spans would be wrong the other way — "Mary Chen
    I48.91" must still lose the name — so each span becomes the sub-spans
    between its code tokens. Remnants that are only punctuation/space are
    dropped."""
    kept: list[tuple[int, int]] = []
    for start, end in spans:
        cursor = start
        for m in CODE_TOKEN.finditer(text, start, end):
            if m.start() > cursor:
                kept.append((cursor, m.start()))
            cursor = m.end()
        if cursor < end:
            kept.append((cursor, end))
    return [(s, e) for s, e in kept if any(ch.isalnum() for ch in text[s:e])]


# --- residual scan ------------------------------------------------------------------
#
# Residual detectors that are deliberately BROADER than (and independent of)
# the redaction patterns. Scanning redacted text with the same regexes that
# just ran can only ever find ordering bugs, never a pattern gap — so these
# over-match on purpose; they feed a fail-closed gate and a review list, not a
# substitution.
_RESIDUAL_DATE = re.compile(
    rf"\b(?:\d{{1,2}}\s?[/.-]\s?\d{{1,2}}\s?[/.-]\s?\d{{2,4}}|\d{{4}}-\d{{1,2}}-\d{{1,2}}"
    rf"|\d{{1,2}}/\d{{4}}"
    rf"|{_MONTHS}[\s-]+\d{{1,2}}(?:st|nd|rd|th)?,?[\s-]+\d{{2,4}}"
    rf"|\d{{1,2}}(?:st|nd|rd|th)?[\s-]+(?:of\s+)?{_MONTHS},?[\s-]+\d{{2,4}}"
    rf"|{_MONTHS},?\s+\d{{4}}|\d{{1,2}}{_MONTHS}\d{{2,4}})\b",
    re.IGNORECASE,
)
_RESIDUAL_PARTIAL_DATE = re.compile(
    rf"\b(?:(?:0?[1-9]|1[0-2])\s?[/-]\s?(?:0?[1-9]|[12]\d|3[01])\b(?!\s?[/-]\s?\d)"
    rf"|{_MONTH_FULL}\s+\d{{1,2}}(?:st|nd|rd|th)?\b(?!,?\s*\d{{4}})"
    rf"|\d{{1,2}}(?:st|nd|rd|th)?\s+(?:of\s+)?{_MONTH_FULL}\b(?!,?\s+\d{{4}}))",
    re.IGNORECASE,
)
_RESIDUAL_ZIP = re.compile(r"\b\d{5}(?:-\d{4})?\b(?!\.\d)")  # any 5-digit run incl. ZIP+4
_RESIDUAL_ALNUM_ID = re.compile(
    r"\b(?=[A-Za-z0-9-]{7,24}\b)(?=[A-Za-z0-9-]*[A-Za-z])(?=[A-Za-z0-9-]*\d)[A-Za-z0-9-]{7,24}\b"
)
_RESIDUAL_INITIALS = re.compile(
    r"\b(?:patient|member|beneficiary|insured|subscriber|re)\b:?\s+(?:\w+\s+){0,6}?"
    r"(?-i:[A-Z]\.\s?[A-Z]\.)|\bfor\s+(?-i:[A-Z]\.?\s?[A-Z]\.?),\s*DOS\b",
    re.IGNORECASE,
)
_RESIDUAL_EMPLOYER = re.compile(
    r"\b(?:employer|employed\s+(?:by|at|as)|works\s+(?:at|for|as)|occupation|profession)\b"
    r"[\s:,.-]{0,3}(?:(?:an?|the)\s+)?(?![\[\s])(?!(?:an?|the)\s)[A-Za-z]",
    re.IGNORECASE,
)
_RESIDUAL_STATE_ZIP = re.compile(r"\b[A-Z]{2}\s+\d{5}\b")

# Residual kinds that are a REVIEW signal, not proof of a leak. The alphanumeric-id
# detector over-matches by design — "CMS-1500" and "ICD-10-CM" are letter+digit
# tokens, and the letter prompt tells the model to cite both. Everything else
# scan_residual reports is precise enough to fail the export on. `zip_like` is
# precise once the NCCI code set is supplied (a five-digit run that is neither a
# known code nor cued as one is a leak); without the set it is review-only.
REVIEW_ONLY_KINDS = frozenset({"alnum_id_like", "zip_like_uncertain"})


def split_residual(flags: dict) -> tuple[dict, dict, list]:
    """scan_residual output as (precise leak counts, review-only counts,
    candidate names)."""
    precise = {
        k: v for k, v in flags.items() if k not in REVIEW_ONLY_KINDS and k != "candidate_names"
    }
    review = {k: v for k, v in flags.items() if k in REVIEW_ONLY_KINDS}
    return precise, review, list(flags.get("candidate_names", []))


def scan_residual(text: str | None, known_codes: frozenset[str] | None = None) -> dict:
    """Flag anything that still looks like PHI after redaction — for the validation
    report and the export's fail-closed gate. Formatted leaks are bugs to fix;
    candidate names are a human review list (mostly benign terms like payer
    names, but a missed patient name shows here too). Uses detectors that are
    intentionally broader than the redaction patterns, so a gap in those shows
    up here instead of passing silently."""
    if not text:
        return {}
    flags: dict = {}
    for label, pat in (
        ("email", _EMAIL),
        ("ssn", _SSN),
        ("phone", _PHONE),
        ("ip", _IPV4),
        ("ipv6", _IPV6),
        ("long_number", _LONGNUM),
        ("tax_id", _TAX_ID),
        ("auth_ref", _AUTH),
        ("mbi", _MBI),
        ("member_alnum", _MEMBER_ALNUM),
        ("labeled_id", _LABELED_ID),
        ("date", _RESIDUAL_DATE),
        ("partial_date", _RESIDUAL_PARTIAL_DATE),
        ("state_zip", _RESIDUAL_STATE_ZIP),
        ("alnum_id_like", _RESIDUAL_ALNUM_ID),
        ("po_box", _PO_BOX),
        ("street", _STREET),
        ("county", _COUNTY),
        ("initials", _RESIDUAL_INITIALS),
        ("employer", _RESIDUAL_EMPLOYER),
    ):
        count = len(pat.findall(text))
        if count:
            flags[label] = count
    # Five-digit runs: precise when we can tell CPT from ZIP, review-only otherwise.
    five = [m for m in _FIVE_DIGIT.finditer(text)]
    if five:
        if known_codes is None:
            flags["zip_like_uncertain"] = len(five)
        else:
            unknown = [
                m
                for m in five
                if m.group(0) not in known_codes
                and not _CODE_CUE.search(m.string[max(0, m.start() - 40) : m.start()])
            ]
            if unknown:
                flags["zip_like"] = len(unknown)
    if _RESIDUAL_ZIP.search(text) and known_codes is None and "zip_like_uncertain" not in flags:
        flags["zip_like_uncertain"] = len(_RESIDUAL_ZIP.findall(text))
    candidates = sorted({m.group(0) for m in _CANDIDATE_NAME.finditer(text)})
    if candidates:
        flags["candidate_names"] = candidates
    return flags
