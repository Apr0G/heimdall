"""Prompt VERSION is bound to the prompt TEXT (hard rule 8, LOW-18).

test_prompt_version_is_pinned only catches a bump without a test edit. This
catches the failure the rule targets: editing SYSTEM / build_user_prompt without
bumping VERSION, which would file two different prompts under one
prompt_version in model_runs. Any text change must update BOTH the VERSION and
the digest here — deliberately, in the same commit.
"""

import hashlib

from app.prompts import analysis_prompt, extraction_prompt, letter_prompt


def _digest(system: str, user: str) -> str:
    return hashlib.sha256((system + "\n" + user).encode()).hexdigest()[:16]


PINNED = {
    # (VERSION, digest of SYSTEM + build_user_prompt on fixed inputs)
    "extraction": ("extract_v3", "54e1e3ca74c814dd"),
    "analysis": ("analyze_v5", "9496bdb547376b9a"),
    "letter": ("letter_v4", "d01604c786b394e1"),
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
        _digest(analysis_prompt.SYSTEM, analysis_prompt.build_user_prompt({"a": 1}, "N", "S"))
        == digest
    )


def test_letter_prompt_text_matches_version():
    version, digest = PINNED["letter"]
    assert letter_prompt.VERSION == version
    rendered = letter_prompt.build_user_prompt(
        {"p": 1}, {"a": 1}, {"b": 1}, "N", "S", "level_1_internal"
    )
    assert _digest(letter_prompt.SYSTEM, rendered) == digest
