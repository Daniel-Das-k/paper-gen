from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from collections import OrderedDict
from typing import Awaitable, Callable, TypeVar

from .ai import (
    DocumentAnalyzer,
    SemanticReview,
    SectionQuestionBatch,
    SectionQuestionReview,
    is_transient_model_failure,
    summarize_model_failure,
)
from .blueprints import FACET_CYCLE
from .evidence import attach_verified_evidence, build_evidence_chunks
from .models import (
    BloomLevel,
    BlueprintSlot,
    ContentMap,
    DocumentManifest,
    ExamPaper,
    MarkingCriterion,
    PaperBlueprint,
    PaperPattern,
    QuestionCandidate,
    QuestionKind,
    SourceEvidence,
    ValidatedQuestion,
    ValidationFinding,
    ValidationSeverity,
)
from .blueprints import BlueprintBuilder
from .validation import QuestionValidator, find_duplicate_questions
from .subject_profiles import infer_subject_profile

logger = logging.getLogger("uvicorn.error")
ResultT = TypeVar("ResultT")


class PaperGenerationPipeline:
    """Generate and review one model response per paper section."""

    def __init__(
        self,
        analyzer: DocumentAnalyzer,
        *,
        provider_attempts: int | None = None,
        request_interval_seconds: float | None = None,
        section_generation_concurrency: int | None = None,
    ) -> None:
        self.analyzer = analyzer
        self.provider_attempts = provider_attempts or int(
            os.getenv("QUESTION_PROVIDER_ATTEMPTS", "3")
        )
        self.request_interval_seconds = (
            request_interval_seconds
            if request_interval_seconds is not None
            else float(os.getenv("AI_REQUEST_INTERVAL_SECONDS", "0.5"))
        )
        self.section_generation_concurrency = max(
            1,
            section_generation_concurrency
            if section_generation_concurrency is not None
            else int(os.getenv("SECTION_GENERATION_CONCURRENCY", "5")),
        )
        self.validator = QuestionValidator()
        self.minimum_final_quality_score = int(
            os.getenv(
                "TARGET_QUESTION_QUALITY_SCORE",
                os.getenv("MIN_FINAL_QUALITY_SCORE", "85"),
            )
        )
        self._request_start_lock = asyncio.Lock()
        self._last_request_started_at = 0.0
        self._pipeline_started_at = 0.0
        self._completed_model_calls = 0
        self._planned_model_calls = 0

    async def generate(
        self,
        *,
        pattern: PaperPattern,
        content_map: ContentMap,
        manifest: DocumentManifest,
        blueprint: PaperBlueprint,
        set_label: str | None = None,
    ) -> ExamPaper:
        sections: OrderedDict[str, list[BlueprintSlot]] = OrderedDict()
        for slot in blueprint.slots:
            sections.setdefault(slot.section_id, []).append(slot)
        self._pipeline_started_at = time.perf_counter()
        self._completed_model_calls = 0
        self._planned_model_calls = len(sections) * 2

        logger.info(
            "paper.pipeline.start subject=%s slots=%d sections=%d "
            "planned_model_calls=%d",
            content_map.subject,
            len(blueprint.slots),
            len(sections),
            self._planned_model_calls,
        )
        logger.info(
            "paper.pipeline.rate_control interval_seconds=%.2f provider_attempts=%d "
            "section_concurrency=%d",
            self.request_interval_seconds,
            self.provider_attempts,
            self.section_generation_concurrency,
        )

        all_slots = [slot for slots in sections.values() for slot in slots]
        subject_profile = infer_subject_profile(content_map)
        questions: list[ValidatedQuestion] = []
        if self.section_generation_concurrency == 1:
            for section_id, slots in sections.items():
                questions.extend(
                    await self._generate_and_review_section(
                        section_id=section_id,
                        slots=slots,
                        content_map=content_map,
                        manifest=manifest,
                        prior_question_texts=[
                            item.candidate.question_text for item in questions
                        ],
                    )
                )
        else:
            semaphore = asyncio.Semaphore(self.section_generation_concurrency)
            paper_plan_text = self._paper_generation_plan(all_slots, content_map)

            async def run_section(
                section_id: str,
                slots: list[BlueprintSlot],
            ) -> list[ValidatedQuestion]:
                async with semaphore:
                    return await self._generate_and_review_section(
                        section_id=section_id,
                        slots=slots,
                        content_map=content_map,
                        manifest=manifest,
                        paper_plan_text=paper_plan_text,
                    )

            section_results = await asyncio.gather(
                *(
                    run_section(section_id, slots)
                    for section_id, slots in sections.items()
                )
            )
            questions = [
                question
                for section_questions in section_results
                for question in section_questions
            ]

        logger.info(
            "paper.review.complete reviewed=%d accepted=%d rejected=%d",
            len(questions),
            sum(question.accepted for question in questions),
            sum(not question.accepted for question in questions),
        )

        duplicates = find_duplicate_questions(questions)
        if duplicates:
            logger.warning(
                "paper.pipeline.duplicates_detected groups=%d candidates=%s",
                len(duplicates),
                list(duplicates.values()),
            )
            duplicate_ids = {
                candidate_id for ids in duplicates.values() for candidate_id in ids
            }
            questions = [
                self._append_duplicate_finding(question)
                if question.candidate.candidate_id in duplicate_ids
                else question
                for question in questions
            ]

        questions = await self._repair_rejected_questions(
            questions=questions,
            slots=all_slots,
            content_map=content_map,
            manifest=manifest,
        )
        duplicates = find_duplicate_questions(questions)
        if duplicates:
            duplicate_ids = {
                candidate_id for ids in duplicates.values() for candidate_id in ids
            }
            questions = [
                self._append_duplicate_finding(question)
                if question.accepted
                and question.candidate.candidate_id in duplicate_ids
                else question
                for question in questions
            ]

        # Structural invariant: the paper's shape is static. Exactly one
        # question per blueprint slot, ordered by the blueprint's fixed
        # question numbers — only question content is dynamic.
        slot_order = {
            slot.slot_id: index for index, slot in enumerate(blueprint.slots)
        }
        questions = sorted(
            questions,
            key=lambda question: slot_order.get(
                question.candidate.slot_id, len(slot_order)
            ),
        )
        if [question.candidate.slot_id for question in questions] != [
            slot.slot_id for slot in blueprint.slots
        ]:
            raise RuntimeError(
                "paper structure invariant violated: generated questions do not "
                "match the blueprint's slots one-to-one in order"
            )

        paper = ExamPaper(
            title=f"{content_map.subject} Academic Examination",
            set_label=set_label,
            subject=content_map.subject,
            subject_family=subject_profile.family.value,
            duration_minutes=pattern.duration_minutes,
            total_marks=pattern.total_marks,
            instructions=self._paper_instructions(pattern, subject_profile.family.value),
            questions=questions,
            requires_human_approval=True,
            publication_ready=all(question.accepted for question in questions),
        )
        logger.info(
            "paper.pipeline.complete accepted=%d rejected=%d total=%d "
            "normal_model_calls=%d total_duration_seconds=%.2f",
            sum(question.accepted for question in questions),
            sum(not question.accepted for question in questions),
            len(questions),
            self._completed_model_calls,
            time.perf_counter() - self._pipeline_started_at,
        )
        return paper

    @staticmethod
    def _paper_instructions(
        pattern: PaperPattern,
        subject_family: str,
    ) -> list[str]:
        question_count = sum(
            section.question_count
            for section in pattern.sections
            if section.mandatory
        )
        instructions = [
            (
                f"This question paper contains {question_count} compulsory questions "
                f"in {len(pattern.sections)} sections."
            ),
            *[
                (
                    f"{section.title}: {section.question_count} questions, "
                    f"{section.marks_each} mark"
                    f"{'' if section.marks_each == 1 else 's'} each."
                )
                for section in pattern.sections
            ],
            "Attempt only one alternative where an internal choice is provided.",
            (
                "Questions 19 and 20 are Assertion–Reason questions using the "
                "standard four response codes."
            ),
            (
                "There is no overall choice. Internal choices are available only "
                "in the questions where they are printed."
            ),
            (
                "A 15-minute reading period should be provided before the writing "
                "time begins."
            ),
            "Use of calculators is not permitted unless faculty instructions say otherwise.",
        ]
        if subject_family in {
            "mathematics",
            "physical_science",
            "commerce",
            "computing",
        }:
            instructions.append(
                "Show all essential working, assumptions, and units where applicable."
            )
        instructions.append(
            "This AI-assisted draft requires faculty approval before use."
        )
        return instructions

    async def _repair_rejected_questions(
        self,
        *,
        questions: list[ValidatedQuestion],
        slots: list[BlueprintSlot],
        content_map: ContentMap,
        manifest: DocumentManifest,
        prior_question_texts: list[str] | None = None,
    ) -> list[ValidatedQuestion]:
        targets = [question for question in questions if self._needs_improvement(question)]
        if not targets:
            logger.info("paper.repair.skipped targets=0")
            return questions

        slots_by_id = {slot.slot_id: slot for slot in slots}
        logger.warning(
            "paper.repair.required candidates=%s",
            {
                question.candidate.candidate_id: [
                    finding.code for finding in question.findings
                ]
                for question in targets
            },
        )
        evidence_chunks = build_evidence_chunks(manifest)
        attach_source_pdf = os.getenv(
            "REPAIR_ATTACH_SOURCE_PDF", "false"
        ).lower() in {"1", "true", "yes", "on"}
        repair_source_pdf_path = (
            manifest.source_pdf_path if attach_source_pdf else None
        )
        # Include every other question's text — rejected duplicates must also
        # be avoided, or two concurrent repairs can regenerate the same pair.
        texts_by_slot = {
            question.candidate.slot_id: question.candidate.question_text
            for question in questions
        }
        semaphore = asyncio.Semaphore(self.section_generation_concurrency)
        logger.info(
            "paper.repair.start targets=%d max_attempts_per_question=4 "
            "concurrency=%d attach_source_pdf=%s",
            len(targets),
            self.section_generation_concurrency,
            attach_source_pdf,
        )

        async def repair_target(
            target: ValidatedQuestion,
        ) -> tuple[str, ValidatedQuestion] | None:
            slot = slots_by_id.get(target.candidate.slot_id)
            if slot is None:
                return None
            texts_to_avoid = [
                text
                for slot_id, text in texts_by_slot.items()
                if slot_id != slot.slot_id
            ]
            current = target
            async with semaphore:
                for attempt in range(1, 5):
                    # Escalation ladder: attempts 1-2 retry the slot as
                    # specified, attempt 3 swaps the facet, attempt 4 swaps
                    # the topic — an unsatisfiable spec is changed, not
                    # retried forever.
                    active_slot = self._repair_slot_for_attempt(
                        slot, attempt, content_map
                    )
                    permitted_ids = [
                        chunk_id
                        for chunk_id in active_slot.evidence_chunk_ids
                        if chunk_id in evidence_chunks
                    ]
                    if not permitted_ids:
                        permitted_ids = [
                            chunk.chunk_id
                            for chunk in evidence_chunks.values()
                            if chunk.page_number in active_slot.source_pages
                        ]
                    defect_codes = [
                        finding.code for finding in current.findings
                    ]
                    repair_payload = json.dumps(
                        {
                            "attempt": attempt,
                            "defect_codes": defect_codes,
                            "repair_focus": (
                                "the slot's topic has been REPLACED because the "
                                "previous specification could not be satisfied; "
                                "ignore the earlier question's subject matter and "
                                "write a fresh question on the new locked topic, "
                                "grounded only in the evidence chunks below"
                                if active_slot.topic_id != slot.topic_id
                                else "the previous question duplicated another "
                                "question in the paper; produce a task testing a "
                                "DIFFERENT skill or fact, following the slot facet"
                                if "duplicate_question" in defect_codes
                                else (
                                    "the question MUST contain exactly four "
                                    "labelled options (A) (B) (C) (D), each on "
                                    "its own line"
                                    if "invalid_mcq_options" in defect_codes
                                    else "correct the listed findings"
                                )
                            ),
                            "subject_verification_profile": infer_subject_profile(
                                content_map
                            ).as_prompt(),
                            "locked_slots": [active_slot.model_dump(mode="json")],
                            "rejected_questions": [
                                {
                                    "candidate": current.candidate.model_dump(
                                        mode="json"
                                    ),
                                    "findings": [
                                        finding.model_dump(mode="json")
                                        for finding in current.findings
                                    ],
                                }
                            ],
                            "other_question_texts_to_avoid": texts_to_avoid,
                            "available_evidence_chunks": [
                                {
                                    "chunk_id": evidence_chunks[chunk_id].chunk_id,
                                    "original_page": evidence_chunks[
                                        chunk_id
                                    ].page_number,
                                    "text": evidence_chunks[chunk_id].text,
                                }
                                for chunk_id in permitted_ids[:3]
                            ],
                        },
                        indent=2,
                    )
                    self._planned_model_calls += 1
                    repair_batch = await self._call_with_provider_backoff(
                        operation="question_repair",
                        section_id=slot.slot_id,
                        call=lambda repair_payload=repair_payload, slot=active_slot: (
                            self.analyzer.repair_questions(
                                repair_prompt=repair_payload,
                                expected_question_count=1,
                                source_pdf_path=repair_source_pdf_path,
                                selected_page_start=manifest.selected_page_start,
                                selected_page_end=manifest.selected_page_end,
                                visual_paths=self._section_visuals([slot], manifest),
                            )
                        ),
                    )
                    candidates, missing_slot_ids = self._normalize_candidates(
                        batch=repair_batch,
                        slots=[active_slot],
                        content_map=content_map,
                        manifest=manifest,
                    )
                    deterministic = self.validator.validate(
                        active_slot, candidates[0], manifest
                    )
                    if active_slot.slot_id in missing_slot_ids:
                        deterministic = self._append_finding(
                            deterministic,
                            code="missing_repair_candidate",
                            message="repair call did not return a dedicated replacement",
                        )
                    visual_paths = self._section_visuals([active_slot], manifest)
                    self._planned_model_calls += 1
                    semantic = await self._call_with_provider_backoff(
                        operation="question_repair_review",
                        section_id=slot.slot_id,
                        call=lambda candidate=candidates[0], slot=active_slot: (
                            self.analyzer.review_question(
                                question=candidate,
                                required_bloom_level=slot.bloom_level,
                                evidence_text=self._section_evidence(
                                    [slot], content_map, manifest
                                ),
                                visual_path=visual_paths[0][1] if visual_paths else None,
                            )
                        ),
                    )
                    current = self._apply_semantic_review(deterministic, semantic)
                    logger.info(
                        "paper.repair.question_complete slot_id=%s attempt=%d "
                        "facet=%s topic=%s accepted=%s score=%s",
                        slot.slot_id,
                        attempt,
                        active_slot.facet,
                        active_slot.topic_id,
                        current.accepted,
                        current.quality_score,
                    )
                    if not self._needs_improvement(current):
                        break
            return slot.slot_id, current

        # Duplicate-flagged questions repair sequentially so each subsequent
        # repair sees the previous replacement text — two members of a
        # duplicate pair repairing in parallel can regenerate the same task.
        duplicate_targets = [
            target
            for target in targets
            if any(
                finding.code == "duplicate_question" for finding in target.findings
            )
        ]
        independent_targets = [
            target for target in targets if target not in duplicate_targets
        ]

        async def repair_duplicates_in_sequence() -> list[
            tuple[str, ValidatedQuestion] | None
        ]:
            sequential_results: list[tuple[str, ValidatedQuestion] | None] = []
            for target in duplicate_targets:
                result = await repair_target(target)
                if result is not None:
                    texts_by_slot[result[0]] = result[1].candidate.question_text
                sequential_results.append(result)
            return sequential_results

        gathered = await asyncio.gather(
            repair_duplicates_in_sequence(),
            *(repair_target(target) for target in independent_targets),
        )
        repair_results = list(gathered[0]) + list(gathered[1:])
        replacements: dict[str, ValidatedQuestion] = dict(
            result for result in repair_results if result is not None
        )

        selected_questions = [
            replacements.get(question.candidate.slot_id, question)
            for question in questions
        ]
        logger.info(
            "paper.repair.complete attempted=%d individually_reviewed=%d "
            "accepted=%d rejected=%d",
            len(replacements),
            len(replacements),
            sum(question.accepted for question in selected_questions),
            sum(not question.accepted for question in selected_questions),
        )
        return selected_questions

    async def regenerate_question(
        self,
        *,
        slot: BlueprintSlot,
        current_question: ValidatedQuestion,
        mode: str,
        faculty_comment: str,
        other_question_texts: list[str],
        content_map: ContentMap,
        manifest: DocumentManifest,
    ) -> ValidatedQuestion:
        """Regenerate one faculty-selected question without changing its blueprint slot.

        This is intentionally narrower than the automatic paper repair pass: faculty
        regeneration may improve wording or choose a different task, but it must not
        silently move the question to another topic, mark value, or cognitive level.
        """
        evidence_chunks = build_evidence_chunks(manifest)
        permitted_ids = [
            chunk_id
            for chunk_id in slot.evidence_chunk_ids
            if chunk_id in evidence_chunks
        ]
        if not permitted_ids:
            permitted_ids = [
                chunk.chunk_id
                for chunk in evidence_chunks.values()
                if chunk.page_number in slot.source_pages
            ]
        if not permitted_ids:
            raise ValueError("the question's blueprint slot has no usable source evidence")

        self._pipeline_started_at = time.perf_counter()
        self._completed_model_calls = 0
        self._planned_model_calls = 6
        if mode not in {"guided", "fresh"}:
            raise ValueError("regeneration mode must be guided or fresh")
        current = current_question
        visual_paths = self._section_visuals([slot], manifest)

        for attempt in range(1, 4):
            payload: dict[str, object] = {
                    "attempt": attempt,
                    "regeneration_mode": mode,
                    "repair_focus": (
                        "Write a completely fresh question. Do not reuse, paraphrase, "
                        "or take inspiration from the previous question; use only the "
                        "locked blueprint and permitted source evidence."
                        if mode == "fresh"
                        else (
                            "Replace this one question by following the faculty instruction "
                            "and correcting every automated-review finding. The faculty "
                            "instruction may refine wording or the assessed task, but it "
                            "cannot override the locked blueprint or source evidence."
                        )
                    ),
                    "locked_slots": [slot.model_dump(mode="json")],
                    "other_question_texts_to_avoid": (
                        other_question_texts + [current_question.candidate.question_text]
                        if mode == "fresh"
                        else other_question_texts
                    ),
                    "available_evidence_chunks": [
                        {
                            "chunk_id": evidence_chunks[chunk_id].chunk_id,
                            "original_page": evidence_chunks[chunk_id].page_number,
                            "text": evidence_chunks[chunk_id].text,
                        }
                        for chunk_id in permitted_ids[:3]
                    ],
                }
            if mode == "guided":
                payload["faculty_instruction"] = faculty_comment.strip()
                payload["question_being_replaced"] = {
                    "candidate": current.candidate.model_dump(mode="json"),
                    "findings": [
                        finding.model_dump(mode="json")
                        for finding in current.findings
                    ],
                }
            payload_text = json.dumps(
                payload,
                indent=2,
            )
            batch = await self._call_with_provider_backoff(
                operation="faculty_question_regeneration",
                section_id=slot.slot_id,
                call=lambda payload_text=payload_text: self.analyzer.repair_questions(
                    repair_prompt=payload_text,
                    expected_question_count=1,
                    source_pdf_path=None,
                    selected_page_start=manifest.selected_page_start,
                    selected_page_end=manifest.selected_page_end,
                    visual_paths=visual_paths,
                ),
            )
            candidates, missing = self._normalize_candidates(
                batch=batch,
                slots=[slot],
                content_map=content_map,
                manifest=manifest,
            )
            deterministic = self.validator.validate(slot, candidates[0], manifest)
            if slot.slot_id in missing:
                deterministic = self._append_finding(
                    deterministic,
                    code="missing_repair_candidate",
                    message="regeneration did not return a replacement for this question",
                )
            review = await self._call_with_provider_backoff(
                operation="faculty_question_regeneration_review",
                section_id=slot.slot_id,
                call=lambda candidate=candidates[0]: self.analyzer.review_question(
                    question=candidate,
                    required_bloom_level=slot.bloom_level,
                    evidence_text=self._section_evidence(
                        [slot], content_map, manifest
                    ),
                    visual_path=visual_paths[0][1] if visual_paths else None,
                ),
            )
            current = self._apply_semantic_review(deterministic, review)

            comparison_questions = [current]
            for index, text in enumerate(other_question_texts):
                comparison_questions.append(
                    current.model_copy(
                        update={
                            "candidate": current.candidate.model_copy(
                                update={
                                    "candidate_id": f"existing-question-{index}",
                                    "question_text": text,
                                }
                            )
                        }
                    )
                )
            duplicates = find_duplicate_questions(comparison_questions)
            duplicate_ids = {
                candidate_id
                for candidate_ids in duplicates.values()
                for candidate_id in candidate_ids
            }
            if current.candidate.candidate_id in duplicate_ids:
                current = self._append_duplicate_finding(current)
            if not self._needs_improvement(current):
                break

        return current

    async def _generate_and_review_section(
        self,
        *,
        section_id: str,
        slots: list[BlueprintSlot],
        content_map: ContentMap,
        manifest: DocumentManifest,
        prior_question_texts: list[str] | None = None,
        paper_plan_text: str | None = None,
    ) -> list[ValidatedQuestion]:
        """Generate one section, then review it immediately in a second call."""
        deterministic_results = await self._generate_section(
            section_id=section_id,
            slots=slots,
            content_map=content_map,
            manifest=manifest,
            prior_question_texts=prior_question_texts,
            paper_plan_text=paper_plan_text,
        )
        candidates = [result.candidate for result in deterministic_results]
        slots_prompt = json.dumps(
            [slot.model_dump(mode="json") for slot in slots],
            indent=2,
        )
        review_batch = await self._call_with_provider_backoff(
            operation="section_review",
            section_id=section_id,
            call=lambda: self.analyzer.review_section(
                section_id=section_id,
                slots_prompt=slots_prompt,
                questions=candidates,
                evidence_text=self._section_evidence(
                    slots,
                    content_map,
                    manifest,
                    max_chunks_per_slot=5,
                    excerpt_characters=1200,
                ),
                visual_paths=self._section_visuals(slots, manifest),
            ),
        )
        reviews = self._normalize_reviews(review_batch.reviews, candidates)
        reviewed = [
            self._apply_semantic_review(result, review)
            for result, review in zip(deterministic_results, reviews, strict=True)
        ]
        logger.info(
            "paper.section.reviewed section_id=%s returned=%d accepted=%d rejected=%d",
            section_id,
            len(review_batch.reviews),
            sum(question.accepted for question in reviewed),
            sum(not question.accepted for question in reviewed),
        )
        return reviewed

    async def _generate_section(
        self,
        *,
        section_id: str,
        slots: list[BlueprintSlot],
        content_map: ContentMap,
        manifest: DocumentManifest,
        prior_question_texts: list[str] | None = None,
        paper_plan_text: str | None = None,
    ) -> list[ValidatedQuestion]:
        section_started = time.perf_counter()
        logger.info(
            "paper.section.start section_id=%s questions=%d",
            section_id,
            len(slots),
        )
        slots_prompt = json.dumps(
            [slot.model_dump(mode="json") for slot in slots],
            indent=2,
        )
        evidence_text = self._section_evidence(slots, content_map, manifest)
        if prior_question_texts:
            evidence_text += (
                "\n\nAlready generated questions from earlier sections. Do not test "
                "the same learning objective with equivalent wording or a cosmetically "
                "changed scenario:\n"
                + json.dumps(prior_question_texts, indent=2)
            )
        elif paper_plan_text:
            evidence_text += (
                "\n\nPaper-wide slot plan. Keep this section's learning objectives "
                "distinct from the other planned slots:\n"
                + paper_plan_text
            )
        visual_paths = self._section_visuals(slots, manifest)

        batch = await self._call_with_provider_backoff(
            operation="section_generate",
            section_id=section_id,
            call=lambda: self.analyzer.generate_section(
                section_id=section_id,
                expected_question_count=len(slots),
                slots_prompt=slots_prompt,
                evidence_text=evidence_text,
                visual_paths=visual_paths,
            ),
        )
        candidates, missing_slot_ids = self._normalize_candidates(
            batch=batch,
            slots=slots,
            content_map=content_map,
            manifest=manifest,
        )
        self._log_generated_questions(section_id, slots, candidates)
        deterministic_results = [
            self.validator.validate(slot, candidate, manifest)
            for slot, candidate in zip(slots, candidates, strict=True)
        ]
        deterministic_results = [
            self._append_finding(
                result,
                code="missing_batch_candidate",
                message="section generation did not return a dedicated candidate",
            )
            if result.candidate.slot_id in missing_slot_ids
            else result
            for result in deterministic_results
        ]
        logger.info(
            "paper.section.generated section_id=%s returned=%d normalized=%d "
            "deterministic_passed=%d",
            section_id,
            len(batch.questions),
            len(candidates),
            sum(result.accepted for result in deterministic_results),
        )

        logger.info(
            "paper.section.complete section_id=%s deterministic_passed=%d "
            "deterministic_failed=%d "
            "duration_seconds=%.2f",
            section_id,
            sum(question.accepted for question in deterministic_results),
            sum(not question.accepted for question in deterministic_results),
            time.perf_counter() - section_started,
        )
        return deterministic_results

    @staticmethod
    def _paper_generation_plan(
        slots: list[BlueprintSlot],
        content_map: ContentMap,
    ) -> str:
        topics = {topic.topic_id: topic.name for topic in content_map.topics}
        return json.dumps(
            [
                {
                    "slot_id": slot.slot_id,
                    "section_id": slot.section_id,
                    "topic": topics.get(slot.topic_id, slot.topic_id),
                    "question_kind": slot.question_kind.value,
                    "marks": slot.marks,
                    "bloom_level": slot.bloom_level.value,
                }
                for slot in slots
            ],
            indent=2,
        )

    @staticmethod
    def _section_evidence(
        slots: list[BlueprintSlot],
        content_map: ContentMap,
        manifest: DocumentManifest,
        *,
        max_chunks_per_slot: int = 3,
        excerpt_characters: int = 800,
    ) -> str:
        topics = {topic.topic_id: topic for topic in content_map.topics}
        permission_lines: list[str] = []
        chunks = build_evidence_chunks(manifest)
        selected_by_slot: dict[str, list[str]] = {}
        for slot in slots:
            topic = topics[slot.topic_id]
            allowed_chunk_ids = [
                chunk_id
                for chunk_id in slot.evidence_chunk_ids
                if chunk_id in chunks
            ]
            if not allowed_chunk_ids:
                allowed_chunk_ids = [
                    chunk.chunk_id
                    for chunk in chunks.values()
                    if chunk.page_number in slot.source_pages
                ]
            selected_by_slot[slot.slot_id] = allowed_chunk_ids[:max_chunks_per_slot]
            permission_lines.append(
                f"{slot.slot_id}: topic={topic.name}; unit={topic.unit}; "
                f"source_pages={slot.source_pages}; "
                f"allowed_chunk_ids={selected_by_slot[slot.slot_id]}"
            )
        selected_ids = list(
            dict.fromkeys(
                chunk_id
                for slot in slots
                for chunk_id in selected_by_slot[slot.slot_id]
            )
        )
        chunk_text = "\n\n".join(
            f"[chunk_id={chunk.chunk_id} original_page={chunk.page_number}]\n"
            f"{chunk.text[:excerpt_characters]}"
            for chunk_id in selected_ids
            if (chunk := chunks.get(chunk_id)) is not None
        )
        return (
            f"Subject verification profile:\n"
            f"{infer_subject_profile(content_map).as_prompt()}\n\n"
            "Slot-specific evidence permissions:\n"
            + "\n".join(permission_lines)
            + "\n\n"
            + (
                "For each candidate, use only the chunk_id values listed in that "
                "slot's allowed_chunk_ids. Never use another slot's evidence, even "
                "when it appears elsewhere in this section.\n\n"
            )
            + chunk_text
        )

    @staticmethod
    def _section_visuals(
        slots: list[BlueprintSlot],
        manifest: DocumentManifest,
    ) -> list[tuple[str, str]]:
        assets = {asset.asset_id: asset for asset in manifest.visual_assets}
        visual_ids = list(
            dict.fromkeys(
                slot.visual_asset_id
                for slot in slots
                if slot.visual_asset_id is not None
            )
        )
        return [
            (asset_id, assets[asset_id].image_path)
            for asset_id in visual_ids
            if asset_id in assets
        ]

    @staticmethod
    def _normalize_candidates(
        *,
        batch: SectionQuestionBatch,
        slots: list[BlueprintSlot],
        content_map: ContentMap,
        manifest: DocumentManifest,
    ) -> tuple[list[QuestionCandidate], set[str]]:
        topics = {topic.topic_id: topic for topic in content_map.topics}
        by_slot = {candidate.slot_id: candidate for candidate in batch.questions}
        unused = [
            candidate
            for candidate in batch.questions
            if candidate.slot_id not in {slot.slot_id for slot in slots}
        ]
        normalized: list[QuestionCandidate] = []
        missing: set[str] = set()

        for slot in slots:
            candidate = by_slot.get(slot.slot_id)
            if candidate is None and unused:
                candidate = unused.pop(0)
            if candidate is None:
                missing.add(slot.slot_id)
                topic = topics[slot.topic_id]
                excerpts = [
                    page.text[:400]
                    for page in manifest.pages
                    if page.page_number in topic.source_pages
                ][:2]
                candidate = QuestionCandidate(
                    candidate_id=f"{slot.slot_id}-missing",
                    slot_id=slot.slot_id,
                    question_text="Question generation was incomplete for this slot.",
                    answer="No answer was generated.",
                    marks=slot.marks,
                    bloom_level=slot.bloom_level,
                    bloom_justification="No Bloom justification was generated.",
                    marking_scheme=[
                        MarkingCriterion(
                            criterion="Requires faculty replacement",
                            marks=slot.marks,
                        )
                    ],
                    evidence=SourceEvidence(
                        page_numbers=topic.source_pages,
                        excerpts=excerpts or ["No source excerpt returned."],
                        visual_asset_id=slot.visual_asset_id,
                    ),
                    confidence=0,
                )
            candidate = attach_verified_evidence(candidate, manifest)
            question_text = PaperGenerationPipeline._normalize_question_format(
                slot,
                PaperGenerationPipeline._clean_generated_text(
                    candidate.question_text,
                    remove_question_number=True,
                ),
            )
            normalized.append(
                candidate.model_copy(
                    update={
                        "candidate_id": f"{slot.slot_id}-batch",
                        "slot_id": slot.slot_id,
                        "question_text": question_text,
                        "marks": slot.marks,
                        "bloom_level": slot.bloom_level,
                        "answer": PaperGenerationPipeline._clean_generated_text(
                            candidate.answer,
                        ),
                    }
                )
            )
        return normalized, missing

    @staticmethod
    def _normalize_question_format(slot: BlueprintSlot, value: str) -> str:
        """Apply backend-owned labels while preserving model-authored content."""
        text = value.strip()
        if slot.question_kind == QuestionKind.ASSERTION_REASON:
            first_option = re.search(
                r"(?im)^\s*(?:\([A-D]\)|[A-D][\).:])\s+",
                text,
            )
            stem = text[: first_option.start()].rstrip() if first_option else text
            text = stem + (
                "\n(A) Both Assertion (A) and Reason (R) are true and Reason (R) "
                "is the correct explanation of Assertion (A)."
                "\n(B) Both Assertion (A) and Reason (R) are true, but Reason (R) "
                "is not the correct explanation of Assertion (A)."
                "\n(C) Assertion (A) is true, but Reason (R) is false."
                "\n(D) Assertion (A) is false, but Reason (R) is true."
            )
        elif slot.question_kind == QuestionKind.MULTIPLE_CHOICE:
            option_index = 0

            def canonical_option(match: re.Match[str]) -> str:
                nonlocal option_index
                if option_index >= 4:
                    return match.group(0)
                label = "ABCD"[option_index]
                option_index += 1
                return f"({label}) {match.group(1).strip()}"

            text = re.sub(
                r"(?im)^\s*(?:\([A-Da-d]\)|[A-Da-d][\).:])\s*(.+)$",
                canonical_option,
                text,
            )

        if slot.has_internal_choice:
            text = re.sub(r"(?im)^\s*or\s*$", "OR", text)
            if re.search(r"(?im)^\s*(?:OR\s+)?option\s*\(?b\)?\s*[:.\-)]", text):
                if re.search(r"(?im)^\s*OR\s*$", text):
                    text = re.sub(
                        r"(?im)^\s*option\s*\(?b\)?\s*[:.\-)]\s*", "", text, count=1
                    )
                else:
                    text = re.sub(
                        r"(?im)^\s*(?:OR\s+)?option\s*\(?b\)?\s*[:.\-)]\s*",
                        "OR\n",
                        text,
                        count=1,
                    )
                text = re.sub(
                    r"(?im)^\s*option\s*\(?a\)?\s*[:.\-)]\s*", "", text, count=1
                )
            if slot.internal_choice_scope == "final_subpart":
                text = re.sub(
                    r"(?im)^\s*\(iii\)\s*(?:\r?\n\s*)?(?:either\s*:?\s*)?"
                    r"(?:\r?\n\s*)?\(a\)\s*",
                    "(iii)(a) ",
                    text,
                    count=1,
                )
                text = re.sub(
                    r"(?im)(^\s*OR\s*$\s*)\(b\)\s*",
                    r"\1(iii)(b) ",
                    text,
                    count=1,
                )
                text = re.sub(
                    r"(?im)(^\s*OR\s*$\s*)\(iii\)\s*\(b\)\s*",
                    r"\1(iii)(b) ",
                    text,
                    count=1,
                )
                text = PaperGenerationPipeline._canonicalize_final_subpart_choice(
                    text
                )
        return text.strip()

    @staticmethod
    def _canonicalize_final_subpart_choice(text: str) -> str:
        """Force the (iii)(a) / OR / (iii)(b) layout on model label variants.

        Handles alternatives the model labels as a bare "(a)" on its own line
        after an "(iii)" stem, "OR Option (a)/(b)" inline labels, and
        alternatives with no letter labels at all. Canonical text passes
        through unchanged.
        """
        text = re.sub(
            r"(?im)^\s*\(iii\)\s*(?:OR\s+)?option\s*\(?a\)?\s*[:.\-)]?\s*",
            "(iii)(a) ",
            text,
            count=1,
        )
        text = re.sub(
            r"(?im)^\s*OR\s+option\s*\(?b\)?\s*[:.\-)]?\s*",
            "OR\n(iii)(b) ",
            text,
            count=1,
        )
        parts = re.split(r"(?im)^\s*OR\s*$", text)
        if len(parts) != 2:
            return text
        first, second = parts
        if not re.search(r"(?im)^\s*\(iii\)\s*\(a\)", first):
            relabeled, count = re.subn(
                r"(?im)^\s*\(a\)\s*", "(iii)(a) ", first, count=1
            )
            if count:
                first = relabeled
            else:
                first = re.sub(
                    r"(?im)^\s*\(iii\)\s*(?!\()",
                    "(iii)(a) ",
                    first,
                    count=1,
                )
        if not re.search(r"(?im)^\s*\(iii\)\s*\(b\)", second):
            relabeled, count = re.subn(
                r"(?im)^\s*\(b\)\s*", "(iii)(b) ", second, count=1
            )
            if count:
                second = relabeled
            else:
                second = "(iii)(b) " + second.lstrip()
        return f"{first.rstrip()}\nOR\n{second.lstrip()}"

    @staticmethod
    def _clean_generated_text(
        value: str,
        *,
        remove_question_number: bool = False,
    ) -> str:
        cleaned = value.replace("\\r\\n", "\n").replace("\\n", "\n")

        def matrix_text(match: re.Match[str]) -> str:
            body = re.sub(r"\\{2,}", "; ", match.group(1))
            body = body.replace("&", " ")
            rows = [" ".join(row.split()) for row in body.split(";") if row.strip()]
            return "[" + "; ".join(rows) + "]"

        cleaned = re.sub(
            r"\\*begin\{(?:bmatrix|pmatrix|matrix|vmatrix)\}"
            r"(.*?)\\*end\{(?:bmatrix|pmatrix|matrix|vmatrix)\}",
            matrix_text,
            cleaned,
            flags=re.DOTALL,
        )

        def pipe_matrix_text(match: re.Match[str]) -> str:
            rows = [" ".join(row.split()) for row in match.groups() if row]
            return "[" + "; ".join(rows) + "]"

        # Collapse 2-3 row ASCII pipe matrices into inline bracket form. Each
        # row must hold at least two entries, so absolute values like |A| on
        # consecutive lines never match.
        matrix_row = r"\|[ \t]*([^|\n]+?[ \t]+[^|\n]+?)[ \t]*\|"
        cleaned = re.sub(
            rf"{matrix_row}[ \t]*\n\s*{matrix_row}(?:[ \t]*\n\s*{matrix_row})?",
            pipe_matrix_text,
            cleaned,
        )

        def fraction_text(match: re.Match[str]) -> str:
            numerator, denominator = (part.strip() for part in match.groups())
            atomic = re.compile(r"^[A-Za-z0-9α-ωΑ-Ω.+-]+$")
            if atomic.fullmatch(numerator) and atomic.fullmatch(denominator):
                return f"{numerator}/{denominator}"
            return f"({numerator})/({denominator})"

        cleaned = re.sub(
            r"\\frac\{([^{}]+)\}\{([^{}]+)\}",
            fraction_text,
            cleaned,
        )
        cleaned = re.sub(
            r"\\text\{([^{}]+)\}",
            r"\1",
            cleaned,
        )
        cleaned = re.sub(
            r"(?:visual\s+asset|diagram|figure)\s*\(?p\d+-image-\d+\)?",
            "provided figure",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"\(?p\d+-image-\d+\)?",
            "provided figure",
            cleaned,
            flags=re.IGNORECASE,
        )
        replacements = {
            "\\infty": "∞",
            "\\rightarrow": "→",
            "\\Rightarrow": "⇒",
            "\\implies": "⇒",
            "\\to": "→",
            "\\times": "×",
            "\\cdot": "·",
            "\\leq": "≤",
            "\\le": "≤",
            "\\geq": "≥",
            "\\ge": "≥",
            "\\neq": "≠",
            "\\pm": "±",
            "\\equiv": "≡",
            "\\bmod": "mod",
            "\\mod": "mod",
            "\\phi": "φ",
            "\\mu": "μ",
            "\\tau": "τ",
            "\\sigma": "σ",
            "\\theta": "θ",
            "\\alpha": "α",
            "\\beta": "β",
            "\\gamma": "γ",
            "\\delta": "δ",
            "\\lambda": "λ",
            "\\tan": "tan ",
            "\\cot": "cot ",
            "\\sin": "sin ",
            "\\cos": "cos ",
            "\\log": "log",
            "\\ln": "ln",
            "\\circ": "°",
            "\\sqrt": "√",
            "\\mathbb{R}": "ℝ",
            "\\mathbb{N}": "ℕ",
            "\\mathbb{Q}": "ℚ",
            "\\mathbb{Z}": "ℤ",
            "\\Z": "ℤ",
            "\\eq": "=",
            "\\div": "÷",
            "\\in": "∈",
            "\\subset": "⊂",
            "\\cup": "∪",
            "\\cap": "∩",
            "\\left": "",
            "\\right": "",
            "\\(": "",
            "\\)": "",
            "\\[": "",
            "\\]": "",
            "$": "",
        }
        for source, replacement in replacements.items():
            cleaned = cleaned.replace(source, replacement)
        unicode_escapes = {
            "2264": "≤",
            "2265": "≥",
            "2260": "≠",
            "221e": "∞",
            "2192": "→",
            "03b1": "α",
            "03b2": "β",
            "03b8": "θ",
        }
        cleaned = re.sub(
            r"(?i)\\?u(2264|2265|2260|221e|2192|03b1|03b2|03b8)\b",
            lambda match: unicode_escapes[match.group(1).lower()],
            cleaned,
        )
        cleaned = re.sub(r"\^\s*°", "°", cleaned)
        cleaned = re.sub(r"\^\{([^{}]+)\}", r"^(\1)", cleaned)
        cleaned = re.sub(r"_\{([^{}]+)\}", r"_\1", cleaned)
        cleaned = re.sub(
            r"(?i)\b(tan|cot|sin|cos)\s*(alpha|beta|theta)\b",
            lambda match: f"{match.group(1)} "
            + {"alpha": "α", "beta": "β", "theta": "θ"}[
                match.group(2).lower()
            ],
            cleaned,
        )
        cleaned = re.sub(r"(?i)\bto\s+∈fty\b", "→ ∞", cleaned)
        cleaned = cleaned.replace("**", "").replace("__", "")
        if remove_question_number:
            cleaned = re.sub(
                r"^\s*(?:question\s*)?q?\d+[\s.:)-]+",
                "",
                cleaned,
                count=1,
                flags=re.IGNORECASE,
            )
        return cleaned.strip()

    @staticmethod
    def _normalize_reviews(
        reviews: list[SectionQuestionReview],
        candidates: list[QuestionCandidate],
    ) -> list[SectionQuestionReview | None]:
        by_candidate = {review.candidate_id: review for review in reviews}
        unused = [
            review
            for review in reviews
            if review.candidate_id
            not in {candidate.candidate_id for candidate in candidates}
        ]
        normalized: list[SectionQuestionReview | None] = []
        for candidate in candidates:
            review = by_candidate.get(candidate.candidate_id)
            if review is None and unused:
                review = unused.pop(0)
            normalized.append(review)
        return normalized

    def _apply_semantic_review(
        self,
        deterministic: ValidatedQuestion,
        review: SemanticReview | SectionQuestionReview | None,
    ) -> ValidatedQuestion:
        if review is None:
            return self._append_finding(
                deterministic,
                code="missing_semantic_review",
                message="independent review did not return a review for this question",
            )

        findings: list[ValidationFinding] = []
        checks = {
            "not_grounded": review.grounded_in_evidence,
            "incorrect_answer": review.answer_correct,
            "unclear_wording": review.wording_clear,
            "visual_inconsistency": review.visual_consistent,
            "subject_accuracy": review.subject_accuracy,
            "difficulty_mismatch": review.difficulty_appropriate,
            "invalid_marking_scheme": review.marking_scheme_valid,
            "invalid_options": review.options_valid,
            "invalid_internal_choice": review.internal_choice_valid,
            "low_pedagogical_quality": review.pedagogical_quality,
        }
        if deterministic.candidate.evidence.visual_asset_id:
            checks["visual_not_necessary"] = review.visual_necessary
        problem_reasons = list(
            dict.fromkeys(
                reason.strip()
                for reason in review.reasons
                if reason.strip() and not self._is_positive_review_reason(reason)
            )
        )
        failed_index = 0
        for code, passed in checks.items():
            if not passed:
                joined_reasons = "; ".join(problem_reasons)
                if len(joined_reasons) > 500:
                    joined_reasons = joined_reasons[:500].rstrip() + " …"
                findings.append(
                    ValidationFinding(
                        code=code,
                        severity=ValidationSeverity.ERROR,
                        message=(
                            joined_reasons
                            if failed_index == 0 and joined_reasons
                            else code.replace("_", " ")
                        ),
                    )
                )
                failed_index += 1
        if review.confidence < 0.85:
            findings.append(
                ValidationFinding(
                    code="review_confidence",
                    severity=ValidationSeverity.WARNING,
                    message=(
                        f"independent review confidence {review.confidence:.2f} "
                        "is below 0.85"
                    ),
                )
            )
        if review.quality_score < self.minimum_final_quality_score:
            findings.append(
                ValidationFinding(
                    code="quality_score_below_threshold",
                    severity=ValidationSeverity.WARNING,
                    message=(
                        f"final quality score {review.quality_score}/100 is below 85"
                        if self.minimum_final_quality_score == 85
                        else (
                            f"final quality score {review.quality_score}/100 is below "
                            f"{self.minimum_final_quality_score}"
                        )
                    ),
                )
            )
        requested_bloom = deterministic.candidate.bloom_level
        observed_bloom = review.observed_bloom_level
        if observed_bloom is None and not review.bloom_level_correct:
            # Reviewer flagged a mismatch without naming the level it saw; keep the
            # signal rather than silently recording the question as on-target.
            findings.append(
                ValidationFinding(
                    code="bloom_level_unverified",
                    severity=ValidationSeverity.WARNING,
                    message=(
                        f"reviewer disputed the {requested_bloom.value} level but did "
                        "not report the level it observed"
                    ),
                )
            )
        elif observed_bloom is not None and observed_bloom != requested_bloom:
            levels = list(BloomLevel)
            distance = levels.index(observed_bloom) - levels.index(requested_bloom)
            steps = abs(distance)
            findings.append(
                ValidationFinding(
                    code="bloom_level_deviation",
                    severity=ValidationSeverity.WARNING,
                    message=(
                        f"question demands {observed_bloom.value}, "
                        f"{steps} step{'' if steps == 1 else 's'} "
                        f"{'above' if distance > 0 else 'below'} the "
                        f"{requested_bloom.value} level the blueprint requested; "
                        "reported for faculty review, not a defect"
                    ),
                )
            )
        return deterministic.model_copy(
            update={
                "accepted": deterministic.accepted
                and not any(
                    finding.severity == ValidationSeverity.ERROR
                    for finding in findings
                ),
                "findings": deterministic.findings + findings,
                "quality_score": review.quality_score,
                "observed_bloom_level": observed_bloom,
            }
        )

    @staticmethod
    def _repair_slot_for_attempt(
        slot: BlueprintSlot,
        attempt: int,
        content_map: ContentMap,
    ) -> BlueprintSlot:
        """Escalate the repair target: same spec, then new facet, then new topic."""
        if attempt <= 2:
            return slot
        try:
            facet_index = FACET_CYCLE.index(slot.facet or "")
        except ValueError:
            facet_index = -1
        if attempt == 3:
            return slot.model_copy(
                update={"facet": FACET_CYCLE[(facet_index + 1) % len(FACET_CYCLE)]}
            )
        alternates = [
            topic
            for topic in content_map.topics
            if topic.topic_id != slot.topic_id and topic.evidence_chunk_ids
        ]
        # Visual slots stay on their topic — the verified figure is topic-bound.
        if slot.requires_visual or not alternates:
            return slot.model_copy(
                update={"facet": FACET_CYCLE[(facet_index + 2) % len(FACET_CYCLE)]}
            )
        # Spread swaps across the alternates instead of sending every slot in the
        # paper to whichever topic happens to hold the most chunks — that collapse
        # both defeats the facet cycle's duplicate defence and buries one topic.
        ranked = sorted(
            alternates,
            key=lambda item: (-len(item.evidence_chunk_ids), item.topic_id),
        )
        offset = sum(ord(character) for character in slot.slot_id)
        topic = ranked[offset % len(ranked)]
        return slot.model_copy(
            update={
                "topic_id": topic.topic_id,
                "unit": topic.unit,
                "source_pages": topic.source_pages,
                "evidence_chunk_ids": topic.evidence_chunk_ids[:3],
                "facet": FACET_CYCLE[(facet_index + 1) % len(FACET_CYCLE)],
            }
        )

    @staticmethod
    def _is_positive_review_reason(reason: str) -> bool:
        """Drop reviewer notes that record passing checks rather than defects.

        Reviewers sometimes dump their full rubric into `reasons`, prefixing
        entries with labels like "ANSWER VERIFICATION: Correct." or
        "MARKING SCHEME: Appropriate." — only actual defects should reach
        faculty-facing findings.
        """
        positive = (
            r"(supported|grounded|correct|clear|consistent|matches|appropriate|"
            r"valid|good|strong|sound|confirmed|accurate|acceptable|verified|"
            r"well[- ](?:structured|designed|calibrated|scaffolded)|"
            r"no (?:issues|defects|errors)|passes|"
            r"(?:all|both|each)\b[\w\s,()'./-]{0,80}?"
            r"\b(?:correct|verified|grounded|valid|accurate|sound|supported))"
        )
        label = r"(?:[A-Za-z][A-Za-z0-9 /()'&_-]{0,60}[:–—-]\s*)?"
        return bool(re.match(rf"(?i)^\s*{label}{positive}\b", reason))

    def _needs_improvement(self, question: ValidatedQuestion) -> bool:
        return (
            not question.accepted
            or (
                question.quality_score is not None
                and question.quality_score < self.minimum_final_quality_score
            )
        )

    @staticmethod
    def _log_generated_questions(
        section_id: str,
        slots: list[BlueprintSlot],
        candidates: list[QuestionCandidate],
    ) -> None:
        enabled = os.getenv("LOG_GENERATED_QUESTIONS", "true").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if not enabled:
            return
        logger.info(
            "paper.questions.section_start section_id=%s count=%d",
            section_id,
            len(candidates),
        )
        for slot, candidate in zip(slots, candidates, strict=True):
            logger.info(
                "paper.question.generated number=%s slot_id=%s marks=%d bloom=%s\n%s",
                slot.question_number,
                slot.slot_id,
                candidate.marks,
                candidate.bloom_level.value,
                candidate.question_text.strip(),
            )
        logger.info("paper.questions.section_end section_id=%s", section_id)

    async def _call_with_provider_backoff(
        self,
        *,
        operation: str,
        section_id: str,
        call: Callable[[], Awaitable[ResultT]],
    ) -> ResultT:
        for provider_attempt in range(1, self.provider_attempts + 1):
            await self._wait_for_request_slot()
            request_started = time.perf_counter()
            logger.info(
                "paper.model_call.start operation=%s section_id=%s attempt=%d "
                "progress=%d/%d",
                operation,
                section_id,
                provider_attempt,
                self._completed_model_calls,
                self._planned_model_calls,
            )
            try:
                result = await call()
                request_duration = time.perf_counter() - request_started
                self._completed_model_calls += 1
                elapsed = time.perf_counter() - self._pipeline_started_at
                average = elapsed / self._completed_model_calls
                remaining_calls = max(
                    self._planned_model_calls - self._completed_model_calls,
                    0,
                )
                estimated_remaining = average * remaining_calls
                logger.info(
                    "paper.model_call.complete operation=%s section_id=%s "
                    "duration_seconds=%.2f progress=%d/%d percent=%.1f "
                    "elapsed_seconds=%.2f estimated_remaining_seconds=%.2f",
                    operation,
                    section_id,
                    request_duration,
                    self._completed_model_calls,
                    self._planned_model_calls,
                    (
                        self._completed_model_calls
                        / max(self._planned_model_calls, 1)
                        * 100
                    ),
                    elapsed,
                    estimated_remaining,
                )
                return result
            except Exception as exc:
                request_duration = time.perf_counter() - request_started
                transient = is_transient_model_failure(exc)
                diagnostics = summarize_model_failure(exc)
                if not transient or provider_attempt >= self.provider_attempts:
                    logger.error(
                        "paper.provider.failed operation=%s section_id=%s attempt=%d "
                        "duration_seconds=%.2f transient=%s errors=%s",
                        operation,
                        section_id,
                        provider_attempt,
                        request_duration,
                        transient,
                        diagnostics,
                    )
                    raise
                delay = float(2 ** (provider_attempt - 1))
                logger.warning(
                    "paper.provider.retry operation=%s section_id=%s attempt=%d "
                    "duration_seconds=%.2f delay_seconds=%.1f errors=%s",
                    operation,
                    section_id,
                    provider_attempt,
                    request_duration,
                    delay,
                    diagnostics,
                )
                await asyncio.sleep(delay)
        raise RuntimeError("provider retry loop ended unexpectedly")

    async def _wait_for_request_slot(self) -> None:
        async with self._request_start_lock:
            loop = asyncio.get_running_loop()
            elapsed = loop.time() - self._last_request_started_at
            remaining = self.request_interval_seconds - elapsed
            if remaining > 0:
                await asyncio.sleep(remaining)
            self._last_request_started_at = loop.time()

    @staticmethod
    def _append_finding(
        question: ValidatedQuestion,
        *,
        code: str,
        message: str,
    ) -> ValidatedQuestion:
        finding = ValidationFinding(
            code=code,
            severity=ValidationSeverity.ERROR,
            message=message,
        )
        return question.model_copy(
            update={
                "accepted": False,
                "findings": question.findings + [finding],
            }
        )

    @staticmethod
    def _append_duplicate_finding(question: ValidatedQuestion) -> ValidatedQuestion:
        finding = ValidationFinding(
            code="duplicate_question",
            severity=ValidationSeverity.ERROR,
            message="question duplicates another question in the paper",
        )
        return question.model_copy(
            update={
                "accepted": False,
                "findings": question.findings + [finding],
            }
        )


async def generate_paper_sets(
    *,
    analyzer: "DocumentAnalyzer",
    pattern: PaperPattern,
    content_map: ContentMap,
    manifest: DocumentManifest,
    set_count: int,
) -> tuple[list[tuple[PaperBlueprint, ExamPaper]], list[str]]:
    """Generate interchangeable sets of one paper, plus any cross-set duplicates.

    Exam cells hand out several sets of the same paper so neighbours cannot copy.
    The sets must be equivalent — same topics, marks, cognitive levels and outcome
    coverage — while asking different questions, so each set is planned from the
    same content map with its facet cycle offset. Sets are generated sequentially
    because each is checked against the ones before it.

    Returns the (blueprint, paper) pairs and a warning per question that repeats
    across sets, which no single paper's duplicate detector can see.
    """
    if set_count < 1:
        raise ValueError("set_count must be at least 1")
    results: list[tuple[PaperBlueprint, ExamPaper]] = []
    for index in range(set_count):
        blueprint = BlueprintBuilder().build(
            pattern, content_map, manifest, set_index=index
        )
        label = chr(ord("A") + index) if set_count > 1 else None
        paper = await PaperGenerationPipeline(analyzer).generate(
            pattern=pattern,
            content_map=content_map,
            manifest=manifest,
            blueprint=blueprint,
            set_label=label,
        )
        results.append((blueprint, paper))
        logger.info(
            "paper.sets.generated set=%s accepted=%d total=%d",
            label or "-",
            sum(question.accepted for question in paper.questions),
            len(paper.questions),
        )

    warnings: list[str] = []
    if len(results) > 1:
        combined = [
            question for _, paper in results for question in paper.questions
        ]
        for stem, candidate_ids in find_duplicate_questions(combined).items():
            owners = sorted(
                {identifier.split("-", 1)[0] for identifier in candidate_ids}
            )
            warnings.append(
                f"the same question appears in more than one set "
                f"({', '.join(owners)}): {stem[:80]}"
            )
    return results, warnings
