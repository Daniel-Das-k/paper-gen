from __future__ import annotations

from collections import Counter
import re
from difflib import SequenceMatcher
from typing import Callable

from .evidence import build_evidence_chunks
from .models import (
    BloomLevel,
    BlueprintSlot,
    DocumentManifest,
    QuestionCandidate,
    QuestionKind,
    ValidatedQuestion,
    ValidationFinding,
    ValidationSeverity,
)


#: Question kinds whose text necessarily carries options or a stem-and-reason
#: pair, so a word ceiling would be meaningless.
OBJECTIVE_QUESTION_KINDS = frozenset(
    {QuestionKind.MULTIPLE_CHOICE, QuestionKind.ASSERTION_REASON}
)

#: Marks at or below which a prose question must be a single direct instruction.
SHORT_ANSWER_MAX_MARKS = 2

#: Word ceiling for such a question. The college's own two-markers run 5-20
#: words; this leaves room without admitting a scenario.
SHORT_ANSWER_MAX_WORDS = 35


class QuestionValidator:
    """Deterministic gates; semantic/grounding reviewers plug in after these."""

    def __init__(self, minimum_confidence: float = 0.80) -> None:
        self.minimum_confidence = minimum_confidence

    def validate(
        self,
        slot: BlueprintSlot,
        candidate: QuestionCandidate,
        manifest: DocumentManifest,
    ) -> ValidatedQuestion:
        findings: list[ValidationFinding] = []

        def error(code: str, message: str) -> None:
            findings.append(
                ValidationFinding(
                    code=code,
                    severity=ValidationSeverity.ERROR,
                    message=message,
                )
            )

        def warning(code: str, message: str) -> None:
            findings.append(
                ValidationFinding(
                    code=code,
                    severity=ValidationSeverity.WARNING,
                    message=message,
                )
            )

        if candidate.slot_id != slot.slot_id:
            error("slot_mismatch", "candidate was generated for a different blueprint slot")
        if candidate.marks != slot.marks:
            error("marks_mismatch", "candidate marks do not match the blueprint")
        if candidate.bloom_level != slot.bloom_level:
            error("bloom_mismatch", "candidate Bloom level does not match the blueprint")
        if candidate.confidence < self.minimum_confidence:
            warning(
                "low_confidence",
                f"confidence {candidate.confidence:.2f} is below "
                f"{self.minimum_confidence:.2f}",
            )
        if not candidate.evidence.page_numbers:
            error("missing_evidence", "candidate has no source page evidence")
        valid_pages = {page.page_number for page in manifest.pages}
        if any(page not in valid_pages for page in candidate.evidence.page_numbers):
            error("invalid_source_page", "candidate cites a page outside the document")
        allowed_pages = set(slot.source_pages)
        if allowed_pages and not set(candidate.evidence.page_numbers).issubset(
            allowed_pages
        ):
            error(
                "cross_topic_evidence",
                "candidate cites source pages outside its locked blueprint topic",
            )
        chunks = build_evidence_chunks(manifest)
        invalid_chunk_ids = [
            chunk_id
            for chunk_id in candidate.evidence.chunk_ids
            if chunk_id not in chunks
        ]
        if invalid_chunk_ids:
            error(
                "invalid_evidence_chunk",
                "candidate cites an evidence chunk outside the managed source",
            )
        valid_chunk_ids = [
            chunk_id
            for chunk_id in candidate.evidence.chunk_ids
            if chunk_id in chunks
        ]
        chunk_pages = {
            chunks[chunk_id].page_number for chunk_id in valid_chunk_ids
        }
        if valid_chunk_ids and not chunk_pages.issubset(
            set(candidate.evidence.page_numbers)
        ):
            error(
                "evidence_page_mismatch",
                "evidence pages do not match the backend-owned source chunks",
            )
        if (
            slot.evidence_chunk_ids
            and valid_chunk_ids
            and not set(valid_chunk_ids).issubset(set(slot.evidence_chunk_ids))
        ):
            error(
                "cross_topic_evidence_chunk",
                "candidate cites evidence outside its locked topic chunks",
            )
        cited_text = " ".join(
            page.text
            for page in manifest.pages
            if page.page_number in candidate.evidence.page_numbers
        )
        normalized_source = self._normalize_evidence_text(cited_text)
        matching_excerpts = [
            excerpt
            for excerpt in candidate.evidence.excerpts
            if len(self._normalize_evidence_text(excerpt)) >= 12
            and self._normalize_evidence_text(excerpt) in normalized_source
        ]
        if not valid_chunk_ids and not matching_excerpts:
            error(
                "unverified_evidence_excerpt",
                "question does not cite a verified backend-owned evidence chunk",
            )
        scheme_total = sum(item.marks for item in candidate.marking_scheme)
        # With an internal choice the scheme may enumerate criteria for both
        # alternatives once each, so totals up to 2x the marks are coherent.
        scheme_is_valid = scheme_total == candidate.marks or (
            slot.has_internal_choice
            and candidate.marks < scheme_total <= 2 * candidate.marks
        )
        if not scheme_is_valid:
            error("rubric_total", "marking scheme does not add up to question marks")
        normalized_criteria = [
            " ".join(re.findall(r"[a-z0-9]+", item.criterion.lower()))
            for item in candidate.marking_scheme
        ]
        if len(normalized_criteria) != len(set(normalized_criteria)):
            error(
                "duplicate_marking_criteria",
                "marking scheme repeats the same credit criterion more than once",
            )
        if candidate.marks >= 5 and len(candidate.marking_scheme) < 2:
            warning(
                "rubric_lacks_granularity",
                "a question worth five marks or more should award credit across at least two explicit reasoning steps",
            )
        answer_words = len(re.findall(r"\b[\w'-]+\b", candidate.answer))
        if candidate.marks >= 5 and answer_words < candidate.marks * 2:
            warning(
                "answer_too_brief_for_marks",
                f"the model answer has {answer_words} words for {candidate.marks} marks; verify that it demonstrates every required step",
            )
        if candidate.estimated_answer_minutes is not None:
            minutes_per_mark = candidate.estimated_answer_minutes / candidate.marks
            if minutes_per_mark < 0.5 or minutes_per_mark > 3.0:
                warning(
                    "answer_time_mismatch",
                    f"estimated answer time {candidate.estimated_answer_minutes:g} minutes is not proportionate to {candidate.marks} marks",
                )
        # ")/(" is intentionally NOT flagged: the backend's own LaTeX cleaner
        # renders \frac{a}{b} as (a)/(b), which is valid student-facing text.
        malformed_notation = re.compile(
            r"(?i)(?:\\[A-Za-z]+|\\*begin\{(?:bmatrix|pmatrix|matrix|vmatrix)\}|"
            r"\bu[0-9a-f]{4}\b|\*\*|__|\^(?:\\?circ)\b|"
            r"\b(?:tan|cot|sin|cos)(?:alpha|beta|theta)\b|∈fty)"
        )
        if malformed_notation.search(candidate.question_text):
            error(
                "malformed_student_notation",
                "student-facing question contains unrendered mathematical or markup syntax",
            )
        meta_reference = re.compile(
            r"(?i)\b(?:the source material|the provided evidence|"
            r"the course material|from chapter \d+|in chapter \d+|"
            r"exercise \d+(?:\.\d+)*|theorems? \d+|definition \d+|"
            r"discussed in (?:chapter|section) \d+)\b"
        )
        if meta_reference.search(candidate.question_text):
            error(
                "meta_reference",
                "student-facing question references source-internal material "
                "(chapter, exercise, or numbered theorem/definition); state the "
                "needed fact or property in the question instead",
            )
        if slot.question_kind in {
            QuestionKind.MULTIPLE_CHOICE,
            QuestionKind.ASSERTION_REASON,
        }:
            option_labels = {
                label.upper()
                for groups in re.findall(
                    r"(?:^|\s)(?:\(([A-D])\)|([A-D])[\).:])\s*",
                    candidate.question_text,
                    flags=re.IGNORECASE | re.MULTILINE,
                )
                for label in groups
                if label
            }
            if option_labels != {"A", "B", "C", "D"}:
                error(
                    "invalid_mcq_options",
                    "objective question must contain options A, B, C, and D",
                )
            option_bodies = [
                self._normalize_mcq_option(body)
                for body in re.findall(
                    r"(?im)^\s*(?:\([A-D]\)|[A-D][\).:])\s*(.+)$",
                    candidate.question_text,
                )
            ]
            if len(option_bodies) == 4 and len(set(option_bodies)) != 4:
                error(
                    "duplicate_mcq_options",
                    "multiple-choice options must be distinct",
                )
            if not re.search(
                r"(?i)^\s*(?:option\s*)?\(?[A-D]\)?(?:[\).:]|\s|$)",
                candidate.answer,
            ):
                error(
                    "missing_mcq_answer_key",
                    "objective answer must identify the correct option label",
                )
        if slot.question_kind == QuestionKind.ASSERTION_REASON:
            if not re.search(
                r"(?i)\bassertion\s*\(A\)", candidate.question_text
            ) or not re.search(r"(?i)\breason\s*\(R\)", candidate.question_text):
                error(
                    "invalid_assertion_reason",
                    "assertion-reason question must label Assertion (A) and Reason (R)",
                )
            required_meanings = (
                r"both.+true",
                r"correct explanation",
                r"not.+correct explanation",
                r"assertion.+true.+reason.+false",
                r"assertion.+false.+reason.+true",
            )
            if any(
                not re.search(pattern, candidate.question_text, re.IGNORECASE | re.DOTALL)
                for pattern in required_meanings
            ):
                error(
                    "invalid_assertion_reason_options",
                    "assertion-reason item must include the four standard response meanings",
                )
        if slot.has_internal_choice and not re.search(
            r"\bOR\b",
            candidate.question_text,
            flags=re.IGNORECASE,
        ):
            error(
                "missing_internal_choice",
                "blueprint requires two complete alternatives separated by OR",
            )
        self._validate_choice_structure(slot, candidate, error, warning)
        self._validate_cognitive_demand(slot, candidate, error, warning)

        evidence_asset = candidate.evidence.visual_asset_id
        if slot.requires_visual:
            if evidence_asset != slot.visual_asset_id:
                error("visual_mismatch", "question does not use the blueprint visual")
            if re.search(
                r"\bp\d+-image-\d+\b",
                candidate.question_text,
                flags=re.IGNORECASE,
            ):
                error(
                    "exposed_visual_asset_id",
                    "student-facing question exposes an internal visual identifier",
                )
            assets = {asset.asset_id: asset for asset in manifest.visual_assets}
            asset = assets.get(slot.visual_asset_id or "")
            if not asset or not asset.question_eligible:
                error("unverified_visual", "visual has not passed multimodal verification")
            elif allowed_pages and asset.page_number not in allowed_pages:
                error(
                    "visual_topic_page_mismatch",
                    "required visual is outside the slot's locked topic pages",
                )
            elif not self._visual_matches_question(
                candidate.question_text,
                asset.topic or "",
                asset.caption or "",
                asset.nearby_text or "",
                " ".join(asset.visible_labels),
                slot.topic_id,
            ):
                warning(
                    "visual_question_mismatch",
                    "question text has weak lexical overlap with the required visual; "
                    "confirm relevance during semantic review",
                )
            if slot.has_internal_choice:
                alternatives = [
                    part.strip()
                    for part in re.split(
                        r"(?im)^\s*OR\s*$",
                        candidate.question_text,
                    )
                    if part.strip()
                ]
                if len(alternatives) == 2 and any(
                    not re.search(
                        r"\b(figure|diagram|graph|image|visual)\b",
                        alternative,
                        flags=re.IGNORECASE,
                    )
                    for alternative in alternatives
                ):
                    error(
                        "visual_choice_mismatch",
                        "both internal-choice alternatives must meaningfully use the required figure",
                    )

        return ValidatedQuestion(
            candidate=candidate,
            accepted=not any(
                item.severity == ValidationSeverity.ERROR for item in findings
            ),
            findings=findings,
        )

    @staticmethod
    def _normalize_evidence_text(value: str) -> str:
        return " ".join(re.findall(r"[a-z0-9]+", value.lower()))

    @staticmethod
    def _normalize_mcq_option(value: str) -> str:
        """Preserve mathematical operators when comparing distractors."""
        value = (
            value.lower()
            .replace("−", "-")
            .replace("–", "-")
            .replace("—", "-")
            .replace("plus", "+")
            .replace("minus", "-")
            .replace("multiplied by", "×")
            .replace("times", "×")
            .replace("divided by", "÷")
        )
        return " ".join(re.findall(r"[a-z0-9]+|[+\-×÷<>=≤≥]", value))

    @staticmethod
    def _visual_matches_question(question_text: str, *contexts: str) -> bool:
        stopwords = {
            "figure", "provided", "image", "diagram", "graph", "visual",
            "identify", "find", "state", "explain", "using", "shown",
            "with", "from", "that", "this", "what", "which", "where",
            "question", "answer", "given", "following",
        }

        def tokens(value: str) -> set[str]:
            return {
                token
                for token in re.findall(r"[a-z0-9]+", value.lower())
                if len(token) >= 3 and token not in stopwords
            }

        return bool(tokens(question_text) & tokens(" ".join(contexts)))

    @staticmethod
    def _validate_choice_structure(
        slot: BlueprintSlot,
        candidate: QuestionCandidate,
        error: Callable[[str, str], None],
        warning: Callable[[str, str], None],
    ) -> None:
        if slot.question_kind not in {
            QuestionKind.MULTIPLE_CHOICE,
            QuestionKind.ASSERTION_REASON,
        }:
            labels = {
                label.upper()
                for groups in re.findall(
                    r"(?m)^\s*(?:\(([A-Da-d])\)|([A-Da-d])[\).:])\s+",
                    candidate.question_text,
                )
                for label in groups
                if label
            }
            looks_like_objective_question = bool(
                re.search(
                    r"(?i)\b(choose|select|which\s+(?:one|option|statement|answer))\b",
                    candidate.question_text,
                )
            )
            if labels == {"A", "B", "C", "D"} and looks_like_objective_question:
                error(
                    "unexpected_mcq_format",
                    "non-objective slot contains a multiple-choice question",
                )
        # A two-mark question is answered in about two minutes. The reference
        # papers run 5 to 20 words ("Define a self-referential structure."); a
        # 45-word scenario is a long-answer question wearing a 2-mark label, and
        # the prompt rule alone did not hold.
        # Objective formats carry their options in the question text and are
        # long by construction; the rule is about prose short-answer questions.
        if (
            slot.marks <= SHORT_ANSWER_MAX_MARKS
            and slot.question_kind not in OBJECTIVE_QUESTION_KINDS
        ):
            words = len(candidate.question_text.split())
            if words > SHORT_ANSWER_MAX_WORDS:
                error(
                    "short_question_too_long",
                    f"a {slot.marks}-mark question runs {words} words; keep it to "
                    f"one direct instruction under {SHORT_ANSWER_MAX_WORDS} words "
                    "with no scenario",
                )
            subpart_count = len(
                re.findall(r"(?im)^\s*\(i+\)\s*", candidate.question_text)
            )
            if subpart_count:
                error(
                    "short_question_has_subparts",
                    f"a {slot.marks}-mark question must contain one direct task, not {subpart_count} labelled subpart{'s' if subpart_count != 1 else ''}",
                )

        alternatives = re.split(
            r"(?im)^\s*OR\s*$",
            candidate.question_text,
        )
        if slot.has_internal_choice:
            nonempty = [part.strip() for part in alternatives if part.strip()]
            if len(alternatives) != 2 or len(nonempty) != 2:
                error(
                    "invalid_internal_choice_structure",
                    "internal choice must contain exactly two alternatives and one OR",
                )
            elif slot.internal_choice_scope == "final_subpart":
                prefix = nonempty[0]
                if not all(
                    re.search(pattern, prefix, re.IGNORECASE | re.MULTILINE)
                    for pattern in (
                        r"^\s*\(i\)",
                        r"^\s*\(ii\)",
                        r"^\s*\(iii\)\s*\(a\)",
                    )
                ) or not re.search(
                    r"^\s*\(iii\)\s*\(b\)",
                    nonempty[1],
                    re.IGNORECASE | re.MULTILINE,
                ):
                    error(
                        "invalid_scoped_internal_choice",
                        "case-study choice must be between subparts (iii)(a) and (iii)(b)",
                    )
            elif slot.internal_choice_scope == "whole_question":
                # Each alternative is one task worth the slot's full marks. The
                # model otherwise reaches for "Answer EITHER (i) OR (ii)", which
                # turns the choice into a subpart split and misstates the marks.
                if not re.search(r"^\s*\(a\)", nonempty[0], re.MULTILINE) or (
                    not re.search(r"^\s*\(b\)", nonempty[1], re.MULTILINE)
                ):
                    error(
                        "unlabelled_internal_choice",
                        "the two alternatives must be labelled (a) and (b)",
                    )
                if re.search(
                    r"(?i)\bEITHER\b.*\(i+\)|answer\s+either\s*\(i\)",
                    candidate.question_text,
                ):
                    error(
                        "internal_choice_split_into_subparts",
                        "the choice is between (a) and (b); an alternative carries "
                        "the full marks and must not be split into (i)/(ii) parts",
                    )
            elif min(len(part.split()) for part in nonempty) > 0:
                first_task = re.split(
                    r"(?im)^\s*\(?(?:a|part\s*a|alternative\s*1)\)?[\).:]?\s*",
                    nonempty[0],
                    maxsplit=1,
                )[-1]
                lengths = [len(first_task.split()), len(nonempty[1].split())]
                if max(lengths) / min(lengths) > 3.5:
                    warning(
                        "unbalanced_internal_choice",
                        "internal-choice alternatives have substantially different workloads",
                    )
        elif len(alternatives) > 1:
            error(
                "unexpected_internal_choice",
                "slot does not permit an internal choice",
            )

    @staticmethod
    def _validate_cognitive_demand(
        slot: BlueprintSlot,
        candidate: QuestionCandidate,
        error: Callable[[str, str], None],
        warning: Callable[[str, str], None],
    ) -> None:
        text = candidate.question_text.lower()
        word_count = len(re.findall(r"\b\w+\b", text))
        bloom_order = list(BloomLevel)
        command_patterns = {
            BloomLevel.CREATE: r"\b(design|formulate|develop|propose)\b",
            BloomLevel.EVALUATE: (
                r"\b(evaluate|critique|recommend|defend|critically\s+assess)\b"
            ),
            BloomLevel.ANALYZE: (
                r"\b(analy[sz]e|differentiate|investigate|decompose)\b"
            ),
        }
        demanded_levels = [
            level
            for level, pattern in command_patterns.items()
            if re.search(pattern, text)
        ]
        if demanded_levels and max(
            bloom_order.index(level) for level in demanded_levels
        ) > bloom_order.index(slot.bloom_level):
            warning(
                "bloom_demand_exceeds_blueprint",
                "verify that the actual cognitive work does not exceed the locked Bloom level",
            )
        if slot.bloom_level == BloomLevel.CREATE and not re.search(
            r"\b(create|design|formulate|construct|develop|model|propose)\b",
            text,
        ):
            warning(
                "insufficient_create_demand",
                "Create-level slot must require an original design, model, or formulation",
            )
        if slot.bloom_level == BloomLevel.EVALUATE and not re.search(
            r"\b(evaluate|justify|assess|critique|compare|recommend|defend)\b",
            text,
        ):
            warning(
                "insufficient_evaluate_demand",
                "Evaluate-level slot must require a justified judgment",
            )
        if slot.bloom_level == BloomLevel.ANALYZE and not re.search(
            r"\b(analy[sz](?:e|ing)|compar(?:e|ing|ison)|differentiat(?:e|ing)|"
            r"examin(?:e|ing)|classif(?:y|ying)|deriv(?:e|ing)|investigat(?:e|ing)|"
            r"relationship|why|how)\b",
            text,
        ) and not (
            word_count >= 45
            and len(re.findall(r"(?im)^\s*(?:\([a-d]\)|[a-d][\).])\s*", text))
            >= 2
        ):
            warning(
                "insufficient_analyze_demand",
                "Analyze-level slot must require decomposition, comparison, or reasoning",
            )
        if slot.marks >= 5 and word_count < 22:
            warning(
                "insufficient_mark_demand",
                "five-mark question is too short to require a sufficiently developed response",
            )
        if slot.marks >= 5:
            alternatives = [
                part.strip()
                for part in re.split(r"(?im)^\s*OR\s*$", text)
                if part.strip()
            ]
            developed_task = re.compile(
                r"\b(analy[sz]|explain|show|verify|justify|derive|formulate|"
                r"construct|evaluate|design|compare|prove|interpret)"
            )
            if any(
                len(re.findall(r"\b\w+\b", alternative)) < 12
                or not developed_task.search(alternative)
                for alternative in alternatives
            ):
                warning(
                    "insufficient_mark_demand",
                    "each five-mark alternative must require developed, multi-step reasoning",
                )
        if slot.question_kind == QuestionKind.CASE_STUDY:
            case_body = re.split(
                r"(?im)^\s*\(i\)\s*",
                candidate.question_text,
                maxsplit=1,
            )[0]
            case_word_count = len(re.findall(r"\b[\w'-]+\b", case_body))
            # A substantive scenario paragraph counts as a case even when it
            # does not use the literal words "case", "scenario", or "study".
            has_case = (
                bool(re.search(r"\b(cases?|scenarios?|study|studies)\b", text))
                or case_word_count >= 35
            )
            has_subparts = all(
                re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
                for pattern in (r"^\s*\(i\)", r"^\s*\(ii\)", r"^\s*\(iii\)")
            )
            if not has_case or not has_subparts:
                error(
                    "invalid_case_study",
                    "case-study slot requires a shared scenario and subquestions (i), (ii), and (iii)",
                )
            if case_word_count < 35:
                error(
                    "case_study_too_thin",
                    "case study must provide a substantive, self-contained scenario or "
                    "dataset before its subquestions",
                )
            concrete_context = bool(
                re.search(r"\d", case_body)
                or re.search(
                    r"(?i)\b(company|firm|school|hospital|researcher|team|client|"
                    r"manufacturer|experiment|survey|dataset|data|records?|tank|"
                    r"observations?|measurements?|parameters?)\b",
                    case_body,
                )
            )
            if not concrete_context:
                error(
                    "case_study_lacks_concrete_context",
                    "case study must contain a concrete actor, dataset, observation, or supplied values",
                )
            case_tokens = QuestionValidator._case_tokens(case_body)
            subparts = [
                part.strip()
                for part in re.split(
                    r"(?im)^\s*(?:\(i\)|\(ii\)|\(iii\)\s*\([ab]\)|OR)\s*",
                    candidate.question_text,
                )[1:]
                if part.strip()
            ]
            if subparts and any(
                not (case_tokens & QuestionValidator._case_tokens(part))
                for part in subparts
            ):
                error(
                    "case_study_subpart_disconnected",
                    "every case-study subpart and alternative must use information from the shared case",
                )

    @staticmethod
    def _case_tokens(value: str) -> set[str]:
        stopwords = {
            "case", "study", "scenario", "question", "answer", "state",
            "identify", "explain", "analyze", "analyse", "evaluate", "calculate",
            "determine", "compare", "justify", "using", "given", "following",
            "mathematical", "model", "modelling", "real", "life", "problem",
            "first", "second", "result", "value", "information", "according",
            "what", "which", "why", "how", "this", "that", "with", "from",
            "into", "only", "must", "does", "have", "been", "their", "about",
        }
        tokens = {
            token
            for token in re.findall(r"[a-z0-9]+", value.lower())
            if len(token) >= 4 and token not in stopwords
        }
        # Function/variable names like C(t), f(x), or θ₁ are how mathematical
        # subparts reference the shared case; keep them despite their length.
        tokens.update(
            match.replace(" ", "")
            for match in re.findall(r"\b[a-z]\s*\([a-z]\)", value.lower())
        )
        return tokens


def find_duplicate_questions(
    questions: list[ValidatedQuestion],
) -> dict[str, list[str]]:
    normalized: Counter[str] = Counter(_question_stem(question) for question in questions)
    duplicates = {text for text, count in normalized.items() if count > 1}
    matches = {
        text: [
            question.candidate.candidate_id
            for question in questions
            if _question_stem(question) == text
        ]
        for text in duplicates
    }
    stems = [
        (question.candidate.candidate_id, _question_stem(question))
        for question in questions
    ]
    for index, (left_id, left) in enumerate(stems):
        if len(left.split()) < 6:
            continue
        for right_id, right in stems[index + 1 :]:
            if len(right.split()) < 6:
                continue
            left_numbers = re.findall(r"\b\d+(?:\.\d+)?\b", left)
            right_numbers = re.findall(r"\b\d+(?:\.\d+)?\b", right)
            ratio = SequenceMatcher(None, left, right).ratio()
            left_tokens = set(left.split())
            right_tokens = set(right.split())
            jaccard = len(left_tokens & right_tokens) / max(
                1, len(left_tokens | right_tokens)
            )
            same_numeric_template = False
            if (left_numbers or right_numbers) and left_numbers != right_numbers:
                left_template = re.sub(r"\b\d+(?:\.\d+)?\b", "<number>", left)
                right_template = re.sub(r"\b\d+(?:\.\d+)?\b", "<number>", right)
                template_ratio = SequenceMatcher(
                    None,
                    left_template,
                    right_template,
                ).ratio()
                left_template_tokens = set(left_template.split())
                right_template_tokens = set(right_template.split())
                template_jaccard = len(
                    left_template_tokens & right_template_tokens
                ) / max(
                    1,
                    len(left_template_tokens | right_template_tokens),
                )
                same_numeric_template = (
                    template_ratio >= 0.92 or template_jaccard >= 0.90
                )
            left_core = _core_question_tokens(left)
            right_core = _core_question_tokens(right)
            core_jaccard = len(left_core & right_core) / max(
                1, len(left_core | right_core)
            )
            if (
                ratio >= 0.90
                or jaccard >= 0.88
                or same_numeric_template
                or core_jaccard >= 0.62
            ):
                key = f"semantic:{left[:80]}"
                matches.setdefault(key, [])
                for candidate_id in (left_id, right_id):
                    if candidate_id not in matches[key]:
                        matches[key].append(candidate_id)
    return matches


def _question_stem(question: ValidatedQuestion) -> str:
    text = question.candidate.question_text.lower()
    option_matches = re.findall(
        r"(?im)^\s*(?:\(([a-d])\)|([a-d])[\).:])\s+",
        text,
    )
    option_labels = {
        label
        for match in option_matches
        for label in match
        if label
    }
    if option_labels == {"a", "b", "c", "d"}:
        text = re.sub(
            r"(?im)^\s*(?:\([a-d]\)|[a-d][\).:])\s+.*$",
            " ",
            text,
        )
    text = re.sub(r"\b(?:question|q)\s*\d+\b", " ", text)
    return " ".join(re.findall(r"[a-z0-9]+", text))


def _core_question_tokens(value: str) -> set[str]:
    stopwords = {
        "the", "a", "an", "and", "or", "of", "to", "in", "for", "with",
        "from", "by", "is", "are", "was", "were", "be", "been", "being",
        "this", "that", "these", "those", "what", "which", "who", "why",
        "how", "where", "when", "does", "do", "did", "using", "use", "based",
        "following", "given", "each", "if", "has", "have", "had",
        "determine", "find", "calculate", "obtained", "matrix", "matrices",
    }

    synonyms = {
        "dimension": "order",
        "dimensions": "order",
        "multiply": "product",
        "multiplied": "product",
        "multiplying": "product",
    }

    def stem(token: str) -> str:
        for suffix in ("ments", "ment", "ities", "ity", "ing", "ed", "es", "s"):
            if len(token) > len(suffix) + 3 and token.endswith(suffix):
                return token[: -len(suffix)]
        return token

    return {
        stem(synonyms.get(token, token))
        for token in value.split()
        if len(token) >= 3 and token not in stopwords and not token.isdigit()
    }
