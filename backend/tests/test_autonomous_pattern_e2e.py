"""End-to-end cover for the autonomous 100-mark college pattern.

The pattern is only useful if a paper actually comes out the other side, so this
drives the real pipeline, validator and renderers with a stub provider and asserts
the shape a college expects: 16 questions, 100 marks, either/or alternatives in
Part B and Part C, and section headings taken from the pattern rather than the
five-section school defaults.
"""

import asyncio
import hashlib
import json
import tempfile

from pathlib import Path

from question_paper_gen.ai import (
    SectionQuestionBatch,
    SectionQuestionReview,
    SectionReviewBatch,
    SemanticReview,
)
from question_paper_gen.blueprints import BlueprintBuilder
from question_paper_gen.models import (
    BloomLevel,
    ContentMap,
    DocumentManifest,
    DocumentQuality,
    GeneratedQuestionPaper,
    MarkingCriterion,
    PageContent,
    QuestionCandidate,
    SourceEvidence,
    Topic,
)
from question_paper_gen.outputs import save_generated_paper
from question_paper_gen.patterns import autonomous_semester_pattern
from question_paper_gen.pipeline import PaperGenerationPipeline

# Distinct text per page: evidence chunks resolve by excerpt match, so pages that
# repeat the same wording would all resolve to page 1 and trip cross-topic checks.
PAGES = {
    1: (
        "Relational schema design introduces relations, attributes, candidate keys "
        "and primary keys. A functional dependency X to Y holds when each X value "
        "determines exactly one Y value. Armstrong axioms give reflexivity, "
        "augmentation and transitivity for deriving a dependency closure. "
    ) * 6,
    2: (
        "Normalization removes redundancy by decomposing relations. First normal "
        "form requires atomic attributes. Second normal form removes partial "
        "dependency on a composite key. Third normal form removes transitive "
        "dependency on non key attributes. "
    ) * 6,
    3: (
        "Lossless join decomposition guarantees the original relation is "
        "recoverable by natural join. Transaction concurrency control uses two "
        "phase locking with a growing and a shrinking phase. Isolation levels "
        "trade serialisability against throughput. "
    ) * 6,
}


def _manifest() -> DocumentManifest:
    return DocumentManifest(
        document_id="doc-autonomous",
        original_filename="dbms-units.pdf",
        sha256="b" * 64,
        source_pdf_path="/tmp/source.pdf",
        artifact_directory="/tmp/artifacts",
        pages=[
            PageContent(
                page_number=number,
                width=600,
                height=800,
                text=text,
                rendered_image_path=f"/tmp/page-{number}.png",
            )
            for number, text in PAGES.items()
        ],
        visual_assets=[],
        quality=DocumentQuality(
            passed=True,
            page_count=len(PAGES),
            text_character_count=sum(len(text) for text in PAGES.values()),
        ),
    )


def _content() -> ContentMap:
    topics = [
        ("schema", "Relational Schema Design", [1]),
        ("dependency", "Functional Dependencies", [1]),
        ("normalization", "Normalization and Normal Forms", [2]),
        ("lossless", "Lossless Join Decomposition", [3]),
        ("transactions", "Transaction Concurrency Control", [3]),
    ]
    return ContentMap(
        subject="Database Management Systems",
        topics=[
            Topic(
                topic_id=topic_id,
                name=name,
                unit=str(index + 1),
                source_pages=pages,
                supported_bloom_levels=list(BloomLevel),
            )
            for index, (topic_id, name, pages) in enumerate(topics)
        ],
    )


class StubAnalyzer:
    """Minimal provider stand-in that returns well-formed, distinct questions."""

    def __init__(self) -> None:
        self.generation_calls = 0
        self.review_calls = 0

    @staticmethod
    def _distinct(slot_id: str, facet: str = "", tokens: int = 18) -> str:
        return " ".join(
            hashlib.sha256(f"{slot_id}-{facet}-{index}".encode()).hexdigest()[:10]
            for index in range(tokens)
        )

    async def generate_section(
        self,
        *,
        section_id: str,
        expected_question_count: int,
        slots_prompt: str,
        evidence_text: str,
        visual_paths: list[tuple[str, str]],
    ) -> SectionQuestionBatch:
        self.generation_calls += 1
        verbs = {
            "remember": "Define",
            "understand": "Explain",
            "apply": "Apply the method to solve",
            "analyze": "Analyze and explain",
            "evaluate": "Evaluate and justify",
            "create": "Design and justify",
        }
        questions = []
        for slot in json.loads(slots_prompt):
            verb = verbs[slot["bloom_level"]]
            # Two-mark questions must stay inside the short-question rule.
            marker = self._distinct(
                slot["slot_id"],
                slot.get("facet") or "",
                tokens=6 if int(slot["marks"]) <= 2 else 18,
            )
            text = (
                f"{verb} the source concept concerning {marker}"
                if int(slot["marks"]) <= 2
                else (
                    f"{verb} the source concept concerning {marker}, showing each "
                    "reasoning step and explaining how the conclusion follows from "
                    "the supplied academic evidence"
                )
            )
            if slot["has_internal_choice"]:
                text = (
                    f"(a) {text} in the first source setting.\nOR\n"
                    f"(b) {text} in the alternative source setting."
                )
            pages = slot["source_pages"] or [1]
            questions.append(
                QuestionCandidate(
                    candidate_id=f"{slot['slot_id']}-stub",
                    slot_id=slot["slot_id"],
                    question_text=text,
                    answer="Answer grounded in the supplied source.",
                    marks=slot["marks"],
                    bloom_level=slot["bloom_level"],
                    bloom_justification="The task requires the configured process.",
                    marking_scheme=[
                        MarkingCriterion(
                            criterion="Complete correct response",
                            marks=slot["marks"],
                        )
                    ],
                    evidence=SourceEvidence(
                        page_numbers=pages,
                        excerpts=[PAGES[pages[0]][:180]],
                    ),
                    confidence=0.95,
                )
            )
        return SectionQuestionBatch(questions=questions)

    @staticmethod
    def _clean_review(**overrides: object) -> dict[str, object]:
        payload: dict[str, object] = {
            "grounded_in_evidence": True,
            "answer_correct": True,
            "bloom_level_correct": True,
            "wording_clear": True,
            "subject_accuracy": True,
            "difficulty_appropriate": True,
            "marking_scheme_valid": True,
            "options_valid": True,
            "internal_choice_valid": True,
            "pedagogical_quality": True,
            "quality_score": 92,
            "confidence": 0.95,
            "reasons": [],
        }
        payload.update(overrides)
        return payload

    async def review_section(
        self,
        *,
        section_id: str,
        slots_prompt: str,
        questions: list[QuestionCandidate],
        evidence_text: str,
        visual_paths: list[tuple[str, str]],
    ) -> SectionReviewBatch:
        self.review_calls += 1
        return SectionReviewBatch(
            reviews=[
                SectionQuestionReview(
                    **self._clean_review(
                        candidate_id=question.candidate_id,
                        observed_bloom_level=question.bloom_level,
                    )
                )
                for question in questions
            ]
        )

    async def review_question(
        self,
        *,
        question: QuestionCandidate,
        required_bloom_level: BloomLevel,
        evidence_text: str,
        visual_path: str | None = None,
    ) -> SemanticReview:
        return SemanticReview(
            **self._clean_review(observed_bloom_level=question.bloom_level)
        )


def _generate() -> tuple[GeneratedQuestionPaper, DocumentManifest, ContentMap, object]:
    pattern = autonomous_semester_pattern()
    manifest, content = _manifest(), _content()
    blueprint = BlueprintBuilder().build(pattern, content, manifest)
    analyzer = StubAnalyzer()
    paper = asyncio.run(
        PaperGenerationPipeline(analyzer, request_interval_seconds=0).generate(
            pattern=pattern,
            content_map=content,
            manifest=manifest,
            blueprint=blueprint,
        )
    )
    assert analyzer.generation_calls == 3, "one generation call per part"
    assert analyzer.review_calls == 3, "one review call per part"
    return paper, manifest, content, blueprint


def test_autonomous_pattern_generates_a_complete_publishable_paper() -> None:
    paper, _, _, _ = _generate()

    assert len(paper.questions) == 16
    assert sum(question.candidate.marks for question in paper.questions) == 100
    assert all(question.accepted for question in paper.questions)
    assert paper.publication_ready
    assert paper.requires_human_approval
    assert not [
        finding
        for question in paper.questions
        for finding in question.findings
        if finding.severity.value == "error"
    ]


def test_autonomous_paper_reports_the_expected_bloom_spread() -> None:
    paper, _, _, blueprint = _generate()

    summary = GeneratedQuestionPaper.from_internal(paper, blueprint).bloom_summary

    assert summary.total == 16
    assert summary.deviations == 0
    assert summary.observed == {
        "remember": 3,
        "understand": 4,
        "apply": 5,
        "analyze": 3,
        "create": 1,
    }


def test_autonomous_paper_renders_part_headings_and_either_or_choices() -> None:
    paper, manifest, content, blueprint = _generate()
    published = GeneratedQuestionPaper.from_internal(paper, blueprint)

    with tempfile.TemporaryDirectory() as directory:
        saved = save_generated_paper(
            manifest=manifest,
            content_map=content,
            blueprint=blueprint,
            paper=published,
            output_directory=directory,
            pdf_output_directory=directory,
        )
        markdown = Path(saved.markdown_path).read_text(encoding="utf-8")
        pdf_bytes = Path(saved.pdf_path).stat().st_size

    # Headings come from the pattern, not the five-section school defaults.
    assert "## PART A — Answer ALL questions (10 x 2 = 20 marks)" in markdown
    assert "## PART B — Answer ALL questions (5 x 13 = 65 marks)" in markdown
    assert "## PART C — Answer ANY ONE question (1 x 15 = 15 marks)" in markdown
    assert "SECTION A" not in markdown

    # Five Part B alternatives plus the single Part C alternative, printed as
    # the bracketed [OR] the college uses.
    assert markdown.count("[OR]") == 6
    assert "**Maximum marks:** 100" in markdown
    assert "## Bloom Level Coverage" in markdown
    assert pdf_bytes > 10_000


def _three_sets():
    from question_paper_gen.patterns import get_pattern
    from question_paper_gen.pipeline import generate_paper_sets

    analyzer = StubAnalyzer()
    results, warnings = asyncio.run(
        generate_paper_sets(
            analyzer=analyzer,
            pattern=get_pattern(None),
            content_map=_content(),
            manifest=_manifest(),
            set_count=3,
        )
    )
    return results, warnings, analyzer


def test_three_sets_are_interchangeable_but_ask_different_questions() -> None:
    """An exam cell must be able to hand any set to any student."""
    results, warnings, analyzer = _three_sets()

    assert [paper.set_label for _, paper in results] == ["A", "B", "C"]
    for _, paper in results:
        assert len(paper.questions) == 16
        assert sum(q.candidate.marks for q in paper.questions) == 100
        assert paper.publication_ready

    # Interchangeable: identical marks and cognitive level, slot for slot.
    shapes = [
        [(q.candidate.marks, q.candidate.bloom_level) for q in paper.questions]
        for _, paper in results
    ]
    assert shapes[0] == shapes[1] == shapes[2]

    # But no question is reused between any two sets.
    texts = [
        {q.candidate.question_text for q in paper.questions} for _, paper in results
    ]
    assert not texts[0] & texts[1]
    assert not texts[0] & texts[2]
    assert not texts[1] & texts[2]
    assert warnings == []

    # One analysis is shared; only generation and review repeat per set.
    assert analyzer.generation_calls == 9
    assert analyzer.review_calls == 9


def test_every_slot_draws_a_different_facet_in_each_set() -> None:
    """The facet cycle is the only thing making sets differ — assert it holds."""
    from question_paper_gen.blueprints import BlueprintBuilder
    from question_paper_gen.patterns import get_pattern

    manifest, content = _manifest(), _content()
    blueprints = [
        BlueprintBuilder().build(get_pattern(None), content, manifest, set_index=index)
        for index in range(3)
    ]

    for position in range(len(blueprints[0].slots)):
        slots = [blueprint.slots[position] for blueprint in blueprints]
        assert len({slot.facet for slot in slots}) == 3
        # Same syllabus position in every set.
        assert len({(slot.topic_id, slot.marks, slot.bloom_level) for slot in slots}) == 1


def test_a_question_repeated_across_sets_is_reported() -> None:
    """If generation ignores the facet the sets collapse — that must not pass silently."""
    from question_paper_gen.patterns import get_pattern
    from question_paper_gen.pipeline import generate_paper_sets

    class FacetBlindAnalyzer(StubAnalyzer):
        @staticmethod
        def _distinct(slot_id: str, facet: str = "", tokens: int = 18) -> str:
            return StubAnalyzer._distinct(slot_id, "", tokens)

    _, warnings = asyncio.run(
        generate_paper_sets(
            analyzer=FacetBlindAnalyzer(),
            pattern=get_pattern(None),
            content_map=_content(),
            manifest=_manifest(),
            set_count=2,
        )
    )

    assert warnings
    assert all("more than one set" in warning for warning in warnings)


def test_course_outcome_tags_follow_the_units_without_any_typed_wording() -> None:
    """CAT-I tags 4/4/2 in Part A and 2/2/1 in Part B as CO1/CO2/CO3."""
    from question_paper_gen.blueprints import BlueprintBuilder
    from question_paper_gen.models import BloomLevel, ContentMap, Topic
    from question_paper_gen.patterns import get_pattern

    content = ContentMap(
        subject="Data Structures",
        topics=[
            Topic(
                topic_id=f"u{unit}t{index}",
                name=f"Unit {unit} topic {index}",
                unit=str(unit),
                source_pages=[1],
                supported_bloom_levels=list(BloomLevel),
            )
            for unit in (1, 2, 3)
            for index in range(3)
        ],
        # Deliberately no course_outcomes: the tag must not depend on them.
    )
    manifest, pattern = _manifest(), get_pattern("cat-1-75")
    blueprint = BlueprintBuilder().build(pattern, content, manifest)
    paper = asyncio.run(
        PaperGenerationPipeline(StubAnalyzer(), request_interval_seconds=0).generate(
            pattern=pattern,
            content_map=content,
            manifest=manifest,
            blueprint=blueprint,
        )
    )
    published = GeneratedQuestionPaper.from_internal(paper, blueprint)

    tags = [question.course_outcome_code for question in published.questions]
    assert tags == (
        ["CO1"] * 4
        + ["CO2"] * 4
        + ["CO3"] * 2
        + ["CO1"] * 2
        + ["CO2"] * 2
        + ["CO3"]
    )
    assert published.course_outcome_coverage.marks_by_outcome == {
        "CO1": 30,
        "CO2": 30,
        "CO3": 15,
    }
    assert published.course_outcome_coverage.unmapped_marks == 0
