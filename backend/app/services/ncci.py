"""NCCI edit lookups: PTP bundling conflicts and MUE unit limits.

Reads the reference tables loaded by ``app.scripts.load_ncci``. The evaluation
rules are pure functions (unit-testable without a database); the async functions
wrap them with the table lookups.

Semantics (NCCI Policy Manual Ch. 1 + MLN901346):

* A PTP edit denies the column-2 code when billed with the column-1 code on the
  same date of service. Modifier indicator 0 = never bypassable; 1 = bypassable
  with an NCCI-associated modifier on the column-2 line; 9 = the edit was
  retroactively withdrawn (deletion_date == effective_date) and is a no-op.
* Active window is [effective_date, deletion_date) — exclusive end, so a
  retroactive withdrawal matches no date of service.
* MUE: MAI 1 is a claim-line edit (units compared per line); MAI 2/3 are
  date-of-service edits (units summed across all lines of the code). MAI 2 is
  policy-absolute; MAI 3 is clinical and payable on appeal with evidence.
* This is the *practitioner* edit set (CMS-1500 professional claims). Commercial
  payers largely mirror Medicare NCCI but can differ — callers must present
  results as Medicare-baseline flags, not payer truth.
"""

import logging
from dataclasses import dataclass
from datetime import date

from sqlalchemy import desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import NcciLoad, NcciMue, NcciPtpEdit

logger = logging.getLogger(__name__)

# NCCI PTP-associated modifiers, verbatim from NCCI Policy Manual Ch. 1 §E.
# Explicitly NOT associated (do not bypass an edit): 22, 76, 77.
NCCI_ASSOCIATED_MODIFIERS = frozenset(
    # anatomic
    ["E1", "E2", "E3", "E4", "FA", "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9"]
    + ["TA", "T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9"]
    + ["LT", "RT", "LC", "LD", "RC", "LM", "RI"]
    # global surgery
    + ["24", "25", "57", "58", "78", "79"]
    # other
    + ["27", "59", "91", "XE", "XS", "XP", "XU"]
)


@dataclass(frozen=True)
class ClaimLine:
    """One billed line, normalized: 5-character HCPCS/CPT, uppercased modifiers."""

    cpt: str
    modifiers: tuple[str, ...] = ()
    units: int = 1


@dataclass(frozen=True)
class PtpFinding:
    column1: str
    column2: str
    modifier_indicator: int
    rationale: str | None
    bypassed: bool  # indicator 1 and an associated modifier is present on the column-2 line


@dataclass(frozen=True)
class MueFinding:
    hcpcs: str
    units_billed: int
    mue_value: int
    mai: int
    rationale: str | None


@dataclass(frozen=True)
class NcciResult:
    ptp: tuple[PtpFinding, ...] = ()
    mue: tuple[MueFinding, ...] = ()
    # Version tags of the loads that served the lookups ("ptp v322r0 / mue 2026Q3"),
    # stamped onto risk reports for auditability. None when no data is loaded.
    version_tag: str | None = None
    data_available: bool = False


def normalize_code(raw: str) -> str:
    """Uppercase, strip, and drop anything after the first non-alphanumeric —
    extraction sometimes yields "99213-25"; the table key is the bare code."""
    code = raw.strip().upper()
    for i, ch in enumerate(code):
        if not ch.isalnum():
            return code[:i]
    return code


def is_active(effective: date, deletion: date | None, dos: date) -> bool:
    """[effective, deletion) — a retroactively withdrawn edit (deletion ==
    effective) is active on no date."""
    if dos < effective:
        return False
    return deletion is None or dos < deletion


def evaluate_ptp_pair(
    modifier_indicator: int, column2_modifiers: tuple[str, ...]
) -> PtpFinding | None:
    """Pure disposition for one active edit pair; caller fills the code fields.
    Returns None when the row is a no-op (indicator 9)."""
    if modifier_indicator == 9:
        return None
    bypassed = modifier_indicator == 1 and any(
        m in NCCI_ASSOCIATED_MODIFIERS for m in column2_modifiers
    )
    return PtpFinding(
        column1="",
        column2="",
        modifier_indicator=modifier_indicator,
        rationale=None,
        bypassed=bypassed,
    )


def evaluate_mue(hcpcs: str, lines: list[ClaimLine], mue_value: int, mai: int) -> int | None:
    """Units in violation for one code, or None if within the limit.

    MAI 1 (line edit): each line judged alone — return the max single-line
    units if any line exceeds the MUE. MAI 2/3 (date-of-service edits): sum
    units across all lines of the code first.
    """
    units_per_line = [line.units for line in lines if line.cpt == hcpcs]
    if not units_per_line:
        return None
    if mai == 1:
        worst = max(units_per_line)
        return worst if worst > mue_value else None
    total = sum(units_per_line)
    return total if total > mue_value else None


async def latest_version_tag(session: AsyncSession) -> str | None:
    """Combined tag of the newest PTP and MUE loads, e.g. "ptp v322r0 / mue 2026Q3"."""
    parts: list[str] = []
    for kind, label in (("ptp", "version_tag"), ("mue", "quarter")):
        row = await session.scalar(
            select(NcciLoad)
            .where(NcciLoad.kind == kind)
            .order_by(desc(NcciLoad.loaded_at))
            .limit(1)
        )
        if row is not None:
            parts.append(f"{kind} {getattr(row, label)}")
    return " / ".join(parts) if parts else None


async def ptp_conflicts(
    session: AsyncSession, lines: list[ClaimLine], date_of_service: date | None
) -> list[PtpFinding]:
    """Active PTP edits among the billed codes on the date of service.

    DOS defaults to today when the claim didn't yield one — pre-checks screen
    claims about to be submitted, so "adjudicated under current edits" is the
    right fallback (callers surface a verify-the-DOS note separately).
    """
    dos = date_of_service or date.today()
    codes = {normalize_code(line.cpt) for line in lines if line.cpt.strip()}
    if len(codes) < 2:
        return []
    mods_by_code: dict[str, tuple[str, ...]] = {}
    for line in lines:
        code = normalize_code(line.cpt)
        mods_by_code[code] = mods_by_code.get(code, ()) + tuple(
            m.strip().upper() for m in line.modifiers
        )

    rows = (
        await session.scalars(
            select(NcciPtpEdit).where(
                NcciPtpEdit.column1.in_(codes),
                NcciPtpEdit.column2.in_(codes),
                NcciPtpEdit.modifier_indicator != 9,
                NcciPtpEdit.effective_date <= dos,
                or_(NcciPtpEdit.deletion_date.is_(None), NcciPtpEdit.deletion_date > dos),
            )
        )
    ).all()

    findings: list[PtpFinding] = []
    for row in rows:
        if row.column1 == row.column2:
            continue
        disposition = evaluate_ptp_pair(row.modifier_indicator, mods_by_code.get(row.column2, ()))
        if disposition is None:
            continue
        findings.append(
            PtpFinding(
                column1=row.column1,
                column2=row.column2,
                modifier_indicator=row.modifier_indicator,
                rationale=row.rationale,
                bypassed=disposition.bypassed,
            )
        )
    return findings


async def mue_violations(session: AsyncSession, lines: list[ClaimLine]) -> list[MueFinding]:
    """MUE unit violations among the billed lines, judged against the newest
    loaded quarter — pre-checks concern claims about to be adjudicated, so
    current values are the correct ones (history is retained for appeal work)."""
    latest_quarter = await session.scalar(
        select(NcciMue.effective_quarter).order_by(desc(NcciMue.effective_quarter)).limit(1)
    )
    if latest_quarter is None:
        return []
    codes = {normalize_code(line.cpt) for line in lines if line.cpt.strip()}
    if not codes:
        return []
    normalized = [
        ClaimLine(cpt=normalize_code(line.cpt), modifiers=line.modifiers, units=line.units)
        for line in lines
    ]
    rows = (
        await session.scalars(
            select(NcciMue).where(
                NcciMue.hcpcs.in_(codes), NcciMue.effective_quarter == latest_quarter
            )
        )
    ).all()
    findings: list[MueFinding] = []
    for row in rows:
        violating_units = evaluate_mue(row.hcpcs, normalized, row.mue_value, row.mai)
        if violating_units is not None:
            findings.append(
                MueFinding(
                    hcpcs=row.hcpcs,
                    units_billed=violating_units,
                    mue_value=row.mue_value,
                    mai=row.mai,
                    rationale=row.rationale,
                )
            )
    return findings


async def check_claim(
    session: AsyncSession, lines: list[ClaimLine], date_of_service: date | None
) -> NcciResult:
    """Full deterministic pass for a claim. ``data_available`` is False before
    the first load — callers must degrade to advisory wording, never imply a
    clean NCCI result from an empty table."""
    tag = await latest_version_tag(session)
    if tag is None:
        return NcciResult()
    ptp = await ptp_conflicts(session, lines, date_of_service)
    mue = await mue_violations(session, lines)
    logger.info(
        "ncci check complete",
        extra={
            "context": {
                "lines": len(lines),
                "ptp_findings": len(ptp),
                "mue_findings": len(mue),
                "version": tag,
            }
        },
    )
    return NcciResult(ptp=tuple(ptp), mue=tuple(mue), version_tag=tag, data_available=True)


async def ptp_indicator_for_pair(
    session: AsyncSession, code_a: str, code_b: str, date_of_service: date | None
) -> PtpFinding | None:
    """Appeal-side CO-97 helper: the active edit (either direction) between two
    codes, or None when no edit exists / no data is loaded — in which case the
    caller keeps today's manual-verification wording."""
    a, b = normalize_code(code_a), normalize_code(code_b)
    if not a or not b or a == b:
        return None
    dos = date_of_service or date.today()
    row = await session.scalar(
        select(NcciPtpEdit)
        .where(
            or_(
                (NcciPtpEdit.column1 == a) & (NcciPtpEdit.column2 == b),
                (NcciPtpEdit.column1 == b) & (NcciPtpEdit.column2 == a),
            ),
            NcciPtpEdit.modifier_indicator != 9,
            NcciPtpEdit.effective_date <= dos,
            or_(NcciPtpEdit.deletion_date.is_(None), NcciPtpEdit.deletion_date > dos),
        )
        .limit(1)
    )
    if row is None:
        return None
    return PtpFinding(
        column1=row.column1,
        column2=row.column2,
        modifier_indicator=row.modifier_indicator,
        rationale=row.rationale,
        bypassed=False,
    )
