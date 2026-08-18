import asyncio

from question_paper_gen.ai import (
    SemanticReview,
    SectionQuestionBatch,
    SectionQuestionReview,
    SectionReviewBatch,
)
from question_paper_gen.blueprints import BlueprintBuilder
from question_paper_gen.models import (
    BloomLevel,
    ContentMap,
    DocumentManifest,
    DocumentQuality,
    MarkingCriterion,
    PageContent,
    QuestionCandidate,
    SourceEvidence,
    Topic,
    ValidatedQuestion,
)
from question_paper_gen.patterns import default_college_pattern
from question_paper_gen.pipeline import PaperGenerationPipeline


class FakeAnalyzer:
    def __init__(self) -> None:
        self.generation_calls = 0
        self.review_calls = 0
        self.repair_calls = 0
        self.reviewed_question_counts: list[int] = []

    async def generate_section(
        self,
        *,
        section_id: str,
        expected_question_count: int,
        slots_prompt: str,
        evidence_text: str,
        visual_paths: list[tuple[str, str]],
    ) -> SectionQuestionBatch:
        import json

        self.generation_calls += 1
        slots = json.loads(slots_prompt)
        def unique_focus(slot: dict[str, object]) -> str:
            import hashlib

            return " ".join(
                hashlib.sha256(
                    f"{slot['slot_id']}-{index}".encode("utf-8")
                ).hexdigest()[:12]
                for index in range(20)
            )

        def answer_text(slot: dict[str, object]) -> str:
            if slot["question_kind"] in {"multiple_choice", "assertion_reason"}:
                return "Option A is supported by the supplied source."
            return "Answer grounded in the supplied source."

        def question_text(slot: dict[str, object]) -> str:
            if slot["question_kind"] == "multiple_choice":
                stem = (
                    "Analyze which grounded source statement is best supported"
                    if slot["bloom_level"] == "analyze"
                    else "Which grounded source statement is best supported"
                )
                return (
                    f"{stem} for the distinct {unique_focus(slot)} concept?\n"
                    "(A) First\n(B) Second\n(C) Third\n(D) Fourth"
                )
            if slot["question_kind"] == "assertion_reason":
                return (
                    f"Assertion (A): The grounded {unique_focus(slot)} source statement "
                    "is true.\n"
                    f"Reason (R): The source directly supports the {unique_focus(slot)} "
                    "statement.\n"
                    "(A) Both Assertion (A) and Reason (R) are true and Reason (R) "
                    "is the correct explanation of Assertion (A).\n"
                    "(B) Both Assertion (A) and Reason (R) are true, but Reason (R) "
                    "is not the correct explanation of Assertion (A).\n"
                    "(C) Assertion (A) is true, but Reason (R) is false.\n"
                    "(D) Assertion (A) is false, but Reason (R) is true."
                )
            if slot["question_kind"] == "case_study":
                return (
                    f"Case scenario {unique_focus(slot)}: A school database team is "
                    "reorganising student records before a new academic year. The "
                    "supplied dataset contains repeated student, course, and teacher "
                    "details. The team must improve the design while preserving all "
                    "dependencies, preventing inconsistent updates, and retaining the "
                    "relationships needed for reports.\n"
                    "(i) Identify one repeated student detail in the records.\n"
                    "(ii) Analyze how a dependency can cause inconsistent student records.\n"
                    "(iii) (a) Evaluate and justify a design that reduces record duplication.\n"
                    "OR\n"
                    "(iii) (b) Compare two student-record designs and recommend the one "
                    "that better preserves dependencies."
                )
            bloom = str(slot["bloom_level"])
            section_concept = {
                "section_b": "relation keys and dependency rules",
                "section_c": "normal-form decomposition and lossless joins",
                "section_d": "schema design trade-offs and integrity constraints",
            }[str(slot["section_id"])]
            prompt = {
                "remember": "Define the source concept",
                "understand": "Explain the source concept",
                "apply": "Apply the source method to solve a grounded problem",
                "analyze": "Analyze how the source components relate and explain the result",
                "evaluate": "Evaluate the source approach and justify a reasoned judgment",
                "create": (
                    "Design and formulate a source-grounded model, define its constraints, "
                    "and explain why the proposed structure satisfies them"
                ),
            }[bloom]
            base = (
                f"{prompt} about {section_concept} with the distinct "
                f"{unique_focus(slot)} focus"
            )
            if int(slot["marks"]) >= 5:
                base += (
                    ", showing each reasoning step and explaining how the conclusion "
                    "follows from the supplied academic evidence"
                )
            if slot["has_internal_choice"]:
                return (
                    f"{base} using the first source example.\nOR\n"
                    f"{base} using the second source example."
                )
            return base

        return SectionQuestionBatch(
            questions=[
                QuestionCandidate(
                    candidate_id=f"{slot['slot_id']}-temporary",
                    slot_id=slot["slot_id"],
                    question_text=question_text(slot),
                    answer=answer_text(slot),
                    marks=slot["marks"],
                    bloom_level=slot["bloom_level"],
                    bloom_justification=(
                        "The task requires the configured cognitive process."
                    ),
                    marking_scheme=[
                        MarkingCriterion(
                            criterion="Complete correct response",
                            marks=slot["marks"],
                        )
                    ],
                    evidence=SourceEvidence(
                        page_numbers=[1],
                        excerpts=["grounded source chapter"],
                    ),
                    confidence=0.95,
                )
                for slot in slots
            ]
        )

    async def review_section(
        self,
        *,
        section_id: str,
        slots_prompt: str,
        questions: list[QuestionCandidate],
        evidence_text: str,
        visual_paths: list[tuple[str, str]],
    ) -> SectionReviewBatch:
        self.review_calls += 1
        self.reviewed_question_counts.append(len(questions))
        return SectionReviewBatch(
            reviews=[
                SectionQuestionReview(
                    candidate_id=question.candidate_id,
                    grounded_in_evidence=True,
                    answer_correct=True,
                    bloom_level_correct=True,
                    wording_clear=True,
                    visual_consistent=True,
                    visual_necessary=False,
                    subject_accuracy=True,
                    difficulty_appropriate=True,
                    marking_scheme_valid=True,
                    options_valid=True,
                    internal_choice_valid=True,
                    pedagogical_quality=True,
                    quality_score=100,
                    confidence=0.95,
                )
                for question in questions
            ]
        )


class ConcurrentFakeAnalyzer(FakeAnalyzer):
    def __init__(self) -> None:
        super().__init__()
        self.active_generation_calls = 0
        self.maximum_generation_concurrency = 0

    async def generate_section(self, **kwargs: object) -> SectionQuestionBatch:
        self.active_generation_calls += 1
        self.maximum_generation_concurrency = max(
            self.maximum_generation_concurrency,
            self.active_generation_calls,
        )
        try:
            await asyncio.sleep(0.01)
            return await super().generate_section(**kwargs)
        finally:
            self.active_generation_calls -= 1


class RepairingFakeAnalyzer(FakeAnalyzer):
    def __init__(self) -> None:
        super().__init__()
        self.question_review_calls = 0

    async def review_section(
        self,
        *,
        section_id: str,
        slots_prompt: str,
        questions: list[QuestionCandidate],
        evidence_text: str,
        visual_paths: list[tuple[str, str]],
    ) -> SectionReviewBatch:
        self.review_calls += 1
        self.reviewed_question_counts.append(len(questions))
        return SectionReviewBatch(
            reviews=[
                SectionQuestionReview(
                    candidate_id=question.candidate_id,
                    grounded_in_evidence=(
                        self.review_calls > 1 or index != 0
                    ),
                    answer_correct=True,
                    bloom_level_correct=True,
                    wording_clear=True,
                    visual_consistent=True,
                    visual_necessary=False,
                    subject_accuracy=True,
                    difficulty_appropriate=True,
                    marking_scheme_valid=True,
                    options_valid=True,
                    internal_choice_valid=True,
                    pedagogical_quality=True,
                    quality_score=100,
                    confidence=0.95,
                    reasons=(
                        ["First draft needs source repair"]
                        if self.review_calls == 1 and index == 0
                        else []
                    ),
                )
                for index, question in enumerate(questions)
            ]
        )

    async def repair_questions(
        self,
        *,
        repair_prompt: str,
        **_: object,
    ) -> SectionQuestionBatch:
        import json

        self.repair_calls += 1
        slot = json.loads(repair_prompt)["locked_slots"][0]
        return SectionQuestionBatch(
            questions=[
                QuestionCandidate(
                    candidate_id="repaired",
                    slot_id=slot["slot_id"],
                    question_text=(
                        "Which response is grounded?\n"
                        "(A) First\n(B) Second\n(C) Third\n(D) Fourth"
                    ),
                    answer="Option (A).",
                    marks=slot["marks"],
                    bloom_level=slot["bloom_level"],
                    bloom_justification="The learner recalls source material.",
                    marking_scheme=[
                        MarkingCriterion(
                            criterion="Correct option",
                            marks=slot["marks"],
                        )
                    ],
                    evidence=SourceEvidence(
                        page_numbers=[1],
                        excerpts=["grounded source chapter"],
                    ),
                    confidence=0.95,
                )
            ]
        )

    async def review_question(
        self,
        **_: object,
    ) -> SemanticReview:
        self.question_review_calls += 1
        return SemanticReview(
            grounded_in_evidence=True,
            answer_correct=True,
            bloom_level_correct=True,
            wording_clear=True,
            visual_consistent=True,
            visual_necessary=True,
            subject_accuracy=True,
            difficulty_appropriate=True,
            marking_scheme_valid=True,
            options_valid=True,
            internal_choice_valid=True,
            pedagogical_quality=True,
            quality_score=100,
            confidence=0.95,
        )


class RetryingRepairAnalyzer(RepairingFakeAnalyzer):
    async def review_question(self, **_: object) -> SemanticReview:
        self.question_review_calls += 1
        return SemanticReview(
            grounded_in_evidence=True,
            answer_correct=True,
            bloom_level_correct=True,
            wording_clear=True,
            visual_consistent=True,
            visual_necessary=True,
            subject_accuracy=True,
            difficulty_appropriate=True,
            marking_scheme_valid=True,
            options_valid=True,
            internal_choice_valid=True,
            pedagogical_quality=True,
            quality_score=80 if self.question_review_calls == 1 else 100,
            confidence=0.95,
        )

def test_pipeline_produces_review_required_80_mark_draft() -> None:
    manifest = DocumentManifest(
        document_id="doc",
        original_filename="notes.pdf",
        sha256="a" * 64,
        source_pdf_path="/tmp/source.pdf",
        artifact_directory="/tmp/artifacts",
        pages=[
            PageContent(
                page_number=1,
                width=600,
                height=800,
                text="A grounded source chapter with sufficient academic content.",
                rendered_image_path="/tmp/page.png",
            )
        ],
        visual_assets=[],
        quality=DocumentQuality(
            passed=True,
            page_count=1,
            text_character_count=100,
        ),
    )
    content = ContentMap(
        subject="Database Systems",
        topics=[
            Topic(
                topic_id="normalization",
                name="Normalization",
                unit="1",
                source_pages=[1],
                supported_bloom_levels=list(BloomLevel),
            ),
            Topic(
                topic_id="keys",
                name="Relation keys",
                unit="1",
                source_pages=[1],
                supported_bloom_levels=list(BloomLevel),
            ),
            Topic(
                topic_id="indexing",
                name="Indexing",
                unit="2",
                source_pages=[1],
                supported_bloom_levels=list(BloomLevel),
            ),
            Topic(
                topic_id="transactions",
                name="Transactions",
                unit="2",
                source_pages=[1],
                supported_bloom_levels=list(BloomLevel),
            ),
        ],
    )
    pattern = default_college_pattern()
    blueprint = BlueprintBuilder().build(pattern, content, manifest)

    analyzer = ConcurrentFakeAnalyzer()
    paper = asyncio.run(
        PaperGenerationPipeline(
            analyzer,
            request_interval_seconds=0,
        ).generate(
            pattern=pattern,
            content_map=content,
            manifest=manifest,
            blueprint=blueprint,
        )
    )

    assert len(paper.questions) == 38
    assert sum(question.candidate.marks for question in paper.questions) == 80
    assert all(question.accepted for question in paper.questions)
    assert paper.publication_ready
    assert paper.requires_human_approval
    assert paper.publication_ready
    assert paper.subject_family == "computing"
    assert all(question.quality_score == 100 for question in paper.questions)
    assert analyzer.generation_calls == 5
    assert analyzer.maximum_generation_concurrency == 5
    assert analyzer.review_calls == 5
    assert sorted(analyzer.reviewed_question_counts) == [3, 4, 5, 6, 20]


def test_pipeline_repairs_and_rereviews_rejected_questions() -> None:
    manifest = DocumentManifest(
        document_id="doc",
        original_filename="notes.pdf",
        sha256="a" * 64,
        source_pdf_path="/tmp/source.pdf",
        artifact_directory="/tmp/artifacts",
        pages=[
            PageContent(
                page_number=1,
                width=600,
                height=800,
                text="A grounded source chapter with sufficient academic content.",
                rendered_image_path="/tmp/page.png",
            )
        ],
        visual_assets=[],
        quality=DocumentQuality(
            passed=True,
            page_count=1,
            text_character_count=100,
        ),
    )
    content = ContentMap(
        subject="Database Systems",
        topics=[
            Topic(
                topic_id="normalization",
                name="Normalization",
                unit="1",
                source_pages=[1],
                supported_bloom_levels=list(BloomLevel),
            ),
            Topic(
                topic_id="keys",
                name="Relation keys",
                unit="1",
                source_pages=[1],
                supported_bloom_levels=list(BloomLevel),
            ),
            Topic(
                topic_id="indexing",
                name="Indexing",
                unit="2",
                source_pages=[1],
                supported_bloom_levels=list(BloomLevel),
            ),
            Topic(
                topic_id="transactions",
                name="Transactions",
                unit="2",
                source_pages=[1],
                supported_bloom_levels=list(BloomLevel),
            ),
        ],
    )
    pattern = default_college_pattern()
    blueprint = BlueprintBuilder().build(pattern, content, manifest)
    analyzer = RepairingFakeAnalyzer()

    paper = asyncio.run(
        PaperGenerationPipeline(
            analyzer,
            request_interval_seconds=0,
        ).generate(
            pattern=pattern,
            content_map=content,
            manifest=manifest,
            blueprint=blueprint,
        )
    )

    assert all(question.accepted for question in paper.questions)
    assert analyzer.generation_calls == 5
    assert analyzer.repair_calls == 1
    assert analyzer.question_review_calls == 1
    assert analyzer.review_calls == 5
    assert sum(analyzer.reviewed_question_counts) == 38


def test_pipeline_retries_an_individual_question_when_repair_score_is_low() -> None:
    manifest = DocumentManifest(
        document_id="doc",
        original_filename="notes.pdf",
        sha256="a" * 64,
        source_pdf_path="/tmp/source.pdf",
        artifact_directory="/tmp/artifacts",
        pages=[
            PageContent(
                page_number=1,
                width=600,
                height=800,
                text="A grounded source chapter with sufficient academic content.",
                rendered_image_path="/tmp/page.png",
            )
        ],
        visual_assets=[],
        quality=DocumentQuality(
            passed=True,
            page_count=1,
            text_character_count=100,
        ),
    )
    content = ContentMap(
        subject="Database Systems",
        topics=[
            Topic(
                topic_id="normalization",
                name="Normalization",
                unit="1",
                source_pages=[1],
                supported_bloom_levels=list(BloomLevel),
            ),
            Topic(
                topic_id="keys",
                name="Relation keys",
                unit="1",
                source_pages=[1],
                supported_bloom_levels=list(BloomLevel),
            ),
            Topic(
                topic_id="indexing",
                name="Indexing",
                unit="2",
                source_pages=[1],
                supported_bloom_levels=list(BloomLevel),
            ),
            Topic(
                topic_id="transactions",
                name="Transactions",
                unit="2",
                source_pages=[1],
                supported_bloom_levels=list(BloomLevel),
            ),
        ],
    )
    pattern = default_college_pattern()
    blueprint = BlueprintBuilder().build(pattern, content, manifest)
    analyzer = RetryingRepairAnalyzer()

    paper = asyncio.run(
        PaperGenerationPipeline(analyzer, request_interval_seconds=0).generate(
            pattern=pattern,
            content_map=content,
            manifest=manifest,
            blueprint=blueprint,
        )
    )

    assert paper.publication_ready
    assert analyzer.repair_calls == 2
    assert analyzer.question_review_calls == 2
    assert analyzer.review_calls == 5


def test_generated_text_cleanup_removes_internal_ids_and_common_latex() -> None:
    cleaned = PaperGenerationPipeline._clean_generated_text(
        (
            "Q3. Refer to Visual Asset p21-image-1 and calculate "
            "21 \\bmod 8.\\nUse \\phi and \\mu."
        ),
        remove_question_number=True,
    )

    assert cleaned == (
        "Refer to provided figure and calculate 21 mod 8.\nUse φ and μ."
    )


def test_generated_text_cleanup_preserves_readable_mathematics() -> None:
    cleaned = PaperGenerationPipeline._clean_generated_text(
        r"A=\begin{bmatrix}2 & 3 \\ 1 & 4\end{bmatrix}; "
        r"\frac{dy}{dt}=5-\frac{y}{40}; x+y u2264 45000; "
        r"t \to \infty; \tan\alpha=1; 45^\circ; **evaluate**."
    )

    assert "A=[2 3; 1 4]" in cleaned
    assert "dy/dt=5-y/40" in cleaned
    assert "x+y ≤ 45000" in cleaned
    assert "t → ∞" in cleaned
    assert "tan α=1" in cleaned
    assert "45°" in cleaned
    assert "evaluate" in cleaned
    assert "\\" not in cleaned
    assert "**" not in cleaned


def test_backend_canonicalizes_case_study_choice_labels() -> None:
    slot = _case_study_slot()
    generated = (
        "Case study with a substantive shared mathematical scenario.\n"
        "(i) Interpret the first fact.\n"
        "(ii) Apply the relationship.\n"
        "(iii)\nEither:\n(a) Analyze and justify the conclusion.\n"
        "or\n(b) Compare and justify the alternative."
    )

    normalized = PaperGenerationPipeline._normalize_question_format(slot, generated)

    assert "Either:" not in normalized
    assert "(iii)(a) Analyze" in normalized
    assert "\nOR\n(iii)(b) Compare" in normalized


def test_final_quality_score_below_threshold_is_advisory() -> None:
    candidate = QuestionCandidate(
        candidate_id="candidate",
        slot_id="slot",
        question_text="Define the supplied concept.",
        answer="A source-grounded definition.",
        marks=1,
        bloom_level=BloomLevel.REMEMBER,
        bloom_justification="This requires recall.",
        marking_scheme=[MarkingCriterion(criterion="Definition", marks=1)],
        evidence=SourceEvidence(
            page_numbers=[1], excerpts=["grounded source chapter"]
        ),
        confidence=0.95,
    )
    review = SectionQuestionReview(
        candidate_id="candidate",
        grounded_in_evidence=True,
        answer_correct=True,
        bloom_level_correct=True,
        wording_clear=True,
        subject_accuracy=True,
        difficulty_appropriate=True,
        marking_scheme_valid=True,
        options_valid=True,
        internal_choice_valid=True,
        pedagogical_quality=True,
        quality_score=80,
        confidence=0.95,
    )

    result = PaperGenerationPipeline(
        FakeAnalyzer(), request_interval_seconds=0
    )._apply_semantic_review(
        ValidatedQuestion(candidate=candidate, accepted=True),
        review,
    )

    assert result.accepted
    assert result.quality_score == 80
    assert "quality_score_below_threshold" in {
        finding.code for finding in result.findings
    }
    assert {
        finding.severity.value
        for finding in result.findings
        if finding.code == "quality_score_below_threshold"
    } == {"warning"}


def test_semantic_review_does_not_repeat_the_same_reason_for_every_failed_check() -> None:
    candidate = QuestionCandidate(
        candidate_id="candidate",
        slot_id="slot",
        question_text="Define the supplied concept.",
        answer="An unsupported answer.",
        marks=1,
        bloom_level=BloomLevel.REMEMBER,
        bloom_justification="This requires recall.",
        marking_scheme=[MarkingCriterion(criterion="Definition", marks=1)],
        evidence=SourceEvidence(page_numbers=[1], excerpts=["grounded source chapter"]),
        confidence=0.95,
    )
    review = SectionQuestionReview(
        candidate_id="candidate",
        grounded_in_evidence=False,
        answer_correct=False,
        bloom_level_correct=True,
        wording_clear=True,
        subject_accuracy=True,
        difficulty_appropriate=True,
        marking_scheme_valid=True,
        options_valid=True,
        internal_choice_valid=True,
        pedagogical_quality=True,
        quality_score=60,
        confidence=0.95,
        reasons=["The answer uses an unsupported theorem.", "The answer uses an unsupported theorem."],
    )

    result = PaperGenerationPipeline(
        FakeAnalyzer(), request_interval_seconds=0
    )._apply_semantic_review(
        ValidatedQuestion(candidate=candidate, accepted=True),
        review,
    )

    messages = [finding.message for finding in result.findings]
    assert messages.count("The answer uses an unsupported theorem.") == 1

def _case_study_slot() -> "BlueprintSlot":
    from question_paper_gen.models import BlueprintSlot, QuestionKind

    return BlueprintSlot(
        slot_id="section_e-1",
        question_number="36",
        section_id="section_e",
        marks=4,
        bloom_level=BloomLevel.APPLY,
        question_kind=QuestionKind.CASE_STUDY,
        topic_id="normalization",
        unit="1",
        has_internal_choice=True,
        internal_choice_scope="final_subpart",
    )


def test_unlabelled_case_study_alternatives_are_canonicalized() -> None:
    generated = (
        "A plant monitors chlorine concentration over a shift.\n"
        "(i) Evaluate the left-hand limit.\n"
        "(ii) Evaluate the right-hand limit.\n"
        "(iii) At t = 2, determine whether C(t) is continuous.\n"
        "OR\n"
        "At t = 6, analyse whether C(t) is continuous."
    )

    normalized = PaperGenerationPipeline._normalize_question_format(
        _case_study_slot(), generated
    )

    assert "(iii)(a) At t = 2" in normalized
    assert "\nOR\n(iii)(b) At t = 6" in normalized


def test_bare_letter_case_study_alternatives_are_canonicalized() -> None:
    generated = (
        "A surveying team measures the angle of elevation to a cliff top.\n"
        "(i) Calculate the angle of elevation.\n"
        "(ii) Show that tan(θ) = h/d.\n"
        "(iii) The team considers two measurement scenarios:\n"
        "(a) They move to a position farther away. Calculate the new angle.\n"
        "OR\n"
        "(iii)(b) They survey a taller cliff. Calculate the new angle."
    )

    normalized = PaperGenerationPipeline._normalize_question_format(
        _case_study_slot(), generated
    )

    assert "(iii)(a) They move" in normalized
    assert "(iii)(b) They survey" in normalized


def test_canonical_case_study_choice_text_is_unchanged() -> None:
    generated = (
        "A study of sensor data over a shift.\n"
        "(i) Interpret the first reading.\n"
        "(ii) Apply the threshold rule.\n"
        "(iii)(a) Analyze the trend and justify a conclusion.\n"
        "OR\n"
        "(iii)(b) Compare the readings and justify the most reliable one."
    )

    normalized = PaperGenerationPipeline._normalize_question_format(
        _case_study_slot(), generated
    )

    assert normalized == generated


def test_positive_reviewer_notes_are_dropped_from_finding_messages() -> None:
    candidate = QuestionCandidate(
        candidate_id="candidate",
        slot_id="slot",
        question_text="Define the supplied concept.",
        answer="An unsupported answer.",
        marks=1,
        bloom_level=BloomLevel.REMEMBER,
        bloom_justification="This requires recall.",
        marking_scheme=[MarkingCriterion(criterion="Definition", marks=1)],
        evidence=SourceEvidence(page_numbers=[1], excerpts=["grounded source chapter"]),
        confidence=0.95,
    )
    review = SectionQuestionReview(
        candidate_id="candidate",
        grounded_in_evidence=False,
        answer_correct=True,
        bloom_level_correct=True,
        wording_clear=True,
        subject_accuracy=True,
        difficulty_appropriate=True,
        marking_scheme_valid=True,
        options_valid=True,
        internal_choice_valid=True,
        pedagogical_quality=True,
        quality_score=60,
        confidence=0.95,
        reasons=[
            "ANSWER VERIFICATION: Correct. dV/dt = 10π follows from the formula.",
            "MARKING SCHEME: Appropriate and complete.",
            "PEDAGOGICAL QUALITY: Good context and realistic values.",
            "The tested theorem is absent from the permitted evidence.",
        ],
    )

    result = PaperGenerationPipeline(
        FakeAnalyzer(), request_interval_seconds=0
    )._apply_semantic_review(
        ValidatedQuestion(candidate=candidate, accepted=True),
        review,
    )

    messages = " ".join(finding.message for finding in result.findings)
    assert "The tested theorem is absent from the permitted evidence." in messages
    assert "ANSWER VERIFICATION" not in messages
    assert "MARKING SCHEME" not in messages
    assert "PEDAGOGICAL QUALITY" not in messages

class FacetEscalationAnalyzer(RepairingFakeAnalyzer):
    """Keeps rejecting repairs until the third attempt, capturing payloads."""

    def __init__(self) -> None:
        super().__init__()
        self.repair_payloads: list[dict] = []

    async def repair_questions(self, *, repair_prompt: str, **kwargs: object):
        import json

        self.repair_payloads.append(json.loads(repair_prompt))
        return await super().repair_questions(repair_prompt=repair_prompt, **kwargs)

    async def review_question(self, **_: object) -> SemanticReview:
        self.question_review_calls += 1
        return SemanticReview(
            grounded_in_evidence=True,
            answer_correct=True,
            bloom_level_correct=True,
            wording_clear=True,
            visual_consistent=True,
            visual_necessary=True,
            subject_accuracy=True,
            difficulty_appropriate=True,
            marking_scheme_valid=True,
            options_valid=True,
            internal_choice_valid=True,
            pedagogical_quality=True,
            quality_score=80 if self.question_review_calls <= 2 else 100,
            confidence=0.95,
        )


def test_repair_ladder_swaps_facet_on_third_attempt() -> None:
    manifest = DocumentManifest(
        document_id="doc",
        original_filename="notes.pdf",
        sha256="a" * 64,
        source_pdf_path="/tmp/source.pdf",
        artifact_directory="/tmp/artifacts",
        pages=[
            PageContent(
                page_number=1,
                width=600,
                height=800,
                text="A grounded source chapter with sufficient academic content.",
                rendered_image_path="/tmp/page.png",
            )
        ],
        visual_assets=[],
        quality=DocumentQuality(
            passed=True,
            page_count=1,
            text_character_count=100,
        ),
    )
    content = ContentMap(
        subject="Database Systems",
        topics=[
            Topic(
                topic_id="normalization",
                name="Normalization",
                unit="1",
                source_pages=[1],
                supported_bloom_levels=list(BloomLevel),
            ),
            Topic(
                topic_id="keys",
                name="Relation keys",
                unit="1",
                source_pages=[1],
                supported_bloom_levels=list(BloomLevel),
            ),
            Topic(
                topic_id="indexing",
                name="Indexing",
                unit="2",
                source_pages=[1],
                supported_bloom_levels=list(BloomLevel),
            ),
            Topic(
                topic_id="transactions",
                name="Transactions",
                unit="2",
                source_pages=[1],
                supported_bloom_levels=list(BloomLevel),
            ),
        ],
    )
    pattern = default_college_pattern()
    blueprint = BlueprintBuilder().build(pattern, content, manifest)
    analyzer = FacetEscalationAnalyzer()

    asyncio.run(
        PaperGenerationPipeline(analyzer, request_interval_seconds=0).generate(
            pattern=pattern,
            content_map=content,
            manifest=manifest,
            blueprint=blueprint,
        )
    )

    assert analyzer.repair_calls == 3
    first_facet = analyzer.repair_payloads[0]["locked_slots"][0]["facet"]
    third_facet = analyzer.repair_payloads[2]["locked_slots"][0]["facet"]
    assert first_facet != third_facet


def test_option_a_b_labels_are_normalized_to_or_layout() -> None:
    from question_paper_gen.models import BlueprintSlot, QuestionKind

    slot = BlueprintSlot(
        slot_id="section_d-3",
        question_number="34",
        section_id="section_d",
        marks=5,
        bloom_level=BloomLevel.APPLY,
        question_kind=QuestionKind.LONG_ANSWER,
        topic_id="normalization",
        unit="1",
        has_internal_choice=True,
    )
    generated = (
        "Option A: Solve the first grounded task and justify each step.\n"
        "Option B: Solve the second grounded task and justify each step."
    )

    normalized = PaperGenerationPipeline._normalize_question_format(slot, generated)

    assert "Option A" not in normalized
    assert "Option B" not in normalized
    assert "\nOR\n" in normalized


def test_pipe_matrices_are_collapsed_to_inline_brackets() -> None:
    cleaned = PaperGenerationPipeline._clean_generated_text(
        "For the matrix A = |3  5|\n|2  7|, find det(A). Note that |A| = 11\n"
        "|B| = 4 are the determinant values."
    )

    assert "[3 5; 2 7]" in cleaned
    assert "|A| = 11" in cleaned
    assert "|B| = 4" in cleaned

def test_paper_question_numbers_follow_blueprint_order() -> None:
    manifest = DocumentManifest(
        document_id="doc",
        original_filename="notes.pdf",
        sha256="a" * 64,
        source_pdf_path="/tmp/source.pdf",
        artifact_directory="/tmp/artifacts",
        pages=[
            PageContent(
                page_number=1,
                width=600,
                height=800,
                text="A grounded source chapter with sufficient academic content.",
                rendered_image_path="/tmp/page.png",
            )
        ],
        visual_assets=[],
        quality=DocumentQuality(
            passed=True,
            page_count=1,
            text_character_count=100,
        ),
    )
    content = ContentMap(
        subject="Database Systems",
        topics=[
            Topic(
                topic_id=f"topic-{index}",
                name=f"Topic {index}",
                unit="1",
                source_pages=[1],
                supported_bloom_levels=list(BloomLevel),
            )
            for index in range(1, 5)
        ],
    )
    pattern = default_college_pattern()
    blueprint = BlueprintBuilder().build(pattern, content, manifest)

    paper = asyncio.run(
        PaperGenerationPipeline(
            ConcurrentFakeAnalyzer(), request_interval_seconds=0
        ).generate(
            pattern=pattern,
            content_map=content,
            manifest=manifest,
            blueprint=blueprint,
        )
    )

    assert [q.candidate.slot_id for q in paper.questions] == [
        slot.slot_id for slot in blueprint.slots
    ]
    from question_paper_gen.models import GeneratedQuestionPaper

    public = GeneratedQuestionPaper.from_internal(paper, blueprint)
    assert [item.question_number for item in public.questions] == [
        str(number) for number in range(1, 39)
    ]


def test_inline_or_option_labels_are_canonicalized() -> None:
    generated = (
        "A tank is being filled at a controlled rate with recorded readings.\n"
        "(i) Find the rate of change of volume. (1 mark)\n"
        "(ii) At what time does the rate equal 12? (1 mark)\n"
        "(iii) OR Option (a): Find the rate at which the height rises. (2 marks)\n"
        "OR Option (b): Determine the safe operating interval. (2 marks)"
    )

    normalized = PaperGenerationPipeline._normalize_question_format(
        _case_study_slot(), generated
    )

    assert "(iii)(a) Find the rate" in normalized
    assert "\nOR\n(iii)(b) Determine the safe" in normalized
    assert "Option" not in normalized
