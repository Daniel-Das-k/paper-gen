import pytest
from pydantic import ValidationError

from pydantic_ai.exceptions import ModelHTTPError
from question_paper_gen.ai import (
    _is_transient_model_error,
    is_transient_model_failure,
    summarize_model_failure,
)
from question_paper_gen.models import (
    BloomLevel,
    PaperPattern,
    QuestionKind,
    SectionPattern,
    SubpartPattern,
)
from question_paper_gen.patterns import default_college_pattern


def test_default_pattern_matches_supplied_80_mark_sample() -> None:
    pattern = default_college_pattern()

    assert pattern.total_marks == 80
    assert sum(
        section.question_count * section.marks_each for section in pattern.sections
    ) == 80
    assert [section.question_count for section in pattern.sections] == [20, 5, 6, 4, 3]
    assert [section.marks_each for section in pattern.sections] == [1, 2, 3, 5, 4]
    assert [section.internal_choice_count for section in pattern.sections] == [
        0,
        2,
        2,
        2,
        3,
    ]
    assert pattern.sections[0].question_kind == QuestionKind.MULTIPLE_CHOICE
    assert pattern.sections[0].question_kind_sequence == [
        *([QuestionKind.MULTIPLE_CHOICE] * 18),
        QuestionKind.ASSERTION_REASON,
        QuestionKind.ASSERTION_REASON,
    ]
    assert pattern.sections[-1].question_kind == QuestionKind.CASE_STUDY
    assert [
        section.internal_choice_positions for section in pattern.sections
    ] == [[], [2, 3], [1, 3], [2, 3], [1, 2, 3]]
    assert [part.marks for part in pattern.sections[-1].subparts] == [1, 1, 2]
    assert pattern.sections[-1].internal_choice_scope == "final_subpart"
    assert [section.visual_question_count for section in pattern.sections] == [
        1,
        0,
        1,
        1,
        1,
    ]
    assert pattern.sections[0].bloom_sequence[:6] == [BloomLevel.REMEMBER] * 6


def test_pattern_rejects_wrong_total() -> None:
    with pytest.raises(ValidationError, match="section marks total"):
        PaperPattern(
            pattern_id="bad",
            name="Bad",
            duration_minutes=60,
            total_marks=99,
            sections=[
                SectionPattern(
                    section_id="s",
                    title="S",
                    question_kind=QuestionKind.SHORT_ANSWER,
                    question_count=1,
                    marks_each=2,
                    bloom_sequence=[BloomLevel.REMEMBER],
                )
            ],
        )


def test_section_rejects_incorrect_subpart_total() -> None:
    with pytest.raises(ValidationError, match="subpart marks"):
        SectionPattern(
            section_id="long",
            title="Long",
            question_kind=QuestionKind.LONG_ANSWER,
            question_count=1,
            marks_each=13,
            subparts=[
                SubpartPattern(label="a", marks=6),
                SubpartPattern(label="b", marks=6),
            ],
            bloom_sequence=[BloomLevel.ANALYZE],
        )


def test_section_rejects_too_many_internal_choices() -> None:
    with pytest.raises(ValidationError, match="internal_choice_count"):
        SectionPattern(
            section_id="choice",
            title="Choice",
            question_kind=QuestionKind.SHORT_ANSWER,
            question_count=1,
            marks_each=2,
            choices_per_question=2,
            internal_choice_count=2,
            bloom_sequence=[BloomLevel.APPLY],
        )


def test_model_fallback_only_accepts_transient_errors() -> None:
    assert _is_transient_model_error(
        ModelHTTPError(503, "gemini-3.6-flash", {"status": "UNAVAILABLE"})
    )
    assert _is_transient_model_error(
        ModelHTTPError(429, "gemini-3.6-flash", {"status": "RESOURCE_EXHAUSTED"})
    )
    assert not _is_transient_model_error(
        ModelHTTPError(400, "gemini-3.6-flash", {"status": "INVALID_ARGUMENT"})
    )
    assert not _is_transient_model_error(
        ModelHTTPError(403, "gemini-3.6-flash", {"status": "PERMISSION_DENIED"})
    )


def test_grouped_model_failures_are_diagnosed_without_response_bodies() -> None:
    grouped = ExceptionGroup(
        "fallbacks failed",
        [
            ModelHTTPError(503, "gemini-3.6-flash", {"private": "body"}),
            ModelHTTPError(429, "gemini-3.5-flash", {"private": "body"}),
        ],
    )

    assert is_transient_model_failure(grouped)
    summary = summarize_model_failure(grouped)
    assert "model=gemini-3.6-flash status=503" in summary
    assert "model=gemini-3.5-flash status=429" in summary
    assert "private" not in summary
