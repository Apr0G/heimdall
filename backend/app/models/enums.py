from sqlalchemy import Enum as SAEnum


def _pg_enum(*values: str, name: str) -> SAEnum:
    """A native Postgres enum. create_type=False because the Alembic migration
    owns CREATE TYPE / DROP TYPE; the ORM only references the existing type."""
    return SAEnum(*values, name=name, native_enum=True, create_type=False)


user_role = _pg_enum("doctor", "office_manager", "admin", name="user_role")

case_status = _pg_enum(
    "draft", "processing", "ready", "submitted", "resolved", "error", name="case_status"
)

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
    "extraction", "analysis", "letter_draft", "classification", name="model_run_purpose"
)

model_run_status = _pg_enum("success", "error", name="model_run_status")

outcome_action = _pg_enum("appealed", "not_appealed", "pending", name="outcome_action")

outcome_result = _pg_enum(
    "overturned", "upheld", "partial", "pending", "withdrawn", name="outcome_result"
)

outcome_source = _pg_enum("user_reported", "imported", name="outcome_source")

# Enum names in creation order, for the migration to CREATE/DROP TYPE.
ALL_ENUM_NAMES = [
    "user_role",
    "case_status",
    "plan_type",
    "doc_type",
    "ocr_status",
    "denial_category",
    "probability_band",
    "appeal_level",
    "letter_status",
    "model_run_purpose",
    "model_run_status",
    "outcome_action",
    "outcome_result",
    "outcome_source",
]
