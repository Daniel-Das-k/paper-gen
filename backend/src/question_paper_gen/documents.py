from __future__ import annotations

import hashlib
import logging
import math
import re
import tempfile
from pathlib import Path

import fitz

from .models import (
    BoundingBox,
    DocumentManifest,
    DocumentQuality,
    PageContent,
    VisualAsset,
    VisualType,
    normalize_artifact_path,
)

logger = logging.getLogger("uvicorn.error")


class DocumentInspectionError(ValueError):
    pass


class PdfInspector:
    """Extract text, page renders, and embedded visual candidates from a PDF."""

    def __init__(
        self,
        artifact_root: str | Path = "artifacts",
        render_dpi: int = 180,
        max_pages: int = 1000,
        max_file_size_mb: int = 50,
    ) -> None:
        self.artifact_root = Path(artifact_root)
        self.render_dpi = render_dpi
        self.max_pages = max_pages
        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024

    def inspect_units(
        self,
        sources: list[UnitSource],
    ) -> DocumentManifest:
        """Inspect several uploads as one exam source, one file per syllabus unit.

        A continuous assessment test covers whole units and, where a unit is split
        between two tests, only part of one — so each upload carries its own page
        range. The selected pages are concatenated into a single isolated PDF
        before any model call, exactly as a single-file selection is, and every
        page keeps the unit it came from. That is what lets a question be bound to
        its unit and therefore to its course outcome without guessing.
        """
        if not sources:
            raise DocumentInspectionError("no unit files were supplied")
        merged = fitz.open()
        page_units: list[tuple[str, str, int]] = []
        try:
            for source in sources:
                path = Path(source.file_path)
                self._validate_source(path)
                try:
                    document = fitz.open(path)
                except Exception as exc:
                    raise DocumentInspectionError(
                        f"could not open {source.original_filename}: {exc}"
                    ) from exc
                with document:
                    if document.needs_pass:
                        raise DocumentInspectionError(
                            f"{source.original_filename} is password-protected"
                        )
                    if document.page_count == 0:
                        raise DocumentInspectionError(
                            f"{source.original_filename} has no pages"
                        )
                    start = source.start_page or 1
                    end = source.end_page or document.page_count
                    self._validate_page_range(start, end, document.page_count)
                    merged.insert_pdf(
                        document, from_page=start - 1, to_page=end - 1
                    )
                    for original in range(start, end + 1):
                        page_units.append(
                            (source.unit, source.original_filename, original)
                        )
            if merged.page_count > self.max_pages:
                raise DocumentInspectionError(
                    f"the selected pages total {merged.page_count}; "
                    f"limit is {self.max_pages}"
                )
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as handle:
                merged_path = Path(handle.name)
            merged.save(merged_path)
        finally:
            merged.close()

        try:
            manifest = self.inspect(merged_path)
        finally:
            merged_path.unlink(missing_ok=True)

        # Every page carries the unit it was uploaded under.
        tagged = [
            page.model_copy(
                update={
                    "unit": page_units[index][0],
                    "source_filename": page_units[index][1],
                    "original_page_number": page_units[index][2],
                }
            )
            if index < len(page_units)
            else page
            for index, page in enumerate(manifest.pages)
        ]
        logger.info(
            "pdf.inspect_units.complete files=%d pages=%d units=%s",
            len(sources),
            len(tagged),
            ",".join(sorted({source.unit for source in sources})),
        )
        return manifest.model_copy(update={"pages": tagged})

    def inspect(
        self,
        file_path: str | Path,
        *,
        start_page: int | None = None,
        end_page: int | None = None,
    ) -> DocumentManifest:
        source = Path(file_path)
        logger.info(
            "pdf.inspect.start file=%s requested_start=%s requested_end=%s",
            source.name,
            start_page,
            end_page,
        )
        self._validate_source(source)
        data = source.read_bytes()
        sha256 = hashlib.sha256(data).hexdigest()

        try:
            document = fitz.open(stream=data, filetype="pdf")
        except Exception as exc:
            raise DocumentInspectionError(f"could not open PDF: {exc}") from exc

        if document.needs_pass:
            document.close()
            raise DocumentInspectionError("password-protected PDFs are not supported")
        if document.page_count == 0:
            document.close()
            raise DocumentInspectionError("PDF has no pages")
        if document.page_count > self.max_pages:
            document.close()
            raise DocumentInspectionError(
                f"PDF has {document.page_count} pages; limit is {self.max_pages}"
            )
        total_pages = document.page_count
        selected_start = start_page if start_page is not None else 1
        selected_end = end_page if end_page is not None else total_pages
        self._validate_page_range(selected_start, selected_end, total_pages)

        document_id = f"{sha256[:12]}-p{selected_start}-{selected_end}"
        output_dir = self.artifact_root / document_id
        pages_dir = output_dir / "pages"
        assets_dir = output_dir / "visuals"
        pages_dir.mkdir(parents=True, exist_ok=True)
        assets_dir.mkdir(parents=True, exist_ok=True)
        stored_pdf_path = output_dir / "source-selected.pdf"
        selected_document = fitz.open()
        selected_document.insert_pdf(
            document,
            from_page=selected_start - 1,
            to_page=selected_end - 1,
        )
        selected_document.save(stored_pdf_path)
        selected_document.close()

        pages: list[PageContent] = []
        assets: list[VisualAsset] = []
        pages_without_text: list[int] = []
        total_characters = 0

        for page_index in range(selected_start - 1, selected_end):
            page = document.load_page(page_index)
            page_number = page_index + 1
            text = self._clean_text(page.get_text("text"))
            total_characters += len(text)
            if len(text) < 20:
                pages_without_text.append(page_number)

            page_image_path = pages_dir / f"page-{page_number:04d}.png"
            page.get_pixmap(dpi=self.render_dpi, alpha=False).save(page_image_path)

            page_asset_ids: list[str] = []
            for image_index, image_info in enumerate(page.get_images(full=True), start=1):
                xref = image_info[0]
                try:
                    extracted = document.extract_image(xref)
                    image_bytes = extracted["image"]
                    rectangles = page.get_image_rects(xref)
                    rect = rectangles[0] if rectangles else None
                    if not self._is_usable_embedded_visual(
                        page.rect,
                        rect,
                        width=int(extracted.get("width", 0)),
                        height=int(extracted.get("height", 0)),
                        byte_count=len(image_bytes),
                    ):
                        continue
                    extension = extracted.get("ext", "png")
                    image_path = assets_dir / (
                        f"page-{page_number:04d}-image-{image_index:02d}.{extension}"
                    )
                    image_path.write_bytes(image_bytes)
                    asset_id = f"p{page_number}-image-{image_index}"
                    page_asset_ids.append(asset_id)
                    assets.append(
                        VisualAsset(
                            asset_id=asset_id,
                            page_number=page_number,
                            asset_type=VisualType.RASTER_IMAGE,
                            bounding_box=(
                                BoundingBox(
                                    x0=rect.x0,
                                    y0=rect.y0,
                                    x1=rect.x1,
                                    y1=rect.y1,
                                )
                                if rect and not rect.is_empty
                                else None
                            ),
                            image_path=normalize_artifact_path(image_path),
                            caption=self._find_nearby_caption(page, rect),
                            nearby_text=self._nearby_text(page, rect),
                            question_eligible=False,
                            confidence=0,
                            rejection_reason="awaiting multimodal visual analysis",
                        )
                    )
                except Exception:
                    # One malformed embedded image must not fail the entire document.
                    continue

            pages.append(
                PageContent(
                    page_number=page_number,
                    width=page.rect.width,
                    height=page.rect.height,
                    text=text,
                    rendered_image_path=normalize_artifact_path(page_image_path),
                    visual_asset_ids=page_asset_ids,
                )
            )

        document.close()
        warnings: list[str] = []
        errors: list[str] = []
        if pages_without_text:
            warnings.append(
                f"{len(pages_without_text)} page(s) contain little or no extractable text; "
                "OCR or multimodal inspection is required"
            )
        if total_characters < 20:
            errors.append("document contains too little readable text")
        elif total_characters < 100:
            warnings.append(
                "document contains limited extractable text; inspect source quality"
            )
        instructional_pages = [
            page.page_number for page in pages if self._looks_instructional(page.text)
        ]
        minimum_instructional_pages = max(1, math.ceil(len(pages) * 0.25))
        if (
            len(pages) >= 5
            and len(instructional_pages) < minimum_instructional_pages
        ):
            errors.append(
                "selected range is mostly cover, front-matter, contents, or blank "
                "pages; choose pages containing explained instructional material"
            )
        if not assets:
            warnings.append(
                "no embedded raster figures found; vector diagrams may still exist in page renders"
            )

        quality = DocumentQuality(
            passed=not errors,
            page_count=len(pages),
            text_character_count=total_characters,
            pages_without_text=pages_without_text,
            warnings=warnings,
            errors=errors,
        )
        logger.info(
            "pdf.inspect.complete document_id=%s pages=%d text_characters=%d "
            "embedded_visuals=%d warnings=%d errors=%d selected_range=%d-%d "
            "source_total_pages=%d",
            document_id,
            len(pages),
            total_characters,
            len(assets),
            len(warnings),
            len(errors),
            selected_start,
            selected_end,
            total_pages,
        )
        return DocumentManifest(
            document_id=document_id,
            original_filename=source.name,
            sha256=sha256,
            source_pdf_path=normalize_artifact_path(stored_pdf_path),
            artifact_directory=normalize_artifact_path(output_dir),
            source_total_pages=total_pages,
            selected_page_start=selected_start,
            selected_page_end=selected_end,
            pages=pages,
            visual_assets=assets,
            quality=quality,
        )

    @staticmethod
    def _is_usable_embedded_visual(
        page_rect: fitz.Rect,
        image_rect: fitz.Rect | None,
        *,
        width: int,
        height: int,
        byte_count: int,
    ) -> bool:
        """Reject PDF masks, page backgrounds, glyph fragments, and tiny ornaments."""
        if image_rect is None or image_rect.is_empty or width <= 0 or height <= 0:
            return False
        page_area = max(page_rect.width * page_rect.height, 1)
        coverage = image_rect.width * image_rect.height / page_area
        if coverage >= 0.60:
            return False
        if image_rect.width < 40 or image_rect.height < 30:
            return False
        if width < 100 or height < 60:
            return False
        aspect_ratio = max(width / height, height / width)
        if aspect_ratio > 12:
            return False
        # Very large images compressed to only a few kilobytes are almost always
        # binary clipping masks or blank backgrounds, not student-usable figures.
        # Prefer omitting a doubtful visual to asking the model to infer its meaning.
        if width * height >= 1_000_000 and byte_count < 8_192:
            return False
        return True

    def _validate_source(self, source: Path) -> None:
        if not source.exists() or not source.is_file():
            raise DocumentInspectionError(f"file not found: {source}")
        if source.suffix.lower() != ".pdf":
            raise DocumentInspectionError("the first MVP accepts PDF files only")
        if source.stat().st_size == 0:
            raise DocumentInspectionError("PDF is empty")
        if source.stat().st_size > self.max_file_size_bytes:
            limit_mb = self.max_file_size_bytes // (1024 * 1024)
            raise DocumentInspectionError(f"PDF exceeds the {limit_mb} MB limit")

    @staticmethod
    def _validate_page_range(start_page: int, end_page: int, total_pages: int) -> None:
        if start_page < 1:
            raise DocumentInspectionError("start page must be at least 1")
        if end_page < start_page:
            raise DocumentInspectionError("end page must be greater than or equal to start page")
        if end_page > total_pages:
            raise DocumentInspectionError(
                f"end page {end_page} exceeds document length of {total_pages} pages"
            )

    @staticmethod
    def _clean_text(text: str) -> str:
        text = text.replace("\x00", "")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @staticmethod
    def _looks_instructional(text: str) -> bool:
        normalized = " ".join(text.lower().split())
        if len(normalized) < 40:
            return False
        front_matter_markers = (
            "central board of secondary education",
            "dedicated to:",
            "published by:",
            "acknowledgements",
            "acknowledgments",
            "the constitution of india",
        )
        if any(marker in normalized for marker in front_matter_markers):
            return False
        if "contents" in normalized and normalized.count("unit ") >= 3:
            return False
        words = re.findall(r"[a-zA-Z]{2,}", normalized)
        return len(words) >= 8

    @staticmethod
    def _find_nearby_caption(page: fitz.Page, rect: fitz.Rect | None) -> str | None:
        if rect is None:
            return None
        candidates: list[tuple[float, str]] = []
        for block in page.get_text("blocks"):
            block_rect = fitz.Rect(block[:4])
            block_text = str(block[4]).strip()
            if not block_text:
                continue
            vertical_gap = min(
                abs(block_rect.y0 - rect.y1),
                abs(rect.y0 - block_rect.y1),
            )
            horizontally_overlaps = block_rect.x1 >= rect.x0 and block_rect.x0 <= rect.x1
            if horizontally_overlaps and vertical_gap <= 80:
                if re.match(r"(?i)^(figure|fig\.?|diagram|chart|graph|table)\b", block_text):
                    candidates.append((vertical_gap, block_text))
        return min(candidates, default=(0, None), key=lambda item: item[0])[1]

    @staticmethod
    def _nearby_text(page: fitz.Page, rect: fitz.Rect | None) -> str | None:
        if rect is None:
            return None
        expanded = fitz.Rect(
            max(0, rect.x0 - 80),
            max(0, rect.y0 - 120),
            min(page.rect.width, rect.x1 + 80),
            min(page.rect.height, rect.y1 + 120),
        )
        text = page.get_textbox(expanded).strip()
        return text[:1500] or None


def ensure_manifest_is_local(
    manifest: DocumentManifest, artifact_root: str | Path = "artifacts"
) -> None:
    """Prevent API-supplied manifests from reading files outside artifact storage."""
    root = Path(artifact_root).resolve()
    paths = [
        Path(manifest.source_pdf_path),
        Path(manifest.artifact_directory),
        *(Path(page.rendered_image_path) for page in manifest.pages),
        *(Path(asset.image_path) for asset in manifest.visual_assets),
    ]
    for path in paths:
        resolved = path.resolve()
        if not resolved.is_relative_to(root):
            raise DocumentInspectionError(
                f"manifest path is outside managed artifact storage: {resolved}"
            )
