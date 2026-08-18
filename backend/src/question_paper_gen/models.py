from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator


class BloomLevel(StrEnum):
    REMEMBER = "remember"
    UNDERSTAND = "understand"
    APPLY = "apply"
    ANALYZE = "analyze"
    EVALUATE = "evaluate"
    CREATE = "create"


class QuestionKind(StrEnum):
    MULTIPLE_CHOICE = "multiple_choice"
    ASSERTION_REASON = "assertion_reason"
    VERY_SHORT_ANSWER = "very_short_answer"
    SHORT_ANSWER = "short_answer"
    LONG_ANSWER = "long_answer"
    VERY_LONG_ANSWER = "very_long_answer"
    CASE_STUDY = "case_study"
    DIAGRAM_LABEL = "diagram_label"
    DIAGRAM_INTERPRETATION = "diagram_interpretation"
    GRAPH_INTERPRETATION = "graph_interpretation"
    NUMERICAL = "numerical"


class VisualType(StrEnum):
    RASTER_IMAGE = "raster_image"
    DIAGRAM = "diagram"
    GRAPH = "graph"
    TABLE = "table"
    CIRCUIT = "circuit"
    FLOWCHART = "flowchart"
    EQUATION = "equation"
    UNKNOWN = "unknown"


class ValidationSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class BoundingBox(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float

    @model_validator(mode="after")
    def coordinates_are_ordered(self) -> "BoundingBox":
        if self.x1 <= self.x0 or self.y1 <= self.y0:
            raise ValueError("bounding box must have positive width and height")
        return self


class VisualAsset(BaseModel):
    asset_id: str
    page_number: Annotated[int, Field(ge=1)]
    asset_type: VisualType = VisualType.UNKNOWN
    bounding_box: BoundingBox | None = None
    image_path: str
    caption: str | None = None
    nearby_text: str | None = None
    visible_labels: list[str] = Field(default_factory=list)
    topic: str | None = None
    question_eligible: bool = False
    confidence: Annotated[float, Field(ge=0, le=1)] = 0
    rejection_reason: str | None = None


class PageContent(BaseModel):
    page_number: Annotated[int, Field(ge=1)]
    width: Annotated[float, Field(gt=0)]
    height: Annotated[float, Field(gt=0)]
    text: str
    rendered_image_path: str
    visual_asset_ids: list[str] = Field(default_factory=list)


class DocumentQuality(BaseModel):
    passed: bool
    page_count: Annotated[int, Field(ge=0)]
    text_character_count: Annotated[int, Field(ge=0)]
    pages_without_text: list[int] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class DocumentManifest(BaseModel):
    document_id: str
    original_filename: str
    sha256: str
    source_pdf_path: str
    artifact_directory: str
    source_total_pages: Annotated[int, Field(ge=1)] = 1
    selected_page_start: Annotated[int, Field(ge=1)] = 1
    selected_page_end: Annotated[int, Field(ge=1)] = 1
    pages: list[PageContent]
    visual_assets: list[VisualAsset]
    quality: DocumentQuality

    def eligible_visuals(self) -> list[VisualAsset]:
        return [asset for asset in self.visual_assets if asset.question_eligible]


class Topic(BaseModel):
    topic_id: str
    name: str
    unit: str
    subtopics: list[str] = Field(default_factory=list)
    source_pages: list[int]
    course_outcomes: list[str] = Field(default_factory=list)
    supported_bloom_levels: list[BloomLevel] = Field(default_factory=list)
    evidence_chunk_ids: list[str] = Field(default_factory=list)
    visual_asset_ids: list[str] = Field(default_factory=list)


class ContentMap(BaseModel):
    subject: str
    topics: list[Topic]
    course_outcomes: list[str] = Field(default_factory=list)


class SubpartPattern(BaseModel):
    label: str
    marks: Annotated[int, Field(gt=0)]


class SectionPattern(BaseModel):
    section_id: str
    title: str
    question_kind: QuestionKind
    question_count: Annotated[int, Field(gt=0)]
    marks_each: Annotated[int, Field(gt=0)]
    mandatory: bool = True
    subparts: list[SubpartPattern] = Field(default_factory=list)
    choices_per_question: Annotated[int, Field(ge=1)] = 1
    answers_required: Annotated[int, Field(ge=1)] = 1
    internal_choice_count: Annotated[int, Field(ge=0)] = 0
    bloom_sequence: list[BloomLevel]
    question_kind_sequence: list[QuestionKind] = Field(default_factory=list)
    internal_choice_positions: list[Annotated[int, Field(ge=1)]] = Field(
        default_factory=list
    )
    internal_choice_scope: Literal["whole_question", "final_subpart"] = (
        "whole_question"
    )
    visual_question_count: Annotated[int, Field(ge=0)] = 0

    @model_validator(mode="after")
    def section_is_consistent(self) -> "SectionPattern":
        if len(self.bloom_sequence) != self.question_count:
            raise ValueError("bloom_sequence must contain one level per question")
        if self.answers_required > self.choices_per_question:
            raise ValueError("answers_required cannot exceed choices_per_question")
        if self.visual_question_count > self.question_count:
            raise ValueError("visual_question_count cannot exceed question_count")
        if self.internal_choice_count > self.question_count:
            raise ValueError("internal_choice_count cannot exceed question_count")
        if (
            self.question_kind_sequence
            and len(self.question_kind_sequence) != self.question_count
        ):
            raise ValueError(
                "question_kind_sequence must contain one kind per question"
            )
        if any(
            position > self.question_count
            for position in self.internal_choice_positions
        ):
            raise ValueError(
                "internal_choice_positions must refer to questions in the section"
            )
        if len(set(self.internal_choice_positions)) != len(
            self.internal_choice_positions
        ):
            raise ValueError("internal_choice_positions cannot contain duplicates")
        if (
            self.internal_choice_positions
            and self.internal_choice_count
            and len(self.internal_choice_positions) != self.internal_choice_count
        ):
            raise ValueError(
                "internal_choice_count must match internal_choice_positions"
            )
        if self.internal_choice_count and self.choices_per_question < 2:
            raise ValueError(
                "choices_per_question must be at least 2 when internal choices exist"
            )
        if self.subparts and sum(part.marks for part in self.subparts) != self.marks_each:
            raise ValueError("subpart marks must add up to marks_each")
        if self.internal_choice_scope == "final_subpart" and not self.subparts:
            raise ValueError("final_subpart choice scope requires subparts")
        return self


class PaperPattern(BaseModel):
    pattern_id: str
    name: str
    duration_minutes: Annotated[int, Field(gt=0)]
    total_marks: Annotated[int, Field(gt=0)]
    sections: list[SectionPattern]

    @model_validator(mode="after")
    def total_is_consistent(self) -> "PaperPattern":
        calculated = sum(
            section.question_count * section.marks_each
            for section in self.sections
            if section.mandatory
        )
        if calculated != self.total_marks:
            raise ValueError(
                f"section marks total {calculated}, expected {self.total_marks}"
            )
        return self


class BlueprintSlot(BaseModel):
    slot_id: str
    question_number: str
    section_id: str
    marks: Annotated[int, Field(gt=0)]
    bloom_level: BloomLevel
    requested_bloom_level: BloomLevel | None = None
    question_kind: QuestionKind
    topic_id: str
    unit: str
    facet: str | None = None
    source_pages: list[Annotated[int, Field(ge=1)]] = Field(default_factory=list)
    evidence_chunk_ids: list[str] = Field(default_factory=list)
    course_outcome: str | None = None
    subparts: list[SubpartPattern] = Field(default_factory=list)
    has_internal_choice: bool = False
    internal_choice_scope: Literal["whole_question", "final_subpart"] = (
        "whole_question"
    )
    choices_per_question: Annotated[int, Field(ge=1)] = 1
    answers_required: Annotated[int, Field(ge=1)] = 1
    requires_visual: bool = False
    visual_asset_id: str | None = None

    @model_validator(mode="after")
    def visual_is_consistent(self) -> "BlueprintSlot":
        if self.requires_visual and not self.visual_asset_id:
            raise ValueError("a visual slot requires visual_asset_id")
        if self.answers_required > self.choices_per_question:
            raise ValueError("answers_required cannot exceed choices_per_question")
        return self


class PaperBlueprint(BaseModel):
    pattern_id: str
    subject: str
    slots: list[BlueprintSlot]
    warnings: list[str] = Field(default_factory=list)


class SourceEvidence(BaseModel):
    chunk_ids: list[str] = Field(default_factory=list)
    page_numbers: list[int]
    excerpts: list[str]
    visual_asset_id: str | None = None


class MarkingCriterion(BaseModel):
    criterion: str
    marks: Annotated[int, Field(gt=0)]


class QuestionCandidate(BaseModel):
    candidate_id: str
    slot_id: str
    question_text: str
    answer: str
    marks: Annotated[int, Field(gt=0)]
    bloom_level: BloomLevel
    bloom_justification: str
    marking_scheme: list[MarkingCriterion]
    evidence: SourceEvidence
    confidence: Annotated[float, Field(ge=0, le=1)]


class ValidationFinding(BaseModel):
    code: str
    severity: ValidationSeverity
    message: str


class ValidatedQuestion(BaseModel):
    candidate: QuestionCandidate
    accepted: bool
    findings: list[ValidationFinding] = Field(default_factory=list)
    quality_score: Annotated[int, Field(ge=0, le=100)] | None = None


class ExamPaper(BaseModel):
    title: str
    subject: str
    subject_family: str = "general"
    duration_minutes: int
    total_marks: int
    instructions: list[str]
    questions: list[ValidatedQuestion]
    requires_human_approval: bool = True
    publication_ready: bool = False


class QuestionPaperItem(BaseModel):
    question_id: str
    slot_id: str
    question_number: str
    section_id: str
    question_kind: QuestionKind
    question_text: str
    marks: Annotated[int, Field(gt=0)]
    bloom_level: BloomLevel
    visual_asset_id: str | None = None
    accepted: bool
    quality_score: Annotated[int, Field(ge=0, le=100)] | None = None
    findings: list[ValidationFinding] = Field(default_factory=list)


class GeneratedQuestionPaper(BaseModel):
    title: str
    subject: str
    subject_family: str = "general"
    duration_minutes: int
    total_marks: int
    instructions: list[str]
    questions: list[QuestionPaperItem]
    requires_human_approval: bool = True
    publication_ready: bool = False

    @classmethod
    def from_internal(
        cls,
        paper: ExamPaper,
        blueprint: PaperBlueprint | None = None,
    ) -> "GeneratedQuestionPaper":
        """Discard internal solutions and expose only questions and gate status."""
        slots = {slot.slot_id: slot for slot in blueprint.slots} if blueprint else {}
        return cls(
            title=paper.title,
            subject=paper.subject,
            subject_family=paper.subject_family,
            duration_minutes=paper.duration_minutes,
            total_marks=paper.total_marks,
            instructions=paper.instructions,
            questions=[
                QuestionPaperItem(
                    question_id=question.candidate.candidate_id,
                    slot_id=question.candidate.slot_id,
                    question_number=(
                        slots[question.candidate.slot_id].question_number
                        if question.candidate.slot_id in slots
                        else str(index)
                    ),
                    section_id=(
                        slots[question.candidate.slot_id].section_id
                        if question.candidate.slot_id in slots
                        else question.candidate.slot_id.rsplit("-", 1)[0]
                    ),
                    question_kind=(
                        slots[question.candidate.slot_id].question_kind
                        if question.candidate.slot_id in slots
                        else QuestionKind.SHORT_ANSWER
                    ),
                    question_text=question.candidate.question_text,
                    marks=question.candidate.marks,
                    bloom_level=question.candidate.bloom_level,
                    visual_asset_id=question.candidate.evidence.visual_asset_id,
                    accepted=question.accepted,
                    quality_score=question.quality_score,
                    findings=question.findings,
                )
                for index, question in enumerate(paper.questions, start=1)
            ],
            requires_human_approval=paper.requires_human_approval,
            publication_ready=paper.publication_ready,
        )


def normalize_artifact_path(path: str | Path) -> str:
    return str(Path(path).resolve())
