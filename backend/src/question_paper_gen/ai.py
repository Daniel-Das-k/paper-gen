from __future__ import annotations

import logging
import os
import re
import time

import fitz
from collections import Counter
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_ai import Agent, BinaryContent
from pydantic_ai.exceptions import ModelHTTPError, UnexpectedModelBehavior
import boto3
from botocore.config import Config as BotocoreConfig
from pydantic_ai.models.bedrock import BedrockConverseModel
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.profiles import ModelProfile
from pydantic_ai.providers.bedrock import BedrockModelProfile, BedrockProvider

from .evidence import build_evidence_chunks
from .models import (
    BloomLevel,
    ContentMap,
    DocumentManifest,
    PageContent,
    QuestionCandidate,
    QuestionQualityDimensions,
    Topic,
    VisualAsset,
    VisualType,
)

logger = logging.getLogger("uvicorn.error")


def _bedrock_structured_output_profile(
    provider_profile: ModelProfile | None,
) -> BedrockModelProfile:
    """Force a typed output tool for Claude models that support tool choice."""
    profile = BedrockModelProfile.from_profile(provider_profile)
    profile.bedrock_supports_tool_choice = True
    return profile


def _is_transient_model_error(error: Exception) -> bool:
    """Fall back only for capacity, rate-limit, timeout, and server failures."""
    response = getattr(error, "response", {})
    response_metadata = response.get("ResponseMetadata", {}) if isinstance(response, dict) else {}
    response_error = response.get("Error", {}) if isinstance(response, dict) else {}
    status_code = (
        getattr(error, "status_code", None)
        or getattr(error, "code", None)
        or response_metadata.get("HTTPStatusCode")
    )
    provider_code = response_error.get("Code", "")
    transient = status_code in {408, 429, 500, 502, 503, 504}
    if not transient:
        message = f"{provider_code} {error}".upper()
        transient = any(
            marker in message
            for marker in (
                "429 RESOURCE_EXHAUSTED",
                "500 INTERNAL",
                "502 BAD_GATEWAY",
                "503 UNAVAILABLE",
                "504 DEADLINE_EXCEEDED",
                "THROTTLINGEXCEPTION",
                "SERVICEUNAVAILABLEEXCEPTION",
                "MODELNOTREADYEXCEPTION",
                "MODELSTREAMERROREXCEPTION",
                "MODELTIMEOUTEXCEPTION",
                "TOO MANY REQUESTS",
                # Connection-level failures carry no HTTP status, so they must be
                # matched by message or a large analysis request that drops mid
                # flight fails outright instead of retrying.
                "CONNECTION WAS CLOSED",
                "COULD NOT CONNECT",
                "CONNECTIONCLOSEDERROR",
                "ENDPOINTCONNECTIONERROR",
                "CONNECTIONERROR",
                "CONNECTION ABORTED",
                "CONNECTION RESET",
                "CONNECTTIMEOUTERROR",
                "CONNECT TIMEOUT",
                "READTIMEOUTERROR",
                "READ TIMEOUT",
                "TIMED OUT",
            )
        )
    if transient:
        logger.warning(
            "ai.model_fallback.triggered error_type=%s status=%s",
            type(error).__name__,
            status_code or "unknown",
        )
    return transient


def _is_input_too_long_error(error: BaseException) -> bool:
    """Whether Bedrock rejected a request for exceeding model context."""
    if isinstance(error, BaseExceptionGroup):
        return any(_is_input_too_long_error(item) for item in error.exceptions)
    message = str(error).lower()
    return "input is too long" in message or "input too long" in message


def is_transient_model_failure(error: Exception) -> bool:
    """Recognize a transient failure, including a grouped fallback-model failure."""
    grouped_errors = getattr(error, "exceptions", None)
    if grouped_errors:
        return all(is_transient_model_failure(item) for item in grouped_errors)
    return _is_transient_model_error(error)


def summarize_model_failure(error: Exception) -> str:
    """Return safe diagnostic details without request bodies or credentials."""
    grouped_errors = getattr(error, "exceptions", None)
    if grouped_errors:
        return "; ".join(summarize_model_failure(item) for item in grouped_errors)
    model_name = getattr(error, "model_name", None)
    response = getattr(error, "response", {})
    response_metadata = response.get("ResponseMetadata", {}) if isinstance(response, dict) else {}
    status_code = (
        getattr(error, "status_code", None)
        or getattr(error, "code", None)
        or response_metadata.get("HTTPStatusCode")
    )
    parts = [type(error).__name__]
    if model_name:
        parts.append(f"model={model_name}")
    if status_code:
        parts.append(f"status={status_code}")
    if isinstance(error, UnexpectedModelBehavior):
        detail = " ".join(error.message.split())
        if detail:
            parts.append(f"detail={detail[:240]}")
    if len(parts) == 1:
        message = str(error).upper()
        for marker in ("429", "500", "502", "503", "504"):
            if marker in message:
                parts.append(f"status={marker}")
                break
    return " ".join(parts)


class AIConfigurationError(RuntimeError):
    pass


class InsufficientInstructionalContent(ValueError):
    pass


class VisualAssessment(BaseModel):
    asset_type: VisualType
    description: str
    visible_labels: list[str] = Field(default_factory=list)
    topic: str | None = None
    question_eligible: bool
    confidence: float = Field(ge=0, le=1)
    rejection_reason: str | None = None


class BatchVisualAssessment(VisualAssessment):
    asset_id: str


class DocumentAnalysisOutput(BaseModel):
    content_map: ContentMap
    instructional_content_sufficient: bool
    insufficiency_reason: str | None = None
    visual_assessments: list[BatchVisualAssessment] = Field(default_factory=list)


class SyllabusUnit(BaseModel):
    number: str
    title: str
    topics: str


class SyllabusExtraction(BaseModel):
    """What an Anna University style syllabus page states about one course."""

    subject_code: str | None = None
    subject_name: str | None = None
    regulation: str | None = None
    units: list[SyllabusUnit] = Field(default_factory=list)
    course_outcomes: list[str] = Field(default_factory=list)
    extraction_confident: bool = True
    problem: str | None = None


class SemanticReview(BaseModel):
    grounded_in_evidence: bool
    answer_correct: bool
    bloom_level_correct: bool
    observed_bloom_level: BloomLevel | None = None
    wording_clear: bool
    visual_consistent: bool = True
    visual_necessary: bool = True
    subject_accuracy: bool
    difficulty_appropriate: bool
    marking_scheme_valid: bool
    options_valid: bool
    internal_choice_valid: bool
    pedagogical_quality: bool
    quality_score: int = Field(ge=0, le=100)
    quality_dimensions: QuestionQualityDimensions | None = None
    confidence: float = Field(ge=0, le=1)
    reasons: list[str] = Field(default_factory=list)


class SectionQuestionBatch(BaseModel):
    questions: list[QuestionCandidate]


class SectionQuestionReview(SemanticReview):
    candidate_id: str


class SectionReviewBatch(BaseModel):
    reviews: list[SectionQuestionReview]


#: The provider caps a request two different ways and both bite. A 200K-context
#: model refuses more than 100 PDF pages, and it also refuses any request whose
#: tokens exceed the window — and 100 pages of PDF is roughly the whole 200K
#: window on its own. Pages alone are therefore the wrong budget; tokens are.
PROVIDER_MAX_PDF_PAGES = 100

#: Context window of the analysis model. Override for a 1M-context model.
DEFAULT_CONTEXT_TOKENS = 200_000

#: What one PDF page costs once rendered and tokenised. The previous 2K estimate
#: still let a 55-page sample overflow once the chunk catalog and figures were
#: added, so use a conservative mixed text/diagram allowance.
DEFAULT_TOKENS_PER_PDF_PAGE = 3_500

#: Held back for everything that is not the PDF. Roughly: 24k reply, 10k chunk
#: catalog, ~19k for twelve candidate figures, 4k of prompt — rounded up so the
#: window is not filled to the millimetre.
DEFAULT_RESERVED_TOKENS = 70_000

#: Page cost is an estimate, so the budget must not fill the window exactly —
#: that is how a request lands at 202,387 tokens against a 200,000 limit. Aim at
#: this share of the window and leave the rest as slack.
CONTEXT_FILL_FACTOR = 0.9

#: Kept for callers and tests; read the live value through max_attached_pdf_pages().
MAX_ATTACHED_PDF_PAGES = PROVIDER_MAX_PDF_PAGES


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def max_attached_pdf_pages() -> int:
    """How many PDF pages fit this model's context, not just its page limit.

    Sending 100 pages satisfied the page cap and then overflowed the window at
    202,387 tokens. The budget is therefore derived: whatever the context window
    has left after the prompt, catalog, figures and reply are reserved, divided
    by what a page costs — then clamped to the provider's own page ceiling.
    """
    explicit = os.getenv("MAX_ATTACHED_PDF_PAGES")
    if explicit:
        try:
            return max(1, min(int(explicit), PROVIDER_MAX_PDF_PAGES))
        except ValueError:
            pass
    context = _env_int("BEDROCK_CONTEXT_TOKENS", DEFAULT_CONTEXT_TOKENS)
    reserved = _env_int("BEDROCK_RESERVED_TOKENS", DEFAULT_RESERVED_TOKENS)
    per_page = _env_int("TOKENS_PER_PDF_PAGE", DEFAULT_TOKENS_PER_PDF_PAGE)
    usable = int(context * CONTEXT_FILL_FACTOR)
    affordable = max(1, (usable - reserved) // per_page)
    return min(affordable, PROVIDER_MAX_PDF_PAGES)


def bounded_pdf_attachment(
    pdf_path: str | Path,
    page_limit: int | None = None,
) -> tuple[bytes, int, int]:
    """Return PDF bytes the provider will accept, plus what was sent and held.

    Three units of course material easily exceed a 200K-context model's 100-page
    limit. Sending the first hundred pages would make the later units invisible
    to the model — on a unit-wise paper that means CAT-I sees unit 1 and little
    else — so pages are sampled evenly across the whole selection instead. The
    extracted page text is unaffected and still covers every page, and it is the
    text that evidence chunks and grounding are built from; the PDF only adds
    layout and figures on top.
    """
    limit = max_attached_pdf_pages()
    if page_limit is not None:
        limit = min(limit, max(1, page_limit))
    path = Path(pdf_path)
    with fitz.open(path) as document:
        total = document.page_count
        if total <= limit:
            return path.read_bytes(), total, total
        step = total / limit
        keep = sorted(
            {min(total - 1, int(index * step)) for index in range(limit)}
        )
        sampled = fitz.open()
        for page_index in keep:
            sampled.insert_pdf(document, from_page=page_index, to_page=page_index)
        data = sampled.tobytes()
        sampled.close()
    return data, len(keep), total


class DocumentAnalyzer:
    """AWS Bedrock Claude analysis isolated behind a typed provider boundary."""

    def __init__(self, model_name: str | None = None) -> None:
        region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
        if not region:
            raise AIConfigurationError(
                "set AWS_REGION or AWS_DEFAULT_REGION to enable Bedrock analysis"
            )
        default_model = model_name or os.getenv(
            "BEDROCK_MODEL",
            "us.anthropic.claude-haiku-4-5-20251001-v1:0",
        )
        fallback_names = [
            name.strip()
            for name in os.getenv(
                "BEDROCK_FALLBACK_MODELS",
                "us.anthropic.claude-3-5-haiku-20241022-v1:0",
            ).split(",")
            if name.strip()
        ]
        # Large PDF requests need time in both directions. `connect_timeout` is
        # also the socket timeout while urllib3 writes the request body, so the
        # old 30-second value could abort a multi-megabyte upload before Bedrock
        # had even received it. Keep upload and response budgets independent.
        connect_timeout = max(
            30, _env_int("BEDROCK_CONNECT_TIMEOUT_SECONDS", 120)
        )
        read_timeout = max(60, _env_int("BEDROCK_READ_TIMEOUT_SECONDS", 600))
        provider = BedrockProvider(
            bedrock_client=boto3.client(
                "bedrock-runtime",
                region_name=region,
                config=BotocoreConfig(
                    read_timeout=read_timeout,
                    connect_timeout=connect_timeout,
                    retries={"max_attempts": 3, "mode": "adaptive"},
                ),
            )
        )
        max_output_tokens = max(
            1024,
            int(os.getenv("BEDROCK_MAX_OUTPUT_TOKENS", "24000")),
        )
        analysis_temperature = float(os.getenv("ANALYSIS_TEMPERATURE", "0.1"))
        generation_temperature = float(os.getenv("GENERATION_TEMPERATURE", "0.7"))
        review_temperature = float(os.getenv("REVIEW_TEMPERATURE", "0.1"))

        def role_model_names(env_name: str) -> list[str]:
            # An explicit model_name argument overrides per-role env selection.
            selected = default_model
            if model_name is None:
                selected = os.getenv(env_name) or default_model
            return list(dict.fromkeys([selected, *fallback_names]))

        def build_model(
            names: list[str],
            temperature: float,
        ) -> BedrockConverseModel | FallbackModel:
            models: list[BedrockConverseModel] = []
            for name in names:
                model_max_tokens = (
                    min(max_output_tokens, 8192)
                    if "claude-3-5-haiku" in name
                    else max_output_tokens
                )
                models.append(
                    BedrockConverseModel(
                        name,
                        provider=provider,
                        profile=_bedrock_structured_output_profile(
                            provider.model_profile(name)
                        ),
                        settings={
                            "max_tokens": model_max_tokens,
                            "temperature": temperature,
                        },
                    )
                )
            if len(models) > 1:
                return FallbackModel(
                    models[0],
                    *models[1:],
                    fallback_on=_is_transient_model_error,
                )
            return models[0]

        analysis_names = role_model_names("BEDROCK_ANALYSIS_MODEL")
        generation_names = role_model_names("BEDROCK_GENERATION_MODEL")
        review_names = role_model_names("BEDROCK_REVIEW_MODEL")
        analysis_model = build_model(analysis_names, analysis_temperature)
        generation_model = build_model(generation_names, generation_temperature)
        review_model = build_model(review_names, review_temperature)
        logger.info(
            "ai.models.configured provider=aws_bedrock region=%s analysis=%s "
            "generation=%s review=%s fallbacks=%s max_output_tokens=%d "
            "generation_temperature=%.2f review_temperature=%.2f "
            "forced_output_tool=true",
            region,
            analysis_names[0],
            generation_names[0],
            review_names[0],
            ",".join(fallback_names) or "none",
            max_output_tokens,
            generation_temperature,
            review_temperature,
        )
        output_retries = max(1, int(os.getenv("AI_OUTPUT_RETRIES", "2")))
        self.content_agent = Agent(
            model=analysis_model,
            output_type=ContentMap,
            output_retries=output_retries,
        )
        self.syllabus_agent = Agent(
            model=analysis_model,
            output_type=SyllabusExtraction,
            output_retries=output_retries,
        )
        self.visual_agent = Agent(
            model=analysis_model,
            output_type=VisualAssessment,
            output_retries=output_retries,
        )
        self.document_analysis_agent = Agent(
            model=analysis_model,
            output_type=DocumentAnalysisOutput,
            output_retries=output_retries,
        )
        self.question_agent = Agent(
            model=generation_model,
            output_type=QuestionCandidate,
            output_retries=output_retries,
        )
        self.review_agent = Agent(
            model=review_model,
            output_type=SemanticReview,
            output_retries=output_retries,
        )
        self.section_question_agent = Agent(
            model=generation_model,
            output_type=SectionQuestionBatch,
            output_retries=output_retries,
        )
        self.section_review_agent = Agent(
            model=review_model,
            output_type=SectionReviewBatch,
            output_retries=output_retries,
        )

    async def extract_syllabus(self, pdf_path: str) -> SyllabusExtraction:
        """Read one course's syllabus page: units and approved course outcomes.

        Transcription, not interpretation. The outcomes are a governance artifact
        the department wrote, so they come back verbatim for a human to confirm --
        this never becomes a source of outcomes nobody approved.
        """
        started = time.perf_counter()
        path = Path(pdf_path)
        logger.info("ai.syllabus_extraction.start file=%s", path.name)
        result = await self.syllabus_agent.run(
            [
                """
                Transcribe one course's syllabus page from the attached PDF.

                - Copy the course outcomes VERBATIM, one entry per listed outcome,
                  in the order printed. Do not reword, renumber, merge, split,
                  summarise, or invent them, and do not carry over the "On
                  completion of the course students will be able to:" preamble.
                - Copy the course objectives nowhere: objectives and outcomes are
                  different sections. Take only the section headed Course Outcomes.
                - For each unit, return its number exactly as printed (I, II, 1, 2),
                  its title, and the topic line beneath it.
                - Return subject_code, subject_name and regulation only if printed.
                - If the page holds several courses, or you cannot find a course
                  outcomes section, set extraction_confident to false, explain in
                  problem, and return whatever you are sure of.
                """,
                BinaryContent(
                    data=bounded_pdf_attachment(path)[0],
                    media_type="application/pdf",
                ),
            ]
        )
        output = result.output
        logger.info(
            "ai.syllabus_extraction.complete subject=%s units=%d outcomes=%d "
            "confident=%s duration_seconds=%.2f model_calls=1",
            output.subject_name,
            len(output.units),
            len(output.course_outcomes),
            output.extraction_confident,
            time.perf_counter() - started,
        )
        return output

    async def analyze_document(
        self,
        manifest: DocumentManifest,
        course_outcomes: list[str] | None = None,
    ) -> tuple[ContentMap, list[VisualAsset]]:
        """Analyze content and a bounded visual set in one multimodal request.

        `course_outcomes` are the department's approved outcomes. They are a closed
        set the model may only choose from — never extend, never invent. When none
        are supplied, topics come back with no outcome at all rather than a
        plausible-looking guess.
        """
        started = time.perf_counter()
        candidates = self._select_visual_candidates(manifest)
        logger.info(
            "ai.document_analysis.start document_id=%s pages=%d "
            "visual_candidates_total=%d visual_candidates_sent=%d",
            manifest.document_id,
            len(manifest.pages),
            len(manifest.visual_assets),
            len(candidates),
        )
        pdf_path = Path(manifest.source_pdf_path)
        pdf_bytes, attached_pages, total_pages = bounded_pdf_attachment(pdf_path)
        if attached_pages < total_pages:
            logger.info(
                "ai.document_analysis.pdf_sampled attached=%d of=%d limit=%d",
                attached_pages,
                total_pages,
                max_attached_pdf_pages(),
            )
        sampling_note = (
            ""
            if attached_pages == total_pages
            else (
                f"\n            - The attached PDF is an evenly spaced sample of "
                f"{attached_pages} pages from the {total_pages}-page selection, "
                "because the provider accepts no more. The page text catalog "
                "below is complete and authoritative; use the PDF only for "
                "layout and figures, and never conclude a topic is absent merely "
                "because its pages are not in the attachment.\n"
            )
        )
        chunk_catalog = self._content_chunk_catalog(manifest)
        approved_outcomes = [
            outcome.strip() for outcome in (course_outcomes or []) if outcome.strip()
        ]
        if approved_outcomes:
            outcome_lines = "\n".join(
                f"              CO{index}: {outcome}"
                for index, outcome in enumerate(approved_outcomes, start=1)
            )
            outcome_instruction = (
                "\n            - The department has approved these course outcomes. "
                "For each topic, set course_outcomes to the ONE entry from this list "
                "whose wording the topic's content actually serves, copied verbatim. "
                "Choose nothing outside the list, never reword an entry, and leave "
                "course_outcomes empty when no entry genuinely fits:\n"
                f"{outcome_lines}\n"
            )
        else:
            outcome_instruction = (
                "\n            - Leave every topic's course_outcomes empty. Course "
                "outcomes are approved by the department and cannot be inferred from "
                "source material.\n"
            )
        content: list[object] = [
            f"""
            Analyze this selected excerpt from a college study document in one response.

            The supplied PDF contains only original source pages
            {manifest.selected_page_start} through {manifest.selected_page_end}.

            Content-map requirements:
            - Identify the subject conservatively.
            - Include only substantive instructional topics actually explained in the
              selected pages.
            - Split the material at section granularity: a full textbook chapter
              typically yields 4-10 distinct topics. Never merge the whole selection
              into 2-3 broad topics, and list each topic's genuinely explained
              subtopics — topic and subtopic counts determine how many distinct
              questions the paper can draw from these pages.
            - Do not treat covers, acknowledgements, introductions, a syllabus, a table
              of contents, unit-name lists, answer keys, exercise-answer lists, solution
              appendices, or blank pages as teachable topic evidence. A page of bare
              answers (e.g. "EXERCISE 2.1 1. π/6 2. π/6 ...") explains nothing.
            - If the selected pages consist mainly of exercise answers without the
              corresponding instructional material, set
              instructional_content_sufficient to false and say so in
              insufficiency_reason so the user can select the chapter pages instead.
            - Every topic must cite ORIGINAL page numbers from the selected range.
            - Every topic must return evidence_chunk_ids from the backend-owned catalog
              below. Choose only chunks that directly explain that topic; do not attach
              every chunk from the same page.
            - Do not invent subtopics, formulas, examples, facts, or course outcomes.{outcome_instruction}{sampling_note}
            - supported_bloom_levels is about what a student can be ASKED TO DO with
              the concept, not about how the page is written. Source material is
              expository by nature; that does not cap it at Remember/Understand.
              Judge each level against these tests, and include every level that
              passes:
                Remember    the topic states facts, definitions, or terminology.
                Understand  the topic explains why something holds or how it works.
                Apply       the topic gives a method, algorithm, formula, procedure,
                            or worked example a student could run on a fresh case.
                Analyze     the topic has parts that interact, alternatives that can
                            be compared, or a failure mode that can be diagnosed.
                Evaluate    the topic involves a choice, trade-off, or criterion by
                            which one option is judged better than another.
                Create      the topic supports designing, deriving, or constructing
                            something new from its rules.
              A topic that presents a procedure supports Apply even if the page only
              demonstrates it once. A topic covering two techniques for the same
              problem supports Analyze and usually Evaluate. Report a ceiling of
              Understand only when the topic is purely descriptive with no method,
              no interacting parts, and no alternatives.
            - Set instructional_content_sufficient to false when the pages do not contain
              any meaningful explained instructional material. Do not reject merely
              because the excerpt cannot support Evaluate or Create questions.

            Backend-owned evidence chunk catalog:
            {chunk_catalog}

            Visual requirements:
            - Assess only the explicitly labelled visual assets attached after the PDF.
            - Return one visual_assessments entry for each attached asset_id.
            - A visual is question-eligible only when its academic labels, relationships,
              axes, values, or components are readable and useful for a standalone question.
            - Reject logos, portraits, decorative artwork, page furniture, and unclear crops.
            """,
            BinaryContent(data=pdf_bytes, media_type="application/pdf"),
        ]
        for asset in candidates:
            path = Path(asset.image_path)
            if not path.exists():
                continue
            content.extend(
                [
                    (
                        f"Visual asset_id={asset.asset_id}; original_page="
                        f"{asset.page_number}; caption={asset.caption or ''}; "
                        f"nearby_text={(asset.nearby_text or '')[:500]}"
                    ),
                    BinaryContent(
                        data=path.read_bytes(),
                        media_type=self._media_type(path),
                    ),
                ]
            )
        try:
            result = await self.document_analysis_agent.run(content)
        except Exception as exc:
            if not _is_input_too_long_error(exc) or attached_pages <= 1:
                raise
            # Page/token estimates vary with diagrams and scan density. Bedrock
            # is the final authority, so recover once with a substantially
            # smaller, still evenly distributed attachment. The complete text
            # chunk catalog remains in the request and preserves full coverage.
            retry_limit = max(1, attached_pages // 2)
            retry_pdf, retry_pages, _ = bounded_pdf_attachment(
                pdf_path, page_limit=retry_limit
            )
            retry_note = (
                f"\n            - The attached PDF is an evenly spaced sample of "
                f"{retry_pages} pages from the {total_pages}-page selection, "
                "reduced to fit the model context. The page text catalog below "
                "is complete and authoritative.\n"
            )
            prompt = str(content[0])
            content[0] = (
                prompt.replace(sampling_note, retry_note)
                if sampling_note
                else f"{prompt}{retry_note}"
            )
            content[1] = BinaryContent(
                data=retry_pdf, media_type="application/pdf"
            )
            logger.warning(
                "ai.document_analysis.context_retry document_id=%s "
                "attached_pages=%d retry_pages=%d total_pages=%d",
                manifest.document_id,
                attached_pages,
                retry_pages,
                total_pages,
            )
            result = await self.document_analysis_agent.run(content)
        if not result.output.instructional_content_sufficient:
            reason = (
                result.output.insufficiency_reason
                or "selected pages do not contain enough instructional material"
            )
            logger.warning(
                "ai.document_analysis.insufficient document_id=%s reason=%s",
                manifest.document_id,
                reason,
            )
            raise InsufficientInstructionalContent(reason)

        assessments = {
            assessment.asset_id: assessment
            for assessment in result.output.visual_assessments
        }
        selected_ids = {asset.asset_id for asset in candidates}
        analyzed_assets: list[VisualAsset] = []
        for asset in manifest.visual_assets:
            assessment = assessments.get(asset.asset_id)
            if assessment is None:
                reason = (
                    "not selected by bounded visual prefilter"
                    if asset.asset_id not in selected_ids
                    else "model did not return a visual assessment"
                )
                analyzed_assets.append(
                    asset.model_copy(
                        update={
                            "question_eligible": False,
                            "confidence": 0,
                            "rejection_reason": reason,
                        }
                    )
                )
                continue
            analyzed_assets.append(
                asset.model_copy(
                    update={
                        "asset_type": assessment.asset_type,
                        "visible_labels": assessment.visible_labels,
                        "topic": assessment.topic,
                        "question_eligible": (
                            assessment.question_eligible
                            and assessment.confidence >= 0.80
                        ),
                        "confidence": assessment.confidence,
                        "rejection_reason": assessment.rejection_reason,
                    }
                )
            )

        content_map = self._normalize_content_pages(
            result.output.content_map,
            manifest,
        )
        if not content_map.topics:
            raise InsufficientInstructionalContent(
                "selected pages contain no topics with verifiable instructional evidence"
            )
        analyzed_assets = await self._verify_visual_assessments(
            manifest=manifest,
            content=content_map,
            candidates=candidates,
            assets=analyzed_assets,
        )
        content_map = self._link_topics_to_assets(content_map, analyzed_assets)
        content_map = self._enforce_topic_units(content_map, manifest)
        content_map = self._enforce_course_outcomes(content_map, course_outcomes)
        logger.info(
            "ai.document_analysis.complete document_id=%s subject=%s topics=%d "
            "eligible_visuals=%d duration_seconds=%.2f model_calls=1",
            manifest.document_id,
            content_map.subject,
            len(content_map.topics),
            sum(asset.question_eligible for asset in analyzed_assets),
            time.perf_counter() - started,
        )
        return content_map, analyzed_assets

    async def _verify_visual_assessments(
        self,
        *,
        manifest: DocumentManifest,
        content: ContentMap,
        candidates: list[VisualAsset],
        assets: list[VisualAsset],
    ) -> list[VisualAsset]:
        """Ground batch results and recover useful figures without trusting IDs.

        Multimodal models occasionally describe the right image under a later
        asset_id when several images share one request. A visual is therefore
        accepted only when its own page and metadata match a source-grounded
        topic. Unresolved candidates on instructional pages are then assessed
        one image per request, where ID drift is impossible.
        """
        candidate_ids = {asset.asset_id for asset in candidates}
        pages = {page.page_number: page for page in manifest.pages}
        verified: list[VisualAsset] = []
        unresolved: list[VisualAsset] = []

        for asset in assets:
            source_grounded = self._visual_matches_source_topic(asset, content)
            if asset.question_eligible:
                if not source_grounded:
                    logger.warning(
                        "ai.visual_analysis.batch_mismatch asset_id=%s "
                        "page=%d topic=%s",
                        asset.asset_id,
                        asset.page_number,
                        asset.topic or "unknown",
                    )
                asset = asset.model_copy(
                    update={
                        "question_eligible": False,
                        "confidence": 0,
                        "rejection_reason": (
                            "batch assessment requires single-image verification"
                            if source_grounded
                            else "batch assessment did not match this asset's "
                            "source page and topic"
                        ),
                    }
                )
            verified.append(asset)
            if (
                asset.asset_id in candidate_ids
                and not asset.question_eligible
                and self._page_has_source_topic(asset.page_number, content)
            ):
                unresolved.append(asset)

        # Prefer candidates whose extraction metadata already names the topic,
        # then larger figures. Keep recovery bounded for latency and cost.
        unresolved.sort(
            key=lambda asset: (
                self._visual_matches_source_topic(asset, content),
                self._visual_area(asset),
            ),
            reverse=True,
        )
        retry_limit = max(
            0, int(os.getenv("MAX_VISUAL_REASSESSMENTS", "4"))
        )
        replacements: dict[str, VisualAsset] = {}
        for asset in unresolved[:retry_limit]:
            page = pages.get(asset.page_number)
            if page is None:
                continue
            reassessed = await self._assess_single_visual(asset, page)
            if reassessed.question_eligible and not self._visual_matches_source_topic(
                reassessed, content
            ):
                reassessed = reassessed.model_copy(
                    update={
                        "question_eligible": False,
                        "confidence": 0,
                        "rejection_reason": (
                            "individual assessment did not match the source topic"
                        ),
                    }
                )
            replacements[asset.asset_id] = reassessed

        if replacements:
            logger.info(
                "ai.visual_analysis.individual_rechecks candidates=%d eligible=%d",
                len(replacements),
                sum(asset.question_eligible for asset in replacements.values()),
            )
        return [replacements.get(asset.asset_id, asset) for asset in verified]

    async def _assess_single_visual(
        self, asset: VisualAsset, page: PageContent
    ) -> VisualAsset:
        """Assess exactly one image so the result cannot bind to another ID."""
        path = Path(asset.image_path)
        if not path.exists():
            return asset.model_copy(
                update={
                    "question_eligible": False,
                    "confidence": 0,
                    "rejection_reason": "visual file is missing",
                }
            )
        prompt = f"""
            Inspect the ONE attached visual extracted from original page
            {asset.page_number} of an academic PDF. Your response applies only
            to asset_id={asset.asset_id}; do not describe any other figure named
            in the surrounding page context.

            Caption: {asset.caption or ""}
            Nearby text: {asset.nearby_text or page.text[:2500]}

            It is question-eligible only when its own visible labels,
            relationships, axes, values, or components are readable and useful
            for a standalone examination question. Reject logos, institutional
            banners, quotations, portraits, decoration, page furniture, and
            unclear crops. Never infer labels that are not visible in the image.
        """
        result = await self.visual_agent.run(
            [
                prompt,
                BinaryContent(
                    data=path.read_bytes(), media_type=self._media_type(path)
                ),
            ]
        )
        assessment = result.output
        return asset.model_copy(
            update={
                "asset_type": assessment.asset_type,
                "visible_labels": assessment.visible_labels,
                "topic": assessment.topic,
                "question_eligible": (
                    assessment.question_eligible and assessment.confidence >= 0.80
                ),
                "confidence": assessment.confidence,
                "rejection_reason": assessment.rejection_reason,
            }
        )

    async def analyze_content(
        self,
        manifest: DocumentManifest,
        course_outcomes: list[str] | None = None,
    ) -> ContentMap:
        started = time.perf_counter()
        logger.info(
            "ai.content_analysis.start document_id=%s pages=%d",
            manifest.document_id,
            len(manifest.pages),
        )
        pdf_path = Path(manifest.source_pdf_path)
        pdf_bytes, attached_pages, total_pages = bounded_pdf_attachment(pdf_path)
        if attached_pages < total_pages:
            logger.info(
                "ai.document_analysis.pdf_sampled attached=%d of=%d limit=%d",
                attached_pages,
                total_pages,
                max_attached_pdf_pages(),
            )
        sampling_note = (
            ""
            if attached_pages == total_pages
            else (
                f"\n            - The attached PDF is an evenly spaced sample of "
                f"{attached_pages} pages from the {total_pages}-page selection, "
                "because the provider accepts no more. The page text catalog "
                "below is complete and authoritative; use the PDF only for "
                "layout and figures, and never conclude a topic is absent merely "
                "because its pages are not in the attachment.\n"
            )
        )
        chunk_catalog = self._content_chunk_catalog(manifest)
        approved_outcomes = [
            outcome.strip() for outcome in (course_outcomes or []) if outcome.strip()
        ]
        if approved_outcomes:
            outcome_lines = "\n".join(
                f"              CO{index}: {outcome}"
                for index, outcome in enumerate(approved_outcomes, start=1)
            )
            outcome_instruction = (
                "\n            - The department has approved these course outcomes. "
                "For each topic, set course_outcomes to the ONE entry from this list "
                "whose wording the topic's content actually serves, copied verbatim. "
                "Choose nothing outside the list, never reword an entry, and leave "
                "course_outcomes empty when no entry genuinely fits:\n"
                f"{outcome_lines}\n"
            )
        else:
            outcome_instruction = (
                "\n            - Leave every topic's course_outcomes empty. Course "
                "outcomes are approved by the department and cannot be inferred from "
                "source material.\n"
            )
        pdf_bytes, _, _ = bounded_pdf_attachment(pdf_path)
        binary = BinaryContent(data=pdf_bytes, media_type="application/pdf")
        result = await self.content_agent.run(
            [
                f"""
                Analyze this college study document and return a source-grounded content map.

                Requirements:
                - Identify the subject conservatively.
                - Split content into academic topics and units at section
                  granularity: a full chapter typically yields 4-10 distinct
                  topics, each with its genuinely explained subtopics. Never
                  merge the whole selection into 2-3 broad topics.
                - This PDF contains only original source pages
                  {manifest.selected_page_start} through {manifest.selected_page_end}.
                - Every topic must cite ORIGINAL source page numbers within that range.
                - Every topic must select directly relevant evidence_chunk_ids from the
                  backend-owned catalog below.
                - List only subtopics actually supported by the document.
                - Infer supported Bloom levels from the activities the material enables.
                - Do not invent course outcomes. Leave them empty when none are supplied.
                - Leave visual_asset_ids empty; they are linked by the application.

                Backend-owned evidence chunk catalog:
                {chunk_catalog}
                """,
                binary,
            ]
        )
        content_map = self._normalize_content_pages(result.output, manifest)
        content_map = self._link_topics_to_assets(
            content_map, manifest.visual_assets
        )
        logger.info(
            "ai.content_analysis.complete document_id=%s subject=%s topics=%d "
            "duration_seconds=%.2f",
            manifest.document_id,
            content_map.subject,
            len(content_map.topics),
            time.perf_counter() - started,
        )
        return content_map

    async def analyze_visuals(
        self, manifest: DocumentManifest
    ) -> list[VisualAsset]:
        logger.info(
            "ai.visual_analysis.start document_id=%s candidates=%d",
            manifest.document_id,
            len(manifest.visual_assets),
        )
        analyzed: list[VisualAsset] = []
        pages = {page.page_number: page for page in manifest.pages}
        for asset in manifest.visual_assets:
            asset_started = time.perf_counter()
            logger.info(
                "ai.visual_analysis.asset_start document_id=%s asset_id=%s page=%d",
                manifest.document_id,
                asset.asset_id,
                asset.page_number,
            )
            path = Path(asset.image_path)
            if not path.exists():
                logger.warning(
                    "ai.visual_analysis.asset_missing document_id=%s asset_id=%s",
                    manifest.document_id,
                    asset.asset_id,
                )
                analyzed.append(asset)
                continue
            page = pages[asset.page_number]
            prompt = f"""
                Inspect this visual extracted from page {asset.page_number} of an academic PDF.

                Nearby page context:
                {asset.caption or ""}
                {asset.nearby_text or page.text[:2500]}

                Classify the visual and decide whether it is safe for a diagram-based
                examination question. It is eligible only when labels, relationships,
                axes, values, or components are sufficiently clear. Never guess unreadable
                content. Return low confidence and a rejection reason when uncertain.
            """
            media_type = self._media_type(path)
            result = await self.visual_agent.run(
                [prompt, BinaryContent(data=path.read_bytes(), media_type=media_type)]
            )
            assessment = result.output
            logger.info(
                "ai.visual_analysis.asset_complete document_id=%s asset_id=%s "
                "type=%s eligible=%s confidence=%.2f duration_seconds=%.2f",
                manifest.document_id,
                asset.asset_id,
                assessment.asset_type.value,
                assessment.question_eligible and assessment.confidence >= 0.80,
                assessment.confidence,
                time.perf_counter() - asset_started,
            )
            analyzed.append(
                asset.model_copy(
                    update={
                        "asset_type": assessment.asset_type,
                        "visible_labels": assessment.visible_labels,
                        "topic": assessment.topic,
                        "question_eligible": (
                            assessment.question_eligible
                            and assessment.confidence >= 0.80
                        ),
                        "confidence": assessment.confidence,
                        "rejection_reason": assessment.rejection_reason,
                    }
                )
            )
        logger.info(
            "ai.visual_analysis.complete document_id=%s eligible=%d total=%d",
            manifest.document_id,
            sum(asset.question_eligible for asset in analyzed),
            len(analyzed),
        )
        return analyzed

    async def generate_question(
        self,
        *,
        slot_prompt: str,
        evidence_text: str,
        visual_path: str | None = None,
    ) -> QuestionCandidate:
        logger.info("ai.question_generation.request visual=%s", bool(visual_path))
        content: list[object] = [
            f"""
            You are generating one candidate for a standards-aligned examination.
            Follow this locked blueprint slot exactly:
            {slot_prompt}

            Source evidence:
            {evidence_text}

            Rules:
            - The supplied evidence defines the allowed concept, formula, method,
              terminology, and syllabus boundary.
            - Prefer an original, realistic, self-contained application. You may create
              new names, contexts, quantities, and values when they are internally
              consistent and require only the evidenced concept to solve.
            - Do not introduce an unevidenced concept, formula, law, theorem, historical
              claim, scientific fact, or subject-specific method.
            - Make the question standalone and unambiguous.
            - Return exact source page numbers and short supporting excerpts.
            - The marking scheme must add exactly to the question marks.
            - Explain why the actual reasoning demand matches the Bloom level.
            - Do not claim confidence above the evidence quality.
            """
        ]
        if visual_path:
            path = Path(visual_path)
            content.append(
                BinaryContent(data=path.read_bytes(), media_type=self._media_type(path))
            )
        result = await self.question_agent.run(content)
        logger.info(
            "ai.question_generation.response slot_id=%s confidence=%.2f",
            result.output.slot_id,
            result.output.confidence,
        )
        return result.output

    async def generate_section(
        self,
        *,
        section_id: str,
        expected_question_count: int,
        slots_prompt: str,
        evidence_text: str,
        visual_paths: list[tuple[str, str]],
    ) -> SectionQuestionBatch:
        started = time.perf_counter()
        logger.info(
            "ai.section_generation.request section_id=%s questions=%d visuals=%d",
            section_id,
            expected_question_count,
            len(visual_paths),
        )
        content: list[object] = [
            f"""
            Generate one complete section of a standards-aligned examination in a single response.

            Section: {section_id}
            Expected question count: EXACTLY {expected_question_count}

            Locked blueprint slots:
            {slots_prompt}

            Source evidence:
            {evidence_text}

            Requirements:
            - Return exactly one QuestionCandidate for every blueprint slot.
            - Preserve every slot_id, marks value, and effective bloom_level exactly.
              requested_bloom_level records the pattern's original target; bloom_level
              is the source-supported cognitive demand to generate.
            - When a slot includes a facet, the question MUST take that specific angle
              on the topic. Different slots share topics but never facets, so two
              questions on the same topic must not reduce to the same underlying task
              with changed numbers.
            - Treat the supplied evidence as a concept and syllabus boundary, not as
              text that must be copied. Every tested concept, formula, method, law,
              theorem, and technical term must be supported by the permitted evidence.
            - Create original, realistic, self-contained questions by default. New names,
              contexts, quantities, datasets, and numerical values are allowed and
              encouraged when they are internally consistent and solvable using only
              the evidenced concepts. State every new fact or assumption needed to solve
              the question in the stem, case, table, or figure.
            - Do not introduce an outside concept, formula, method, scientific claim,
              historical fact, or required general knowledge that is absent from the
              permitted evidence.
            - Make every question standalone and unambiguous.
            - Avoid duplicate concepts and wording across this section.
            - Student-facing text must use readable plain Unicode mathematics. Do not
              emit raw LaTeX commands, Markdown emphasis, escaped Unicode codes, or
              programming notation such as ** for powers.
            - Student-facing text must be fully self-contained. Never reference "the
              source material", the textbook, chapter/section/exercise numbers, or
              numbered theorems and definitions ("Theorem 5", "Definition 1") — the
              student sitting this paper has no textbook. State any needed fact or
              property explicitly in the question.
            - Adapt any single worked example from the source at most once. Prefer
              inventing a fresh scenario over reusing the source's most prominent
              example, especially when another slot shares the same topic.
            - Respect subparts, choices_per_question, and answers_required.
            - For multiple_choice slots, include exactly four labelled options (A-D)
              in question_text and state the correct option in the answer. All four
              distractors must be mathematically and semantically distinct, not merely
              different phrasings of the same condition.
            - For assertion_reason slots, provide an Assertion (A), a Reason (R), and
              exactly these four response meanings: (A) both are true and R correctly
              explains A; (B) both are true but R does not explain A; (C) A is true
              but R is false; (D) A is false but R is true. State the correct option
              in the answer and independently verify both statements.
            - Never give four response options to a slot other than multiple_choice
              or assertion_reason.
            - If has_internal_choice is true, question_text must contain two complete
              and workload-equivalent alternatives separated by one standalone "OR".
              When internal_choice_scope is whole_question, use EXACTLY this layout —
              a line beginning "(a) ", then a line containing only "OR", then a line
              beginning "(b) ". Write the separator as the bare word OR on its
              own line; the paper renders it as the bracketed [OR] the college
              prints. Each alternative is ONE self-contained task carrying
              the slot's FULL marks: a student who answers (a) is marked out of all
              of them. Never split an alternative into "(i)"/"(ii)" parts, never
              write "Answer EITHER (i) OR (ii)", and never award marks per part.
              When internal_choice_scope is final_subpart, use EXACTLY this layout —
              the shared case paragraph, then lines beginning "(i) ", "(ii) ", and
              "(iii)(a) ", then a line containing only "OR", then a line beginning
              "(iii)(b) ". Never start question_text with OR; otherwise provide one
              task only.
            - A question worth 2 marks or fewer must be a single direct instruction on
              one line, answerable in about two minutes. Never give it a scenario, a
              case paragraph, a named organisation, or multiple sub-questions — those
              belong to the long-answer sections. Reserve original scenarios for
              questions worth 5 marks or more.
            - Set estimated_answer_minutes to a realistic estimate for an adequately
              prepared student. Use the actual reading and reasoning workload: roughly
              1-2 minutes per mark is normal, with more time only for substantial
              diagrams, calculations, datasets, or design work.
            - For case_study slots, create an original real-world case, passage, dataset,
              table, or experimental situation followed by exactly three connected
              subquestions marked (i), (ii), and (iii), with marks 1, 1, and 2. The
              case must be substantive and self-contained, and its information must be
              necessary for all three parts. Do not write a textbook definition followed
              by three unrelated routine exercises. Parts should progress from
              interpretation to application or reasoning.
            - Match the real cognitive workload, not merely a Bloom verb. Do not insert
              formulaic command words just to signal a level. A 5-mark
              answer must require multi-step reasoning plus explanation or derivation.
              Analyze must decompose or compare; Evaluate must require a justified
              judgment; Create must require a model, design, or formulation with constraints.
            - Never exceed the slot's effective bloom_level either. A remember slot must
              be answerable by pure recall of a stated fact, formula, or definition; an
              understand slot by explanation or direct interpretation. Do not escalate a
              low-level slot into application, analysis, or evaluation work, and never
              claim a lower level than the reasoning your question actually demands.
            - When requires_visual is true, use the attached visual and set
              evidence.visual_asset_id to the slot's exact visual_asset_id.
              Refer to it only as "the provided figure"; never print its internal ID.
              The figure must be necessary to answer the question, and the question's
              topic and values must visibly match the figure. If the visual slot also
              has internal choice, both alternatives must meaningfully depend on the
              provided figure.
            - Select at least one supplied chunk_id and return it in
              evidence.chunk_ids. Use only IDs explicitly listed under that slot's
              allowed_chunk_ids. The backend owns the quotation text; do not invent
              or borrow IDs from another slot. Return the corresponding original pages.
            - Source citations justify the tested concept and method; they do not need
              to contain the newly created scenario or numerical values.
            - Each marking scheme must add exactly to that question's marks. For a
              question with an internal choice, give criteria for ONE alternative
              only (the alternatives are equivalent); never sum both alternatives.
              For questions worth 5 marks or more, split credit across the actual
              reasoning, calculation, justification, or design steps. Never award all
              marks through one vague criterion such as "complete answer".
            - Write a model answer that demonstrates every marking criterion. Verify
              calculations, units, option labels, and conclusions independently.
            - Write matrices and determinants inline in bracket form, e.g.
              A = [3 5; 2 7]. NEVER draw multi-line ASCII art with vertical bars,
              and never place a multi-line matrix inside an MCQ option — each
              option must fit on its own single line.
            - Explain why the reasoning demand matches the Bloom level.
            - Do not claim confidence above the evidence quality.
            """
        ]
        for asset_id, visual_path in visual_paths:
            path = Path(visual_path)
            content.extend(
                [
                    f"Visual asset {asset_id} follows:",
                    BinaryContent(
                        data=path.read_bytes(),
                        media_type=self._media_type(path),
                    ),
                ]
            )
        result = await self.section_question_agent.run(content)
        logger.info(
            "ai.section_generation.response section_id=%s returned=%d "
            "duration_seconds=%.2f",
            section_id,
            len(result.output.questions),
            time.perf_counter() - started,
        )
        return result.output

    async def review_section(
        self,
        *,
        section_id: str,
        slots_prompt: str,
        questions: list[QuestionCandidate],
        evidence_text: str,
        visual_paths: list[tuple[str, str]],
    ) -> SectionReviewBatch:
        started = time.perf_counter()
        logger.info(
            "ai.section_review.request section_id=%s questions=%d visuals=%d",
            section_id,
            len(questions),
            len(visual_paths),
        )
        content: list[object] = [
            f"""
            Independently review this complete college-examination section.
            Treat the supplied evidence as the boundary for tested concepts and methods.
            Original self-contained scenarios and values are allowed.

            Section: {section_id}
            Locked blueprint slots:
            {slots_prompt}

            Candidate questions:
            {SectionQuestionBatch(questions=questions).model_dump_json(indent=2)}

            Source evidence:
            {evidence_text}

            Return exactly one review for every candidate_id. Check each question
            independently for concept grounding, answer correctness, clarity, marking
            logic, and visual consistency. Also reject meaningful duplication within
            the section.

            Bloom level is reported, not enforced. For every question set
            observed_bloom_level to the level it genuinely demands, judged from the
            cognitive work a student must actually do — not from its verbs and not from
            the level the question claims. Set bloom_level_correct to whether that
            observed level equals the slot's locked bloom_level. A mismatch is recorded
            for the faculty reviewer and never on its own makes a question defective: an
            otherwise sound, well-grounded, correctly answered question is a PASS even
            when it sits above or below its slot's level. Judge every other check
            independently of it, and do not lower quality_score for a mismatch alone. For visual questions,
            set visual_necessary=false when the task is answerable without the image
            or the attached image is merely decorative or topically unrelated. In
            particular, set it false when every value and fact needed to solve the
            question is already stated in question_text and the image only illustrates
            the general topic. For non-visual questions, leave visual_necessary=true
            because that check is not applicable.

            Grounding: the evidence above consists of bounded excerpts, not the full
            source. Set grounded_in_evidence=true when the tested concept, method,
            formula, and terminology fall within the topics and techniques those
            excerpts and the slot's locked topic cover. Do not require the excerpt to
            contain a worked example, pedagogical scaffolding, or the exact function
            or values used in the question. Set it false only when the question tests
            a concept, law, or method outside that scope.

            reasons: list ONLY actual defects, one short sentence (at most 25 words)
            per failed boolean. Never include verification notes, praise,
            restatements of passing checks, or your full rubric — passing checks are
            already communicated by the boolean fields.
            Always return quality_dimensions using 0-100 integer scores for grounding,
            correctness, clarity, marks_fit, bloom_alignment, originality, and
            answer_scheme. Score visual_relevance only for a visual question.
            Originality means a distinct assessed task, not changed names or numbers.
            The overall quality_score must not exceed a materially weak dimension and
            must be below 85 when grounding, correctness, marks fit, or answer scheme
            is materially defective.
            Be conservative.
            """
        ]
        for asset_id, visual_path in visual_paths:
            path = Path(visual_path)
            content.extend(
                [
                    f"Visual asset {asset_id} follows:",
                    BinaryContent(
                        data=path.read_bytes(),
                        media_type=self._media_type(path),
                    ),
                ]
            )
        result = await self.section_review_agent.run(content)
        logger.info(
            "ai.section_review.response section_id=%s returned=%d "
            "duration_seconds=%.2f",
            section_id,
            len(result.output.reviews),
            time.perf_counter() - started,
        )
        return result.output

    async def repair_questions(
        self,
        *,
        repair_prompt: str,
        expected_question_count: int,
        source_pdf_path: str | None,
        selected_page_start: int,
        selected_page_end: int,
        visual_paths: list[tuple[str, str]],
    ) -> SectionQuestionBatch:
        """Replace rejected candidates in one bounded, feedback-driven call."""
        started = time.perf_counter()
        logger.info(
            "ai.paper_repair.request questions=%d visuals=%d attach_pdf=%s",
            expected_question_count,
            len(visual_paths),
            bool(source_pdf_path),
        )
        source_description = (
            "The attached PDF defines the permitted concepts, methods, formulas,\n"
            "            terminology, and syllabus scope, and represents original pages\n"
            f"            {selected_page_start} through {selected_page_end}."
            if source_pdf_path
            else (
                "The evidence chunks supplied in the repair payload define the\n"
                "            permitted concepts, methods, formulas, terminology, and\n"
                "            syllabus scope. They were extracted from original source pages\n"
                f"            {selected_page_start} through {selected_page_end}."
            )
        )
        content: list[object] = [
            f"""
            Repair the rejected examination questions described below.
            Return EXACTLY {expected_question_count} replacement QuestionCandidates,
            one for every supplied slot_id.

            {source_description}

            Repair payload:
            {repair_prompt}

            Requirements:
            - Correct every listed validation and review finding.
            - Preserve slot_id, marks, effective bloom_level, and question type exactly.
              bloom_level is authoritative when it differs from requested_bloom_level.
              Never exceed the effective bloom_level: a remember or understand slot
              must stay a genuine recall or comprehension task.
            - When the locked slot includes a facet, the replacement MUST take that
              specific angle on the topic — it is the primary tool for escaping a
              duplicate: change the underlying task, not just names and numbers.
            - Do not repeat or paraphrase ANY question text listed in
              other_question_texts_to_avoid — test a different fact, value, or
              scenario, even if the original defect was unrelated to duplication.
            - Never introduce a tested concept, formula, method, law, theorem, technical
              term, or required subject knowledge that is not supported by the permitted
              source material described above.
            - Create a fresh self-contained scenario, dataset, names, quantities, and
              numerical values when useful. New values need not occur in the source
              material, but they must be realistic, internally consistent, uniquely
              solvable, and independently verified using a source-supported method.
            - Use only evidence chunks and original pages permitted by the locked slot.
            - Select at least one valid source chunk ID supplied in the locked evidence
              and return it in evidence.chunk_ids. Never invent chunk IDs.
            - For MCQs, provide exactly four clearly labelled options A-D and identify
              the correct option in the answer.
            - For assertion-reason slots, provide Assertion (A), Reason (R), the
              standard four assertion-reason response meanings, and identify the
              independently verified correct option.
            - Never give four response options to a slot other than multiple_choice
              or assertion_reason.
            - For internal choices, provide two complete, workload-equivalent alternatives
              separated by exactly one standalone OR; never begin with OR. When the
              scope is whole_question label them "(a) " and "(b) ", each a single
              self-contained task carrying the slot's full marks — never split an
              alternative into "(i)"/"(ii)" parts and never write "Answer EITHER (i)
              OR (ii)". A question worth 2 marks or fewer must stay a single direct
              instruction on one line, with no scenario and no sub-questions. When the
              locked scope is final_subpart, keep the shared case and parts (i) and (ii)
              once and put the OR only between alternatives (iii)(a) and (iii)(b).
            - A 5-mark question must require multi-step reasoning plus explanation or
              derivation. Evaluate requires justified judgment; Create requires a model
              or design with constraints.
            - Set estimated_answer_minutes from the actual reading and reasoning
              workload, normally about 1-2 minutes per mark.
            - A case-study slot needs an original, substantive, self-contained shared
              scenario or dataset and exactly three connected subquestions worth
              1, 1, and 2 marks. All parts must depend on the supplied case information;
              do not use a definition paragraph followed by unrelated exercises.
            - For visual slots, use the attached required image, set
              evidence.visual_asset_id to the exact required ID, and refer to it only
              as "the provided figure" in student-facing text. The figure must be
              necessary and topically relevant to the actual task. When internal choice
              exists, both replacement alternatives must depend on the figure.
            - Do not include question numbers or internal asset IDs in question_text.
            - Student-facing text must use readable plain Unicode mathematics. Do not
              emit raw LaTeX commands, Markdown emphasis, escaped Unicode codes, or
              programming notation such as ** for powers.
            - Student-facing text must be fully self-contained: never reference "the
              source material", the textbook, chapter/section/exercise numbers, or
              numbered theorems and definitions. State any needed fact in the question.
            - The marking scheme must total exactly the question's marks, counting an
              internal choice's alternatives once (criteria for one alternative only).
              For 5 marks or more, use multiple specific criteria tied to answer steps,
              and make the model answer demonstrate every criterion.
            - Write matrices inline in bracket form, e.g. A = [3 5; 2 7]; never as
              multi-line ASCII art with vertical bars.
            """
        ]
        if source_pdf_path:
            content.append(
                BinaryContent(
                    data=bounded_pdf_attachment(source_pdf_path)[0],
                    media_type="application/pdf",
                )
            )
        for asset_id, visual_path in visual_paths:
            visual = Path(visual_path)
            if not visual.exists():
                continue
            content.extend(
                [
                    f"Required visual asset_id={asset_id}:",
                    BinaryContent(
                        data=visual.read_bytes(),
                        media_type=self._media_type(visual),
                    ),
                ]
            )
        result = await self.section_question_agent.run(content)
        logger.info(
            "ai.paper_repair.response returned=%d duration_seconds=%.2f",
            len(result.output.questions),
            time.perf_counter() - started,
        )
        return result.output

    async def review_question(
        self,
        *,
        question: QuestionCandidate,
        required_bloom_level: BloomLevel,
        evidence_text: str,
        visual_path: str | None = None,
    ) -> SemanticReview:
        logger.info(
            "ai.question_review.request candidate_id=%s",
            question.candidate_id,
        )
        content: list[object] = [
            f"""
            Independently review this proposed standards-aligned examination question.
            Treat the supplied evidence as the boundary for tested concepts and methods.
            Original self-contained scenarios and values are allowed.

            Required Bloom level: {required_bloom_level.value}
            Candidate:
            {question.model_dump_json(indent=2)}

            Source evidence:
            {evidence_text}

            Reject unsupported facts, ambiguous wording, wrong answers, incorrect
            marking schemes, malformed student-facing mathematical notation,
            disconnected case-study parts, and claims about visual labels or
            relationships that are not visible. Verify only this replacement; do not
            assume that a previous whole-paper finding was fixed. Be conservative about
            concrete defects without enforcing stylistic preferences.

            Bloom level is reported, not enforced. Always set observed_bloom_level to
            the level the question genuinely demands, judged from the cognitive work a
            student must actually do — not from its verbs and not from the level the
            question claims. Set bloom_level_correct to whether that observed level
            equals the required level. A mismatch is recorded for the faculty reviewer
            and never on its own makes a question defective: an otherwise sound,
            well-grounded, correctly answered question is a PASS even when it sits above
            or below the required level. Judge every other check independently of it.

            Always return quality_dimensions using 0-100 integer scores for grounding,
            correctness, clarity, marks_fit, bloom_alignment, originality, and
            answer_scheme. Score visual_relevance only when an image is attached.
            Assess marks_fit from expected student workload and required answer depth.
            Assess answer_scheme from correctness and mark-wise completeness. Keep the
            overall quality_score at or below any materially weak dimension.
            """
        ]
        if visual_path:
            path = Path(visual_path)
            content.append(
                BinaryContent(data=path.read_bytes(), media_type=self._media_type(path))
            )
        result = await self.review_agent.run(content)
        logger.info(
            "ai.question_review.response candidate_id=%s grounded=%s correct=%s "
            "bloom=%s clear=%s confidence=%.2f",
            question.candidate_id,
            result.output.grounded_in_evidence,
            result.output.answer_correct,
            result.output.bloom_level_correct,
            result.output.wording_clear,
            result.output.confidence,
        )
        return result.output

    @staticmethod
    def _enforce_topic_units(
        content: ContentMap,
        manifest: DocumentManifest,
    ) -> ContentMap:
        """Set each topic's unit from the pages it came from.

        When the faculty member uploads one file per unit we know exactly which
        pages belong to which upload row, so the unit is computed rather than
        inferred from chapter headings. Evidence chunk ownership is authoritative:
        models sometimes cite the printed page number from each source PDF after
        the files have been merged, making several uploads all look like pages
        1-10. Only when a topic has no valid evidence chunks do source-page votes
        provide the fallback.
        """
        page_units = {
            page.page_number: page.unit
            for page in manifest.pages
            if page.unit
        }
        if not page_units:
            return content
        chunks = build_evidence_chunks(manifest)
        topics = []
        for topic in content.topics:
            evidence_pages = [
                chunks[chunk_id].page_number
                for chunk_id in topic.evidence_chunk_ids
                if chunk_id in chunks
            ]
            pages = evidence_pages or topic.source_pages
            votes = Counter(page_units[page] for page in pages if page in page_units)
            topics.append(
                topic.model_copy(update={"unit": votes.most_common(1)[0][0]})
                if votes
                else topic
            )
        return content.model_copy(update={"topics": topics})

    @staticmethod
    def _enforce_course_outcomes(
        content: ContentMap,
        course_outcomes: list[str] | None,
    ) -> ContentMap:
        """Keep only outcomes the department actually approved.

        Course outcomes are a governance artifact, not something derivable from a
        textbook. `Topic.course_outcomes` is part of the analysis schema, so the
        model fills it in whether or not the prompt asks — producing convincing
        strings like "Learn the basics of NumPy arrays" that no Board of Studies
        ever approved. Anything outside the supplied list is dropped here.
        """
        approved = [outcome.strip() for outcome in (course_outcomes or []) if outcome.strip()]
        allowed = {outcome.casefold(): outcome for outcome in approved}
        topics = [
            topic.model_copy(
                update={
                    "course_outcomes": [
                        allowed[candidate.strip().casefold()]
                        for candidate in topic.course_outcomes
                        if candidate.strip().casefold() in allowed
                    ]
                }
            )
            for topic in content.topics
        ]
        return content.model_copy(
            update={"course_outcomes": approved, "topics": topics}
        )

    @staticmethod
    def _normalize_content_pages(
        content: ContentMap,
        manifest: DocumentManifest,
    ) -> ContentMap:
        selected_count = manifest.selected_page_end - manifest.selected_page_start + 1
        chunks = build_evidence_chunks(manifest)
        topics: list[Topic] = []
        for topic in content.topics:
            normalized: list[int] = []
            for page in topic.source_pages:
                if manifest.selected_page_start <= page <= manifest.selected_page_end:
                    normalized.append(page)
                elif 1 <= page <= selected_count:
                    normalized.append(manifest.selected_page_start + page - 1)
            normalized = list(dict.fromkeys(normalized))
            selected_chunk_ids = [
                chunk_id
                for chunk_id in topic.evidence_chunk_ids
                if chunk_id in chunks
                and (not normalized or chunks[chunk_id].page_number in normalized)
            ][:8]
            if not selected_chunk_ids and normalized:
                topic_terms = DocumentAnalyzer._academic_tokens(
                    " ".join([topic.name, *topic.subtopics])
                )
                selected_chunk_ids = [
                    chunk_id
                    for chunk_id, chunk in chunks.items()
                    if chunk.page_number in normalized
                    and topic_terms
                    & DocumentAnalyzer._academic_tokens(chunk.text)
                ][:8]
            if selected_chunk_ids and not normalized:
                normalized = list(
                    dict.fromkeys(
                        chunks[chunk_id].page_number for chunk_id in selected_chunk_ids
                    )
                )
            if not normalized or not selected_chunk_ids:
                logger.warning(
                    "ai.content_analysis.topic_discarded topic_id=%s reason=no_verified_evidence",
                    topic.topic_id,
                )
                continue
            bloom_levels = list(BloomLevel)
            if topic.supported_bloom_levels:
                highest_supported = max(
                    bloom_levels.index(level)
                    for level in topic.supported_bloom_levels
                )
                supported_bloom_levels = bloom_levels[: highest_supported + 1]
            else:
                supported_bloom_levels = [
                    BloomLevel.REMEMBER,
                    BloomLevel.UNDERSTAND,
                ]
            topics.append(
                topic.model_copy(
                    update={
                        "source_pages": normalized,
                        "evidence_chunk_ids": list(dict.fromkeys(selected_chunk_ids)),
                        "supported_bloom_levels": supported_bloom_levels,
                    }
                )
            )
        return content.model_copy(update={"topics": topics})

    @staticmethod
    def _content_chunk_catalog(manifest: DocumentManifest) -> str:
        """Include every chunk ID while sharing a bounded, fair text preview."""
        chunks = list(build_evidence_chunks(manifest).values())
        if not chunks:
            return "No extractable evidence chunks."
        # The catalog lists every chunk id so no page is invisible, but the
        # previews share a bounded budget: at 100k characters it was consuming a
        # quarter of the context window on its own.
        catalog_budget = _env_int("CHUNK_CATALOG_CHARS", 40_000)
        preview_size = max(120, min(500, catalog_budget // len(chunks)))
        return "\n\n".join(
            f"[chunk_id={chunk.chunk_id} original_page={chunk.page_number}]\n"
            f"{chunk.text[:preview_size]}"
            for chunk in chunks
        )

    @staticmethod
    def _academic_tokens(value: str) -> set[str]:
        stopwords = {
            "and", "the", "for", "with", "from", "into", "using", "unit",
            "figure", "diagram", "image", "example", "chapter", "topic",
            "mathematical", "model", "modelling", "physical", "problem",
            "activity", "principle", "method",
            "mathematical", "model", "modelling", "physical", "problem",
            "activity", "principle", "method",
            "this", "that", "are", "was", "were", "has", "have",
        }
        return {
            token
            for token in re.findall(r"[a-z0-9]+", value.lower())
            if len(token) >= 3 and token not in stopwords
        }

    @staticmethod
    def _link_topics_to_assets(
        content: ContentMap, assets: list[VisualAsset]
    ) -> ContentMap:
        topics: list[Topic] = []
        for topic in content.topics:
            linked = [
                asset.asset_id
                for asset in assets
                if asset.question_eligible
                and asset.page_number in topic.source_pages
                and DocumentAnalyzer._visual_matches_topic(asset, topic)
            ]
            topics.append(
                topic.model_copy(update={"visual_asset_ids": list(dict.fromkeys(linked))})
            )
        return content.model_copy(update={"topics": topics})

    @staticmethod
    def _page_has_source_topic(page_number: int, content: ContentMap) -> bool:
        return any(page_number in topic.source_pages for topic in content.topics)

    @staticmethod
    def _visual_matches_source_topic(
        asset: VisualAsset, content: ContentMap
    ) -> bool:
        return any(
            asset.page_number in topic.source_pages
            and DocumentAnalyzer._visual_matches_topic(asset, topic)
            for topic in content.topics
        )

    @staticmethod
    def _visual_area(asset: VisualAsset) -> float:
        box = asset.bounding_box
        return (box.x1 - box.x0) * (box.y1 - box.y0) if box else 0

    @staticmethod
    def _visual_matches_topic(asset: VisualAsset, topic: Topic) -> bool:
        """Fail closed unless visual metadata shares meaningful topic terms."""
        stopwords = {
            "and", "the", "for", "with", "from", "into", "using", "unit",
            "figure", "diagram", "image", "example", "chapter", "topic",
            "mathematical", "model", "modelling", "physical", "problem",
            "activity", "principle", "method",
        }

        def tokens(value: str) -> set[str]:
            return {
                token
                for token in re.findall(r"[a-z0-9]+", value.lower())
                if len(token) >= 3 and token not in stopwords
            }

        topic_terms = tokens(" ".join([topic.name, *topic.subtopics]))
        assessed_terms = tokens(asset.topic or "")
        context_terms = tokens(
            " ".join(
                [
                    asset.caption or "",
                    asset.nearby_text or "",
                    " ".join(asset.visible_labels),
                ]
            )
        )
        exact_assessed_topic = bool(topic_terms) and topic_terms == assessed_terms
        return exact_assessed_topic or (
            len(topic_terms & assessed_terms) >= 2
            or len(topic_terms & context_terms) >= 2
        )

    @staticmethod
    def _select_visual_candidates(
        manifest: DocumentManifest,
    ) -> list[VisualAsset]:
        limit = max(0, int(os.getenv("MAX_VISUAL_CANDIDATES", "12")))
        if not limit:
            return []

        candidates = [
            asset
            for asset in manifest.visual_assets
            if Path(asset.image_path).exists()
        ]
        return sorted(
            candidates,
            key=lambda asset: (
                DocumentAnalyzer._visual_area(asset),
                len(asset.nearby_text or ""),
            ),
            reverse=True,
        )[:limit]

    @staticmethod
    def _media_type(path: Path) -> str:
        extension = path.suffix.lower()
        return {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }.get(extension, "application/octet-stream")
