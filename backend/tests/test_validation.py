from question_paper_gen.models import (
    BloomLevel,
    BlueprintSlot,
    DocumentManifest,
    DocumentQuality,
    MarkingCriterion,
    PageContent,
    QuestionCandidate,
    QuestionKind,
    SourceEvidence,
)
from question_paper_gen.validation import QuestionValidator, find_duplicate_questions


def _manifest() -> DocumentManifest:
    return DocumentManifest(
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
                text="Normalization source.",
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


def _slot() -> BlueprintSlot:
    return BlueprintSlot(
        slot_id="short-1",
        question_number="1",
        section_id="short",
        marks=2,
        bloom_level=BloomLevel.REMEMBER,
        question_kind=QuestionKind.SHORT_ANSWER,
        topic_id="normalization",
        unit="1",
    )


def test_valid_candidate_passes_deterministic_gates() -> None:
    candidate = QuestionCandidate(
        candidate_id="q1",
        slot_id="short-1",
        question_text="Define database normalization.",
        answer="Normalization organizes relations to reduce redundancy.",
        marks=2,
        bloom_level=BloomLevel.REMEMBER,
        bloom_justification="The learner recalls a definition.",
        marking_scheme=[MarkingCriterion(criterion="Correct definition", marks=2)],
        evidence=SourceEvidence(
            page_numbers=[1],
            excerpts=["Normalization source."],
        ),
        confidence=0.90,
    )

    result = QuestionValidator().validate(_slot(), candidate, _manifest())

    assert result.accepted
    assert result.findings == []


def test_two_mark_question_with_labelled_subparts_is_rejected() -> None:
    candidate = QuestionCandidate(
        candidate_id="q1",
        slot_id="short-1",
        question_text="(i) Define normalization.\n(ii) State one advantage.",
        answer="Normalization reduces redundancy and improves consistency.",
        marks=2,
        bloom_level=BloomLevel.REMEMBER,
        bloom_justification="Recall.",
        marking_scheme=[MarkingCriterion(criterion="Complete response", marks=2)],
        evidence=SourceEvidence(page_numbers=[1], excerpts=["Normalization source."]),
        confidence=0.90,
        estimated_answer_minutes=2,
    )

    result = QuestionValidator().validate(_slot(), candidate, _manifest())

    assert "short_question_has_subparts" in {
        finding.code for finding in result.findings
    }


def test_long_answer_reports_weak_scheme_answer_and_time_estimate() -> None:
    slot = _slot().model_copy(update={"marks": 10})
    candidate = QuestionCandidate(
        candidate_id="q1",
        slot_id=slot.slot_id,
        question_text=(
            "Analyze the normalization process and justify the selected decomposition "
            "by showing the required dependency-preservation reasoning steps."
        ),
        answer="A short answer.",
        marks=10,
        bloom_level=slot.bloom_level,
        bloom_justification="Recall.",
        marking_scheme=[MarkingCriterion(criterion="Complete response", marks=10)],
        evidence=SourceEvidence(page_numbers=[1], excerpts=["Normalization source."]),
        confidence=0.90,
        estimated_answer_minutes=2,
    )

    result = QuestionValidator().validate(slot, candidate, _manifest())
    codes = {finding.code for finding in result.findings}

    assert result.accepted
    assert {
        "rubric_lacks_granularity",
        "answer_too_brief_for_marks",
        "answer_time_mismatch",
    }.issubset(codes)


def test_duplicate_marking_criteria_are_rejected() -> None:
    candidate = QuestionCandidate(
        candidate_id="q1",
        slot_id="short-1",
        question_text="Define database normalization.",
        answer="Normalization organizes data to reduce redundancy.",
        marks=2,
        bloom_level=BloomLevel.REMEMBER,
        bloom_justification="Recall.",
        marking_scheme=[
            MarkingCriterion(criterion="Correct definition", marks=1),
            MarkingCriterion(criterion="Correct definition", marks=1),
        ],
        evidence=SourceEvidence(page_numbers=[1], excerpts=["Normalization source."]),
        confidence=0.90,
    )

    result = QuestionValidator().validate(_slot(), candidate, _manifest())

    assert not result.accepted
    assert "duplicate_marking_criteria" in {
        finding.code for finding in result.findings
    }


def test_unrendered_student_notation_is_rejected() -> None:
    candidate = QuestionCandidate(
        candidate_id="q1",
        slot_id="short-1",
        question_text=r"Solve x + y u2264 10 using \begin{pmatrix}1 & 2\end{pmatrix}.",
        answer="A verified result.",
        marks=2,
        bloom_level=BloomLevel.REMEMBER,
        bloom_justification="Recall.",
        marking_scheme=[MarkingCriterion(criterion="Answer", marks=2)],
        evidence=SourceEvidence(page_numbers=[1], excerpts=["Normalization source."]),
        confidence=0.90,
    )

    result = QuestionValidator().validate(_slot(), candidate, _manifest())

    assert "malformed_student_notation" in {
        finding.code for finding in result.findings
    }


def test_wrong_marks_and_low_confidence_are_rejected() -> None:
    candidate = QuestionCandidate(
        candidate_id="q1",
        slot_id="short-1",
        question_text="Define database normalization.",
        answer="An uncertain answer.",
        marks=3,
        bloom_level=BloomLevel.REMEMBER,
        bloom_justification="Recall.",
        marking_scheme=[MarkingCriterion(criterion="Definition", marks=3)],
        evidence=SourceEvidence(page_numbers=[1], excerpts=["Normalization source."]),
        confidence=0.50,
    )

    result = QuestionValidator().validate(_slot(), candidate, _manifest())

    assert not result.accepted
    assert {finding.code for finding in result.findings} == {
        "marks_mismatch",
        "low_confidence",
    }


def test_lowercase_mcq_options_are_accepted() -> None:
    slot = _slot().model_copy(
        update={
            "question_kind": QuestionKind.MULTIPLE_CHOICE,
            "marks": 1,
        }
    )
    candidate = QuestionCandidate(
        candidate_id="q1",
        slot_id=slot.slot_id,
        question_text=(
            "What is normalization?\n"
            "(a) Organization\n(b) Duplication\n(c) Encryption\n(d) Sorting"
        ),
        answer="Option (a).",
        marks=1,
        bloom_level=slot.bloom_level,
        bloom_justification="Recall.",
        marking_scheme=[MarkingCriterion(criterion="Correct option", marks=1)],
        evidence=SourceEvidence(
            page_numbers=[1],
            excerpts=["Normalization source."],
        ),
        confidence=0.90,
    )

    result = QuestionValidator().validate(slot, candidate, _manifest())

    assert result.accepted


def test_non_mcq_with_four_options_is_rejected() -> None:
    candidate = QuestionCandidate(
        candidate_id="q1",
        slot_id="short-1",
        question_text="Choose one.\nA) One\nB) Two\nC) Three\nD) Four",
        answer="One.",
        marks=2,
        bloom_level=BloomLevel.REMEMBER,
        bloom_justification="Recall.",
        marking_scheme=[MarkingCriterion(criterion="Answer", marks=2)],
        evidence=SourceEvidence(
            page_numbers=[1], excerpts=["Normalization source."]
        ),
        confidence=0.90,
    )

    result = QuestionValidator().validate(_slot(), candidate, _manifest())

    assert not result.accepted
    assert "unexpected_mcq_format" in {
        finding.code for finding in result.findings
    }


def test_mcq_plus_and_minus_options_are_not_treated_as_duplicates() -> None:
    slot = _slot().model_copy(
        update={"question_kind": QuestionKind.MULTIPLE_CHOICE, "marks": 1}
    )
    candidate = QuestionCandidate(
        candidate_id="q1",
        slot_id=slot.slot_id,
        question_text=(
            "What is the downstream speed?\n"
            "(A) Boat speed + stream speed\n"
            "(B) Boat speed - stream speed\n"
            "(C) Boat speed × stream speed\n"
            "(D) Boat speed ÷ stream speed"
        ),
        answer="Option A.",
        marks=1,
        bloom_level=slot.bloom_level,
        bloom_justification="Recall.",
        marking_scheme=[MarkingCriterion(criterion="Correct option", marks=1)],
        evidence=SourceEvidence(
            page_numbers=[1], excerpts=["Normalization source."]
        ),
        confidence=0.90,
    )

    result = QuestionValidator().validate(slot, candidate, _manifest())

    assert "duplicate_mcq_options" not in {
        finding.code for finding in result.findings
    }


def test_long_answer_subparts_are_not_treated_as_mcq_options() -> None:
    slot = _slot().model_copy(
        update={
            "marks": 5,
            "bloom_level": BloomLevel.CREATE,
            "question_kind": QuestionKind.LONG_ANSWER,
            "has_internal_choice": True,
            "choices_per_question": 2,
        }
    )
    text = (
        "(a) Design a grounded model with constraints and compute its first result.\n"
        "(b) Construct the related inequality and explain why its direction changes.\n"
        "(c) Analyze the model's assumptions and justify the selected constraints.\n"
        "(d) Evaluate the final result against the supplied source conditions.\n"
        "OR\n"
        "(a) Formulate an alternative model using the supplied source constraints.\n"
        "(b) Develop its result and explain why the proposed design is valid.\n"
        "(c) Analyze the alternative assumptions and justify the constraints.\n"
        "(d) Evaluate the alternative result against the source conditions."
    )
    candidate = QuestionCandidate(
        candidate_id="q1",
        slot_id=slot.slot_id,
        question_text=text,
        answer="A complete source-grounded construction.",
        marks=5,
        bloom_level=slot.bloom_level,
        bloom_justification="The learner creates a constrained model.",
        marking_scheme=[MarkingCriterion(criterion="Complete model", marks=5)],
        evidence=SourceEvidence(
            page_numbers=[1], excerpts=["Normalization source."]
        ),
        confidence=0.90,
    )

    result = QuestionValidator().validate(slot, candidate, _manifest())

    assert "unexpected_mcq_format" not in {
        finding.code for finding in result.findings
    }


def test_one_step_five_mark_alternative_is_rejected() -> None:
    slot = _slot().model_copy(
        update={
            "marks": 5,
            "bloom_level": BloomLevel.EVALUATE,
            "question_kind": QuestionKind.LONG_ANSWER,
            "has_internal_choice": True,
            "choices_per_question": 2,
        }
    )
    candidate = QuestionCandidate(
        candidate_id="q1",
        slot_id=slot.slot_id,
        question_text=(
            "(a) Find the remainder when 226 multiplied by 369 is divided by 8.\n"
            "OR\n"
            "(b) Evaluate the modular result and verify every step using the "
            "supplied rules."
        ),
        answer="A complete calculation.",
        marks=5,
        bloom_level=slot.bloom_level,
        bloom_justification="Evaluation.",
        marking_scheme=[MarkingCriterion(criterion="Working and result", marks=5)],
        evidence=SourceEvidence(
            page_numbers=[1], excerpts=["Normalization source."]
        ),
        confidence=0.90,
    )

    result = QuestionValidator().validate(slot, candidate, _manifest())

    assert "insufficient_mark_demand" in {
        finding.code for finding in result.findings
    }
    assert result.accepted


def test_semantically_similar_questions_are_detected() -> None:
    candidates = []
    for candidate_id, text in (
        (
            "q1",
            "Two runners complete a 100 metre race in 36 and 48 seconds. By how many metres does the first runner win?",
        ),
        (
            "q2",
            "Two runners complete a 100 metre race in 36 and 48 seconds. By how many metres does the first runner defeat the second?",
        ),
    ):
        candidate = QuestionCandidate(
            candidate_id=candidate_id,
            slot_id="short-1",
            question_text=text,
            answer="25 metres.",
            marks=2,
            bloom_level=BloomLevel.REMEMBER,
            bloom_justification="Recall.",
            marking_scheme=[MarkingCriterion(criterion="Answer", marks=2)],
            evidence=SourceEvidence(
                page_numbers=[1], excerpts=["Normalization source."]
            ),
            confidence=0.90,
        )
        candidates.append(
            QuestionValidator().validate(_slot(), candidate, _manifest())
        )

    duplicates = find_duplicate_questions(candidates)

    assert any(set(ids) == {"q1", "q2"} for ids in duplicates.values())


def test_same_problem_with_only_changed_values_is_detected() -> None:
    candidates = []
    for candidate_id, text in (
        (
            "q1",
            "Two runners complete a 100 metre race in 36 and 48 seconds. "
            "By how many metres does the first runner win?",
        ),
        (
            "q2",
            "Two runners complete a 120 metre race in 30 and 45 seconds. "
            "By how many metres does the first runner win?",
        ),
    ):
        candidate = QuestionCandidate(
            candidate_id=candidate_id,
            slot_id="short-1",
            question_text=text,
            answer="A verified result.",
            marks=2,
            bloom_level=BloomLevel.REMEMBER,
            bloom_justification="The learner applies the source-supported method.",
            marking_scheme=[MarkingCriterion(criterion="Answer", marks=2)],
            evidence=SourceEvidence(
                page_numbers=[1], excerpts=["Normalization source."]
            ),
            confidence=0.90,
        )
        candidates.append(
            QuestionValidator().validate(_slot(), candidate, _manifest())
        )

    duplicates = find_duplicate_questions(candidates)

    assert any(set(ids) == {"q1", "q2"} for ids in duplicates.values())


def test_same_matrix_learning_objective_with_rephrased_wording_is_detected() -> None:
    candidates = []
    for candidate_id, text in (
        (
            "q1",
            "If matrix A has order 2 by 3 and matrix B has order 3 by 4, "
            "determine the order of the product AB.",
        ),
        (
            "q2",
            "Given a 2 by 3 matrix P and a 3 by 4 matrix Q, find the dimensions "
            "of the matrix obtained by multiplying PQ.",
        ),
    ):
        candidate = QuestionCandidate(
            candidate_id=candidate_id,
            slot_id="short-1",
            question_text=text,
            answer="The product has order 2 by 4.",
            marks=2,
            bloom_level=BloomLevel.REMEMBER,
            bloom_justification="The learner applies the matrix-order rule.",
            marking_scheme=[MarkingCriterion(criterion="Correct order", marks=2)],
            evidence=SourceEvidence(page_numbers=[1], excerpts=["Normalization source."]),
            confidence=0.90,
        )
        candidates.append(QuestionValidator().validate(_slot(), candidate, _manifest()))

    duplicates = find_duplicate_questions(candidates)

    assert any(set(ids) == {"q1", "q2"} for ids in duplicates.values())


def test_explicit_higher_bloom_demand_is_flagged_without_rigid_rejection() -> None:
    slot = _slot().model_copy(update={"bloom_level": BloomLevel.UNDERSTAND})
    candidate = QuestionCandidate(
        candidate_id="q1",
        slot_id=slot.slot_id,
        question_text="Design a new normalization model and justify its constraints.",
        answer="A complete model.",
        marks=slot.marks,
        bloom_level=slot.bloom_level,
        bloom_justification="The learner explains the concept.",
        marking_scheme=[MarkingCriterion(criterion="Response", marks=slot.marks)],
        evidence=SourceEvidence(page_numbers=[1], excerpts=["Normalization source."]),
        confidence=0.90,
    )

    result = QuestionValidator().validate(slot, candidate, _manifest())

    assert result.accepted
    assert "bloom_demand_exceeds_blueprint" in {
        finding.code for finding in result.findings
    }


def test_standard_assertion_reason_question_passes() -> None:
    manifest = _manifest()
    slot = _slot().model_copy(
        update={"question_kind": QuestionKind.ASSERTION_REASON}
    )
    candidate = QuestionCandidate(
        candidate_id="assertion-reason",
        slot_id=slot.slot_id,
        question_text=(
            "Assertion (A): The supplied source statement is true.\n"
            "Reason (R): The source explains the statement.\n"
            "(A) Both Assertion (A) and Reason (R) are true and Reason (R) is "
            "the correct explanation of Assertion (A).\n"
            "(B) Both Assertion (A) and Reason (R) are true, but Reason (R) is "
            "not the correct explanation of Assertion (A).\n"
            "(C) Assertion (A) is true, but Reason (R) is false.\n"
            "(D) Assertion (A) is false, but Reason (R) is true."
        ),
        answer="Option (A).",
        marks=slot.marks,
        bloom_level=slot.bloom_level,
        bloom_justification="The statements must be evaluated.",
        marking_scheme=[
            MarkingCriterion(criterion="Correct response", marks=slot.marks)
        ],
        evidence=SourceEvidence(
            page_numbers=[1],
            excerpts=["Normalization source."],
        ),
        confidence=0.95,
    )

    result = QuestionValidator().validate(slot, candidate, manifest)

    assert result.accepted


def test_case_study_choice_is_scoped_to_final_subpart() -> None:
    manifest = _manifest()
    slot = _slot().model_copy(
        update={
            "question_kind": QuestionKind.CASE_STUDY,
            "marks": 4,
            "bloom_level": BloomLevel.EVALUATE,
            "has_internal_choice": True,
            "choices_per_question": 2,
            "internal_choice_scope": "final_subpart",
        }
    )
    candidate = QuestionCandidate(
        candidate_id="case-study",
        slot_id=slot.slot_id,
        question_text=(
            "Case study: A school database team is reorganising its student records "
            "before a new academic year. The supplied dataset lists repeated student, "
            "course, and teacher details. The team must preserve every dependency while "
            "reducing duplication and ensuring that updates cannot create inconsistent "
            "records.\n"
            "(i) Identify one repeated student detail in the records.\n"
            "(ii) Explain how a dependency can create inconsistent records.\n"
            "(iii) (a) Analyze how reorganising the student records reduces duplication.\n"
            "OR\n"
            "(iii) (b) Evaluate a student-record dependency and justify whether it reduces duplication."
        ),
        answer="A complete source-grounded response.",
        marks=4,
        bloom_level=slot.bloom_level,
        bloom_justification="The case applies the supplied relationship.",
        marking_scheme=[
            MarkingCriterion(criterion="Part (i)", marks=1),
            MarkingCriterion(criterion="Part (ii)", marks=1),
            MarkingCriterion(criterion="Part (iii)", marks=2),
        ],
        evidence=SourceEvidence(
            page_numbers=[1],
            excerpts=["Normalization source."],
        ),
        confidence=0.95,
    )

    result = QuestionValidator().validate(slot, candidate, manifest)

    assert result.accepted


def test_cross_topic_evidence_is_rejected_but_original_values_are_allowed() -> None:
    manifest = _manifest().model_copy(
        update={
            "pages": [
                *_manifest().pages,
                PageContent(
                    page_number=2,
                    width=600,
                    height=800,
                    text="An unrelated example uses the value 99.",
                    rendered_image_path="/tmp/page-2.png",
                ),
            ]
        }
    )
    slot = _slot().model_copy(update={"source_pages": [1]})
    candidate = QuestionCandidate(
        candidate_id="cross-topic",
        slot_id=slot.slot_id,
        question_text="Calculate the result for the value 99.",
        answer="99.",
        marks=slot.marks,
        bloom_level=slot.bloom_level,
        bloom_justification="Recall.",
        marking_scheme=[
            MarkingCriterion(criterion="Correct result", marks=slot.marks)
        ],
        evidence=SourceEvidence(
            page_numbers=[2],
            excerpts=["An unrelated example uses the value 99."],
        ),
        confidence=0.95,
    )

    result = QuestionValidator().validate(slot, candidate, manifest)
    codes = {finding.code for finding in result.findings}

    assert "cross_topic_evidence" in codes
    assert "unsupported_question_values" not in codes


def test_original_values_are_allowed_with_concept_evidence() -> None:
    manifest = _manifest()
    slot = _slot().model_copy(update={"source_pages": [1]})
    candidate = QuestionCandidate(
        candidate_id="original-application",
        slot_id=slot.slot_id,
        question_text="Apply the supplied relationship to a new value of 847.",
        answer="A verified result.",
        marks=slot.marks,
        bloom_level=slot.bloom_level,
        bloom_justification="The learner applies the evidenced relationship.",
        marking_scheme=[
            MarkingCriterion(criterion="Correct application", marks=slot.marks)
        ],
        evidence=SourceEvidence(
            page_numbers=[1],
            excerpts=["Normalization source."],
        ),
        confidence=0.95,
    )

    result = QuestionValidator().validate(slot, candidate, manifest)

    assert result.accepted


def test_thin_definition_only_case_study_is_rejected() -> None:
    manifest = _manifest()
    slot = _slot().model_copy(
        update={
            "question_kind": QuestionKind.CASE_STUDY,
            "marks": 4,
            "has_internal_choice": True,
            "choices_per_question": 2,
            "internal_choice_scope": "final_subpart",
        }
    )
    candidate = QuestionCandidate(
        candidate_id="thin-case",
        slot_id=slot.slot_id,
        question_text=(
            "Case study: A function maps inputs to outputs.\n"
            "(i) State its name.\n"
            "(ii) Calculate the first result.\n"
            "(iii) (a) Explain the result.\n"
            "OR\n"
            "(iii) (b) Compare the result."
        ),
        answer="A complete response.",
        marks=4,
        bloom_level=slot.bloom_level,
        bloom_justification="The case applies the evidenced relationship.",
        marking_scheme=[
            MarkingCriterion(criterion="Part (i)", marks=1),
            MarkingCriterion(criterion="Part (ii)", marks=1),
            MarkingCriterion(criterion="Part (iii)", marks=2),
        ],
        evidence=SourceEvidence(
            page_numbers=[1],
            excerpts=["Normalization source."],
        ),
        confidence=0.95,
    )

    result = QuestionValidator().validate(slot, candidate, manifest)

    assert "case_study_too_thin" in {
        finding.code for finding in result.findings
    }
    assert not result.accepted


def test_visual_question_must_share_academic_context() -> None:
    assert QuestionValidator._visual_matches_question(
        "Use the provided circuit to identify the rectifier diode.",
        "half-wave rectifier circuit with diode and resistor",
    )
    assert not QuestionValidator._visual_matches_question(
        "Use the provided figure to calculate partnership profit.",
        "half-wave rectifier circuit with diode and resistor",
    )

def test_unicode_minus_mcq_options_are_distinct() -> None:
    slot = _slot().model_copy(
        update={"question_kind": QuestionKind.MULTIPLE_CHOICE, "marks": 1}
    )
    candidate = QuestionCandidate(
        candidate_id="q1",
        slot_id=slot.slot_id,
        question_text=(
            "What is the derivative of sin(2x + 3)?\n"
            "(A) 2cos(2x + 3)\n(B) cos(2x + 3)\n"
            "(C) −2cos(2x + 3)\n(D) −cos(2x + 3)"
        ),
        answer="Option (A).",
        marks=1,
        bloom_level=slot.bloom_level,
        bloom_justification="Recall.",
        marking_scheme=[MarkingCriterion(criterion="Correct option", marks=1)],
        evidence=SourceEvidence(page_numbers=[1], excerpts=["Normalization source."]),
        confidence=0.90,
    )

    result = QuestionValidator().validate(slot, candidate, _manifest())

    assert "duplicate_mcq_options" not in {
        finding.code for finding in result.findings
    }


def test_plain_text_fraction_is_not_flagged_as_markup() -> None:
    candidate = QuestionCandidate(
        candidate_id="q1",
        slot_id="short-1",
        question_text=(
            "Determine whether f(x) = (x² − 1)/(x − 1) is "
            "continuous at x = 1. Justify your answer."
        ),
        answer="A verified result.",
        marks=2,
        bloom_level=BloomLevel.REMEMBER,
        bloom_justification="Recall.",
        marking_scheme=[MarkingCriterion(criterion="Answer", marks=2)],
        evidence=SourceEvidence(page_numbers=[1], excerpts=["Normalization source."]),
        confidence=0.90,
    )

    result = QuestionValidator().validate(_slot(), candidate, _manifest())

    assert "malformed_student_notation" not in {
        finding.code for finding in result.findings
    }


def test_case_study_without_literal_case_keyword_is_accepted() -> None:
    slot = _slot().model_copy(
        update={
            "question_kind": QuestionKind.CASE_STUDY,
            "marks": 4,
            "has_internal_choice": True,
            "internal_choice_scope": "final_subpart",
        }
    )
    candidate = QuestionCandidate(
        candidate_id="q1",
        slot_id=slot.slot_id,
        question_text=(
            "A water treatment plant uses a sensor to monitor the chlorine "
            "concentration C(t) in a storage tank over a 10-hour period, where "
            "t is time in hours. The plant records the measurements 2, 4, and 6 "
            "at three checkpoints, and the control team must confirm that the "
            "readings stay within the safety threshold defined by the supplied "
            "sensor data before releasing the water supply for the day.\n"
            "(i) Interpret the first sensor measurement from the tank data.\n"
            "(ii) Apply the threshold rule to the recorded tank measurements.\n"
            "(iii)(a) Analyze the tank sensor trend and justify a conclusion.\n"
            "OR\n"
            "(iii)(b) Compare the tank checkpoint readings and justify which "
            "measurement is most reliable."
        ),
        answer="A verified result.",
        marks=4,
        bloom_level=slot.bloom_level,
        bloom_justification="Recall.",
        marking_scheme=[MarkingCriterion(criterion="All parts", marks=4)],
        evidence=SourceEvidence(page_numbers=[1], excerpts=["Normalization source."]),
        confidence=0.90,
    )

    result = QuestionValidator().validate(slot, candidate, _manifest())

    assert "invalid_case_study" not in {finding.code for finding in result.findings}

def test_internal_choice_rubric_may_list_both_alternatives_once() -> None:
    slot = _slot().model_copy(
        update={
            "question_kind": QuestionKind.CASE_STUDY,
            "marks": 4,
            "has_internal_choice": True,
            "internal_choice_scope": "final_subpart",
        }
    )
    candidate = QuestionCandidate(
        candidate_id="q1",
        slot_id=slot.slot_id,
        question_text=(
            "A sensor team studies tank data with values 2, 4, and 6 recorded "
            "across the shift, and the supplied case describes how the "
            "measurements were gathered and why the thresholds matter for the "
            "safety decision the team must make before releasing the batch.\n"
            "(i) Interpret the first tank measurement.\n"
            "(ii) Apply the threshold rule to the tank measurements.\n"
            "(iii)(a) Analyze the tank trend and justify a conclusion.\n"
            "OR\n"
            "(iii)(b) Compare the tank readings and justify the most reliable."
        ),
        answer="A verified result.",
        marks=4,
        bloom_level=BloomLevel.REMEMBER,
        bloom_justification="Recall.",
        marking_scheme=[
            MarkingCriterion(criterion="(i)", marks=1),
            MarkingCriterion(criterion="(ii)", marks=1),
            MarkingCriterion(criterion="(iii)(a)", marks=2),
            MarkingCriterion(criterion="(iii)(b)", marks=2),
        ],
        evidence=SourceEvidence(page_numbers=[1], excerpts=["Normalization source."]),
        confidence=0.90,
    )

    result = QuestionValidator().validate(slot, candidate, _manifest())

    assert "rubric_total" not in {finding.code for finding in result.findings}


def test_rubric_total_still_rejected_without_internal_choice() -> None:
    candidate = QuestionCandidate(
        candidate_id="q1",
        slot_id="short-1",
        question_text="Define database normalization.",
        answer="A verified result.",
        marks=2,
        bloom_level=BloomLevel.REMEMBER,
        bloom_justification="Recall.",
        marking_scheme=[
            MarkingCriterion(criterion="Definition", marks=2),
            MarkingCriterion(criterion="Example", marks=2),
        ],
        evidence=SourceEvidence(page_numbers=[1], excerpts=["Normalization source."]),
        confidence=0.90,
    )

    result = QuestionValidator().validate(_slot(), candidate, _manifest())

    assert "rubric_total" in {finding.code for finding in result.findings}

def test_meta_references_to_source_material_are_rejected() -> None:
    candidate = QuestionCandidate(
        candidate_id="q1",
        slot_id="short-1",
        question_text=(
            "Based on Definition 1 from the source material, describe the "
            "behaviour of the cost function discussed in Chapter 6."
        ),
        answer="A verified result.",
        marks=2,
        bloom_level=BloomLevel.REMEMBER,
        bloom_justification="Recall.",
        marking_scheme=[MarkingCriterion(criterion="Answer", marks=2)],
        evidence=SourceEvidence(page_numbers=[1], excerpts=["Normalization source."]),
        confidence=0.90,
    )

    result = QuestionValidator().validate(_slot(), candidate, _manifest())

    assert "meta_reference" in {finding.code for finding in result.findings}


def test_self_contained_questions_pass_the_meta_reference_gate() -> None:
    candidate = QuestionCandidate(
        candidate_id="q1",
        slot_id="short-1",
        question_text=(
            "A continuous function on a closed interval attains its maximum "
            "either at a critical point or an endpoint. Use this property to "
            "explain where the absolute maximum of f(x) = x² on [0, 2] lies."
        ),
        answer="A verified result.",
        marks=2,
        bloom_level=BloomLevel.REMEMBER,
        bloom_justification="Recall.",
        marking_scheme=[MarkingCriterion(criterion="Answer", marks=2)],
        evidence=SourceEvidence(page_numbers=[1], excerpts=["Normalization source."]),
        confidence=0.90,
    )

    result = QuestionValidator().validate(_slot(), candidate, _manifest())

    assert "meta_reference" not in {finding.code for finding in result.findings}


def test_whole_question_choice_must_be_labelled_a_and_b() -> None:
    """Part B alternatives are (a) and (b); unlabelled text is a defect."""
    slot = _slot().model_copy(
        update={
            "marks": 13,
            "question_kind": QuestionKind.LONG_ANSWER,
            "has_internal_choice": True,
            "choices_per_question": 2,
            "internal_choice_scope": "whole_question",
        }
    )
    candidate = QuestionCandidate(
        candidate_id="q1",
        slot_id=slot.slot_id,
        question_text=(
            "Explain the normalization process and justify each decomposition step.\n"
            "OR\n"
            "Compare two decompositions and recommend one with full reasoning."
        ),
        answer="A complete answer.",
        marks=13,
        bloom_level=slot.bloom_level,
        bloom_justification="Applies the method.",
        marking_scheme=[MarkingCriterion(criterion="Complete response", marks=13)],
        evidence=SourceEvidence(
            page_numbers=[1], excerpts=["Normalization source."]
        ),
        confidence=0.90,
    )

    result = QuestionValidator().validate(slot, candidate, _manifest())

    assert "unlabelled_internal_choice" in {f.code for f in result.findings}
    assert not result.accepted


def test_part_b_choice_must_not_be_split_into_subparts() -> None:
    """A student answering (a) is marked out of 13, not a 7/6 breakdown."""
    slot = _slot().model_copy(
        update={
            "marks": 13,
            "question_kind": QuestionKind.LONG_ANSWER,
            "has_internal_choice": True,
            "choices_per_question": 2,
            "internal_choice_scope": "whole_question",
        }
    )
    candidate = QuestionCandidate(
        candidate_id="q1",
        slot_id=slot.slot_id,
        question_text=(
            "Answer EITHER (i) OR (ii):\n"
            "(i) Explain the normalization process and justify each step.\n"
            "OR\n"
            "(ii) Compare two decompositions and recommend one with reasoning."
        ),
        answer="A complete answer.",
        marks=13,
        bloom_level=slot.bloom_level,
        bloom_justification="Applies the method.",
        marking_scheme=[MarkingCriterion(criterion="Complete response", marks=13)],
        evidence=SourceEvidence(
            page_numbers=[1], excerpts=["Normalization source."]
        ),
        confidence=0.90,
    )

    result = QuestionValidator().validate(slot, candidate, _manifest())

    assert "internal_choice_split_into_subparts" in {
        f.code for f in result.findings
    }
    assert not result.accepted


def test_a_two_mark_question_must_stay_one_instruction() -> None:
    """The college's own two-markers run 5-20 words; a scenario is a defect."""
    slot = _slot().model_copy(
        update={"marks": 2, "question_kind": QuestionKind.VERY_SHORT_ANSWER}
    )
    candidate = QuestionCandidate(
        candidate_id="q1",
        slot_id=slot.slot_id,
        question_text=(
            "A convolutional layer receives data with shape (channels, height, "
            "width), whereas a fully connected layer flattens this into a single "
            "vector of values. Explain what information is lost by flattening and "
            "describe why a convolution layer preserves the spatial structure of "
            "the input data across its operations."
        ),
        answer="Spatial structure is lost.",
        marks=2,
        bloom_level=slot.bloom_level,
        bloom_justification="Recall.",
        marking_scheme=[MarkingCriterion(criterion="Correct response", marks=2)],
        evidence=SourceEvidence(
            page_numbers=[1], excerpts=["Normalization source."]
        ),
        confidence=0.90,
    )

    result = QuestionValidator().validate(slot, candidate, _manifest())

    assert "short_question_too_long" in {f.code for f in result.findings}
    assert not result.accepted


def test_a_concise_two_mark_question_passes() -> None:
    slot = _slot().model_copy(
        update={"marks": 2, "question_kind": QuestionKind.VERY_SHORT_ANSWER}
    )
    candidate = QuestionCandidate(
        candidate_id="q1",
        slot_id=slot.slot_id,
        question_text="Define a self-referential structure and give one example.",
        answer="A structure containing a pointer to its own type.",
        marks=2,
        bloom_level=slot.bloom_level,
        bloom_justification="Recall.",
        marking_scheme=[MarkingCriterion(criterion="Correct response", marks=2)],
        evidence=SourceEvidence(
            page_numbers=[1], excerpts=["Normalization source."]
        ),
        confidence=0.90,
    )

    result = QuestionValidator().validate(slot, candidate, _manifest())

    assert "short_question_too_long" not in {f.code for f in result.findings}
