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
from question_paper_gen.patterns import (
    DEFAULT_PATTERN_ID,
    autonomous_semester_pattern,
    available_patterns,
    get_pattern,
)


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


def test_autonomous_semester_pattern_matches_the_100_mark_house_style() -> None:
    pattern = autonomous_semester_pattern()

    assert pattern.pattern_id == "autonomous-semester-100"
    assert pattern.total_marks == 100
    assert pattern.duration_minutes == 180
    assert [section.section_id for section in pattern.sections] == [
        "part_a",
        "part_b",
        "part_c",
    ]
    assert [section.question_count for section in pattern.sections] == [10, 5, 1]
    assert [section.marks_each for section in pattern.sections] == [2, 13, 15]
    assert [section.visual_question_count for section in pattern.sections] == [0, 5, 1]
    assert sum(
        section.question_count * section.marks_each for section in pattern.sections
    ) == 100


def test_autonomous_part_b_is_a_whole_question_either_or() -> None:
    part_b = autonomous_semester_pattern().sections[1]

    # Every Part B question is "(a) OR (b)". Whichever the student answers is
    # marked out of the full 13 — there is no subpart breakdown to award from.
    assert part_b.choices_per_question == 2
    assert part_b.answers_required == 1
    assert part_b.internal_choice_count == 5
    assert part_b.internal_choice_positions == [1, 2, 3, 4, 5]
    assert part_b.internal_choice_scope == "whole_question"
    assert part_b.subparts == []
    assert part_b.marks_each == 13


def test_autonomous_part_c_is_a_single_higher_order_choice() -> None:
    part_c = autonomous_semester_pattern().sections[2]

    assert part_c.question_count == 1
    assert part_c.marks_each == 15
    assert part_c.choices_per_question == 2
    assert part_c.answers_required == 1
    assert part_c.bloom_sequence == [BloomLevel.CREATE]


def test_autonomous_pattern_spans_lower_and_higher_order_bloom_levels() -> None:
    """NBA evaluators sample a paper for cognitive spread, so assert it explicitly."""
    levels = [
        level
        for section in autonomous_semester_pattern().sections
        for level in section.bloom_sequence
    ]

    assert len(levels) == 16
    assert levels.count(BloomLevel.REMEMBER) == 3
    assert levels.count(BloomLevel.UNDERSTAND) == 4
    assert levels.count(BloomLevel.APPLY) == 5
    assert levels.count(BloomLevel.ANALYZE) == 3
    assert levels.count(BloomLevel.CREATE) == 1


def test_pattern_registry_resolves_by_id_and_defaults_when_unset() -> None:
    assert DEFAULT_PATTERN_ID == "autonomous-semester-100"
    assert get_pattern(None).pattern_id == "autonomous-semester-100"
    assert get_pattern(None).total_marks == 100
    assert get_pattern("autonomous-semester-100").pattern_id == (
        "autonomous-semester-100"
    )
    assert {pattern.pattern_id for pattern in available_patterns()} == {
        "cat-1-75",
        "cat-2-75",
        "autonomous-semester-100",
    }


def test_school_board_pattern_is_no_longer_offered() -> None:
    """The product sets college end-semester papers only."""
    with pytest.raises(KeyError):
        get_pattern("sample-paper-80-v2")


def test_unknown_pattern_id_raises_rather_than_silently_defaulting() -> None:
    with pytest.raises(KeyError, match="unknown pattern_id"):
        get_pattern("does-not-exist")


def test_cat_papers_combine_all_short_and_long_questions() -> None:
    """CAT papers print one Part A followed by one Part B across all units."""
    expected_units = {
        "cat-1-75": (
            ["1"] * 4 + ["2"] * 4 + ["3"] * 2,
            ["1"] * 2 + ["2"] * 2 + ["3"],
        ),
        "cat-2-75": (
            ["3"] * 2 + ["4"] * 4 + ["5"] * 4,
            ["3"] + ["4"] * 2 + ["5"] * 2,
        ),
    }
    for pattern_id, (short_units, long_units) in expected_units.items():
        pattern = get_pattern(pattern_id)

        assert pattern.total_marks == 75
        assert pattern.duration_minutes == 120
        assert [section.section_id for section in pattern.sections] == [
            "part_a",
            "part_b",
        ]
        part_a, part_b = pattern.sections
        assert part_a.title == "PART A — Answer ALL questions (10 x 2 = 20 marks)"
        assert part_a.question_count == 10
        assert part_a.marks_each == 2
        assert part_a.unit_cycle == short_units
        assert part_a.visual_question_count == 0

        assert part_b.title == "PART B — Answer ALL questions (5 x 11 = 55 marks)"
        assert part_b.question_count == 5
        assert part_b.marks_each == 11
        assert part_b.unit_cycle == long_units
        assert part_b.choices_per_question == 2
        assert part_b.internal_choice_positions == [1, 2, 3, 4, 5]
        assert part_b.subparts == []
        assert part_b.visual_question_count == 5

        assert sum(
            section.question_count * section.marks_each
            for section in pattern.sections
        ) == 75


def test_the_three_papers_a_year_actually_sets_are_all_offered() -> None:
    offered = {pattern.pattern_id: pattern for pattern in available_patterns()}

    assert set(offered) == {"cat-1-75", "cat-2-75", "autonomous-semester-100"}
    assert offered["cat-1-75"].total_marks == 75
    assert offered["cat-2-75"].total_marks == 75
    assert offered["autonomous-semester-100"].total_marks == 100



def test_every_paper_binds_its_questions_to_syllabus_units() -> None:
    """Unit N assesses CO N, so each paper must say which units it covers."""
    covered = {}
    for pattern_id in ("cat-1-75", "cat-2-75", "autonomous-semester-100"):
        units: set[str] = set()
        for section in get_pattern(pattern_id).sections:
            if section.unit_number:
                units.add(section.unit_number)
            units.update(section.unit_cycle)
        covered[pattern_id] = units

    assert covered["cat-1-75"] == {"1", "2", "3"}
    assert covered["cat-2-75"] == {"3", "4", "5"}
    assert covered["autonomous-semester-100"] == {"1", "2", "3", "4", "5"}
