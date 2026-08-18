import json

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
        slot_id="section_a-1",
        question_number="1",
        section_id="section_a",
        marks=1,
        bloom_level=BloomLevel.REMEMBER,
        question_kind=QuestionKind.MULTIPLE_CHOICE,
        topic_id="atoms",
        unit="1",
    )
    candidate = QuestionCandidate(
        candidate_id="section_a-1-batch",
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
        pattern_id="sample-paper-80-v2",
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
    assert saved_question["section_id"] == "section_a"
    assert saved_question["question_kind"] == "multiple_choice"
    assert saved_question["question_text"] == candidate.question_text
    assert "answer" not in saved_question
    assert "marking_scheme" not in saved_question
    assert "evidence" not in saved_question
    markdown = saved.markdown_path.read_text(encoding="utf-8")
    assert "Status:** Faculty approval required" in markdown
    assert "SECTION A — MCQ AND ASSERTION–REASON" in markdown
    assert "Faculty Answer and Review Appendix" not in markdown
    assert "Option (A)." not in markdown
    with fitz.open(saved.pdf_path) as pdf:
        pdf_text = "".join(page.get_text() for page in pdf)
    assert "Chemistry Academic Examination" in pdf_text
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
