"""Token-cost estimation for the admin overview.

Rates are integer CENTS per MILLION tokens (Hard rule 11: no float currency).
These are ESTIMATES for internal ops visibility, not billing: Bedrock pricing is
set by AWS (https://aws.amazon.com/bedrock/pricing/) — historically identical to
first-party on-demand Claude rates, but verify there when rates change.

The arithmetic stays exact until one final floor division, so callers should
aggregate token sums per model_id first and call `estimate_cost_cents` once per
group: floor loss is then bounded at <1 cent per distinct model, not per run.
"""

# Claude Sonnet 4.6: $3.00/MTok input, $15.00/MTok output.
RATES_CENTS_PER_MTOK: tuple[tuple[str, tuple[int, int]], ...] = (
    ("claude-sonnet-4-6", (300, 1500)),
)

# model_runs.model_id is nullable and settings.bedrock_model_id can be unset, so
# unknown/None ids are expected, not exceptional. Fall back to the current
# production model's rate rather than silently pricing those tokens at zero.
DEFAULT_RATE_CENTS_PER_MTOK: tuple[int, int] = (300, 1500)


def rate_for_model(model_id: str | None) -> tuple[int, int]:
    """(input, output) cents-per-MTok for a model id.

    Substring match, because stored ids are Bedrock inference-profile ids like
    "us.anthropic.claude-sonnet-4-6" wrapping the bare model name.
    """
    if model_id:
        for needle, rate in RATES_CENTS_PER_MTOK:
            if needle in model_id:
                return rate
    return DEFAULT_RATE_CENTS_PER_MTOK


def estimate_cost_cents(input_tokens: int, output_tokens: int, model_id: str | None) -> int:
    """Estimated cost in integer cents. Exact integer math; floors sub-cent."""
    in_rate, out_rate = rate_for_model(model_id)
    return (input_tokens * in_rate + output_tokens * out_rate) // 1_000_000
