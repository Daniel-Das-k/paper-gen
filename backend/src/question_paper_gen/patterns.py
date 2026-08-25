from collections.abc import Callable

from .models import (
    BloomLevel,
    PaperPattern,
    QuestionKind,
    SectionPattern,
)


def autonomous_semester_pattern() -> PaperPattern:
    """Return the 100-mark end-semester pattern used by autonomous engineering colleges.

    This is the Anna University affiliated/autonomous house style: Part A carries ten
    compulsory two-mark questions, Part B five thirteen-mark questions each offering an
    either/or choice between two alternatives, and Part C one compulsory fifteen-mark
    question offering the same choice. Part B alternatives are split into (i) and (ii)
    subparts worth 7 and 6 marks.

    Bloom coverage is deliberate rather than incidental: NBA and NAAC evaluators sample
    a paper and ask, question by question, which course outcome and cognitive level each
    item targets, so the sequence spans lower-order (Part A), transition (Part B) and
    higher-order (Part C) demand.
    """
    return PaperPattern(
        pattern_id="autonomous-semester-100",
        name="Autonomous End-Semester — 100 Marks",
        duration_minutes=180,
        total_marks=100,
        sections=[
            SectionPattern(
                section_id="part_a",
                title="PART A — Answer ALL questions (10 x 2 = 20 marks)",
                question_kind=QuestionKind.VERY_SHORT_ANSWER,
                question_count=10,
                marks_each=2,
                # Two questions from each of the five units, so the paper covers
                # the whole course and CO1..CO5 each carry marks.
                unit_cycle=["1", "1", "2", "2", "3", "3", "4", "4", "5", "5"],
                bloom_sequence=[
                    BloomLevel.REMEMBER,
                    BloomLevel.UNDERSTAND,
                    BloomLevel.REMEMBER,
                    BloomLevel.UNDERSTAND,
                    BloomLevel.REMEMBER,
                    BloomLevel.UNDERSTAND,
                    BloomLevel.APPLY,
                    BloomLevel.UNDERSTAND,
                    BloomLevel.APPLY,
                    BloomLevel.ANALYZE,
                ],
            ),
            SectionPattern(
                section_id="part_b",
                title="PART B — Answer ALL questions (5 x 13 = 65 marks)",
                question_kind=QuestionKind.LONG_ANSWER,
                question_count=5,
                marks_each=13,
                # Each long-answer question may use one verified diagram when
                # it is linked to that question's topic. This is a ceiling, not
                # a target: text-only questions remain the default when a
                # figure would not add instructional value.
                visual_question_count=5,
                unit_cycle=["1", "2", "3", "4", "5"],
                choices_per_question=2,
                answers_required=1,
                internal_choice_count=5,
                internal_choice_positions=[1, 2, 3, 4, 5],
                internal_choice_scope="whole_question",
                bloom_sequence=[
                    BloomLevel.APPLY,
                    BloomLevel.APPLY,
                    BloomLevel.ANALYZE,
                    BloomLevel.APPLY,
                    BloomLevel.ANALYZE,
                ],
            ),
            SectionPattern(
                section_id="part_c",
                title="PART C — Answer ANY ONE question (1 x 15 = 15 marks)",
                question_kind=QuestionKind.LONG_ANSWER,
                question_count=1,
                marks_each=15,
                # Higher-order Part C may also use a relevant visual, provided
                # an eligible topic-matched asset remains available.
                visual_question_count=1,
                unit_cycle=["5"],
                choices_per_question=2,
                answers_required=1,
                internal_choice_count=1,
                internal_choice_positions=[1],
                internal_choice_scope="whole_question",
                bloom_sequence=[BloomLevel.CREATE],
            ),
        ],
    )


def _combined_cat_sections(
    units: list[tuple[str, str]],
) -> list[SectionPattern]:
    """Build one combined Part A and one combined Part B for a CAT.

    Questions remain bound to their upload row through `unit_cycle`, but the
    printed paper groups all two-mark questions first and all eleven-mark
    questions second. This keeps CO mapping intact without repeating headings.

    A unit covered in full contributes 4 x 2 + 2 x 11 = 30 marks; a unit split
    across two tests contributes half of that, 2 x 2 + 1 x 11 = 15. Three units
    per test therefore total 75 either way — 30 + 30 + 15.
    """
    short_units: list[str] = []
    long_units: list[str] = []
    short_bloom: list[BloomLevel] = []
    long_bloom: list[BloomLevel] = []
    for unit, coverage in units:
        full = coverage == "full"
        short_count, long_count = (4, 2) if full else (2, 1)
        short_units.extend([unit] * short_count)
        long_units.extend([unit] * long_count)
        short_bloom.extend(
            [
                BloomLevel.REMEMBER,
                BloomLevel.UNDERSTAND,
                BloomLevel.REMEMBER,
                BloomLevel.UNDERSTAND,
            ]
            if full
            else [BloomLevel.REMEMBER, BloomLevel.UNDERSTAND]
        )
        long_bloom.extend(
            [BloomLevel.APPLY, BloomLevel.ANALYZE]
            if full
            else [BloomLevel.APPLY]
        )

    return [
        SectionPattern(
            section_id="part_a",
            title=(
                "PART A — Answer ALL questions "
                f"({len(short_units)} x 2 = {len(short_units) * 2} marks)"
            ),
            question_kind=QuestionKind.VERY_SHORT_ANSWER,
            question_count=len(short_units),
            marks_each=2,
            unit_cycle=short_units,
            bloom_sequence=short_bloom,
        ),
        SectionPattern(
            section_id="part_b",
            title=(
                "PART B — Answer ALL questions "
                f"({len(long_units)} x 11 = {len(long_units) * 11} marks)"
            ),
            question_kind=QuestionKind.LONG_ANSWER,
            question_count=len(long_units),
            marks_each=11,
            unit_cycle=long_units,
            # Every long answer may use a verified, topic-matched visual, but
            # unused capacity is never treated as a missing requirement.
            visual_question_count=len(long_units),
            choices_per_question=2,
            answers_required=1,
            internal_choice_count=len(long_units),
            internal_choice_positions=list(range(1, len(long_units) + 1)),
            internal_choice_scope="whole_question",
            bloom_sequence=long_bloom,
        ),
    ]


def cat_one_pattern() -> PaperPattern:
    """CAT-I: units 1 and 2 in full, unit 3 to the halfway point."""
    return PaperPattern(
        pattern_id="cat-1-75",
        name="Continuous Assessment Test I — 75 Marks",
        duration_minutes=120,
        total_marks=75,
        sections=_combined_cat_sections(
            [("1", "full"), ("2", "full"), ("3", "half")]
        ),
    )


def cat_two_pattern() -> PaperPattern:
    """CAT-II: the second half of unit 3, then units 4 and 5 in full."""
    return PaperPattern(
        pattern_id="cat-2-75",
        name="Continuous Assessment Test II — 75 Marks",
        duration_minutes=120,
        total_marks=75,
        sections=_combined_cat_sections(
            [("3", "half"), ("4", "full"), ("5", "full")]
        ),
    )


#: The pattern used when a caller does not name one.
DEFAULT_PATTERN_ID = "autonomous-semester-100"

_PATTERN_BUILDERS: dict[str, Callable[[], PaperPattern]] = {
    "cat-1-75": cat_one_pattern,
    "cat-2-75": cat_two_pattern,
    "autonomous-semester-100": autonomous_semester_pattern,
}


def available_patterns() -> list[PaperPattern]:
    """Return every selectable pattern, in the order an exam year runs."""
    return [build() for build in _PATTERN_BUILDERS.values()]


def get_pattern(pattern_id: str | None) -> PaperPattern:
    """Resolve a pattern by id, falling back to the default when unset.

    Raises KeyError for an unknown id so the API can answer 404 rather than
    silently generating a paper the caller did not ask for.
    """
    if pattern_id is None:
        pattern_id = DEFAULT_PATTERN_ID
    try:
        return _PATTERN_BUILDERS[pattern_id]()
    except KeyError:
        raise KeyError(
            f"unknown pattern_id {pattern_id!r}; "
            f"available: {', '.join(sorted(_PATTERN_BUILDERS))}"
        ) from None
