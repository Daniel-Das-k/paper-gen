from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from dotenv import load_dotenv
from pydantic import BaseModel

from .ai import (
    AIConfigurationError,
    DocumentAnalyzer,
    InsufficientInstructionalContent,
    summarize_model_failure,
)
from .blueprints import BlueprintBuilder, BlueprintError
from .documents import DocumentInspectionError, PdfInspector, ensure_manifest_is_local
from .models import (
    ContentMap,
    DocumentManifest,
    GeneratedQuestionPaper,
    PaperBlueprint,
    PaperPattern,
)
from .patterns import default_college_pattern
from .pipeline import PaperGenerationPipeline
from .outputs import default_pdf_output_directory, save_generated_paper


load_dotenv()
logger = logging.getLogger("uvicorn.error")

app = FastAPI(
    title="Question Paper Generator",
    version="0.1.0",
    description=(
        "Source-grounded PDF inspection and Bloom-aligned paper blueprint API. "
        "Generated examination content always requires human approval."
    ),
)
allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://127.0.0.1:5173,http://localhost:5173",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalysisRequest(BaseModel):
    manifest: DocumentManifest


class AnalysisResponse(BaseModel):
    manifest: DocumentManifest
    content_map: ContentMap


class BlueprintRequest(BaseModel):
    manifest: DocumentManifest
    content_map: ContentMap
    pattern: PaperPattern | None = None


class PreparationResponse(BaseModel):
    manifest: DocumentManifest
    content_map: ContentMap
    blueprint: PaperBlueprint


class FullWorkflowResponse(PreparationResponse):
    paper: GeneratedQuestionPaper
    pdf_download_url: str


class PreparedGenerationRequest(BaseModel):
    manifest: DocumentManifest
    content_map: ContentMap


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/patterns/default", response_model=PaperPattern)
def get_default_pattern() -> PaperPattern:
    return default_college_pattern()


@app.get("/v1/generated-papers/{filename}")
def download_generated_paper(filename: str) -> FileResponse:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*\.pdf", filename):
        raise HTTPException(status_code=404, detail="generated paper not found")
    output_root = default_pdf_output_directory().resolve()
    path = (output_root / filename).resolve()
    if not path.is_relative_to(output_root) or not path.is_file():
        raise HTTPException(status_code=404, detail="generated paper not found")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=filename,
    )


@app.get("/v1/documents/{document_id}/visuals/{asset_id}")
def get_visual_asset(document_id: str, asset_id: str) -> FileResponse:
    """Serve only an extracted visual belonging to a managed document."""
    if not re.fullmatch(r"[a-f0-9]{12}-p\d+-\d+", document_id):
        raise HTTPException(status_code=404, detail="visual asset not found")
    match = re.fullmatch(r"p(\d+)-image-(\d+)", asset_id)
    if not match:
        raise HTTPException(status_code=404, detail="visual asset not found")
    page_number, image_number = (int(value) for value in match.groups())
    visual_directory = (Path("artifacts") / document_id / "visuals").resolve()
    artifact_root = Path("artifacts").resolve()
    if not visual_directory.is_relative_to(artifact_root):
        raise HTTPException(status_code=404, detail="visual asset not found")
    filename_prefix = (
        f"page-{page_number:04d}-image-{image_number:02d}."
    )
    matches = [
        path
        for path in visual_directory.glob(f"{filename_prefix}*")
        if path.is_file() and path.resolve().is_relative_to(artifact_root)
    ]
    if len(matches) != 1:
        raise HTTPException(status_code=404, detail="visual asset not found")
    return FileResponse(matches[0])


@app.post("/v1/documents/inspect", response_model=DocumentManifest)
async def inspect_document(
    file: UploadFile = File(...),
    start_page: int = Form(1),
    end_page: int | None = Form(None),
) -> DocumentManifest:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix != ".pdf":
        raise HTTPException(status_code=400, detail="only PDF files are supported")
    with tempfile.NamedTemporaryFile(suffix=".pdf") as temporary:
        logger.info("document.inspect.start filename=%s", file.filename)
        shutil.copyfileobj(file.file, temporary)
        temporary.flush()
        try:
            manifest = PdfInspector().inspect(
                temporary.name,
                start_page=start_page,
                end_page=end_page,
            )
            logger.info(
                "document.inspect.complete document_id=%s pages=%d visual_candidates=%d",
                manifest.document_id,
                manifest.quality.page_count,
                len(manifest.visual_assets),
            )
            return manifest.model_copy(
                update={"original_filename": file.filename or "uploaded.pdf"}
            )
        except DocumentInspectionError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/v1/documents/analyze", response_model=AnalysisResponse)
async def analyze_document(request: AnalysisRequest) -> AnalysisResponse:
    try:
        logger.info(
            "document.analyze.start document_id=%s", request.manifest.document_id
        )
        ensure_manifest_is_local(request.manifest)
        analyzer = DocumentAnalyzer()
        content_map, assets = await analyzer.analyze_document(request.manifest)
        manifest = request.manifest.model_copy(update={"visual_assets": assets})
        logger.info(
            "document.analyze.complete document_id=%s subject=%s topics=%d "
            "eligible_visuals=%d",
            manifest.document_id,
            content_map.subject,
            len(content_map.topics),
            len(manifest.eligible_visuals()),
        )
        return AnalysisResponse(manifest=manifest, content_map=content_map)
    except AIConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except InsufficientInstructionalContent as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI analysis failed: {exc}") from exc


@app.post("/v1/blueprints/build", response_model=PaperBlueprint)
def build_blueprint(request: BlueprintRequest) -> PaperBlueprint:
    try:
        logger.info(
            "blueprint.build.start document_id=%s pattern=%s",
            request.manifest.document_id,
            (request.pattern or default_college_pattern()).pattern_id,
        )
        blueprint = BlueprintBuilder().build(
            request.pattern or default_college_pattern(),
            request.content_map,
            request.manifest,
        )
        logger.info(
            "blueprint.build.complete document_id=%s slots=%d warnings=%d",
            request.manifest.document_id,
            len(blueprint.slots),
            len(blueprint.warnings),
        )
        return blueprint
    except BlueprintError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


async def _prepare_uploaded_pdf(
    file: UploadFile,
    *,
    start_page: int | None,
    end_page: int | None,
) -> tuple[
    DocumentAnalyzer,
    DocumentManifest,
    ContentMap,
    PaperBlueprint,
    PaperPattern,
]:
    preparation_started = time.perf_counter()
    logger.info(
        "workflow.prepare.start stage=0/3 filename=%s requested_range=%s-%s",
        file.filename,
        start_page if start_page is not None else "first",
        end_page if end_page is not None else "last",
    )
    suffix = Path(file.filename or "").suffix.lower()
    if suffix != ".pdf":
        raise HTTPException(status_code=400, detail="only PDF files are supported")
    try:
        analyzer = DocumentAnalyzer()
        with tempfile.NamedTemporaryFile(suffix=".pdf") as temporary:
            shutil.copyfileobj(file.file, temporary)
            temporary.flush()
            stage_started = time.perf_counter()
            logger.info("workflow.prepare.stage_start stage=1/3 name=pdf_inspection")
            manifest = PdfInspector().inspect(
                temporary.name,
                start_page=start_page,
                end_page=end_page,
            )
            if not manifest.quality.passed:
                raise DocumentInspectionError(
                    "; ".join(manifest.quality.errors)
                )
            manifest = manifest.model_copy(
                update={"original_filename": file.filename or "uploaded.pdf"}
            )
        logger.info(
            "workflow.prepare.stage_complete stage=1/3 name=pdf_inspection "
            "duration_seconds=%.2f document_id=%s pages=%d visual_candidates=%d "
            "quality_passed=%s",
            time.perf_counter() - stage_started,
            manifest.document_id,
            manifest.quality.page_count,
            len(manifest.visual_assets),
            manifest.quality.passed,
        )
        stage_started = time.perf_counter()
        logger.info(
            "workflow.prepare.stage_start stage=2/3 name=combined_document_analysis"
        )
        content_map, assets = await analyzer.analyze_document(manifest)
        manifest = manifest.model_copy(update={"visual_assets": assets})
        logger.info(
            "workflow.prepare.stage_complete stage=2/3 "
            "name=combined_document_analysis duration_seconds=%.2f "
            "document_id=%s eligible=%d total=%d topics=%d model_calls=1",
            time.perf_counter() - stage_started,
            manifest.document_id,
            len(manifest.eligible_visuals()),
            len(manifest.visual_assets),
            len(content_map.topics),
        )
        stage_started = time.perf_counter()
        logger.info("workflow.prepare.stage_start stage=3/3 name=blueprint_planning")
        pattern = default_college_pattern()
        blueprint = BlueprintBuilder().build(pattern, content_map, manifest)
        logger.info(
            "workflow.prepare.stage_complete stage=3/3 name=blueprint_planning "
            "duration_seconds=%.2f document_id=%s slots=%d warnings=%d",
            time.perf_counter() - stage_started,
            manifest.document_id,
            len(blueprint.slots),
            len(blueprint.warnings),
        )
        logger.info(
            "workflow.prepare.complete document_id=%s total_duration_seconds=%.2f",
            manifest.document_id,
            time.perf_counter() - preparation_started,
        )
        return analyzer, manifest, content_map, blueprint, pattern
    except (
        DocumentInspectionError,
        BlueprintError,
        InsufficientInstructionalContent,
    ) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AIConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"preparation failed: {exc}") from exc


@app.post("/v1/workflows/prepare", response_model=PreparationResponse)
async def prepare_workflow(
    file: UploadFile = File(...),
    start_page: int | None = Form(None),
    end_page: int | None = Form(None),
) -> PreparationResponse:
    request_started = time.perf_counter()
    _, manifest, content_map, blueprint, _ = await _prepare_uploaded_pdf(
        file,
        start_page=start_page,
        end_page=end_page,
    )
    logger.info(
        "request.prepare.complete document_id=%s duration_seconds=%.2f",
        manifest.document_id,
        time.perf_counter() - request_started,
    )
    return PreparationResponse(
        manifest=manifest,
        content_map=content_map,
        blueprint=blueprint,
    )


@app.post("/v1/workflows/generate", response_model=FullWorkflowResponse)
async def generate_workflow(
    file: UploadFile = File(...),
    start_page: int | None = Form(None),
    end_page: int | None = Form(None),
) -> FullWorkflowResponse:
    request_started = time.perf_counter()
    analyzer, manifest, content_map, blueprint, pattern = await _prepare_uploaded_pdf(
        file,
        start_page=start_page,
        end_page=end_page,
    )
    return await _generate_prepared_paper(
        analyzer=analyzer,
        manifest=manifest,
        content_map=content_map,
        blueprint=blueprint,
        pattern=pattern,
        request_started=request_started,
        preparation_model_calls=1,
    )


@app.post(
    "/v1/workflows/generate-prepared",
    response_model=FullWorkflowResponse,
)
async def generate_prepared_workflow(
    request: PreparedGenerationRequest,
) -> FullWorkflowResponse:
    """Generate from a reviewed preparation without analyzing the PDF again."""
    request_started = time.perf_counter()
    try:
        ensure_manifest_is_local(request.manifest)
        if any(
            not topic.evidence_chunk_ids for topic in request.content_map.topics
        ):
            raise DocumentInspectionError(
                "prepared analysis is missing verified topic evidence; run Prepare again"
            )
        pattern = default_college_pattern()
        blueprint = BlueprintBuilder().build(
            pattern,
            request.content_map,
            request.manifest,
        )
        analyzer = DocumentAnalyzer()
        logger.info(
            "workflow.generate_prepared.reused document_id=%s selected_range=%d-%d "
            "preparation_model_calls_saved=1",
            request.manifest.document_id,
            request.manifest.selected_page_start,
            request.manifest.selected_page_end,
        )
        return await _generate_prepared_paper(
            analyzer=analyzer,
            manifest=request.manifest,
            content_map=request.content_map,
            blueprint=blueprint,
            pattern=pattern,
            request_started=request_started,
            preparation_model_calls=0,
        )
    except (DocumentInspectionError, BlueprintError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AIConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


async def _generate_prepared_paper(
    *,
    analyzer: DocumentAnalyzer,
    manifest: DocumentManifest,
    content_map: ContentMap,
    blueprint: PaperBlueprint,
    pattern: PaperPattern,
    request_started: float,
    preparation_model_calls: int,
) -> FullWorkflowResponse:
    try:
        generation_model_calls = (
            len({slot.section_id for slot in blueprint.slots}) + 1
        )
        logger.info(
            "workflow.generate.start document_id=%s slots=%d "
            "generation_model_calls=%d total_normal_model_calls=%d",
            manifest.document_id,
            len(blueprint.slots),
            generation_model_calls,
            generation_model_calls + preparation_model_calls,
        )
        generation_started = time.perf_counter()
        paper = await PaperGenerationPipeline(analyzer).generate(
            pattern=pattern,
            content_map=content_map,
            manifest=manifest,
            blueprint=blueprint,
        )
        public_paper = GeneratedQuestionPaper.from_internal(paper, blueprint)
        accepted = sum(question.accepted for question in paper.questions)
        logger.info(
            "workflow.generate.complete document_id=%s accepted=%d rejected=%d "
            "total=%d generation_duration_seconds=%.2f "
            "end_to_end_duration_seconds=%.2f",
            manifest.document_id,
            accepted,
            len(paper.questions) - accepted,
            len(paper.questions),
            time.perf_counter() - generation_started,
            time.perf_counter() - request_started,
        )
        saved = save_generated_paper(
            manifest=manifest,
            content_map=content_map,
            blueprint=blueprint,
            paper=public_paper,
        )
        logger.info(
            "workflow.generate.saved document_id=%s json=%s markdown=%s pdf=%s",
            manifest.document_id,
            saved.json_path,
            saved.markdown_path,
            saved.pdf_path,
        )
        return FullWorkflowResponse(
            manifest=manifest,
            content_map=content_map,
            blueprint=blueprint,
            paper=public_paper,
            pdf_download_url=f"/v1/generated-papers/{saved.pdf_path.name}",
        )
    except Exception as exc:
        logger.exception(
            "workflow.generate.failed document_id=%s", manifest.document_id
        )
        diagnostics = summarize_model_failure(exc)
        raise HTTPException(
            status_code=502,
            detail=(
                "generation failed during a model operation: "
                f"{diagnostics}"
            ),
        ) from exc
