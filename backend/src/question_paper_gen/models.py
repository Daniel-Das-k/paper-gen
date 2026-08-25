from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated, ClassVar, Literal

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
    #: The syllabus unit this page belongs to, when the faculty member uploaded
    #: one file per unit. Knowing it from the upload is far safer than inferring
    #: it from the content, and it is what binds a question to its course outcome.
    unit: str | None = None
    #: Where the page came from, for a paper assembled out of several uploads.
    source_filename: str | None = None
    original_page_number: Annotated[int, Field(ge=1)] | None = None


class UnitSource(BaseModel):
    """One uploaded file and the pages of it that this exam covers.

    CAT-I examines units 1 and 2 in full and only the first half of unit 3, so
    the third upload carries a page range while the first two do not.
    """

    unit: str
    file_path: str
    original_filename: str
    start_page: Annotated[int, Field(ge=1)] | None = None
    end_page: Annotated[int, Field(ge=1)] | None = None


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
    #: The syllabus unit this section examines when the entire section belongs
    #: to one unit. Combined sections use `unit_cycle` instead.
    unit_number: str | None = None
    #: Optional printed numbering override. Papers that leave both unset number
    #: questions continuously across sections.
    question_number_prefix: str | None = None
    question_number_start: int | None = None
    #: The unit each question in this section examines, when the section spans
    #: several. An end-semester Part A prints one heading but still draws two
    #: questions from each of the five units, so it needs per-question binding
    #: rather than a single `unit_number`.
    unit_cycle: list[str] = Field(default_factory=list)
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
    #: Maximum useful visual questions to allocate when verified, topic-matched
    #: assets exist. This is never a requirement to manufacture or force a figure.
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
        if self.unit_cycle and len(self.unit_cycle) != self.question_count:
            raise ValueError("unit_cycle must contain one unit per question")
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
    observed_bloom_level: BloomLevel | None = None
    """Level the reviewer judged the question to actually demand.

    `candidate.bloom_level` is the level the blueprint asked for; this is the level
    the question turned out to exercise. They differ when the source cannot support
    the requested demand — reported to faculty, never a reason to reject.
    """


class ExamPaper(BaseModel):
    title: str
    #: "A", "B", ... when several interchangeable sets are produced for one exam.
    set_label: str | None = None
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
    observed_bloom_level: BloomLevel | None = None
    bloom_matches_blueprint: bool = True
    #: The printed tag, e.g. "CO2". Derived from the unit the question examines,
    #: so it is always present: unit 2 assesses CO2 whether or not the department
    #: has typed the outcome text into this app yet.
    course_outcome_code: str | None = None
    #: The approved wording, when the department supplied it.
    course_outcome: str | None = None
    visual_asset_id: str | None = None
    accepted: bool
    faculty_modified: bool = False
    quality_score: Annotated[int, Field(ge=0, le=100)] | None = None
    findings: list[ValidationFinding] = Field(default_factory=list)


class BloomSummary(BaseModel):
    """Per-paper account of what the blueprint asked for versus what was written."""

    requested: dict[str, int] = Field(default_factory=dict)
    observed: dict[str, int] = Field(default_factory=dict)
    deviations: int = 0
    total: int = 0
    unverified: int = 0

    @property
    def deviation_rate(self) -> float:
        return self.deviations / self.total if self.total else 0.0


class AnswerKeyEntry(BaseModel):
    """One question's answer, for the faculty member checking the paper.

    Kept out of `GeneratedQuestionPaper` on purpose: that model is the projection
    handed to students, and it must stay answer-free no matter what a caller asks
    for. The key travels beside it, never inside it.
    """

    question_id: str
    question_number: str
    section_id: str
    marks: Annotated[int, Field(gt=0)]
    criteria: list[MarkingCriterion] = Field(default_factory=list)
    answer: str

    @classmethod
    def build(
        cls,
        questions: list["ValidatedQuestion"],
        slots: dict[str, "BlueprintSlot"],
    ) -> list["AnswerKeyEntry"]:
        entries: list[AnswerKeyEntry] = []
        for index, question in enumerate(questions, start=1):
            candidate = question.candidate
            slot = slots.get(candidate.slot_id)
            entries.append(
                cls(
                    question_id=candidate.candidate_id,
                    question_number=slot.question_number if slot else str(index),
                    section_id=slot.section_id if slot else "",
                    marks=candidate.marks,
                    criteria=candidate.marking_scheme,
                    answer=candidate.answer,
                )
            )
        return entries


class ExamHeader(BaseModel):
    """The masthead of a Rajalakshmi paper.

    Nearly all of it is the same on every paper the college issues, so it is
    constant here rather than something faculty retype. Only the fields that
    genuinely change per exam — subject, code, semester, date — are left empty
    for the caller to supply.
    """

    college: str = "RAJALAKSHMI ENGINEERING COLLEGE"
    institution_line: str = "An AUTONOMOUS Institution"
    affiliation: str = "Affiliated to ANNA UNIVERSITY, Chennai"
    exam_title: str = ""
    year: str = ""
    semester: str = ""
    branch: str = "B.E. / B.Tech."
    subject_code: str = ""
    subject_name: str = ""
    qp_code: str = ""
    regulation: str = "Regulations 2023"
    common_to: str = "CSE, ECE, EEE, IT, AIML, CSD, AI & DS, CS"
    date: str = ""
    register_number_boxes: Annotated[int, Field(ge=0, le=20)] = 12

    #: Printed exam name implied by the pattern, so nobody types it in.
    _PATTERN_TITLES: ClassVar[dict[str, str]] = {
        "cat-1-75": "Continuous Assessment Test-I [CAT-I]",
        "cat-2-75": "Continuous Assessment Test-II [CAT-II]",
        "autonomous-semester-100": "End Semester Examination",
    }

    def completed_for(
        self, pattern_id: str, subject: str, duration_minutes: int
    ) -> "ExamHeader":
        """Fill anything the caller left blank that the paper already knows."""
        return self.model_copy(
            update={
                "exam_title": self.exam_title
                or self._PATTERN_TITLES.get(pattern_id, "Examination"),
                "subject_name": self.subject_name or subject,
            }
        )


class CourseOutcomeCoverage(BaseModel):
    """Marks carried by each approved course outcome across the paper."""

    marks_by_outcome: dict[str, int] = Field(default_factory=dict)
    unmapped_marks: int = 0
    total_marks: int = 0


class GeneratedQuestionPaper(BaseModel):
    title: str
    set_label: str | None = None
    subject: str
    subject_family: str = "general"
    duration_minutes: int
    total_marks: int
    instructions: list[str]
    questions: list[QuestionPaperItem]
    bloom_summary: BloomSummary = Field(default_factory=BloomSummary)
    exam_header: ExamHeader = Field(default_factory=ExamHeader)
    course_outcome_coverage: CourseOutcomeCoverage = Field(
        default_factory=CourseOutcomeCoverage
    )
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
            set_label=paper.set_label,
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
                    observed_bloom_level=question.observed_bloom_level,
                    bloom_matches_blueprint=(
                        question.observed_bloom_level is None
                        or question.observed_bloom_level
                        == question.candidate.bloom_level
                    ),
                    course_outcome=(
                        slots[question.candidate.slot_id].course_outcome
                        if question.candidate.slot_id in slots
                        else None
                    ),
                    course_outcome_code=cls._outcome_code(
                        slots.get(question.candidate.slot_id)
                    ),
                    visual_asset_id=question.candidate.evidence.visual_asset_id,
                    accepted=question.accepted,
                    quality_score=question.quality_score,
                    findings=question.findings,
                )
                for index, question in enumerate(paper.questions, start=1)
            ],
            bloom_summary=cls._summarize_bloom(paper.questions),
            course_outcome_coverage=cls._summarize_outcomes(paper.questions, slots),
            requires_human_approval=paper.requires_human_approval,
            publication_ready=paper.publication_ready,
        )

    @staticmethod
    def _outcome_code(slot: "BlueprintSlot | None") -> str | None:
        """Tag a question with the course outcome its unit assesses.

        Rajalakshmi numbers outcomes to units — unit 1 is CO1 through unit 5 as
        CO5 — so the tag follows from the paper's structure and never has to be
        typed in. Only the outcome's wording is optional.
        """
        if slot is None or not slot.unit:
            return None
        unit = str(slot.unit).strip()
        return f"CO{unit}" if unit.isdigit() else None

    @classmethod
    def _summarize_outcomes(
        cls,
        questions: list[ValidatedQuestion],
        slots: dict[str, "BlueprintSlot"],
    ) -> CourseOutcomeCoverage:
        marks_by_outcome: dict[str, int] = {}
        unmapped = 0
        total = 0
        for question in questions:
            marks = question.candidate.marks
            total += marks
            slot = slots.get(question.candidate.slot_id)
            code = cls._outcome_code(slot)
            wording = slot.course_outcome if slot else None
            # Prefer the approved wording; fall back to the structural tag so the
            # table is never empty just because nobody typed the outcomes in.
            key = f"{code} — {wording}" if code and wording else code or wording
            if key:
                marks_by_outcome[key] = marks_by_outcome.get(key, 0) + marks
            else:
                unmapped += marks
        return CourseOutcomeCoverage(
            marks_by_outcome=marks_by_outcome,
            unmapped_marks=unmapped,
            total_marks=total,
        )

    @staticmethod
    def _summarize_bloom(questions: list[ValidatedQuestion]) -> BloomSummary:
        requested: dict[str, int] = {}
        observed: dict[str, int] = {}
        deviations = 0
        unverified = 0
        for question in questions:
            asked = question.candidate.bloom_level
            requested[asked.value] = requested.get(asked.value, 0) + 1
            actual = question.observed_bloom_level
            if actual is None:
                unverified += 1
                actual = asked
            elif actual != asked:
                deviations += 1
            observed[actual.value] = observed.get(actual.value, 0) + 1
        return BloomSummary(
            requested=requested,
            observed=observed,
            deviations=deviations,
            total=len(questions),
            unverified=unverified,
        )


def normalize_artifact_path(path: str | Path) -> str:
    return str(Path(path).resolve())
