from app.services.model_costs import (
    DEFAULT_RATE_CENTS_PER_MTOK,
    estimate_cost_cents,
    rate_for_model,
)

SONNET_PROFILE_ID = "us.anthropic.claude-sonnet-4-6"


def test_one_mtok_each_way():
    # $3 in + $15 out per MTok = 1800 cents.
    assert estimate_cost_cents(1_000_000, 1_000_000, SONNET_PROFILE_ID) == 1800


def test_sub_cent_floors_to_zero():
    assert estimate_cost_cents(1000, 0, SONNET_PROFILE_ID) == 0
    assert estimate_cost_cents(0, 0, SONNET_PROFILE_ID) == 0


def test_floor_boundary_at_the_input_rate():
    # 300 cents/MTok input: one cent is crossed at 3,334 tokens.
    assert estimate_cost_cents(3333, 0, SONNET_PROFILE_ID) == 0
    assert estimate_cost_cents(3334, 0, SONNET_PROFILE_ID) == 1


def test_rate_matches_inference_profile_ids_by_substring():
    assert rate_for_model(SONNET_PROFILE_ID) == (300, 1500)
    assert rate_for_model("claude-sonnet-4-6") == (300, 1500)


def test_unknown_and_missing_model_ids_use_the_default_rate():
    assert rate_for_model(None) == DEFAULT_RATE_CENTS_PER_MTOK
    assert rate_for_model("") == DEFAULT_RATE_CENTS_PER_MTOK
    assert rate_for_model("some-future-model") == DEFAULT_RATE_CENTS_PER_MTOK


def test_large_token_counts_stay_exact():
    # 10^12 input tokens at 300 cents/MTok is exactly 3 * 10^8 cents — integer
    # math must not drift the way float math would at this magnitude.
    assert estimate_cost_cents(10**12, 0, SONNET_PROFILE_ID) == 3 * 10**8
