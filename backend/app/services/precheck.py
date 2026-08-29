"""Pre-check pipeline services: extraction, deterministic NCCI pass, risk report.

Mirrors the appeal services' discipline: forced JSON + Pydantic + one retry via
claude_client.complete_json, member-ID hashing, PHI-free logging (check ids,
severities, and counts only — finding titles/explanations are model text derived
from clinical notes and never reach a log line), and no silent failures.

Server-side guardrails (the pre-check mirror of never_appealable_codes):
deterministic NCCI findings are merged into the report verbatim — the model
receives them as context and can annotate them, never remove or downgrade them —
and the headline risk band is derived here from finding severities, never taken
from model output.
"""

import logging
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import hashing
from app.models import Case, Extraction, RiskReport
from app.prompts import precheck_extraction_prompt, precheck_review_prompt
from app.schemas.precheck import PrecheckExtractionResult, RiskReviewResult
from app.services import claude_client, ncci
from app.services.analysis import read_clinical_text
from app.services.extraction import _read_extracted_text

logger = logging.getLogger(__name__)


class NoBillableLinesError(RuntimeError):
    """The draft claim yielded no billable lines — almost always a wrong or
    unreadable upload. Typed so _mark_error records a PHI-free name the frontend
    can translate into friendly copy."""


def derive_band(findings: list[dict]) -> str | None:
    """Headline risk from finding severities — server-derived, never model-set.
    None (no findings) renders as "no flags found"; info-only lands at low."""
    severities = {f.get("severity") for f in findings}
    if "high" in severities:
        return "high"
    if "medium" in severities:
        return "moderate"
    if severities:
        return "low"
    return None


def deterministic_findings(result: ncci.NcciResult, *, dos_missing: bool) -> list[dict]:
    """NCCI engine output as finding dicts, same shape as the model's (source
    'ncci'). Severity mapping is fixed policy, documented per branch."""
    findings: list[dict] = []
    if not result.data_available:
        findings.append(
            {
                "check_id": "ncci_unavailable",
                "severity": "info",
                "title": "NCCI bundling and unit checks were skipped",
                "predicted_carc": None,
                "explanation": (
                    "The CMS NCCI edit tables are not loaded yet, so deterministic "
                    "bundling (PTP) and unit (MUE) checks did not run for this "
                    "pre-check."
                ),
                "suggested_fix": None,
                "source": "ncci",
            }
        )
        return findings

    if dos_missing:
        findings.append(
            {
                "check_id": "dos_missing",
                "severity": "info",
                "title": "No date of service found — NCCI edits assumed today's date",
                "predicted_carc": None,
                "explanation": (
                    "The draft claim did not yield a date of service, so bundling "
                    "and unit edits were evaluated against the currently effective "
                    "CMS tables."
                ),
                "suggested_fix": "Verify the date of service on the claim form.",
                "source": "ncci",
            }
        )

    for hit in result.ptp:
        if hit.bypassed:
            findings.append(
                {
                    "check_id": "ncci_ptp",
                    "severity": "info",
                    "title": (
                        f"{hit.column2} is bundled into {hit.column1}, but a modifier "
                        "bypasses the edit"
                    ),
                    "predicted_carc": None,
                    "explanation": (
                        f"CMS NCCI lists {hit.column2} as not separately payable with "
                        f"{hit.column1} (modifier indicator 1), and an NCCI-associated "
                        "modifier is present on the line. Ensure the documentation "
                        "supports the distinct service the modifier asserts."
                        + (f" Edit rationale: {hit.rationale}." if hit.rationale else "")
                    ),
                    "suggested_fix": None,
                    "source": "ncci",
                }
            )
        elif hit.modifier_indicator == 1:
            findings.append(
                {
                    "check_id": "ncci_ptp",
                    "severity": "high",
                    "title": (
                        f"{hit.column2} will be denied as bundled into {hit.column1} "
                        "unless a modifier is added"
                    ),
                    "predicted_carc": "CO-97",
                    "explanation": (
                        f"CMS NCCI lists {hit.column2} as not separately payable with "
                        f"{hit.column1} on the same date of service (modifier "
                        "indicator 1 — bypassable). No NCCI-associated modifier is on "
                        f"the {hit.column2} line."
                        + (f" Edit rationale: {hit.rationale}." if hit.rationale else "")
                    ),
                    "suggested_fix": (
                        "If the services were genuinely distinct (separate session, "
                        "site, lesion, or incision), add the appropriate NCCI-"
                        "associated modifier (e.g. XE/XS/XP/XU or 59) to the "
                        f"{hit.column2} line and ensure the note documents the "
                        "distinction. Otherwise remove the line."
                    ),
                    "source": "ncci",
                }
            )
        else:  # indicator 0 — never bypassable
            findings.append(
                {
                    "check_id": "ncci_ptp",
                    "severity": "high",
                    "title": (
                        f"{hit.column2} cannot be billed with {hit.column1} "
                        "(non-bypassable bundling edit)"
                    ),
                    "predicted_carc": "CO-97",
                    "explanation": (
                        f"CMS NCCI lists {hit.column2} as never separately payable "
                        f"with {hit.column1} on the same date of service (modifier "
                        "indicator 0). No modifier bypasses this edit."
                        + (f" Edit rationale: {hit.rationale}." if hit.rationale else "")
                    ),
                    "suggested_fix": (
                        f"Remove the {hit.column2} line, or bill the services on "
                        "different dates of service if that reflects what happened."
                    ),
                    "source": "ncci",
                }
            )

    for violation in result.mue:
        if violation.mai == 2:
            severity = "high"
            tail = (
                "This is a date-of-service policy edit (MAI 2): units above the "
                "limit are considered impossible per CMS policy, and units-based "
                "appeals are not entertained."
            )
        elif violation.mai == 3:
            severity = "medium"
            tail = (
                "This is a clinical date-of-service edit (MAI 3): higher units are "
                "payable only with medical-review evidence, so expect a denial "
                "without strong documentation."
            )
        else:
            severity = "medium"
            tail = (
                "This is a claim-line edit (MAI 1): units may be split across "
                "lines with appropriate modifiers when clinically distinct."
            )
        findings.append(
            {
                "check_id": "ncci_mue",
                "severity": severity,
                "title": (
                    f"{violation.hcpcs}: {violation.units_billed} units exceeds the "
                    f"Medicare MUE limit of {violation.mue_value}/day"
                ),
                "predicted_carc": "CO-151",
                "explanation": (
                    f"CMS publishes a Medically Unlikely Edit of {violation.mue_value} "
                    f"unit(s) per day for {violation.hcpcs}; this claim bills "
                    f"{violation.units_billed}. {tail}"
                    + (f" MUE rationale: {violation.rationale}." if violation.rationale else "")
                ),
                "suggested_fix": (
                    "Verify the units against the documentation; correct a data-entry "
                    "error, or ensure the record clearly supports the medical "
                    "necessity of every unit."
                ),
                "source": "ncci",
            }
        )
    return findings


def deterministic_edits(result: ncci.NcciResult) -> list[dict]:
    """Diff-style proposed edits derived straight from the NCCI engine — no
    model judgment involved, so they merge ahead of (and immune to) the model's
    own edits. One line per change, imperative, PM-system brief."""
    edits: list[dict] = []
    for hit in result.ptp:
        if hit.bypassed:
            continue
        if hit.modifier_indicator == 1:
            edits.append(
                {
                    "kind": "add_modifier",
                    "target": hit.column2,
                    "instruction": (
                        f"Add modifier 59/XS/XE to {hit.column2} if distinct from "
                        f"{hit.column1} — otherwise remove the line"
                    ),
                    # 59 is the default the UI offers; the biller picks the
                    # X{E,S,P,U} modifier when a specific one fits.
                    "value": "59",
                    "source": "ncci",
                }
            )
        else:
            edits.append(
                {
                    "kind": "remove_line",
                    "target": hit.column2,
                    "instruction": (
                        f"Remove {hit.column2} — never payable with {hit.column1} "
                        "on the same day"
                    ),
                    "value": None,
                    "source": "ncci",
                }
            )
    for violation in result.mue:
        # The limit is a ceiling, never a count to write: MAI 1 judges each
        # line alone, MAI 2/3 the day's total across lines (ncci.evaluate_mue).
        # The patcher needs to know which — a per-day limit that no single
        # line exceeds cannot be met by rewriting every line to the limit.
        per_line = violation.mai == 1
        edits.append(
            {
                "kind": "change_units",
                "target": violation.hcpcs,
                "instruction": (
                    f"Reduce {violation.hcpcs} from {violation.units_billed} to "
                    f"≤{violation.mue_value} units per line"
                    if per_line
                    else f"Reduce {violation.hcpcs} from {violation.units_billed} to "
                    f"≤{violation.mue_value} units/day"
                ),
                "value": str(violation.mue_value),
                "cap": "line" if per_line else "day",
                "source": "ncci",
            }
        )
    return edits


def claim_lines_from_extraction(extraction: Extraction) -> list[ncci.ClaimLine]:
    """The NCCI engine's view of the extracted claim lines (stored in
    extracted_json by run_precheck_extraction)."""
    raw_lines = (extraction.extracted_json or {}).get("claim_lines") or []
    lines: list[ncci.ClaimLine] = []
    for raw in raw_lines:
        if not isinstance(raw, dict) or not str(raw.get("cpt") or "").strip():
            continue
        lines.append(
            ncci.ClaimLine(
                cpt=str(raw["cpt"]),
                modifiers=tuple(str(m) for m in raw.get("modifiers") or []),
                units=int(raw.get("units") or 1),
            )
        )
    return lines


async def run_precheck_extraction(session: AsyncSession, case: Case) -> Extraction:
    """Extract structured claim lines from the draft claim + notes, persist the
    extractions row (line detail in extracted_json; flat code arrays for the
    shared detail UI), and denormalize onto the case. Denial-only fields
    (denial_date, appeal_deadline, CARC codes) stay empty by construction."""
    texts = await _read_extracted_text(session, case)
    user_prompt = precheck_extraction_prompt.build_user_prompt(
        texts.get("claim", ""), texts.get("clinical", "")
    )

    outcome = await claude_client.complete_json(
        case_id=case.id,
        purpose="extraction",
        prompt_version=precheck_extraction_prompt.VERSION,
        system=precheck_extraction_prompt.SYSTEM,
        user_prompt=user_prompt,
        schema=PrecheckExtractionResult,
    )
    result: PrecheckExtractionResult = outcome.data

    if not any(line.cpt.strip() for line in result.claim_lines):
        # Hard rule 9: an unreadable claim is an error, not an empty "success".
        raise NoBillableLinesError("draft claim yielded no billable lines")

    # Same member-ID minimization as the appeal path (hard rule 5).
    member_id_hash = None
    if result.member_id:
        if hashing.is_configured():
            member_id_hash = hashing.keyed_hash(
                result.member_id,
                purpose=hashing.MEMBER_ID,
                scope=str(case.practice_id),
            )
        else:
            logger.warning(
                "member_id_hash omitted: PHI_HASH_PEPPER is not configured",
                extra={"context": {"case_id": str(case.id)}},
            )
    confidence = (
        Decimal(str(round(result.confidence, 2))) if result.confidence is not None else None
    )

    def _dedupe(values: list[str]) -> list[str]:
        return list(dict.fromkeys(v for v in values if v))

    lines = result.claim_lines
    extraction = Extraction(
        case_id=case.id,
        payer_name=result.payer_name,
        plan_type=result.plan_type,
        claim_number=result.claim_number,
        carc_codes=[],
        rarc_codes=[],
        group_codes=[],
        cpt_codes=_dedupe([line.cpt for line in lines]),
        icd10_codes=_dedupe(result.icd10_codes + [c for line in lines for c in line.icd10]),
        modifiers=_dedupe([m for line in lines for m in line.modifiers]),
        pos_codes=_dedupe([line.pos for line in lines if line.pos]),
        date_of_service=result.date_of_service,
        billed_amount_cents=result.billed_amount_cents,
        extracted_json=result.model_dump(mode="json", exclude={"member_id"}),
        confidence=confidence,
        model_run_id=outcome.model_run_id,
    )
    session.add(extraction)

    case.payer_name = result.payer_name
    case.plan_type = result.plan_type
    case.claim_number = result.claim_number
    case.member_id_hash = member_id_hash
    case.patient_initials = result.patient_initials
    case.date_of_service = result.date_of_service
    case.billed_amount_cents = result.billed_amount_cents

    await session.flush()
    logger.info(
        "precheck extraction complete",
        extra={
            "context": {
                "case_id": str(case.id),
                "claim_lines": len(lines),
                "input_tokens": outcome.input_tokens,
                "output_tokens": outcome.output_tokens,
            }
        },
    )
    return extraction


async def run_risk_report(session: AsyncSession, case: Case) -> RiskReport:
    """Deterministic NCCI pass + documentation-review model call, merged into
    the risk_reports row. Ends the pre-check pipeline: sets status='ready'."""
    extraction = await session.scalar(
        select(Extraction)
        .where(Extraction.case_id == case.id)
        .order_by(Extraction.created_at.desc())
    )
    if extraction is None:
        raise RuntimeError("risk report requested before extraction")

    lines = claim_lines_from_extraction(extraction)
    ncci_result = await ncci.check_claim(session, lines, case.date_of_service)
    det_findings = deterministic_findings(ncci_result, dos_missing=case.date_of_service is None)

    clinical_text = await read_clinical_text(session, case)
    user_prompt = precheck_review_prompt.build_user_prompt(
        extraction.extracted_json or {}, det_findings, clinical_text
    )
    outcome = await claude_client.complete_json(
        case_id=case.id,
        purpose="pre_check_review",
        prompt_version=precheck_review_prompt.VERSION,
        system=precheck_review_prompt.SYSTEM,
        user_prompt=user_prompt,
        schema=RiskReviewResult,
        max_tokens=3000,
    )
    review: RiskReviewResult = outcome.data
    if review.dropped_count:
        # Ids/counts only — finding text derives from clinical notes (hard rule 2).
        logger.warning(
            "precheck review findings dropped (unknown check_id)",
            extra={"context": {"case_id": str(case.id), "dropped": review.dropped_count}},
        )

    model_findings = [f.model_dump(mode="json") for f in review.findings]
    # Deterministic findings/edits first and verbatim — table logic outranks
    # the model, and its edits can never displace the engine's.
    findings = det_findings + model_findings
    proposed_edits = deterministic_edits(ncci_result) + [
        e.model_dump(mode="json") for e in review.proposed_edits
    ]

    report = RiskReport(
        case_id=case.id,
        overall_risk_band=derive_band(findings),
        findings=findings,
        proposed_edits=proposed_edits,
        deterministic_count=len(det_findings),
        model_count=len(model_findings),
        ncci_version_tag=ncci_result.version_tag,
        model_run_id=outcome.model_run_id,
    )
    session.add(report)
    case.status = "ready"
    await session.flush()
    logger.info(
        "risk report complete",
        extra={
            "context": {
                "case_id": str(case.id),
                "band": report.overall_risk_band,
                "deterministic": report.deterministic_count,
                "model": report.model_count,
                "checks": sorted({f["check_id"] for f in findings}),
                "ncci_version": report.ncci_version_tag,
                "input_tokens": outcome.input_tokens,
                "output_tokens": outcome.output_tokens,
            }
        },
    )
    return report
