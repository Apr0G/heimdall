"""Prompt VERSION is bound to the prompt TEXT (hard rule 8, LOW-18).

test_prompt_version_is_pinned only catches a bump without a test edit. This
catches the failure the rule targets: editing SYSTEM / build_user_prompt without
bumping VERSION, which would file two different prompts under one
prompt_version in model_runs. Any text change must update BOTH the VERSION and
the digest here — deliberately, in the same commit.
"""

import hashlib

from app.prompts import (
    analysis_prompt,
    extraction_prompt,
    letter_prompt,
    precheck_extraction_prompt,
    precheck_review_prompt,
)


def _digest(system: str, user: str) -> str:
    return hashlib.sha256((system + "\n" + user).encode()).hexdigest()[:16]


PINNED = {
    # (VERSION, digest of SYSTEM + build_user_prompt on fixed inputs)
    "extraction": ("extract_v3", "54e1e3ca74c814dd"),
    "analysis": ("analyze_v6", "9496bdb547376b9a"),
    "letter": ("letter_v6", "d01604c786b394e1"),
    "precheck_extraction": ("pc_extract_v2", "62e4b26c7bbf5f63"),
    "precheck_review": ("pc_review_v3", "bf291579c4f33722"),
}


def test_extraction_prompt_text_matches_version():
    version, digest = PINNED["extraction"]
    assert extraction_prompt.VERSION == version
    assert (
        _digest(extraction_prompt.SYSTEM, extraction_prompt.build_user_prompt("D", "C", "N"))
        == digest
    )


def test_analysis_prompt_text_matches_version():
    version, digest = PINNED["analysis"]
    assert analysis_prompt.VERSION == version
    assert (
        _digest(
            analysis_prompt.SYSTEM,
            analysis_prompt.build_user_prompt({"a": 1}, "N", "S"),
        )
        == digest
    )


def test_letter_prompt_text_matches_version():
    version, digest = PINNED["letter"]
    assert letter_prompt.VERSION == version
    rendered = letter_prompt.build_user_prompt(
        {"p": 1}, {"a": 1}, {"b": 1}, "N", "S", "level_1_internal"
    )
    assert _digest(letter_prompt.SYSTEM, rendered) == digest


def test_precheck_extraction_prompt_text_matches_version():
    version, digest = PINNED["precheck_extraction"]
    assert precheck_extraction_prompt.VERSION == version
    assert (
        _digest(
            precheck_extraction_prompt.SYSTEM,
            precheck_extraction_prompt.build_user_prompt("C", "N"),
        )
        == digest
    )


def test_precheck_review_prompt_text_matches_version():
    version, digest = PINNED["precheck_review"]
    assert precheck_review_prompt.VERSION == version
    assert (
        _digest(
            precheck_review_prompt.SYSTEM,
            precheck_review_prompt.build_user_prompt({"a": 1}, [{"b": 2}], "N"),
        )
        == digest
    )
