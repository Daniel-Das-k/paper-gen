from __future__ import annotations

import asyncio
import logging
import os
import json
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from .ai import (
    SyllabusExtraction,
    AIConfigurationError,
    DocumentAnalyzer,
    InsufficientInstructionalContent,
    summarize_model_failure,
)
from .blueprints import BlueprintBuilder, BlueprintError
from .documents import DocumentInspectionError, PdfInspector, ensure_manifest_is_local
from .demo_store import DemoStore
from .models import (
    AnswerKeyEntry,
    BloomSummary,
    BlueprintSlot,
    ExamHeader,
    MarkingCriterion,
    UnitSource,
    ContentMap,
    DocumentManifest,
    GeneratedQuestionPaper,
    PaperBlueprint,
    PaperPattern,
    QuestionCandidate,
    QuestionPaperItem,
    SourceEvidence,
    ValidatedQuestion,
)
from .patterns import available_patterns, get_pattern
from .pipeline import PaperGenerationPipeline, generate_paper_sets
from .outputs import (
    default_pdf_output_directory,
    save_demo_edited_outputs,
    save_evaluation_scheme,
    save_generated_paper,
)


load_dotenv()
logger = logging.getLogger("uvicorn.error")
demo_store = DemoStore()
demo_tasks: set[asyncio.Task[None]] = set()

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


class GeneratedSet(BaseModel):
    set_label: str | None = None
    paper: GeneratedQuestionPaper
    blueprint: PaperBlueprint
    #: Beside the paper, never inside it — `paper` stays answer-free so it can be
    #: rendered for students without stripping anything.
    answer_key: list[AnswerKeyEntry] = Field(default_factory=list)
    pdf_download_url: str
    #: Answers and mark-wise criteria live only in this downloadable file --
    #: they are never part of the paper or of this response body.
    scheme_download_url: str


class FullWorkflowResponse(PreparationResponse):
    paper: GeneratedQuestionPaper
    pdf_download_url: str
    scheme_download_url: str
    docx_download_url: str | None = None
    #: The first set's answers, so faculty can check correctness while reviewing
    #: rather than opening the scheme PDF alongside.
    answer_key: list[AnswerKeyEntry] = Field(default_factory=list)
    #: Every generated set, including the first. Interchangeable papers an exam
    #: cell can hand to different rows of a hall.
    sets: list[GeneratedSet] = Field(default_factory=list)
    cross_set_warnings: list[str] = Field(default_factory=list)


class PreparedGenerationRequest(BaseModel):
    manifest: DocumentManifest
    content_map: ContentMap
    pattern_id: str | None = None


class DemoQuestionEdit(BaseModel):
    question_text: str = Field(min_length=5)
    answer: str = Field(min_length=1)
    criteria: list[MarkingCriterion] = Field(min_length=1)


class DemoQuestionRegenerate(BaseModel):
    mode: Literal["guided", "fresh"] = "guided"
    comment: str = Field(default="", max_length=1000)


class DemoTransitionRequest(BaseModel):
    actor_role: str
    action: str
    comment: str = ""


class DemoHeaderUpdate(BaseModel):
    header: ExamHeader


def _parse_unit_specs(raw: str | None, count: int) -> list[dict[str, object]]:
    """Read the per-file unit and page range the caller sent alongside the uploads.

    Shape: [{"unit": "1"}, {"unit": "2"}, {"unit": "3", "start_page": 1,
    "end_page": 12}] — one entry per file, in upload order. A unit split across
    two tests carries a range; a unit covered in full does not.
    """
    if not raw:
        raise HTTPException(
            status_code=422,
            detail="units must describe the syllabus unit of each uploaded file",
        )
    try:
        specs = json.loads(raw)
    except json.JSONDecodeError as error:
        raise HTTPException(
            status_code=422, detail=f"units is not valid JSON: {error}"
        ) from error
    if not isinstance(specs, list) or len(specs) != count:
        raise HTTPException(
            status_code=422,
            detail=f"units must contain one entry per uploaded file ({count})",
        )
    for spec in specs:
        if not isinstance(spec, dict) or not str(spec.get("unit", "")).strip():
            raise HTTPException(
                status_code=422, detail="every unit entry needs a unit number"
            )
    return specs


def _parse_course_outcomes(raw: str | None) -> list[str]:
    """Read the department's approved outcomes, one per line.

    Deduplicated case-insensitively while keeping the order and wording faculty
    entered, because that exact wording is what gets printed on the paper.
    """
    if not raw:
        return []
    outcomes: list[str] = []
    seen: set[str] = set()
    for line in raw.splitlines():
        outcome = line.strip()
        if not outcome or outcome.casefold() in seen:
            continue
        seen.add(outcome.casefold())
        outcomes.append(outcome)
    if len(outcomes) > 12:
        raise HTTPException(
            status_code=422,
            detail="a course normally defines at most 12 outcomes; check the list",
        )
    return outcomes


def _resolve_pattern(pattern_id: str | None) -> PaperPattern:
    """Resolve a requested pattern id, answering 404 for one we do not publish.

    Substituting a different pattern would hand back a paper nobody asked for,
    so this fails loudly. The usual cause is a browser still running an older
    build, hence the refresh hint.
    """
    try:
        return get_pattern(pattern_id)
    except KeyError:
        offered = ", ".join(pattern.pattern_id for pattern in available_patterns())
        raise HTTPException(
            status_code=404,
            detail=(
                f"This app no longer offers the paper pattern "
                f"'{pattern_id}'. Refresh the page to pick up the current "
                f"patterns ({offered})."
            ),
        ) from None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/patterns", response_model=list[PaperPattern])
def list_patterns() -> list[PaperPattern]:
    return available_patterns()


@app.get("/v1/patterns/default", response_model=PaperPattern)
def get_default_pattern() -> PaperPattern:
    return get_pattern(None)


@app.get("/v1/patterns/{pattern_id}", response_model=PaperPattern)
def get_pattern_by_id(pattern_id: str) -> PaperPattern:
    return _resolve_pattern(pattern_id)


@app.get("/v1/generated-papers/{filename}")
def download_generated_paper(filename: str) -> FileResponse:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*\.(?:pdf|docx)", filename):
        raise HTTPException(status_code=404, detail="generated paper not found")
    output_root = default_pdf_output_directory().resolve()
    path = (output_root / filename).resolve()
    if not path.is_relative_to(output_root) or not path.is_file():
        raise HTTPException(status_code=404, detail="generated paper not found")
    return FileResponse(
        path,
        media_type=(
            "application/pdf"
            if path.suffix == ".pdf"
            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
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


def _demo_job_view(job: dict[str, object]) -> dict[str, object]:
    return {
        key: job[key]
        for key in (
            "id",
            "status",
            "stage",
            "progress",
            "error",
            "paper_id",
            "created_at",
            "updated_at",
        )
    }


def _demo_download_url(path: Path) -> str:
    return f"/v1/generated-papers/{path.name}"


def _apply_demo_header(
    result: FullWorkflowResponse, metadata: dict[str, object]
) -> FullWorkflowResponse:
    current = result.paper.exam_header
    header = current.model_copy(
        update={
            "year": str(metadata.get("year", "")),
            "semester": str(metadata.get("semester", "")),
            "subject_code": str(metadata.get("course_code", "")),
            "subject_name": str(metadata.get("course_name", "")),
            "date": str(metadata.get("exam_date", "")),
        }
    )
    result.paper = result.paper.model_copy(update={"exam_header": header})
    if result.sets:
        first = result.sets[0]
        first.paper = first.paper.model_copy(update={"exam_header": header})
    return result


def _render_demo_result(
    paper_id: str, result: FullWorkflowResponse
) -> FullWorkflowResponse:
    rendered = save_demo_edited_outputs(
        paper_id=paper_id,
        manifest=result.manifest,
        blueprint=result.blueprint,
        paper=result.paper,
        answer_key=result.answer_key,
    )
    result.pdf_download_url = _demo_download_url(rendered.pdf_path)
    result.scheme_download_url = _demo_download_url(rendered.scheme_path)
    result.docx_download_url = _demo_download_url(rendered.docx_path)
    if result.sets:
        result.sets[0].paper = result.paper
        result.sets[0].answer_key = result.answer_key
        result.sets[0].pdf_download_url = result.pdf_download_url
        result.sets[0].scheme_download_url = result.scheme_download_url
    return result


async def _run_demo_generation(
    job_id: str,
    file_paths: list[Path],
    specs: list[dict[str, object]],
    metadata: dict[str, object],
) -> None:
    try:
        demo_store.update_job(
            job_id,
            status="running",
            stage="Inspecting uploaded unit PDFs",
            progress=10,
        )
        sources = [
            UnitSource(
                unit=str(spec["unit"]),
                file_path=str(path),
                original_filename=str(spec["filename"]),
                start_page=spec.get("start_page"),
                end_page=spec.get("end_page"),
            )
            for path, spec in zip(file_paths, specs)
        ]
        pattern = _resolve_pattern(str(metadata["pattern_id"]))
        manifest = PdfInspector().inspect_units(sources)
        analyzer = DocumentAnalyzer()
        demo_store.update_job(
            job_id,
            stage="Analyzing topics, outcomes and figures",
            progress=28,
        )
        content_map, assets = await analyzer.analyze_document(
            manifest,
            course_outcomes=list(metadata.get("course_outcomes", [])),
        )
        manifest = manifest.model_copy(update={"visual_assets": assets})
        demo_store.update_job(
            job_id,
            stage="Planning units, marks and cognitive levels",
            progress=42,
        )
        blueprint = BlueprintBuilder().build(pattern, content_map, manifest)
        demo_store.update_job(
            job_id,
            stage="Generating and independently reviewing questions",
            progress=52,
        )
        result = await _generate_prepared_paper(
            analyzer=analyzer,
            manifest=manifest,
            content_map=content_map,
            blueprint=blueprint,
            pattern=pattern,
            request_started=time.perf_counter(),
            preparation_model_calls=1,
            set_count=int(metadata.get("set_count", 1)),
        )
        demo_store.update_job(
            job_id,
            stage="Assembling the paper and scheme",
            progress=94,
        )
        # Allocate the persistent paper first, then produce stable demo exports
        # whose identity follows that record rather than the browser session.
        result = _apply_demo_header(result, metadata)
        paper_id = demo_store.create_paper(
            job_id, metadata, result.model_dump(mode="json")
        )
        result = _render_demo_result(paper_id, result)
        demo_store.save_result(
            paper_id,
            result.model_dump(mode="json"),
            action="rendered",
            comment="Applied REC exam details and created local demo exports",
        )
        demo_store.update_job(
            job_id,
            status="completed",
            stage="Paper ready for faculty review",
            progress=100,
            paper_id=paper_id,
        )
    except Exception as exc:
        logger.exception("demo generation failed job_id=%s", job_id)
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        demo_store.update_job(
            job_id,
            status="failed",
            stage="Generation failed",
            progress=100,
            error=detail or "The generation could not be completed",
        )


@app.post("/v1/demo/jobs/generate-units")
async def create_demo_generation_job(
    files: list[UploadFile] = File(...),
    units: str = Form(...),
    pattern_id: str = Form(...),
    course_outcomes: str | None = Form(None),
    set_count: int = Form(1),
    course_code: str = Form(""),
    course_name: str = Form(""),
    year: str = Form(""),
    semester: str = Form(""),
    exam_date: str = Form(""),
) -> dict[str, object]:
    specs = _parse_unit_specs(units, len(files))
    _resolve_pattern(pattern_id)
    metadata: dict[str, object] = {
        "pattern_id": pattern_id,
        "course_outcomes": _parse_course_outcomes(course_outcomes),
        "set_count": max(1, min(set_count, 3)),
        "course_code": course_code.strip(),
        "course_name": course_name.strip(),
        "year": year.strip(),
        "semester": semester.strip(),
        "exam_date": exam_date.strip(),
        "exam_label": get_pattern(pattern_id).name,
    }
    job = demo_store.create_job(metadata)
    upload_directory = demo_store.upload_root / str(job["id"])
    upload_directory.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for index, (upload, spec) in enumerate(zip(files, specs), start=1):
        if Path(upload.filename or "").suffix.lower() != ".pdf":
            demo_store.update_job(
                str(job["id"]),
                status="failed",
                stage="Upload rejected",
                progress=100,
                error="Only PDF files are supported",
            )
            raise HTTPException(status_code=400, detail="only PDF files are supported")
        path = upload_directory / f"unit-{index}.pdf"
        path.write_bytes(await upload.read())
        paths.append(path)
        spec["filename"] = upload.filename or path.name
    task = asyncio.create_task(
        _run_demo_generation(str(job["id"]), paths, specs, metadata)
    )
    demo_tasks.add(task)
    task.add_done_callback(demo_tasks.discard)
    return _demo_job_view(job)


@app.get("/v1/demo/jobs/{job_id}")
def get_demo_generation_job(job_id: str) -> dict[str, object]:
    try:
        return _demo_job_view(demo_store.get_job(job_id))
    except KeyError:
        raise HTTPException(status_code=404, detail="demo job not found") from None


@app.get("/v1/demo/papers")
def list_demo_papers() -> list[dict[str, object]]:
    return demo_store.list_papers()


@app.get("/v1/demo/papers/{paper_id}")
def get_demo_paper(paper_id: str) -> dict[str, object]:
    try:
        return demo_store.get_paper(paper_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="demo paper not found") from None


@app.put("/v1/demo/papers/{paper_id}/questions/{question_id}")
def edit_demo_question(
    paper_id: str, question_id: str, request: DemoQuestionEdit
) -> dict[str, object]:
    try:
        stored = demo_store.get_paper(paper_id)
        result = FullWorkflowResponse.model_validate(stored["result"])
        question = next(
            (item for item in result.paper.questions if item.question_id == question_id),
            None,
        )
        answer = next(
            (item for item in result.answer_key if item.question_id == question_id),
            None,
        )
        if question is None or answer is None:
            raise HTTPException(status_code=404, detail="question not found")
        if sum(item.marks for item in request.criteria) != question.marks:
            raise HTTPException(
                status_code=422,
                detail=f"Marking criteria must add up to {question.marks} marks",
            )
        question.question_text = request.question_text.strip()
        question.accepted = True
        question.faculty_modified = True
        question.findings = []
        question.quality_score = None
        answer.answer = request.answer.strip()
        answer.criteria = request.criteria
        result.paper.publication_ready = all(
            item.accepted for item in result.paper.questions
        )
        result = _render_demo_result(paper_id, result)
        return demo_store.save_result(
            paper_id,
            result.model_dump(mode="json"),
            action="question_edited",
            comment=f"Updated question {question.question_number} and its scheme",
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="demo paper not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _demo_validated_question(
    question: QuestionPaperItem,
    answer: AnswerKeyEntry,
    slot: BlueprintSlot,
    manifest: DocumentManifest,
) -> ValidatedQuestion:
    """Rebuild the internal shape needed by the normal repair pipeline."""
    pages = list(slot.source_pages)
    excerpts = [
        page.text[:400]
        for page in manifest.pages
        if page.page_number in set(pages)
    ][:2]
    return ValidatedQuestion(
        candidate=QuestionCandidate(
            candidate_id=question.question_id,
            slot_id=question.slot_id,
            question_text=question.question_text,
            answer=answer.answer,
            marks=question.marks,
            bloom_level=question.bloom_level,
            bloom_justification="Preserved from the locked blueprint slot.",
            marking_scheme=answer.criteria,
            evidence=SourceEvidence(
                chunk_ids=list(slot.evidence_chunk_ids),
                page_numbers=pages,
                excerpts=excerpts or ["Source evidence is attached to the blueprint slot."],
                visual_asset_id=question.visual_asset_id,
            ),
            confidence=1.0,
        ),
        accepted=question.accepted,
        findings=question.findings,
        quality_score=question.quality_score,
        observed_bloom_level=question.observed_bloom_level,
    )


def _refresh_demo_bloom_summary(result: FullWorkflowResponse) -> None:
    requested: dict[str, int] = {}
    observed: dict[str, int] = {}
    deviations = 0
    unverified = 0
    for question in result.paper.questions:
        requested[question.bloom_level.value] = (
            requested.get(question.bloom_level.value, 0) + 1
        )
        actual = question.observed_bloom_level
        if actual is None:
            unverified += 1
            actual = question.bloom_level
        elif actual != question.bloom_level:
            deviations += 1
        observed[actual.value] = observed.get(actual.value, 0) + 1
    result.paper.bloom_summary = BloomSummary(
        requested=requested,
        observed=observed,
        deviations=deviations,
        total=len(result.paper.questions),
        unverified=unverified,
    )


@app.post("/v1/demo/papers/{paper_id}/questions/{question_id}/regenerate")
async def regenerate_demo_question(
    paper_id: str,
    question_id: str,
    request: DemoQuestionRegenerate,
) -> dict[str, object]:
    try:
        if request.mode == "guided" and len(request.comment.strip()) < 3:
            raise HTTPException(
                status_code=422,
                detail="Guided regeneration needs a faculty instruction of at least 3 characters",
            )
        stored = demo_store.get_paper(paper_id)
        if stored.get("status") != "draft":
            raise HTTPException(
                status_code=409,
                detail="Only a faculty draft can be regenerated",
            )
        result = FullWorkflowResponse.model_validate(stored["result"])
        question = next(
            (item for item in result.paper.questions if item.question_id == question_id),
            None,
        )
        answer = next(
            (item for item in result.answer_key if item.question_id == question_id),
            None,
        )
        if question is None or answer is None:
            raise HTTPException(status_code=404, detail="question not found")
        slot = next(
            (item for item in result.blueprint.slots if item.slot_id == question.slot_id),
            None,
        )
        if slot is None:
            raise HTTPException(status_code=409, detail="question has no blueprint slot")

        current = _demo_validated_question(question, answer, slot, result.manifest)
        regenerated = await PaperGenerationPipeline(DocumentAnalyzer()).regenerate_question(
            slot=slot,
            current_question=current,
            mode=request.mode,
            faculty_comment=request.comment,
            other_question_texts=[
                item.question_text
                for item in result.paper.questions
                if item.question_id != question_id
            ],
            content_map=result.content_map,
            manifest=result.manifest,
        )
        candidate = regenerated.candidate
        # The route identity and printed number stay stable even though the model
        # produces a fresh candidate internally.
        question.question_text = candidate.question_text
        question.observed_bloom_level = regenerated.observed_bloom_level
        question.bloom_matches_blueprint = (
            regenerated.observed_bloom_level is None
            or regenerated.observed_bloom_level == question.bloom_level
        )
        question.visual_asset_id = candidate.evidence.visual_asset_id
        question.accepted = regenerated.accepted
        question.faculty_modified = True
        question.quality_score = regenerated.quality_score
        question.findings = regenerated.findings
        answer.answer = candidate.answer
        answer.criteria = candidate.marking_scheme
        result.paper.publication_ready = all(
            item.accepted for item in result.paper.questions
        )
        _refresh_demo_bloom_summary(result)
        result = _render_demo_result(paper_id, result)
        return demo_store.save_result(
            paper_id,
            result.model_dump(mode="json"),
            action="question_regenerated",
            comment=(
                f"Regenerated question {question.question_number} from a fresh source-grounded task"
                if request.mode == "fresh"
                else (
                    f"Regenerated question {question.question_number}. Faculty instruction: "
                    f"{request.comment.strip()}"
                )
            ),
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="demo paper not found") from None
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception(
            "demo question regeneration failed paper_id=%s question_id=%s",
            paper_id,
            question_id,
        )
        raise HTTPException(
            status_code=502,
            detail=f"Question regeneration failed: {summarize_model_failure(exc)}",
        ) from exc


@app.put("/v1/demo/papers/{paper_id}/header")
def update_demo_header(
    paper_id: str, request: DemoHeaderUpdate
) -> dict[str, object]:
    try:
        stored = demo_store.get_paper(paper_id)
        result = FullWorkflowResponse.model_validate(stored["result"])
        result.paper.exam_header = request.header
        result = _render_demo_result(paper_id, result)
        return demo_store.save_result(
            paper_id,
            result.model_dump(mode="json"),
            action="header_edited",
            comment="Updated examination details and recreated the exports",
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="demo paper not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/v1/demo/papers/{paper_id}/transition")
def transition_demo_paper(
    paper_id: str, request: DemoTransitionRequest
) -> dict[str, object]:
    role = request.actor_role.strip().lower()
    action = request.action.strip().lower()
    if role not in {"faculty", "hod", "coe"} or action not in {
        "submit",
        "approve",
        "return",
    }:
        raise HTTPException(status_code=422, detail="invalid demo workflow action")
    try:
        return demo_store.transition(paper_id, role, action, request.comment)
    except KeyError:
        raise HTTPException(status_code=404, detail="demo paper not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/v1/workflows/generate-units", response_model=FullWorkflowResponse)
async def generate_from_units(
    files: list[UploadFile] = File(...),
    units: str = Form(...),
    pattern_id: str | None = Form(None),
    course_outcomes: str | None = Form(None),
    set_count: int = Form(1),
) -> FullWorkflowResponse:
    """Generate from one upload per syllabus unit.

    The pages named here are the whole of the exam's source: they are cut and
    concatenated into a single isolated PDF before any model call, so nothing
    outside the declared range can reach a question.
    """
    request_started = time.perf_counter()
    specs = _parse_unit_specs(units, len(files))
    pattern = _resolve_pattern(pattern_id)
    for upload in files:
        if Path(upload.filename or "").suffix.lower() != ".pdf":
            raise HTTPException(
                status_code=400, detail="only PDF files are supported"
            )

    temporaries: list[tempfile._TemporaryFileWrapper] = []
    try:
        sources: list[UnitSource] = []
        for upload, spec in zip(files, specs):
            handle = tempfile.NamedTemporaryFile(suffix=".pdf")
            temporaries.append(handle)
            shutil.copyfileobj(upload.file, handle)
            handle.flush()
            sources.append(
                UnitSource(
                    unit=str(spec["unit"]).strip(),
                    file_path=handle.name,
                    original_filename=upload.filename or "unit.pdf",
                    start_page=spec.get("start_page"),
                    end_page=spec.get("end_page"),
                )
            )
        analyzer = DocumentAnalyzer()
        manifest = PdfInspector().inspect_units(sources)
        content_map, assets = await analyzer.analyze_document(
            manifest, course_outcomes=_parse_course_outcomes(course_outcomes)
        )
        manifest = manifest.model_copy(update={"visual_assets": assets})
        blueprint = BlueprintBuilder().build(pattern, content_map, manifest)
    except (
        DocumentInspectionError,
        BlueprintError,
        InsufficientInstructionalContent,
    ) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AIConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"preparation failed: {exc}"
        ) from exc
    finally:
        for handle in temporaries:
            handle.close()

    return await _generate_prepared_paper(
        analyzer=analyzer,
        manifest=manifest,
        content_map=content_map,
        blueprint=blueprint,
        pattern=pattern,
        request_started=request_started,
        preparation_model_calls=1,
        set_count=max(1, min(set_count, 3)),
    )


@app.post("/v1/syllabus/extract", response_model=SyllabusExtraction)
async def extract_syllabus(file: UploadFile = File(...)) -> SyllabusExtraction:
    """Read course outcomes and unit structure from an uploaded syllabus page.

    The result is a suggestion, never a decision: the caller shows it back for a
    human to confirm before it reaches a paper, because course outcomes are
    approved by a Board of Studies and must not originate here.
    """
    if Path(file.filename or "").suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="only PDF files are supported")
    try:
        analyzer = DocumentAnalyzer()
        with tempfile.NamedTemporaryFile(suffix=".pdf") as temporary:
            shutil.copyfileobj(file.file, temporary)
            temporary.flush()
            return await analyzer.extract_syllabus(temporary.name)
    except AIConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"could not read the syllabus: {exc}"
        ) from exc


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
            (request.pattern or get_pattern(None)).pattern_id,
        )
        blueprint = BlueprintBuilder().build(
            request.pattern or get_pattern(None),
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
    pattern_id: str | None = None,
    course_outcomes: list[str] | None = None,
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
    # Resolve the pattern before any PDF work: it is pure validation, and
    # failing here saves the caller an analysis call they cannot use.
    pattern = _resolve_pattern(pattern_id)
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
        content_map, assets = await analyzer.analyze_document(
            manifest, course_outcomes=course_outcomes
        )
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
    except HTTPException:
        # Already a deliberate, well-formed response — re-wrapping it as a 502
        # would bury the real status and message inside "preparation failed".
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"preparation failed: {exc}") from exc


@app.post("/v1/workflows/prepare", response_model=PreparationResponse)
async def prepare_workflow(
    file: UploadFile = File(...),
    start_page: int | None = Form(None),
    end_page: int | None = Form(None),
    pattern_id: str | None = Form(None),
    course_outcomes: str | None = Form(None),
) -> PreparationResponse:
    request_started = time.perf_counter()
    _, manifest, content_map, blueprint, _ = await _prepare_uploaded_pdf(
        file,
        start_page=start_page,
        end_page=end_page,
        pattern_id=pattern_id,
        course_outcomes=_parse_course_outcomes(course_outcomes),
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
    pattern_id: str | None = Form(None),
    course_outcomes: str | None = Form(None),
    set_count: int = Form(1),
) -> FullWorkflowResponse:
    request_started = time.perf_counter()
    analyzer, manifest, content_map, blueprint, pattern = await _prepare_uploaded_pdf(
        file,
        start_page=start_page,
        end_page=end_page,
        pattern_id=pattern_id,
        course_outcomes=_parse_course_outcomes(course_outcomes),
    )
    return await _generate_prepared_paper(
        analyzer=analyzer,
        manifest=manifest,
        content_map=content_map,
        blueprint=blueprint,
        pattern=pattern,
        request_started=request_started,
        preparation_model_calls=1,
        set_count=max(1, min(set_count, 3)),
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
        pattern = _resolve_pattern(request.pattern_id)
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
    set_count: int = 1,
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
        produced, cross_set_warnings = await generate_paper_sets(
            analyzer=analyzer,
            pattern=pattern,
            content_map=content_map,
            manifest=manifest,
            set_count=set_count,
        )
        blueprint, paper = produced[0]
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
        generated_sets: list[GeneratedSet] = []
        for set_blueprint, set_paper in produced:
            set_public = GeneratedQuestionPaper.from_internal(
                set_paper, set_blueprint
            )
            set_saved = save_generated_paper(
                manifest=manifest,
                content_map=content_map,
                blueprint=set_blueprint,
                paper=set_public,
            )
            set_scheme = save_evaluation_scheme(
                manifest=manifest,
                blueprint=set_blueprint,
                paper=set_paper,
                pdf_path=set_saved.pdf_path.with_name(
                    f"{set_saved.pdf_path.stem}-scheme.pdf"
                ),
            )
            generated_sets.append(
                GeneratedSet(
                    set_label=set_paper.set_label,
                    paper=set_public,
                    blueprint=set_blueprint,
                    answer_key=AnswerKeyEntry.build(
                        set_paper.questions,
                        {slot.slot_id: slot for slot in set_blueprint.slots},
                    ),
                    pdf_download_url=(
                        f"/v1/generated-papers/{set_saved.pdf_path.name}"
                    ),
                    scheme_download_url=(
                        f"/v1/generated-papers/{set_scheme.name}"
                    ),
                )
            )
        saved_pdf_name = generated_sets[0].pdf_download_url
        saved_scheme_name = generated_sets[0].scheme_download_url
        logger.info(
            "workflow.generate.saved document_id=%s sets=%d cross_set_warnings=%d",
            manifest.document_id,
            len(generated_sets),
            len(cross_set_warnings),
        )
        return FullWorkflowResponse(
            manifest=manifest,
            content_map=content_map,
            blueprint=blueprint,
            paper=public_paper,
            pdf_download_url=saved_pdf_name,
            scheme_download_url=saved_scheme_name,
            answer_key=generated_sets[0].answer_key,
            sets=generated_sets,
            cross_set_warnings=cross_set_warnings,
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
