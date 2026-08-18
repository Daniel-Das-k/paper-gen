from pathlib import Path

import fitz

from question_paper_gen.documents import PdfInspector


def _create_pdf(path: Path) -> None:
    document = fitz.open()
    for page_number in range(1, 6):
        page = document.new_page()
        page.insert_text(
            (72, 72),
            f"Unit {page_number}: Database Systems\n"
            f"Page marker {page_number}. Normalization removes dependencies.",
            fontsize=12,
        )
    document.save(path)
    document.close()


def test_pdf_inspection_extracts_text_and_page_render(tmp_path: Path) -> None:
    pdf_path = tmp_path / "notes.pdf"
    _create_pdf(pdf_path)

    manifest = PdfInspector(tmp_path / "artifacts").inspect(pdf_path)

    assert manifest.quality.passed
    assert manifest.quality.page_count == 5
    assert manifest.selected_page_start == 1
    assert manifest.selected_page_end == 5
    assert "Normalization" in manifest.pages[0].text
    assert Path(manifest.pages[0].rendered_image_path).exists()
    assert Path(manifest.source_pdf_path).exists()
    assert len(manifest.sha256) == 64


def test_same_pdf_has_stable_document_id(tmp_path: Path) -> None:
    pdf_path = tmp_path / "notes.pdf"
    _create_pdf(pdf_path)
    inspector = PdfInspector(tmp_path / "artifacts")

    first = inspector.inspect(pdf_path)
    second = inspector.inspect(pdf_path)

    assert first.document_id == second.document_id
    assert first.sha256 == second.sha256


def test_pdf_inspection_physically_isolates_selected_original_pages(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "notes.pdf"
    _create_pdf(pdf_path)

    manifest = PdfInspector(tmp_path / "artifacts").inspect(
        pdf_path,
        start_page=2,
        end_page=4,
    )

    assert manifest.source_total_pages == 5
    assert manifest.selected_page_start == 2
    assert manifest.selected_page_end == 4
    assert manifest.quality.page_count == 3
    assert [page.page_number for page in manifest.pages] == [2, 3, 4]
    assert "Page marker 1" not in " ".join(page.text for page in manifest.pages)
    assert "Page marker 5" not in " ".join(page.text for page in manifest.pages)

    selected_pdf = fitz.open(manifest.source_pdf_path)
    try:
        assert selected_pdf.page_count == 3
        assert "Page marker 2" in selected_pdf[0].get_text()
        assert "Page marker 4" in selected_pdf[2].get_text()
    finally:
        selected_pdf.close()


def test_front_matter_only_selection_fails_before_model_call(tmp_path: Path) -> None:
    pdf_path = tmp_path / "front-matter.pdf"
    document = fitz.open()
    front_matter = [
        "CENTRAL BOARD OF SECONDARY EDUCATION Cover",
        "Dedicated to the contributors",
        "Published by: Academic Unit",
        "Acknowledgements and review team",
        "THE CONSTITUTION OF INDIA",
        "CENTRAL BOARD OF SECONDARY EDUCATION Publication",
        "Acknowledgments and patrons",
        "Course introduction and general educational purpose",
        "Contents Unit 1 Unit 2 Unit 3 Unit 4 Unit 5",
        "",
    ]
    for text in front_matter:
        page = document.new_page()
        if text:
            page.insert_text((72, 72), text, fontsize=12)
    document.save(pdf_path)
    document.close()

    manifest = PdfInspector(tmp_path / "artifacts").inspect(
        pdf_path,
        start_page=1,
        end_page=10,
    )

    assert not manifest.quality.passed
    assert any("mostly cover" in error for error in manifest.quality.errors)


def test_visual_prefilter_rejects_page_masks_and_tiny_fragments() -> None:
    page = fitz.Rect(0, 0, 600, 800)

    assert not PdfInspector._is_usable_embedded_visual(
        page,
        fitz.Rect(0, 0, 600, 800),
        width=2480,
        height=3508,
        byte_count=1076,
    )
    assert not PdfInspector._is_usable_embedded_visual(
        page,
        fitz.Rect(100, 100, 120, 108),
        width=90,
        height=14,
        byte_count=150,
    )
    assert not PdfInspector._is_usable_embedded_visual(
        page,
        fitz.Rect(31, 174, 424, 567),
        width=1894,
        height=1894,
        byte_count=3579,
    )
    assert PdfInspector._is_usable_embedded_visual(
        page,
        fitz.Rect(100, 180, 420, 380),
        width=960,
        height=600,
        byte_count=24_000,
    )
