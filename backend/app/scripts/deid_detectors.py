"""Detector layers of the corpus de-identification: two INDEPENDENT PHI detectors
whose findings are unioned on top of the rule layer (deidentify.py).

Why two, and why these two. Published recall for the best single automated
de-identifier on in-distribution clinical narrative is ~97-99% at the token
level (i2b2 2014; Dernoncourt 2017; Chambon 2022) and drops 10-15 points on a new
document genre (CEGS N-GRID 2016). Presidio's default spaCy path scores recall
0.91 on MIMIC-III and 0.73 on out-of-distribution names. No single detector
supports a "removed" claim under §164.514(b)(2)(i); two detectors with different
training data and different failure modes, unioned, do — and their disagreement
rate is the drift monitor when either model changes underneath us.

  Detector B — PresidioDetector: Microsoft Presidio running the Stanford clinical
      de-identifier transformer (MIT; trained on i2b2 2014 + Stanford radiology;
      i2b2 F1 98.9) plus Presidio's pattern recognizers and a few of our own.
      Runs OFFLINE from weights baked into the deid image at a pinned revision.
      `engine="spacy"` (en_core_web_lg) is the laptop / CI fallback and is
      refused in production by the export's preflight.

  Detector A — ComprehendDetector: Amazon Comprehend Medical DetectPHI. HIPAA-
      eligible, inside the AWS BAA, excluded from AWS's service-improvement
      clause (Service Terms §50.3), reached through a VPC interface endpoint.
      Its model auto-updates, so the ModelVersion it reports is recorded per run.

Both detectors return character spans; `merge_spans` unions them and
`apply_spans` substitutes Safe Harbor placeholder tokens. Billing / diagnosis
codes are carved out of every span (a NER model tags "Dx I48.91" as a PERSON),
and the two exceptions the rule itself permits are honoured: a bare YEAR may
stay (§164.514(b)(2)(i)(C)) and an AGE under 90 may stay.

Every detector failure raises; the export treats any exception as "nothing is
written". There is no degraded mode.
"""

import hashlib
import json
import logging
import os
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path

from app.scripts.deidentify import carve_codes

logger = logging.getLogger(__name__)


class DetectorUnavailable(RuntimeError):
    """The detector cannot be constructed here (library / model / client missing).
    The export aborts before reading a single row."""


class DetectorError(RuntimeError):
    """A detector call failed or returned a truncated result. The export aborts
    without writing."""


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    label: str  # normalised: NAME, LOCATION, DATE, ID, PHONE, EMAIL, URL, IP, AGE, OCCUPATION, ORG
    source: str  # "presidio" | "comprehend" | "both"
    score: float


TOKEN_FOR = {
    "NAME": "[NAME]",
    "LOCATION": "[LOCATION]",
    "DATE": "[DATE]",
    "ID": "[ID]",
    "PHONE": "[PHONE]",
    "EMAIL": "[EMAIL]",
    "URL": "[URL]",
    "IP": "[IP]",
    "AGE": "[AGE]",
    "OCCUPATION": "[OCCUPATION]",
    "ORG": "[ORG]",
}

# Presidio entity -> normalised label. NRP (nationality / religion / political
# group) is not a Safe Harbor identifier and is deliberately absent.
PRESIDIO_LABELS = {
    "PERSON": "NAME",
    "LOCATION": "LOCATION",
    "DATE_TIME": "DATE",
    "PHONE_NUMBER": "PHONE",
    "EMAIL_ADDRESS": "EMAIL",
    "URL": "URL",
    "IP_ADDRESS": "IP",
    "US_SSN": "ID",
    "US_MBI": "ID",
    "US_NPI": "ID",
    "US_DRIVER_LICENSE": "ID",
    "US_PASSPORT": "ID",
    "US_BANK_NUMBER": "ID",
    "US_ITIN": "ID",
    "MEDICAL_LICENSE": "ID",
    "CREDIT_CARD": "ID",
    "IBAN_CODE": "ID",
    "ID": "ID",
    "US_ZIP": "LOCATION",
    "US_MRN": "ID",
    "US_PARTIAL_DATE": "DATE",
    "AGE": "AGE",
    "ORGANIZATION": "ORG",
}
# Comprehend Medical PHI type -> normalised label (all under the
# PROTECTED_HEALTH_INFORMATION category). No IP type exists; the rule layer
# carries (O).
COMPREHEND_LABELS = {
    "NAME": "NAME",
    "ADDRESS": "LOCATION",
    "AGE": "AGE",
    "DATE": "DATE",
    "PHONE_OR_FAX": "PHONE",
    "EMAIL": "EMAIL",
    "ID": "ID",
    "URL": "URL",
    "PROFESSION": "OCCUPATION",
}

_PLACEHOLDER = re.compile(r"^\[[A-Z_]+\]$")
_BARE_YEAR = re.compile(r"^(?:18|19|20)\d{2}$")
_DURATION = re.compile(
    r"^\d+(?:\.\d+)?\s*(?:-\s*)?(?:day|week|month|year|hour|minute|min|hr|wk|mo|yr)s?$",
    re.IGNORECASE,
)
_MONTH_WORD = re.compile(
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b", re.IGNORECASE
)
_AGE_NUMBER = re.compile(r"\d{1,3}")
# "45-year-old", "45 years old", "aged 45": a NER DATE that is really an age.
_AGE_SHAPE = re.compile(
    r"^(?:aged?\s*)?\d{1,3}\+?(?:[\s-]*(?:years?|yrs?|y/?o)(?:[\s-]*old)?)?$", re.IGNORECASE
)
# A span whose only digits are one four-digit year ("year 2026", "in 2026").
_YEAR_ONLY = re.compile(r"^\D*(?:18|19|20)\d{2}\D*$")
_ACRONYM = re.compile(r"^[A-Z]{2,5}$")
_KEEP_ORG = frozenset({"medicare", "medicaid", "cms", "ncci", "ama", "hhs"})
# Clinical / billing abbreviations a NER model mistakes for a name when the
# thing after them (a code) has been carved out: "Dx I48.91" -> "Dx".
_KEEP_ABBREV = frozenset(
    "dx pt rx hx tx sx fx bx dos dob eob era npi cpt icd hcpcs carc rarc mrn ssn pos em".split()
)


def _keep(label: str, snippet: str) -> bool:
    """Exceptions the rule itself permits, plus already-placed tokens."""
    s = snippet.strip()
    if _PLACEHOLDER.match(s) or s.startswith("90+"):
        return True
    if label == "DATE" and _AGE_SHAPE.match(s):
        label = "AGE"
    if label == "DATE":
        if _BARE_YEAR.match(s) or _DURATION.match(s):
            return True
        if _YEAR_ONLY.match(s) and not _MONTH_WORD.search(s):
            return True
        # "daily", "annual", "today", "last week": no digit, no month name ->
        # not an element of a date related to the individual.
        if not any(ch.isdigit() for ch in s) and not _MONTH_WORD.search(s):
            return True
    if label == "AGE":
        m = _AGE_NUMBER.search(s)
        if m and int(m.group(0)) < 90:
            return True
    if label in {"NAME", "ORG", "LOCATION"}:
        # A lone all-caps token of 2-5 letters is a form / code / cue acronym
        # (MRN, RARC, CPT, EOB, DOS, NPI) or a state abbreviation, not a name.
        # Real names in OCR'd caps are two tokens and the rule layer's slot and
        # the residual bigram scan cover those.
        if _ACRONYM.match(s) or s.lower().rstrip(".:") in _KEEP_ABBREV:
            return True
    if label == "ORG" and s.lower() in _KEEP_ORG:
        return True
    return False


def normalise(
    raw: Iterable[tuple[int, int, str, float]],
    text: str,
    source: str,
    mapping: dict[str, str],
    known_codes: frozenset[str] | None = None,
) -> list[Span]:
    """Map detector-native results to Spans: relabel, carve codes, apply the
    permitted exceptions. Unknown entity types are DROPPED — a new Comprehend
    or Presidio type is reviewed before it is trusted to redact anything."""
    out: list[Span] = []
    for start, end, entity, score in raw:
        label = mapping.get(entity)
        if label is None or end <= start:
            continue
        for s, e in carve_codes([(start, end)], text, known_codes):
            # Trim the span to its non-blank core so a token never swallows the
            # space before a code ("Mary Chen I48.91" -> "[NAME] I48.91").
            while s < e and text[s].isspace():
                s += 1
            while e > s and text[e - 1].isspace():
                e -= 1
            if s >= e or _keep(label, text[s:e]):
                continue
            out.append(Span(s, e, label, source, float(score)))
    return out


def merge_spans(spans: Sequence[Span]) -> list[Span]:
    """Union of overlapping or touching spans. The merged span carries the
    label of the highest-scoring member and source "both" when two detectors
    contributed."""
    ordered = sorted(spans, key=lambda s: (s.start, -s.end))
    merged: list[Span] = []
    for span in ordered:
        if merged and span.start <= merged[-1].end:
            last = merged[-1]
            best = span if span.score > last.score else last
            source = last.source if last.source == span.source else "both"
            merged[-1] = Span(last.start, max(last.end, span.end), best.label, source, best.score)
        else:
            merged.append(span)
    return merged


def apply_spans(text: str, spans: Sequence[Span]) -> str:
    out = text
    for span in sorted(merge_spans(spans), key=lambda s: s.start, reverse=True):
        out = out[: span.start] + TOKEN_FOR.get(span.label, "[REDACTED]") + out[span.end :]
    return out


def disagreement(a: Sequence[Span], b: Sequence[Span]) -> dict[str, int]:
    """Spans one detector found that the other did not overlap at all, by
    label. High counts on NAME / DATE / ID mean one detector is carrying the
    other on this record — the reviewer's attention goes there first, and a
    step change across exports is the signal that a model changed."""

    def _only(xs: Sequence[Span], ys: Sequence[Span]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for x in xs:
            if not any(y.start < x.end and x.start < y.end for y in ys):
                counts[x.label] = counts.get(x.label, 0) + 1
        return counts

    only_a, only_b = _only(a, b), _only(b, a)
    return {
        **{f"only_{k.lower()}_a": v for k, v in only_a.items()},
        **{f"only_{k.lower()}_b": v for k, v in only_b.items()},
    }


def _installed(name: str) -> str | None:
    try:
        return _pkg_version(name)
    except PackageNotFoundError:
        return None


# spaCy label -> Presidio entity for the general-domain NER (both engines).
# spaCy's default mapping drops ORG and DATE; we want both.
_SPACY_NER_CONFIGURATION = {
    # spaCy's default mapping drops ORG and DATE; we want both.
    "model_to_presidio_entity_mapping": {
        "PER": "PERSON",
        "PERSON": "PERSON",
        "NORP": "NRP",
        "FAC": "LOCATION",
        "LOC": "LOCATION",
        "GPE": "LOCATION",
        "LOCATION": "LOCATION",
        "ORG": "ORGANIZATION",
        "ORGANIZATION": "ORGANIZATION",
        "DATE": "DATE_TIME",
        "TIME": "DATE_TIME",
    },
    "labels_to_ignore": [
        "O",
        "CARDINAL",
        "EVENT",
        "LANGUAGE",
        "LAW",
        "MONEY",
        "ORDINAL",
        "PERCENT",
        "PRODUCT",
        "QUANTITY",
        "WORK_OF_ART",
    ],
    "low_confidence_score_multiplier": 0.4,
    "low_score_entity_names": [],
}


# --- Detector B: Presidio ----------------------------------------------------------


class PresidioDetector:
    """Presidio AnalyzerEngine with either the clinical transformer (production)
    or spaCy `en_core_web_lg` (laptop / CI) as the NER engine, every relevant
    pattern recognizer enabled, and the export's own pattern recognizers added.
    """

    source = "presidio"

    def __init__(
        self,
        *,
        engine: str = "transformers",
        spacy_model: str = "en_core_web_lg",
        transformer_model: str = "StanfordAIMI/stanford-deidentifier-base",
        score_threshold: float = 0.3,
        allow_list: Sequence[str] = (),
    ) -> None:
        if engine not in {"transformers", "spacy"}:
            raise DetectorUnavailable(f"unknown Presidio engine {engine!r}")
        self.engine = engine
        self.spacy_model = spacy_model
        self.transformer_model = transformer_model
        self.score_threshold = score_threshold
        self.allow_list = [a for a in allow_list if a and len(a.strip()) >= 2]
        # NCCI CPT/HCPCS set, set by the export: decides which five-digit runs
        # inside a detector span are codes to keep rather than ZIPs to remove.
        self.known_codes: frozenset[str] | None = None
        self._analyzer = self._build()

    # -- construction --

    def _build(self):
        try:
            import spacy
            from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
            from presidio_analyzer.nlp_engine import NlpEngineProvider
            from presidio_analyzer.predefined_recognizers import UsMbiRecognizer, UsNpiRecognizer
            from presidio_analyzer.recognizer_registry import RecognizerRegistry
        except ImportError as exc:
            raise DetectorUnavailable(
                "Presidio / spaCy are not installed (deid image stage or deid.lock)"
            ) from exc

        hf_recognizer = None
        if self.engine == "transformers":
            try:
                import torch  # noqa: F401
                import transformers  # noqa: F401
                from presidio_analyzer.predefined_recognizers.ner import HuggingFaceNerRecognizer
            except ImportError as exc:
                raise DetectorUnavailable(
                    "engine=transformers needs torch and transformers (deid image stage)"
                ) from exc
            if not spacy.util.is_package("en_core_web_sm"):
                raise DetectorUnavailable(
                    "en_core_web_sm (tokenizer for the pattern recognizers) is missing"
                )
            # The clinical model is driven through transformers' own pipeline
            # (Presidio's native recognizer), not through the spaCy bridge — the
            # bridge pins transformers <5, a line with open advisories, and its
            # token alignment is not needed: the pipeline returns char offsets.
            # Label set of the Stanford checkpoint -> Presidio entities.
            hf_recognizer = HuggingFaceNerRecognizer(
                model_name=self.transformer_model,
                supported_language="en",
                label_mapping={
                    "PATIENT": "PERSON",
                    "HCW": "PERSON",
                    "STAFF": "PERSON",
                    "HOSPITAL": "LOCATION",
                    "HOSP": "LOCATION",
                    "LOC": "LOCATION",
                    "VENDOR": "ORGANIZATION",
                    "PATORG": "ORGANIZATION",
                    "DATE": "DATE_TIME",
                    "ID": "ID",
                    "PHONE": "PHONE_NUMBER",
                    "AGE": "AGE",
                    "EMAIL": "EMAIL_ADDRESS",
                    "OTHERPHI": "ID",
                },
                threshold=self.score_threshold,
                aggregation_strategy="max",
                chunk_size=1200,
                chunk_overlap=120,
                device="cpu",
            )
            hf_recognizer.load()
            # A small spaCy pipeline for tokenisation / lemmas (the pattern
            # recognizers' context enhancer needs them). Its general-domain NER
            # stays on as a weak extra signal; the clinical model is the one
            # that carries the recall.
            configuration = {
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
                "ner_model_configuration": _SPACY_NER_CONFIGURATION,
            }
        else:
            if not spacy.util.is_package(self.spacy_model):
                raise DetectorUnavailable(f"spaCy model {self.spacy_model} is not installed")
            configuration = {
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": self.spacy_model}],
                "ner_model_configuration": _SPACY_NER_CONFIGURATION,
            }
        nlp_engine = NlpEngineProvider(nlp_configuration=configuration).create_engine()

        registry = RecognizerRegistry(supported_languages=["en"])
        registry.load_predefined_recognizers(languages=["en"], nlp_engine=nlp_engine)
        if hf_recognizer is not None:
            registry.add_recognizer(hf_recognizer)
        # Shipped disabled by default; exactly the identifiers our documents carry.
        registry.add_recognizer(UsMbiRecognizer())
        registry.add_recognizer(UsNpiRecognizer())
        # Our own. Low base scores + context words: the context enhancer lifts a
        # match to >= 0.4 only when a cue is nearby, so bare five-digit CPT codes
        # stay below the threshold while "ZIP 90210" and "MRN 48213" do not.
        registry.add_recognizer(
            PatternRecognizer(
                supported_entity="US_ZIP",
                patterns=[Pattern("zip", r"\b\d{5}(?:-\d{4})?\b", 0.05)],
                context=["zip", "zipcode", "postal", "address", "city", "state"],
            )
        )
        registry.add_recognizer(
            PatternRecognizer(
                supported_entity="US_MRN",
                patterns=[Pattern("mrn", r"\b[A-Za-z]{0,3}\d{4,10}\b", 0.05)],
                context=["mrn", "medical record", "chart", "account", "acct", "patient id"],
            )
        )
        registry.add_recognizer(
            PatternRecognizer(
                supported_entity="US_PARTIAL_DATE",
                patterns=[
                    Pattern(
                        "month-day",
                        r"\b(?:0?[1-9]|1[0-2])\s?[/-]\s?(?:0?[1-9]|[12]\d|3[01])\b(?!\s?[/-]\s?\d)",
                        0.4,
                    )
                ],
                context=["dos", "date", "seen", "admitted", "discharged", "visit", "on"],
            )
        )
        return AnalyzerEngine(
            registry=registry,
            nlp_engine=nlp_engine,
            supported_languages=["en"],
            default_score_threshold=self.score_threshold,
        )

    # -- interface --

    def version(self) -> dict:
        info = {
            "engine": self.engine,
            "presidio_analyzer": _installed("presidio-analyzer"),
            "spacy": _installed("spacy"),
        }
        if self.engine == "transformers":
            info["transformer_model"] = self.transformer_model
            info["transformers"] = _installed("transformers")
            info["torch"] = _installed("torch")
            info["model_manifest"] = os.environ.get("DEID_MODEL_MANIFEST_SHA256")
        else:
            info["spacy_model"] = self.spacy_model
            info["spacy_model_version"] = _installed(self.spacy_model)
        return info

    def detect(self, text: str) -> list[Span]:
        try:
            results = self._analyzer.analyze(
                text=text,
                language="en",
                score_threshold=self.score_threshold,
                allow_list=self.allow_list or None,
            )
        except Exception as exc:  # noqa: BLE001 — any failure aborts the export
            raise DetectorError(f"Presidio analyze failed: {type(exc).__name__}") from exc
        return normalise(
            ((r.start, r.end, r.entity_type, r.score) for r in results),
            text,
            self.source,
            PRESIDIO_LABELS,
            self.known_codes,
        )


# --- Detector A: Amazon Comprehend Medical -----------------------------------------


class ComprehendDetector:
    """Amazon Comprehend Medical DetectPHI over the text, chunked under the
    20,000-byte request limit on paragraph boundaries. Every entity at or above
    `score_threshold` is a span (AWS recommends a LOW threshold for PHI use).
    A truncated response (PaginationToken present — DetectPHI cannot resume) or
    any client error is fatal."""

    source = "comprehend"
    MAX_BYTES = 18_000

    def __init__(self, client=None, *, region: str = "us-east-1", score_threshold: float = 0.2):
        if client is None:
            try:
                import boto3
                from botocore.client import Config

                client = boto3.client(
                    "comprehendmedical",
                    region_name=region,
                    config=Config(
                        connect_timeout=10,
                        read_timeout=60,
                        retries={"max_attempts": 5, "mode": "adaptive"},
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                raise DetectorUnavailable("comprehendmedical client unavailable") from exc
        self._client = client
        self.score_threshold = score_threshold
        self.known_codes: frozenset[str] | None = None
        self.model_versions: set[str] = set()
        self.units = 0
        self.calls = 0

    def version(self) -> dict:
        return {
            "service": "comprehendmedical.DetectPHI",
            "model_versions": sorted(self.model_versions),
            "calls": self.calls,
            "units": self.units,
            "score_threshold": self.score_threshold,
        }

    @classmethod
    def chunks(cls, text: str) -> list[tuple[int, str]]:
        """(offset, piece) pairs each under MAX_BYTES of UTF-8, split on newlines
        where possible so an entity is not cut in half."""
        if len(text.encode("utf-8")) <= cls.MAX_BYTES:
            return [(0, text)]
        pieces: list[tuple[int, str]] = []
        start = 0
        while start < len(text):
            end = start
            # Grow on newline boundaries while under the limit.
            candidate = end
            for m in re.finditer(r"\n", text[start:]):
                nxt = start + m.end()
                if len(text[start:nxt].encode("utf-8")) > cls.MAX_BYTES:
                    break
                candidate = nxt
            if candidate <= start:
                # One paragraph longer than the limit: hard-cut by characters.
                candidate = start + 1
                while (
                    candidate < len(text)
                    and len(text[start : candidate + 1].encode("utf-8")) <= cls.MAX_BYTES
                ):
                    candidate += 1
            pieces.append((start, text[start:candidate]))
            start = candidate
        return pieces

    def detect(self, text: str) -> list[Span]:
        raw: list[tuple[int, int, str, float]] = []
        for offset, piece in self.chunks(text):
            if not piece.strip():
                continue
            try:
                resp = self._client.detect_phi(Text=piece)
            except Exception as exc:  # noqa: BLE001 — throttling, auth, network: all fatal
                raise DetectorError(f"DetectPHI failed: {type(exc).__name__}") from exc
            self.calls += 1
            self.units += max(1, -(-len(piece) // 100))
            if resp.get("PaginationToken"):
                raise DetectorError("DetectPHI returned a truncated result (PaginationToken)")
            if resp.get("ModelVersion"):
                self.model_versions.add(str(resp["ModelVersion"]))
            for ent in resp.get("Entities", []):
                if float(ent.get("Score", 0)) < self.score_threshold:
                    continue
                raw.append(
                    (
                        offset + int(ent["BeginOffset"]),
                        offset + int(ent["EndOffset"]),
                        str(ent.get("Type", "")),
                        float(ent.get("Score", 0)),
                    )
                )
        return normalise(raw, text, self.source, COMPREHEND_LABELS, self.known_codes)


# --- orchestration --------------------------------------------------------------------


def redact_with_detectors(
    text: str | None, detectors: Sequence[object]
) -> tuple[str | None, dict[str, int]]:
    """Run every detector on the same text, union the spans, substitute tokens.
    Returns (redacted text, per-label counts and the A/B disagreement)."""
    if not text:
        return text, {}
    found: dict[str, list[Span]] = {}
    for det in detectors:
        found[det.source] = det.detect(text)  # type: ignore[attr-defined]
    all_spans = [s for spans in found.values() for s in spans]
    stats: dict[str, int] = {}
    for span in all_spans:
        stats[f"{span.source}_{span.label.lower()}"] = (
            stats.get(f"{span.source}_{span.label.lower()}", 0) + 1
        )
    if "presidio" in found and "comprehend" in found:
        stats.update(disagreement(found["comprehend"], found["presidio"]))
    return apply_spans(text, all_spans), stats


# --- model integrity --------------------------------------------------------------------


def _hub_cache(hf_cache: Path | None) -> Path:
    if hf_cache is not None:
        return hf_cache
    return Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"


def snapshot_dir(manifest_path: Path, hf_cache: Path | None = None) -> Path:
    """The cached snapshot directory for the manifest's model @ revision. The
    detector is pointed at this PATH rather than the repo id, so loading never
    consults the hub (no refs/ lookup, no network) and can only ever load the
    revision the manifest names."""
    manifest = json.loads(manifest_path.read_text())
    repo_dir = _hub_cache(hf_cache) / ("models--" + manifest["model"].replace("/", "--"))
    return repo_dir / "snapshots" / manifest["revision"]


def verify_model_manifest(manifest_path: Path, hf_cache: Path | None = None) -> str:
    """Fail closed unless every file of the transformer snapshot in the Hugging
    Face cache matches the sha256 recorded in the manifest. The model is the
    detector; a substituted weight file is a substituted detector. Returns the
    manifest's own sha256 so the export can record which manifest it ran under.
    """
    manifest = json.loads(manifest_path.read_text())
    snapshot = snapshot_dir(manifest_path, hf_cache)
    if not snapshot.is_dir():
        raise DetectorUnavailable(
            f"transformer snapshot {manifest['model']}@{manifest['revision'][:12]} "
            "is not in the cache"
        )
    for name, expected in manifest["files"].items():
        path = snapshot / name
        if not path.exists():
            raise DetectorUnavailable(f"model file missing: {name}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != expected:
            raise DetectorUnavailable(f"model file {name} does not match the manifest")
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    os.environ["DEID_MODEL_MANIFEST_SHA256"] = manifest_sha
    return manifest_sha
