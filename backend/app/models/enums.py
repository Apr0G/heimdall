from sqlalchemy.dialects.postgresql import ENUM as PGEnum


def _pg_enum(*values: str, name: str) -> PGEnum:
    """A native Postgres enum. create_type=False because the Alembic migration
    owns CREATE TYPE / DROP TYPE; the ORM only references the existing type.
    (The generic sqlalchemy.Enum silently ignores create_type — only the
    postgresql dialect type honours it.)"""
    return PGEnum(*values, name=name, create_type=False)


user_role = _pg_enum("doctor", "office_manager", "admin", name="user_role")

case_status = _pg_enum(
    "draft", "processing", "ready", "submitted", "resolved", "error", name="case_status"
)

# What kind of work a case is: a denial appeal (the original flow) or a
# pre-submission risk check on a draft claim. Pre-checks reuse the same
# statuses but only ever occupy processing/ready/error (enforced in code).
case_type = _pg_enum("appeal", "pre_check", name="case_type")

plan_type = _pg_enum(
    "commercial",
    "medicare",
    "medicare_advantage",
    "medicaid",
    "medicaid_mco",
    "tricare",
    "other",
    "unknown",
    name="plan_type",
)

doc_type = _pg_enum(
    "denial",
    "claim",
    "clinical",
    "prior_auth",
    "prior_treatment",
    "other",
    name="doc_type",
)

ocr_status = _pg_enum("not_needed", "pending", "completed", "failed", name="ocr_status")

denial_category = _pg_enum(
    "medical_necessity",
    "prior_auth",
    "coding_error",
    "bundling",
    "timely_filing",
    "non_covered",
    "missing_info",
    "wrong_payer",
    # The two never-appeal classes. Added in 0008 so CO-45 and PR-* stop
    # collapsing into "other" and become visible in the corpus labels.
    "contractual_adjustment",
    "patient_responsibility",
    "other",
    name="denial_category",
)

probability_band = _pg_enum("low", "moderate", "high", name="probability_band")

# Shared by analyses.recommended_appeal_level and appeal_letters.appeal_type.
appeal_level = _pg_enum(
    "level_1_internal",
    "peer_to_peer",
    "level_2_internal",
    "external_review",
    name="appeal_level",
)

letter_status = _pg_enum("draft", "finalized", "downloaded", "archived", name="letter_status")

model_run_purpose = _pg_enum(
    "extraction",
    "analysis",
    "letter_draft",
    "classification",
    "pre_check_review",
    name="model_run_purpose",
)

model_run_status = _pg_enum("success", "error", name="model_run_status")

outcome_action = _pg_enum("appealed", "not_appealed", "pending", name="outcome_action")

outcome_result = _pg_enum(
    "overturned", "upheld", "partial", "pending", "withdrawn", name="outcome_result"
)

outcome_source = _pg_enum("user_reported", "imported", name="outcome_source")

# NOTE: there is deliberately no ALL_ENUM_NAMES list here. 0001_initial_schema.py
# carries its own frozen dict of enum names *and members*, which is correct — a
# migration must describe the schema at its own point in time, not follow the ORM.
# The old list claimed the migration consumed it, which was false and would have led
# anyone appending an enum here to ship a type that was never CREATEd.
# test_enum_parity.py asserts these definitions match the live database instead.

deactivation_request_status = _pg_enum(
    "pending", "approved", "denied", name="deactivation_request_status"
)
