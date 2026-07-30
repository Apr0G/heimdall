"""Model enums must match the database enums (LOW-11).

`models/enums.py` used to carry an `ALL_ENUM_NAMES` list whose comment claimed the
migration consumed it. It did not — `0001_initial_schema.py` has its own frozen
dict — so a developer appending an enum to that list would have shipped a type
that was never CREATEd, and found out at runtime.

The list is gone. This is what replaces it: a check against the live database,
which is the only authority that can actually answer the question. Any enum added
to the ORM without a migration fails here.
"""

import pytest
from sqlalchemy import text

from app.models import enums as model_enums

pytestmark = pytest.mark.asyncio

_ENUM_MEMBERS_SQL = text("""
    SELECT t.typname, e.enumlabel
    FROM pg_type t
    JOIN pg_enum e ON e.enumtypid = t.oid
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'public'
    ORDER BY t.typname, e.enumsortorder
""")


def _orm_enums() -> dict[str, set[str]]:
    """Every native Postgres enum declared in models/enums.py."""
    from sqlalchemy import Enum as SAEnum

    found: dict[str, set[str]] = {}
    for value in vars(model_enums).values():
        if isinstance(value, SAEnum) and value.name:
            found[value.name] = set(value.enums)
    return found


@pytest.fixture
async def db_enums(sessions) -> dict[str, set[str]]:
    async with sessions() as session:
        rows = (await session.execute(_ENUM_MEMBERS_SQL)).all()
    found: dict[str, set[str]] = {}
    for typname, label in rows:
        found.setdefault(typname, set()).add(label)
    return found


async def test_every_orm_enum_exists_in_the_database(db_enums):
    missing = sorted(set(_orm_enums()) - set(db_enums))
    assert not missing, (
        f"enum type(s) declared in models/enums.py but never CREATEd by a " f"migration: {missing}"
    )


async def test_enum_members_match(db_enums):
    """Catches both directions: a label the ORM knows and the DB does not (an
    INSERT that will fail at runtime), and a label the DB has that the ORM has
    forgotten (a value the app can read but never write)."""
    mismatches = {}
    for name, orm_members in _orm_enums().items():
        db_members = db_enums.get(name)
        if db_members is None:
            continue  # covered by the test above
        if orm_members != db_members:
            mismatches[name] = {
                "orm_only": sorted(orm_members - db_members),
                "db_only": sorted(db_members - orm_members),
            }
    assert not mismatches, f"enum member drift between the ORM and the database: {mismatches}"


async def test_new_never_appeal_categories_are_present(db_enums):
    """Explicit guard on the 0008 additions, so a bad merge that drops the
    migration fails loudly rather than collapsing CO-45 and PR-* into "other"."""
    assert {"contractual_adjustment", "patient_responsibility"} <= db_enums["denial_category"]
