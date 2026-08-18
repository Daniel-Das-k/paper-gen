from question_paper_gen.evidence import build_evidence_chunks, is_answer_key_page
from question_paper_gen.models import (
    DocumentManifest,
    DocumentQuality,
    PageContent,
)

ANSWER_PAGE = (
    "ANSWERS 209 EXERCISE 2.1 1. 6 −π 2. 6 π 3. 6 π 4. 3 −π 5. 2 3 π "
    "6. 4 π − 7. 6 π 8. 6 π 9. 3 4 π 10. 4 −π 11. 3 4 π 12. 2 3 π 13. B 14. B"
)
DENSE_ANSWER_PAGE = (
    "MATHEMATICS 214 EXERCISE 4.5 1. Consistent 2. Consistent 3. Inconsistent "
    "4. Consistent 5. Inconsistent 6. Consistent 7. x = 2, y = 3 8. x = 5 "
    "9. y = 1 10. x = 0 11. z = 4 12. y = 7"
)
INSTRUCTIONAL_PAGE = (
    "MATHEMATICS 56 A matrix is an ordered rectangular array of numbers or "
    "functions. The numbers or functions are called the elements or the "
    "entries of the matrix. We denote matrices by capital letters. The "
    "horizontal lines of elements are said to constitute rows of the matrix "
    "and the vertical lines of elements are said to constitute columns. A "
    "matrix having m rows and n columns is called a matrix of order m by n. "
    "Consider the following example which illustrates the arrangement of "
    "elements and explains how the order of a matrix is determined in "
    "practice for a rectangular array supplied by a data table."
)


def _manifest(pages: list[tuple[int, str]]) -> DocumentManifest:
    return DocumentManifest(
        document_id="doc",
        original_filename="notes.pdf",
        sha256="a" * 64,
        source_pdf_path="/tmp/source.pdf",
        artifact_directory="/tmp/artifacts",
        pages=[
            PageContent(
                page_number=number,
                width=600,
                height=800,
                text=text,
                rendered_image_path="/tmp/page.png",
            )
            for number, text in pages
        ],
        visual_assets=[],
        quality=DocumentQuality(
            passed=True,
            page_count=len(pages),
            text_character_count=sum(len(text) for _, text in pages),
        ),
    )


def test_answer_key_pages_are_detected() -> None:
    assert is_answer_key_page(ANSWER_PAGE)
    assert is_answer_key_page(DENSE_ANSWER_PAGE)


def test_instructional_pages_are_not_flagged_as_answer_keys() -> None:
    assert not is_answer_key_page(INSTRUCTIONAL_PAGE)


def test_answer_key_pages_are_excluded_from_evidence_chunks() -> None:
    chunks = build_evidence_chunks(
        _manifest(
            [
                (1, INSTRUCTIONAL_PAGE),
                (2, ANSWER_PAGE),
                (3, DENSE_ANSWER_PAGE),
            ]
        )
    )

    cited_pages = {chunk.page_number for chunk in chunks.values()}
    assert cited_pages == {1}
