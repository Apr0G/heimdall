"""Download and load the CMS NCCI practitioner PTP + MUE files into RDS.

One-off in-VPC ECS task (the DB is private), scheduled monthly by
``.github/workflows/load-ncci.yml``::

    python -m app.scripts.load_ncci

Design notes (grounded in the actual 2026 Q3 files):

* URLs are discovered from the CMS landing pages, never hardcoded — the version
  suffix (``v322r0`` → ``r1`` on mid-quarter replacement files) and the 4-way
  practitioner PTP file split boundaries both drift. The ``/license/ama?file=…``
  click-through wraps the real ``/files/zip/…`` path; discovery handles both
  forms. (The AMA license question itself is a legal matter tracked in the
  pre-check plan, not something this script can solve.)
* PTP: 4 zips per quarter, tab-delimited TXT inside, ~2.63M cumulative rows
  including full history back to 1996. Each quarterly set fully REPLACES the
  last — CMS rewrites history (retroactive withdrawals arrive as
  deletion_date == effective_date + indicator 9), so the load is
  delete-then-insert in one transaction, never an append.
* MUE (practitioner services table): 1 zip, CSV in latin-1 (the ``®`` char),
  MAI arrives as "3 Date of Service Edit: Clinical" — the leading digit is the
  value. Snapshot semantics: rows are keyed by (hcpcs, quarter) and each load
  adds its quarter (idempotently replacing the same quarter on re-run).
* Refuses loads that shrink >10% vs the previous recorded load — a truncated
  download must not silently replace a full table.
* Idempotent per version: a (kind, quarter, version_tag) already in ncci_loads
  is skipped unless FORCE=1.

No PHI anywhere in this path; logs print counts and version tags only.
"""

import asyncio
import csv
import hashlib
import io
import os
import re
import zipfile
from dataclasses import dataclass
from datetime import date, datetime

import httpx
from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models import NcciLoad, NcciMue, NcciPtpEdit

PTP_PAGE = (
    "https://www.cms.gov/medicare/coding-billing/"
    "national-correct-coding-initiative-ncci-edits/"
    "medicare-ncci-procedure-procedure-ptp-edits"
)
MUE_PAGE = (
    "https://www.cms.gov/medicare/coding-billing/"
    "national-correct-coding-initiative-ncci-edits/"
    "medicare-ncci-medically-unlikely-edits-mues"
)
# cms.gov 403s default library user agents.
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) heimdall-ncci-loader"

_PTP_ZIP_RE = re.compile(
    r"/files/zip/medicare-ncci-(\d{4})q(\d)-practitioner-ptp-edits-" r"(ccipra-v\d+r\d+)-f(\d)\.zip"
)
# The full practitioner table only — the page also lists facility/DME tables
# and per-type "quarterly additions/deletions" change files, none of which may
# ever be loaded as the table.
_MUE_ZIP_RE = re.compile(
    r"/files/zip/medicare-ncci-(\d{4})-q(\d)-practitioner-services-mue-table\.zip"
)
_DATE_RE = re.compile(r"^\d{8}$")

_BATCH = 10_000
_MIN_PTP_ROWS = 2_000_000
_MIN_MUE_ROWS = 14_000
_MAX_SHRINK = 0.10


@dataclass(frozen=True)
class PtpRow:
    column1: str
    column2: str
    effective_date: date
    deletion_date: date | None
    modifier_indicator: int
    rationale: str | None


@dataclass(frozen=True)
class MueRow:
    hcpcs: str
    mue_value: int
    mai: int
    rationale: str | None


def discover_ptp_urls(page_html: str) -> tuple[str, list[str]]:
    """(version tag like "2026Q3-v322r0", absolute zip URLs f1..fN, deduped).

    Picks the newest (year, quarter, version) group on the page — CMS keeps
    prior quarters listed.
    """
    groups: dict[tuple[int, int, str], set[str]] = {}
    for m in _PTP_ZIP_RE.finditer(page_html):
        year, quarter, ver = int(m.group(1)), int(m.group(2)), m.group(3)
        groups.setdefault((year, quarter, ver), set()).add(m.group(0))
    if not groups:
        raise RuntimeError("no practitioner PTP zip links found on the CMS page")
    year, quarter, ver = max(groups)
    paths = sorted(groups[(year, quarter, ver)])
    tag = f"{year}Q{quarter}-{ver.removeprefix('ccipra-')}"
    return tag, [f"https://www.cms.gov{p}" for p in paths]


def discover_mue_url(page_html: str) -> tuple[str, str]:
    """(quarter like "2026Q3", absolute URL) of the newest practitioner
    full-table MUE zip on the page."""
    hits = {(int(m.group(1)), int(m.group(2)), m.group(0)) for m in _MUE_ZIP_RE.finditer(page_html)}
    if not hits:
        raise RuntimeError("no practitioner MUE full-table zip link found on the CMS page")
    year, quarter, path = max(hits)
    return f"{year}Q{quarter}", f"https://www.cms.gov{path}"


def _parse_cms_date(raw: str) -> date | None:
    raw = raw.strip()
    if not _DATE_RE.match(raw):
        return None  # "*" or blank = no deletion date
    return datetime.strptime(raw, "%Y%m%d").date()


def parse_ptp_txt(text: str) -> list[PtpRow]:
    """Tab-delimited PTP file: 6 header lines then data. Rows are recognized by
    shape (field 4 is an 8-digit date), not by a hardcoded header count."""
    rows: list[PtpRow] = []
    for line in text.splitlines():
        fields = line.split("\t")
        if len(fields) < 6:
            continue
        if not _DATE_RE.match(fields[3].strip()):
            continue  # header/blank line
        effective = _parse_cms_date(fields[3])
        if effective is None:
            continue
        indicator_raw = fields[5].strip()
        if indicator_raw not in {"0", "1", "9"}:
            continue
        rows.append(
            PtpRow(
                column1=fields[0].strip().upper(),
                column2=fields[1].strip().upper(),
                effective_date=effective,
                deletion_date=_parse_cms_date(fields[4]),
                modifier_indicator=int(indicator_raw),
                rationale=fields[6].strip() or None if len(fields) > 6 else None,
            )
        )
    return rows


_MAI_RE = re.compile(r"^\s*([123])\b")


def parse_mue_csv(data: bytes) -> list[MueRow]:
    """Practitioner MUE CSV: latin-1, row 1 is the AMA copyright blob, row 2 is
    headers, then data. Rows recognized by shape (integer MUE value + parseable
    MAI digit), not by position."""
    rows: list[MueRow] = []
    reader = csv.reader(io.StringIO(data.decode("latin-1")))
    for fields in reader:
        if len(fields) < 3:
            continue
        code = fields[0].strip().upper()
        if not code or not code[0].isalnum() or len(code) > 5:
            continue
        try:
            value = int(fields[1].strip())
        except ValueError:
            continue
        mai_match = _MAI_RE.match(fields[2])
        if not mai_match:
            continue
        rationale = fields[3].strip() if len(fields) > 3 and fields[3].strip() else None
        rows.append(
            MueRow(hcpcs=code, mue_value=value, mai=int(mai_match.group(1)), rationale=rationale)
        )
    return rows


def dedupe_ptp(rows: list[PtpRow]) -> list[PtpRow]:
    """Last-wins on the (column1, column2, effective_date) PK — the 4 source
    files should never overlap, but a duplicate key must not abort the load."""
    seen: dict[tuple[str, str, date], PtpRow] = {}
    for row in rows:
        seen[(row.column1, row.column2, row.effective_date)] = row
    return list(seen.values())


def check_shrinkage(previous: int | None, new: int, kind: str) -> None:
    if previous and new < previous * (1 - _MAX_SHRINK):
        raise SystemExit(
            f"FAILED: {kind} load has {new} rows vs {previous} previously "
            f"(>{_MAX_SHRINK:.0%} shrink) — refusing to replace a full table "
            "with a likely-truncated download."
        )


def _fetch(client: httpx.Client, url: str) -> bytes:
    resp = client.get(url, headers={"User-Agent": _UA}, follow_redirects=True, timeout=120)
    resp.raise_for_status()
    return resp.content


def _zip_members(blob: bytes, suffix: str) -> list[bytes]:
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(suffix)]
        if not names:
            raise RuntimeError(f"zip contains no {suffix} member")
        return [zf.read(n) for n in names]


async def main() -> None:
    force = os.environ.get("FORCE") == "1"
    engine = create_async_engine(settings.database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    with httpx.Client() as client:
        ptp_tag, ptp_urls = discover_ptp_urls(_fetch(client, PTP_PAGE).decode("utf-8", "replace"))
        mue_quarter, mue_url = discover_mue_url(_fetch(client, MUE_PAGE).decode("utf-8", "replace"))
        mue_version = mue_quarter

        async with sessions() as session:
            load_ptp = force or not await _already_loaded(session, "ptp", ptp_tag)
            load_mue = force or not await _already_loaded(session, "mue", mue_version)

        if not load_ptp and not load_mue:
            print(f"ncci load: {ptp_tag} and {mue_version} already loaded, nothing to do")
            await engine.dispose()
            return

        # Only download what will actually be loaded (the PTP set is ~80 MB).
        ptp_zips = [_fetch(client, url) for url in ptp_urls] if load_ptp else []
        mue_zip = _fetch(client, mue_url) if load_mue else b""

    ptp_rows: list[PtpRow] = []
    ptp_sha = hashlib.sha256()
    if load_ptp:
        for blob in ptp_zips:
            ptp_sha.update(blob)
            for member in _zip_members(blob, ".txt"):
                ptp_rows.extend(parse_ptp_txt(member.decode("latin-1")))
        ptp_rows = dedupe_ptp(ptp_rows)
        if len(ptp_rows) < _MIN_PTP_ROWS:
            raise SystemExit(
                f"FAILED: parsed only {len(ptp_rows)} PTP rows (< {_MIN_PTP_ROWS}) — "
                "file format may have changed; refusing to load."
            )

    mue_rows: list[MueRow] = []
    if load_mue:
        for member in _zip_members(mue_zip, ".csv"):
            mue_rows.extend(parse_mue_csv(member))
        if len(mue_rows) < _MIN_MUE_ROWS:
            raise SystemExit(
                f"FAILED: parsed only {len(mue_rows)} MUE rows (< {_MIN_MUE_ROWS}) — "
                "file format may have changed; refusing to load."
            )

    async with sessions() as session:
        if load_ptp:
            check_shrinkage(await _last_row_count(session, "ptp"), len(ptp_rows), "ptp")
        if load_mue:
            check_shrinkage(await _last_row_count(session, "mue"), len(mue_rows), "mue")

        if load_ptp:
            await session.execute(delete(NcciPtpEdit))
            for start in range(0, len(ptp_rows), _BATCH):
                batch = ptp_rows[start : start + _BATCH]
                await session.execute(
                    insert(NcciPtpEdit),
                    [
                        {
                            "column1": r.column1,
                            "column2": r.column2,
                            "effective_date": r.effective_date,
                            "deletion_date": r.deletion_date,
                            "modifier_indicator": r.modifier_indicator,
                            "rationale": r.rationale,
                        }
                        for r in batch
                    ],
                )
            session.add(
                NcciLoad(
                    kind="ptp",
                    quarter=ptp_tag.split("-")[0],
                    version_tag=ptp_tag,
                    row_count=len(ptp_rows),
                    sha256=ptp_sha.hexdigest(),
                )
            )

        if load_mue:
            await session.execute(delete(NcciMue).where(NcciMue.effective_quarter == mue_quarter))
            seen: dict[str, MueRow] = {r.hcpcs: r for r in mue_rows}
            await session.execute(
                insert(NcciMue),
                [
                    {
                        "hcpcs": r.hcpcs,
                        "effective_quarter": mue_quarter,
                        "mue_value": r.mue_value,
                        "mai": r.mai,
                        "rationale": r.rationale,
                    }
                    for r in seen.values()
                ],
            )
            session.add(
                NcciLoad(
                    kind="mue",
                    quarter=mue_quarter,
                    version_tag=mue_version,
                    row_count=len(seen),
                    sha256=hashlib.sha256(mue_zip).hexdigest(),
                )
            )

        await session.commit()

    await engine.dispose()
    ptp_note = f"ptp={len(ptp_rows)} rows ({ptp_tag})" if load_ptp else "ptp=skipped (current)"
    mue_note = f"mue={len(mue_rows)} rows ({mue_version})" if load_mue else "mue=skipped (current)"
    print(f"ncci load complete: {ptp_note}, {mue_note}")


async def _already_loaded(session, kind: str, version_tag: str) -> bool:
    return (
        await session.scalar(
            select(NcciLoad.id).where(NcciLoad.kind == kind, NcciLoad.version_tag == version_tag)
        )
    ) is not None


async def _last_row_count(session, kind: str) -> int | None:
    return await session.scalar(
        select(NcciLoad.row_count)
        .where(NcciLoad.kind == kind)
        .order_by(NcciLoad.loaded_at.desc())
        .limit(1)
    )


if __name__ == "__main__":
    asyncio.run(main())
