import zipfile

import fitz

from question_paper_gen.models import (
    AnswerKeyEntry,
    BloomLevel,
    BlueprintSlot,
    DocumentManifest,
    DocumentQuality,
    GeneratedQuestionPaper,
    MarkingCriterion,
    PageContent,
    PaperBlueprint,
    QuestionKind,
    QuestionPaperItem,
)
from question_paper_gen.outputs import save_demo_edited_outputs


def test_demo_edit_recreates_paper_and_matching_scheme(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PDF_OUTPUT_DIR", str(tmp_path))
    manifest = DocumentManifest(
        document_id="abcdef123456-p1-1",
        original_filename="unit.pdf",
        sha256="a" * 64,
        source_pdf_path=str(tmp_path / "source.pdf"),
        artifact_directory=str(tmp_path),
        pages=[
            PageContent(
                page_number=1,
                width=600,
                height=800,
                text="Stacks use last-in first-out ordering.",
                rendered_image_path=str(tmp_path / "page.png"),
            )
        ],
        visual_assets=[],
        quality=DocumentQuality(
            passed=True, page_count=1, text_character_count=40
        ),
    )
    slot = BlueprintSlot(
        slot_id="part_a-1",
        question_number="1",
        section_id="part_a",
        marks=2,
        bloom_level=BloomLevel.UNDERSTAND,
        question_kind=QuestionKind.VERY_SHORT_ANSWER,
        topic_id="stacks",
        unit="1",
    )
    blueprint = PaperBlueprint(
        pattern_id="autonomous-semester-100",
        subject="Data Structures",
        slots=[slot],
    )
    question = QuestionPaperItem(
        question_id="question-1",
        slot_id=slot.slot_id,
        question_number="1",
        section_id=slot.section_id,
        question_kind=slot.question_kind,
        question_text="Explain why a stack follows LIFO order.",
        marks=2,
        bloom_level=BloomLevel.UNDERSTAND,
        accepted=True,
        faculty_modified=True,
    )
    paper = GeneratedQuestionPaper(
        title="Data Structures Examination",
        subject="Data Structures",
        duration_minutes=180,
        total_marks=2,
        instructions=[],
        questions=[question],
        publication_ready=True,
    )
    answer_key = [
        AnswerKeyEntry(
            question_id=question.question_id,
            question_number="1",
            section_id="part_a",
            marks=2,
            criteria=[MarkingCriterion(criterion="Explains LIFO", marks=2)],
            answer="The most recently inserted element is removed first.",
        )
    ]

    outputs = save_demo_edited_outputs(
        paper_id="a" * 32,
        manifest=manifest,
        blueprint=blueprint,
        paper=paper,
        answer_key=answer_key,
    )

    with fitz.open(outputs.pdf_path) as document:
        paper_text = "".join(page.get_text() for page in document)
    with fitz.open(outputs.scheme_path) as document:
        scheme_text = "".join(page.get_text() for page in document)
    assert question.question_text in paper_text
    assert answer_key[0].answer not in paper_text
    assert "The most recently inserted element" in scheme_text
    assert "Explains LIFO" in scheme_text
    with zipfile.ZipFile(outputs.docx_path) as document:
        word_xml = document.read("word/document.xml").decode("utf-8")
    assert "Explain why a stack follows LIFO order." in word_xml
    assert answer_key[0].answer not in word_xml
