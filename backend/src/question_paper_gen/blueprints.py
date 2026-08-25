from __future__ import annotations

import logging
import math
from collections import Counter

from .evidence import build_evidence_chunks
from .models import (
    BloomLevel,
    BlueprintSlot,
    ContentMap,
    DocumentManifest,
    PaperBlueprint,
    PaperPattern,
    QuestionKind,
    Topic,
)

logger = logging.getLogger("uvicorn.error")

# Distinct angles a question can take on one topic. Slots sharing a topic are
# assigned different facets round-robin, so they cannot reduce to the same
# canonical task ("find the adjoint of ..." x4).
#: How far above a topic's reported ceiling a slot may still ask. One level keeps
#: papers examinable on expository sources while staying within what the reviewer
#: can verify; more than that invents demand the source cannot support.
BLOOM_STRETCH_LEVELS = 1

FACET_CYCLE: tuple[str, ...] = (
    "direct computation or procedure on a fresh example",
    "conceptual definition, statement, or why the property holds",
    "an original real-world application scenario that requires the concept",
    "inverse or error reasoning: find the unknown that makes a property hold, "
    "or diagnose why a plausible claim or worked step is wrong",
    "connection or comparison between this topic and another concept from the "
    "same source material",
    "interpretation of a computed result: what the value means and what "
    "follows from it",
)


class BlueprintError(ValueError):
    pass


class BlueprintBuilder:
    """Create one shared, deterministic plan before any question is generated."""

    def build(
        self,
        pattern: PaperPattern,
        content: ContentMap,
        manifest: DocumentManifest,
        set_index: int = 0,
    ) -> PaperBlueprint:
        """Plan one paper.

        `set_index` produces alternate sets of the same paper: every slot keeps its
        topic, marks and Bloom level, so the sets are interchangeable for the exam
        cell, but each slot starts at a different point in the facet cycle. Two sets
        therefore ask genuinely different tasks about the same syllabus rather than
        reshuffling one set of questions.
        """
        logger.info(
            "blueprint.plan.start document_id=%s pattern=%s topics=%d "
            "eligible_visuals=%d",
            manifest.document_id,
            pattern.pattern_id,
            len(content.topics),
            len(manifest.eligible_visuals()),
        )
        if not manifest.quality.passed:
            raise BlueprintError(
                "document failed quality checks: " + "; ".join(manifest.quality.errors)
            )
        if not content.topics:
            raise BlueprintError("content map must contain at least one topic")

        warnings: list[str] = []
        slots: list[BlueprintSlot] = []
        total_slots = sum(section.question_count for section in pattern.sections)
        # Each topic supports len(FACET_CYCLE) distinct angles, each angle in
        # roughly two question formats — and every verified subtopic adds the
        # same again, so coarse topic granularity does not fail a rich source.
        subtopic_total = sum(len(topic.subtopics) for topic in content.topics)
        distinct_capacity = (
            (len(content.topics) + subtopic_total) * len(FACET_CYCLE) * 2
        )
        if total_slots > distinct_capacity:
            raise BlueprintError(
                f"the selected pages support roughly {distinct_capacity} distinct "
                f"questions across {len(content.topics)} topic(s) and "
                f"{subtopic_total} subtopic(s), but this paper pattern needs "
                f"{total_slots}. Select a wider page range (for example, "
                "additional chapters) so questions do not repeat."
            )
        topic_scores = self._topic_richness(content, manifest)
        topic_quotas, omitted_topic_ids = self._topic_quotas(
            content,
            topic_scores,
            total_slots,
        )
        if omitted_topic_ids:
            warnings.append(
                f"{len(omitted_topic_ids)} lower-evidence topic(s) could not receive "
                f"a slot because the paper has only {total_slots} questions"
            )
        eligible_visuals = manifest.eligible_visuals()
        used_visual_ids: set[str] = set()
        topic_usage: Counter[str] = Counter()
        bloom_adjustments: Counter[tuple[BloomLevel, BloomLevel]] = Counter()
        global_number = 1
        for section in pattern.sections:
            section_visuals_remaining = section.visual_question_count
            for section_index in range(section.question_count):
                if section.question_number_prefix is not None:
                    printed_number = (
                        f"{section.question_number_prefix}"
                        f"{(section.question_number_start or 1) + section_index}"
                    )
                else:
                    printed_number = str(global_number)
                requested_bloom = section.bloom_sequence[section_index]
                # Prefer topics traced to the PDF uploaded in this row. If the
                # model did not return a separately tagged topic for a row, use
                # the complete uploaded source pool instead of rejecting the
                # paper. The faculty-selected files are authoritative; chapter
                # names and printed unit numbers inside a PDF are not validated.
                unit_pool = content.topics
                slot_unit = section.unit_number
                if section.unit_cycle:
                    slot_unit = section.unit_cycle[section_index]
                if slot_unit is not None:
                    scoped = [
                        topic
                        for topic in content.topics
                        if str(topic.unit).strip() == slot_unit
                    ]
                    if scoped:
                        unit_pool = scoped
                matching_topics = [
                    topic
                    for topic in unit_pool
                    if topic_usage[topic.topic_id] < topic_quotas[topic.topic_id]
                ]
                if not matching_topics:
                    matching_topics = [
                        topic
                        for topic in unit_pool
                        if topic.topic_id not in omitted_topic_ids
                    ] or list(unit_pool)
                if section_visuals_remaining and eligible_visuals:
                    visual_topics = [
                        topic
                        for topic in matching_topics
                        if any(
                            asset.asset_id in topic.visual_asset_ids
                            and asset.asset_id not in used_visual_ids
                            for asset in eligible_visuals
                        )
                    ]
                    if visual_topics:
                        matching_topics = visual_topics
                topic = min(
                    matching_topics,
                    key=lambda item: (
                        self._bloom_distance(
                            requested_bloom,
                            self._effective_bloom(requested_bloom, item),
                        ),
                        topic_usage[item.topic_id]
                        / max(topic_quotas[item.topic_id], 1),
                        -topic_scores[item.topic_id],
                        item.unit,
                        item.name,
                    ),
                )
                facet = FACET_CYCLE[
                    (topic_usage[topic.topic_id] + set_index) % len(FACET_CYCLE)
                ]
                topic_usage[topic.topic_id] += 1
                bloom = self._effective_bloom(requested_bloom, topic)
                if bloom != requested_bloom:
                    bloom_adjustments[(requested_bloom, bloom)] += 1

                visual = None
                if section_visuals_remaining and eligible_visuals:
                    topic_visuals = [
                        item
                        for item in eligible_visuals
                        if item.asset_id in topic.visual_asset_ids
                        and item.asset_id not in used_visual_ids
                    ]
                    visual = topic_visuals[0] if topic_visuals else None
                    if visual:
                        used_visual_ids.add(visual.asset_id)
                        section_visuals_remaining -= 1
                elif section_visuals_remaining and not eligible_visuals:
                    section_visuals_remaining = 0

                question_kind = (
                    section.question_kind_sequence[section_index]
                    if section.question_kind_sequence
                    else section.question_kind
                )
                has_internal_choice = (
                    section_index + 1 in section.internal_choice_positions
                    if section.internal_choice_positions
                    else section_index
                    >= section.question_count - section.internal_choice_count
                )
                slots.append(
                    BlueprintSlot(
                        slot_id=f"{section.section_id}-{section_index + 1}",
                        question_number=printed_number,
                        section_id=section.section_id,
                        marks=section.marks_each,
                        bloom_level=bloom,
                        requested_bloom_level=requested_bloom,
                        question_kind=question_kind,
                        topic_id=topic.topic_id,
                        # The section owns the unit, not the topic that filled
                        # it, so a question's number and its CO can never
                        # disagree even if topic selection falls back.
                        unit=slot_unit or topic.unit,
                        facet=facet,
                        source_pages=topic.source_pages,
                        evidence_chunk_ids=topic.evidence_chunk_ids[:3],
                        course_outcome=_outcome_for(
                            slot_unit, topic, content
                        ),
                        subparts=section.subparts,
                        has_internal_choice=has_internal_choice,
                        internal_choice_scope=section.internal_choice_scope,
                        choices_per_question=(
                            section.choices_per_question
                            if has_internal_choice
                            else 1
                        ),
                        answers_required=section.answers_required,
                        requires_visual=visual is not None,
                        visual_asset_id=visual.asset_id if visual else None,
                    )
                )
                global_number += 1
            # `visual_question_count` is a ceiling, not a quota. Leaving some
            # capacity unused is the correct outcome when no verified visual
            # matches the selected topics, so it must not produce a warning.

        if bloom_adjustments:
            summary = ", ".join(
                f"{count} {requested.value}→{effective.value}"
                for (requested, effective), count in sorted(
                    bloom_adjustments.items(),
                    key=lambda item: (
                        list(BloomLevel).index(item[0][0]),
                        list(BloomLevel).index(item[0][1]),
                    ),
                )
            )
            warnings.append(
                "Bloom demand was adapted to the selected source: " + summary
            )

        warnings.extend(_cognitive_spread_warnings(slots))
        warnings.extend(_course_outcome_warnings(pattern, content, slots))

        blueprint = PaperBlueprint(
            pattern_id=pattern.pattern_id,
            subject=content.subject,
            slots=slots,
            warnings=list(dict.fromkeys(warnings)),
        )
        logger.info(
            "blueprint.plan.complete document_id=%s slots=%d visual_slots=%d "
            "warnings=%d",
            manifest.document_id,
            len(blueprint.slots),
            sum(slot.requires_visual for slot in blueprint.slots),
            len(blueprint.warnings),
        )
        return blueprint

    @staticmethod
    def _topic_richness(
        content: ContentMap,
        manifest: DocumentManifest,
    ) -> dict[str, float]:
        chunks = build_evidence_chunks(manifest)
        scores: dict[str, float] = {}
        for topic in content.topics:
            chunk_ids = [
                chunk_id for chunk_id in topic.evidence_chunk_ids if chunk_id in chunks
            ]
            if not chunk_ids:
                chunk_ids = [
                    chunk_id
                    for chunk_id, chunk in chunks.items()
                    if chunk.page_number in topic.source_pages
                ]
            evidence_characters = sum(len(chunks[chunk_id].text) for chunk_id in chunk_ids)
            scores[topic.topic_id] = max(
                1.0,
                evidence_characters
                + 400 * len(topic.subtopics)
                + 300 * len(topic.supported_bloom_levels),
            )
        return scores

    @staticmethod
    def _topic_quotas(
        content: ContentMap,
        scores: dict[str, float],
        total_slots: int,
    ) -> tuple[Counter[str], set[str]]:
        ordered = sorted(
            content.topics,
            key=lambda topic: (-scores[topic.topic_id], topic.unit, topic.name),
        )
        included = ordered[:total_slots]
        omitted = {topic.topic_id for topic in ordered[total_slots:]}
        quotas: Counter[str] = Counter({topic.topic_id: 1 for topic in included})
        remaining = total_slots - len(included)
        if remaining <= 0 or not included:
            return quotas, omitted
        score_total = sum(scores[topic.topic_id] for topic in included)
        exact = {
            topic.topic_id: remaining * scores[topic.topic_id] / score_total
            for topic in included
        }
        for topic in included:
            quotas[topic.topic_id] += math.floor(exact[topic.topic_id])
        leftovers = total_slots - sum(quotas.values())
        for topic in sorted(
            included,
            key=lambda item: (
                -(exact[item.topic_id] - math.floor(exact[item.topic_id])),
                -scores[item.topic_id],
                item.unit,
                item.name,
            ),
        )[:leftovers]:
            quotas[topic.topic_id] += 1
        return quotas, omitted

    @staticmethod
    def _effective_bloom(requested: BloomLevel, topic: Topic) -> BloomLevel:
        """Resolve the level to ask for, allowing one step above the reported ceiling.

        The ceiling the analyzer reports is a judgement about expository prose and
        errs low — a chapter that explains gradient descent gets read as
        Remember/Understand even though a student can plainly be asked to compute a
        gradient. Obeying it strictly produced a 100-mark paper with 88 marks at
        Understand, which is not an examination.

        So it is treated as advisory within one level. The cost of stretching is
        bounded: the independent reviewer measures the level each question actually
        demands, a deviation is reported rather than hidden, and the coverage table
        shows faculty exactly where the paper landed. Two levels above is still
        refused, because that produces questions the source genuinely cannot carry.
        """
        supported = list(topic.supported_bloom_levels) or [
            BloomLevel.REMEMBER,
            BloomLevel.UNDERSTAND,
        ]
        if requested in supported:
            return requested
        levels_order = list(BloomLevel)
        ceiling = max(supported, key=levels_order.index)
        stretch = levels_order.index(requested) - levels_order.index(ceiling)
        if 0 < stretch <= BLOOM_STRETCH_LEVELS:
            return requested
        levels = list(BloomLevel)
        requested_index = levels.index(requested)
        lower = [level for level in supported if levels.index(level) < requested_index]
        if lower:
            return max(lower, key=levels.index)
        return min(supported, key=lambda level: abs(levels.index(level) - requested_index))

    @staticmethod
    def _bloom_distance(
        requested: BloomLevel,
        effective: BloomLevel,
    ) -> tuple[int, bool]:
        levels = list(BloomLevel)
        requested_index = levels.index(requested)
        effective_index = levels.index(effective)
        return (abs(requested_index - effective_index), effective_index > requested_index)


def _course_outcome_warnings(
    pattern: PaperPattern,
    content: ContentMap,
    slots: list[BlueprintSlot],
) -> list[str]:
    """Report outcomes the paper is meant to assess but does not.

    Accreditation expects every outcome a paper covers to carry marks. Which
    outcomes those are depends on the paper: an end-semester paper examines the
    whole course, while CAT-I covers only units 1 to 3 and is *supposed* to leave
    CO4 and CO5 untouched. Warning about those would be noise, so a unit-wise
    pattern is judged only against the units it declares.
    """
    if not content.course_outcomes:
        return []
    covered_units: set[str] = set()
    for section in pattern.sections:
        if section.unit_number is not None:
            covered_units.add(section.unit_number)
        covered_units.update(section.unit_cycle)
    if covered_units:
        expected = []
        for unit in covered_units:
            try:
                index = int(unit) - 1
            except ValueError:
                continue
            if 0 <= index < len(content.course_outcomes):
                expected.append(content.course_outcomes[index])
    else:
        expected = list(content.course_outcomes)
    marks_by_outcome: dict[str, int] = {outcome: 0 for outcome in expected}
    untagged = 0
    for slot in slots:
        if slot.course_outcome in marks_by_outcome:
            marks_by_outcome[slot.course_outcome] += slot.marks
        else:
            untagged += slot.marks
    messages: list[str] = []
    unassessed = [
        outcome for outcome, marks in marks_by_outcome.items() if marks == 0
    ]
    if unassessed:
        listed = "; ".join(f'"{outcome}"' for outcome in unassessed)
        messages.append(
            f"{len(unassessed)} course outcome(s) carry no marks in this paper: "
            f"{listed}. Widen the page range or revise the outcome mapping."
        )
    if untagged:
        messages.append(
            f"{untagged} marks are not mapped to any approved course outcome."
        )
    return messages


def _outcome_for(
    slot_unit: str | None,
    topic: Topic,
    content: ContentMap,
) -> str | None:
    """Resolve the course outcome a slot assesses.

    Unit-wise papers bind by position: unit 3 assesses CO3, which is how the
    department writes them and how the printed paper tags them. Flat papers have
    no unit, so they fall back to whichever outcome the topic was mapped to.
    """
    if slot_unit is not None:
        try:
            index = int(slot_unit) - 1
        except ValueError:
            index = -1
        if 0 <= index < len(content.course_outcomes):
            return content.course_outcomes[index]
        return None
    return topic.course_outcomes[0] if topic.course_outcomes else None


#: An examination that puts this share of its marks at a single cognitive level
#: has stopped discriminating between students, whatever its questions look like.
SINGLE_LEVEL_MARK_SHARE = 0.55

#: Accreditation expects some higher-order assessment. Below this share of marks
#: at Analyze or above, the paper is a comprehension test.
MINIMUM_HIGHER_ORDER_SHARE = 0.15


def _cognitive_spread_warnings(slots: list[BlueprintSlot]) -> list[str]:
    """Report a paper that has collapsed onto one cognitive level.

    Downgrading each slot to what its topic can support is individually
    reasonable and collectively produced a 100-mark paper carrying 88 marks at
    Understand. No single slot looked wrong; only the whole paper did. This is
    the check that sees the whole paper.
    """
    total = sum(slot.marks for slot in slots)
    if not total:
        return []
    marks: dict[BloomLevel, int] = {}
    for slot in slots:
        marks[slot.bloom_level] = marks.get(slot.bloom_level, 0) + slot.marks
    messages: list[str] = []

    level, level_marks = max(marks.items(), key=lambda item: item[1])
    if level_marks / total > SINGLE_LEVEL_MARK_SHARE:
        messages.append(
            f"{level_marks} of {total} marks sit at the {level.value} level. "
            "The paper cannot separate strong students from weak ones at a single "
            "level — widen the page range, or select units with more method and "
            "comparison in them."
        )

    order = list(BloomLevel)
    higher = sum(
        value
        for key, value in marks.items()
        if order.index(key) >= order.index(BloomLevel.ANALYZE)
    )
    if higher / total < MINIMUM_HIGHER_ORDER_SHARE:
        messages.append(
            f"only {higher} of {total} marks reach Analyze or above; "
            "accreditation expects meaningful higher-order assessment."
        )
    return messages
