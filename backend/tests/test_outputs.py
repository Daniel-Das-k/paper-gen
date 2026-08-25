import json
import tempfile
from pathlib import Path

import fitz

from question_paper_gen.models import (
    BloomLevel,
    BlueprintSlot,
    ContentMap,
    DocumentManifest,
    DocumentQuality,
    ExamPaper,
    GeneratedQuestionPaper,
    MarkingCriterion,
    PageContent,
    PaperBlueprint,
    QuestionCandidate,
    QuestionKind,
    SourceEvidence,
    Topic,
    ValidatedQuestion,
    ValidationFinding,
    ValidationSeverity,
)
from question_paper_gen.outputs import save_generated_paper


def test_generated_paper_is_saved_as_json_and_markdown(tmp_path) -> None:
    manifest = DocumentManifest(
        document_id="abcdef123456-p1-1",
        original_filename="source.pdf",
        sha256="a" * 64,
        source_pdf_path=str(tmp_path / "source-selected.pdf"),
        artifact_directory=str(tmp_path),
        pages=[
            PageContent(
                page_number=1,
                width=600,
                height=800,
                text="Grounded chemistry source material.",
                rendered_image_path=str(tmp_path / "page-0001.png"),
            )
        ],
        visual_assets=[],
        quality=DocumentQuality(
            passed=True,
            page_count=1,
            text_character_count=37,
        ),
    )
    content = ContentMap(
        subject="Chemistry",
        topics=[
            Topic(
                topic_id="atoms",
                name="Atomic Structure",
                unit="1",
                source_pages=[1],
            )
        ],
    )
    slot = BlueprintSlot(
        slot_id="part_a-1",
        question_number="1",
        section_id="part_a",
        marks=1,
        bloom_level=BloomLevel.REMEMBER,
        question_kind=QuestionKind.MULTIPLE_CHOICE,
        topic_id="atoms",
        unit="1",
    )
    candidate = QuestionCandidate(
        candidate_id="part_a-1-batch",
        slot_id=slot.slot_id,
        question_text="Which statement is correct?\n(A) A\n(B) B\n(C) C\n(D) D",
        answer="Option (A).",
        marks=1,
        bloom_level=BloomLevel.REMEMBER,
        bloom_justification="Recall is required.",
        marking_scheme=[MarkingCriterion(criterion="Correct option", marks=1)],
        evidence=SourceEvidence(page_numbers=[1], excerpts=["Grounded chemistry"]),
        confidence=0.95,
    )
    blueprint = PaperBlueprint(
        pattern_id="autonomous-semester-100",
        subject="Chemistry",
        slots=[slot],
    )
    paper = ExamPaper(
        title="Chemistry Academic Examination",
        subject="Chemistry",
        duration_minutes=180,
        total_marks=80,
        instructions=["Answer all questions."],
        questions=[ValidatedQuestion(candidate=candidate, accepted=True)],
        publication_ready=True,
    )

    public_paper = GeneratedQuestionPaper.from_internal(paper, blueprint)
    saved = save_generated_paper(
        manifest=manifest,
        content_map=content,
        blueprint=blueprint,
        paper=public_paper,
        output_directory=tmp_path / "test_papers",
        pdf_output_directory=tmp_path / "outputs",
    )

    assert saved.json_path.exists()
    assert saved.markdown_path.exists()
    assert saved.pdf_path.exists()
    payload = json.loads(saved.json_path.read_text(encoding="utf-8"))
    assert payload["paper"]["subject"] == "Chemistry"
    saved_question = payload["paper"]["questions"][0]
    assert saved_question["question_number"] == "1"
    assert saved_question["section_id"] == "part_a"
    assert saved_question["question_kind"] == "multiple_choice"
    assert saved_question["question_text"] == candidate.question_text
    assert "answer" not in saved_question
    assert "marking_scheme" not in saved_question
    assert "evidence" not in saved_question
    markdown = saved.markdown_path.read_text(encoding="utf-8")
    assert "Status:** Faculty approval required" in markdown
    assert "PART A — Answer ALL questions (10 x 2 = 20 marks)" in markdown
    assert "Faculty Answer and Review Appendix" not in markdown
    assert "Option (A)." not in markdown
    with fitz.open(saved.pdf_path) as pdf:
        pdf_text = "".join(page.get_text() for page in pdf)
    # The PDF is the college's own paper now, not a generic title page.
    assert "RAJALAKSHMI ENGINEERING COLLEGE" in pdf_text
    assert "Reg. No." in pdf_text
    assert "[Regulations 2023]" in pdf_text
    assert "Which statement is correct?" in pdf_text
    assert "Option (A)." not in pdf_text

    blocked_internal = paper.model_copy(
        update={
            "publication_ready": False,
            "questions": [
                ValidatedQuestion(
                    candidate=candidate,
                    accepted=False,
                    findings=[
                        ValidationFinding(
                            code="incorrect_answer",
                            severity=ValidationSeverity.ERROR,
                            message="Answer must be corrected.",
                        )
                    ],
                )
            ],
        }
    )
    blocked = save_generated_paper(
        manifest=manifest,
        content_map=content,
        blueprint=blueprint,
        paper=GeneratedQuestionPaper.from_internal(blocked_internal, blueprint),
        output_directory=tmp_path / "blocked_papers",
        pdf_output_directory=tmp_path / "outputs",
    ).markdown_path.read_text(encoding="utf-8")
    assert "PUBLICATION BLOCKED" in blocked
    assert "[REVIEW REQUIRED]" in blocked
    assert "Answer must be corrected." in blocked


def test_evaluation_scheme_carries_answers_the_paper_never_shows() -> None:
    """The scheme is the only artifact allowed to contain answers."""
    import fitz

    from question_paper_gen.models import ExamPaper
    from question_paper_gen.outputs import save_evaluation_scheme

    slot = BlueprintSlot(
        slot_id="part_b-1",
        question_number="11",
        section_id="part_b",
        marks=13,
        bloom_level=BloomLevel.APPLY,
        question_kind=QuestionKind.LONG_ANSWER,
        topic_id="atoms",
        unit="1",
    )
    candidate = QuestionCandidate(
        candidate_id="part_b-1-batch",
        slot_id=slot.slot_id,
        question_text="Derive the electronic configuration and justify each shell.",
        answer="Apply the Aufbau principle, then Hund's rule for degenerate orbitals.",
        marks=13,
        bloom_level=BloomLevel.APPLY,
        bloom_justification="The method must be applied to a fresh case.",
        marking_scheme=[
            MarkingCriterion(criterion="States the Aufbau ordering", marks=7),
            MarkingCriterion(criterion="Applies Hund's rule correctly", marks=6),
        ],
        evidence=SourceEvidence(page_numbers=[1], excerpts=["Grounded chemistry"]),
        confidence=0.95,
    )
    blueprint = PaperBlueprint(
        pattern_id="autonomous-semester-100",
        subject="Chemistry",
        slots=[slot],
    )
    manifest = DocumentManifest(
        document_id="abcdef123456-p1-1",
        original_filename="source.pdf",
        sha256="a" * 64,
        source_pdf_path="/tmp/source-selected.pdf",
        artifact_directory="/tmp",
        pages=[
            PageContent(
                page_number=1,
                width=600,
                height=800,
                text="Grounded chemistry source material.",
                rendered_image_path="/tmp/page-0001.png",
            )
        ],
        visual_assets=[],
        quality=DocumentQuality(passed=True, page_count=1, text_character_count=37),
    )
    internal = ExamPaper(
        title="Chemistry Academic Examination",
        subject="Chemistry",
        duration_minutes=180,
        total_marks=100,
        instructions=["Answer all questions"],
        questions=[ValidatedQuestion(candidate=candidate, accepted=True)],
    )

    with tempfile.TemporaryDirectory() as directory:
        scheme_path = save_evaluation_scheme(
            manifest=manifest,
            blueprint=blueprint,
            paper=internal,
            pdf_path=Path(directory) / "paper-scheme.pdf",
        )
        assert scheme_path.is_file()
        with fitz.open(scheme_path) as document:
            text = "\n".join(page.get_text() for page in document)

    # The scheme shows the answer, the mark-wise criteria, and the approval gate.
    assert candidate.answer[:24] in text
    assert candidate.marking_scheme[0].criterion[:20] in text
    assert "SCHEME OF EVALUATION" in text
    assert "REQUIRES FACULTY APPROVAL" in text

    # And the public paper still cannot carry any of it.
    public = GeneratedQuestionPaper.from_internal(internal, blueprint)
    serialized = public.model_dump_json()
    assert candidate.answer not in serialized
    assert candidate.marking_scheme[0].criterion not in serialized


def test_answer_key_travels_beside_the_paper_never_inside_it() -> None:
    """Faculty need answers to review; students must never receive them."""
    from question_paper_gen.models import AnswerKeyEntry, ExamPaper

    slot = BlueprintSlot(
        slot_id="part_b-1",
        question_number="11",
        section_id="part_b",
        marks=13,
        bloom_level=BloomLevel.APPLY,
        question_kind=QuestionKind.LONG_ANSWER,
        topic_id="atoms",
        unit="1",
    )
    candidate = QuestionCandidate(
        candidate_id="part_b-1-batch",
        slot_id=slot.slot_id,
        question_text="(a) Derive the configuration.\nOR\n(b) Justify each shell.",
        answer="Apply the Aufbau principle, then Hund's rule.",
        marks=13,
        bloom_level=BloomLevel.APPLY,
        bloom_justification="Applies a method.",
        marking_scheme=[
            MarkingCriterion(criterion="States the Aufbau ordering", marks=7),
            MarkingCriterion(criterion="Applies Hund's rule", marks=6),
        ],
        evidence=SourceEvidence(page_numbers=[1], excerpts=["Grounded chemistry"]),
        confidence=0.95,
    )
    blueprint = PaperBlueprint(
        pattern_id="autonomous-semester-100", subject="Chemistry", slots=[slot]
    )
    internal = ExamPaper(
        title="Chemistry Academic Examination",
        subject="Chemistry",
        duration_minutes=180,
        total_marks=100,
        instructions=[],
        questions=[ValidatedQuestion(candidate=candidate, accepted=True)],
    )

    key = AnswerKeyEntry.build(
        internal.questions, {slot.slot_id: slot}
    )
    assert len(key) == 1
    assert key[0].question_number == "11"
    assert key[0].answer == candidate.answer
    assert sum(item.marks for item in key[0].criteria) == 13

    # The student-facing paper still cannot carry any of it.
    public = GeneratedQuestionPaper.from_internal(internal, blueprint)
    serialized = public.model_dump_json()
    assert candidate.answer not in serialized
    assert "States the Aufbau ordering" not in serialized


def test_the_pdf_is_the_college_paper_with_questions_placed_into_it() -> None:
    """Everything outside the questions is fixed; only the questions vary."""
    import asyncio

    import fitz

    from question_paper_gen.blueprints import BlueprintBuilder
    from question_paper_gen.models import ExamHeader
    from question_paper_gen.patterns import get_pattern
    from question_paper_gen.pipeline import PaperGenerationPipeline

    import sys

    sys.path.insert(0, "tests")
    from test_autonomous_pattern_e2e import StubAnalyzer, _manifest

    manifest = _manifest()
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
    )
    pattern = get_pattern("cat-1-75")
    blueprint = BlueprintBuilder().build(pattern, content, manifest)
    paper = asyncio.run(
        PaperGenerationPipeline(StubAnalyzer(), request_interval_seconds=0).generate(
            pattern=pattern,
            content_map=content,
            manifest=manifest,
            blueprint=blueprint,
        )
    )
    published = GeneratedQuestionPaper.from_internal(paper, blueprint).model_copy(
        update={
            "exam_header": ExamHeader(
                year="II",
                semester="III",
                subject_code="CS23231",
                qp_code="011071",
                date="09.04.2025",
            )
        }
    )

    with tempfile.TemporaryDirectory() as directory:
        saved = save_generated_paper(
            manifest=manifest,
            content_map=content,
            blueprint=blueprint,
            paper=published,
            output_directory=directory,
            pdf_output_directory=directory,
        )
        with fitz.open(saved.pdf_path) as document:
            text = "\n".join(page.get_text() for page in document)

    # The fixed template, none of which anyone typed for this paper.
    assert "RAJALAKSHMI ENGINEERING COLLEGE" in text
    assert "An AUTONOMOUS Institution" in text
    assert "Continuous Assessment Test-I" in text and "[CAT-I]" in text
    assert "[Regulations 2023]" in text
    assert "Common to CSE, ECE, EEE, IT, AIML, CSD, AI & DS, CS" in text
    assert "Reg. No." in text
    assert "Max. Marks: 75" in text
    assert "Time: 120 Minutes" in text
    assert "PART A — Answer ALL questions (10 x 2 = 20 marks)" in text
    assert "PART B — Answer ALL questions (5 x 11 = 55 marks)" in text

    # Questions run continuously while their CO and level tags keep unit ownership.
    assert "1" in text and "15" in text
    assert "[CO1]" in text and "[CO3]" in text
    assert "[A1]" in text and "[B1]" in text
    assert "[OR]" in text
