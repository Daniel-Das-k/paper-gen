import pytest
from question_paper_gen.blueprints import BlueprintBuilder, BlueprintError
from question_paper_gen.ai import DocumentAnalyzer
from question_paper_gen.models import (
    BloomLevel,
    ContentMap,
    DocumentManifest,
    DocumentQuality,
    PageContent,
    Topic,
    VisualAsset,
    VisualType,
)
from question_paper_gen.patterns import autonomous_semester_pattern


def _manifest(with_visual: bool) -> DocumentManifest:
    asset = VisualAsset(
        asset_id="p1-image-1",
        page_number=1,
        asset_type=VisualType.CIRCUIT,
        image_path="/tmp/circuit.png",
        topic="Rectifiers",
        question_eligible=with_visual,
        confidence=0.95 if with_visual else 0.20,
    )
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
                text="A sufficiently long page of academic source material.",
                rendered_image_path="/tmp/page.png",
                visual_asset_ids=["p1-image-1"],
            )
        ],
        visual_assets=[asset],
        quality=DocumentQuality(
            passed=True,
            page_count=1,
            text_character_count=100,
        ),
    )


def _content() -> ContentMap:
    return ContentMap(
        subject="Electronics",
        topics=[
            Topic(
                topic_id="rectifier",
                name="Rectifiers",
                unit="1",
                source_pages=[1],
                supported_bloom_levels=list(BloomLevel),
                visual_asset_ids=["p1-image-1"],
            ),
            Topic(
                topic_id="filters",
                name="Filters",
                unit="2",
                source_pages=[1],
                supported_bloom_levels=list(BloomLevel),
            ),
            Topic(
                topic_id="amplifiers",
                name="Amplifiers",
                unit="3",
                source_pages=[1],
                supported_bloom_levels=list(BloomLevel),
            ),
            Topic(
                topic_id="oscillators",
                name="Oscillators",
                unit="4",
                source_pages=[1],
                supported_bloom_levels=list(BloomLevel),
            ),
            Topic(
                topic_id="power_supplies",
                name="Power supplies",
                unit="5",
                source_pages=[1],
                supported_bloom_levels=list(BloomLevel),
            ),
        ],
    )


def test_blueprint_binds_the_verified_figure_to_its_own_topic() -> None:
    blueprint = BlueprintBuilder().build(
        autonomous_semester_pattern(), _content(), _manifest(with_visual=True)
    )

    assert sum(slot.requires_visual for slot in blueprint.slots) == 1
    visual_slot = next(slot for slot in blueprint.slots if slot.requires_visual)
    assert visual_slot.topic_id == "rectifier"
    assert visual_slot.visual_asset_id == "p1-image-1"
    assert all(slot.source_pages for slot in blueprint.slots)


def test_blueprint_fails_closed_when_visual_is_unverified() -> None:
    blueprint = BlueprintBuilder().build(
        autonomous_semester_pattern(), _content(), _manifest(with_visual=False)
    )

    assert not any(slot.requires_visual for slot in blueprint.slots)
    assert not any("visual" in warning for warning in blueprint.warnings)


def test_semester_uses_all_useful_matching_visuals_without_forcing_others() -> None:
    content = _content()
    content.topics[1].visual_asset_ids = ["p1-image-2"]
    manifest = _manifest(with_visual=True)
    manifest.visual_assets.append(
        VisualAsset(
            asset_id="p1-image-2",
            page_number=1,
            asset_type=VisualType.DIAGRAM,
            image_path="/tmp/filter.png",
            topic="Filters",
            question_eligible=True,
            confidence=0.93,
        )
    )

    blueprint = BlueprintBuilder().build(
        autonomous_semester_pattern(), content, manifest
    )

    visual_slots = [slot for slot in blueprint.slots if slot.requires_visual]
    assert [(slot.section_id, slot.topic_id) for slot in visual_slots] == [
        ("part_b", "rectifier"),
        ("part_b", "filters"),
    ]
    assert not any("visual" in warning for warning in blueprint.warnings)


def test_semester_does_not_warn_or_force_an_unmatched_eligible_visual() -> None:
    content = _content()
    content.topics[0].visual_asset_ids = []

    blueprint = BlueprintBuilder().build(
        autonomous_semester_pattern(), content, _manifest(with_visual=True)
    )

    assert not any(slot.requires_visual for slot in blueprint.slots)
    assert not any("visual" in warning for warning in blueprint.warnings)


def test_cat_uses_a_verified_visual_only_when_it_matches_the_topic() -> None:
    from question_paper_gen.patterns import get_pattern

    with_visual = BlueprintBuilder().build(
        get_pattern("cat-1-75"), _content(), _manifest(with_visual=True)
    )
    without_visual = BlueprintBuilder().build(
        get_pattern("cat-1-75"), _content(), _manifest(with_visual=False)
    )

    visual_slots = [slot for slot in with_visual.slots if slot.requires_visual]
    assert len(visual_slots) == 1
    assert visual_slots[0].topic_id == "rectifier"
    assert visual_slots[0].section_id == "part_b"
    assert visual_slots[0].visual_asset_id == "p1-image-1"
    assert not any(slot.requires_visual for slot in without_visual.slots)


def test_visuals_are_linked_only_to_semantically_matching_topics() -> None:
    content = _content()
    asset = _manifest(with_visual=True).visual_assets[0]

    linked = DocumentAnalyzer._link_topics_to_assets(content, [asset])

    assert linked.topics[0].visual_asset_ids == ["p1-image-1"]
    assert linked.topics[1].visual_asset_ids == []


def test_blueprint_weights_rich_topics_and_adapts_unsupported_bloom() -> None:
    content = ContentMap(
        subject="General Studies",
        topics=[
            Topic(
                topic_id="rich",
                name="Normalization",
                unit="1",
                subtopics=["Dependencies", "Normal forms", "Lossless decomposition"],
                source_pages=[1],
                supported_bloom_levels=[
                    BloomLevel.REMEMBER,
                    BloomLevel.UNDERSTAND,
                    BloomLevel.APPLY,
                    BloomLevel.ANALYZE,
                ],
            ),
            *[
                Topic(
                    topic_id=f"filler{unit}",
                    name=f"Unit {unit} material",
                    unit=str(unit),
                    source_pages=[1],
                    supported_bloom_levels=[
                        BloomLevel.REMEMBER,
                        BloomLevel.UNDERSTAND,
                    ],
                )
                for unit in (2, 3, 4, 5)
            ],
            Topic(
                topic_id="limited",
                name="Definitions",
                unit="1",
                source_pages=[1],
                supported_bloom_levels=[BloomLevel.REMEMBER],
            ),
            Topic(
                topic_id="filler-a",
                name="Query languages",
                unit="3",
                source_pages=[1],
                supported_bloom_levels=[BloomLevel.REMEMBER, BloomLevel.UNDERSTAND],
            ),
            Topic(
                topic_id="filler-b",
                name="Transactions",
                unit="4",
                source_pages=[1],
                supported_bloom_levels=[BloomLevel.REMEMBER, BloomLevel.UNDERSTAND],
            ),
        ],
    )

    blueprint = BlueprintBuilder().build(
        autonomous_semester_pattern(), content, _manifest(with_visual=False)
    )
    rich_count = sum(slot.topic_id == "rich" for slot in blueprint.slots)
    limited_count = sum(slot.topic_id == "limited" for slot in blueprint.slots)

    # Weighting applies within a unit; across units the paper's structure
    # decides how many questions each unit receives, not evidence richness.
    assert rich_count > limited_count
    assert limited_count >= 1
    assert all(slot.requested_bloom_level is not None for slot in blueprint.slots)
    assert any(
        slot.requested_bloom_level != slot.bloom_level
        for slot in blueprint.slots
        if slot.topic_id == "limited"
    )
    assert any("Bloom demand was adapted" in warning for warning in blueprint.warnings)


def test_content_page_normalization_keeps_only_verified_topic_evidence() -> None:
    manifest = _manifest(with_visual=False).model_copy(
        update={
            "selected_page_start": 11,
            "selected_page_end": 11,
            "source_total_pages": 20,
            "pages": [
                _manifest(with_visual=False).pages[0].model_copy(
                    update={
                        "page_number": 11,
                        "text": "Database normalization removes repeated dependencies.",
                    }
                )
            ],
        }
    )
    content = ContentMap(
        subject="Database Systems",
        topics=[
            Topic(
                topic_id="normalization",
                name="Database normalization",
                unit="1",
                source_pages=[11, 1, 999],
            ),
            Topic(
                topic_id="unverified",
                name="Quantum optics",
                unit="2",
                source_pages=[11],
            ),
        ],
    )

    normalized = DocumentAnalyzer._normalize_content_pages(content, manifest)

    assert [topic.topic_id for topic in normalized.topics] == ["normalization"]
    assert normalized.topics[0].source_pages == [11]
    assert normalized.topics[0].evidence_chunk_ids == ["p11-c1"]

def test_blueprint_rejects_sources_too_thin_for_the_pattern() -> None:
    import pytest

    from question_paper_gen.blueprints import BlueprintError

    thin_content = ContentMap(
        subject="Electronics",
        topics=_content().topics[:1],
    )

    with pytest.raises(BlueprintError, match="wider page range"):
        BlueprintBuilder().build(
            autonomous_semester_pattern(), thin_content, _manifest(with_visual=False)
        )

def test_subtopics_extend_capacity_for_coarse_topic_maps() -> None:
    coarse_content = ContentMap(
        subject="Mathematics - Calculus",
        topics=[
            Topic(
                topic_id=f"5.{index}",
                name=name,
                unit=str(index),
                source_pages=[1],
                subtopics=["definition", "standard results", "worked problems"],
                supported_bloom_levels=list(BloomLevel),
            )
            for index, name in enumerate(
                [
                    "Continuity",
                    "Differentiability",
                    "Derivative applications",
                    "Integration techniques",
                    "Series expansions",
                ],
                start=1,
            )
        ],
    )

    blueprint = BlueprintBuilder().build(
        autonomous_semester_pattern(), coarse_content, _manifest(with_visual=False)
    )

    assert len(blueprint.slots) == 16


def test_autonomous_pattern_builds_sixteen_slots_worth_one_hundred_marks() -> None:
    blueprint = BlueprintBuilder().build(
        autonomous_semester_pattern(), _content(), _manifest(with_visual=True)
    )

    assert len(blueprint.slots) == 16
    assert sum(slot.marks for slot in blueprint.slots) == 100
    assert [slot.question_number for slot in blueprint.slots] == [
        str(number) for number in range(1, 17)
    ]
    assert [slot.section_id for slot in blueprint.slots].count("part_a") == 10
    assert [slot.section_id for slot in blueprint.slots].count("part_b") == 5
    assert [slot.section_id for slot in blueprint.slots].count("part_c") == 1


def test_autonomous_part_b_slots_carry_a_whole_question_choice() -> None:
    blueprint = BlueprintBuilder().build(
        autonomous_semester_pattern(), _content(), _manifest(with_visual=True)
    )
    part_b = [slot for slot in blueprint.slots if slot.section_id == "part_b"]

    assert len(part_b) == 5
    for slot in part_b:
        assert slot.marks == 13
        assert slot.has_internal_choice
        assert slot.choices_per_question == 2
        assert slot.answers_required == 1
        assert slot.internal_choice_scope == "whole_question"
        assert slot.subparts == []


def test_autonomous_slots_sharing_a_topic_get_distinct_facets() -> None:
    """The facet cycle is the structural defence against duplicate questions."""
    blueprint = BlueprintBuilder().build(
        autonomous_semester_pattern(), _content(), _manifest(with_visual=True)
    )

    by_topic: dict[str, list[str | None]] = {}
    for slot in blueprint.slots:
        by_topic.setdefault(slot.topic_id, []).append(slot.facet)
    for topic_id, facets in by_topic.items():
        assert len(set(facets)) == len(facets), f"{topic_id} reused a facet"


def _content_with_outcomes(mapped: int) -> ContentMap:
    """Content whose first `mapped` topics carry an approved outcome."""
    outcomes = [
        "Apply rectifier analysis to design power supplies",
        "Analyse filter behaviour in signal paths",
        "Evaluate amplifier configurations for a given specification",
        "Design oscillator circuits to meet frequency requirements",
    ]
    base = _content()
    return base.model_copy(
        update={
            "course_outcomes": outcomes,
            "topics": [
                topic.model_copy(
                    update={
                        "course_outcomes": [outcomes[index]] if index < mapped else []
                    }
                )
                for index, topic in enumerate(base.topics)
            ],
        }
    )


def _unit_content(units: int = 5) -> ContentMap:
    """Topics tagged with their syllabus unit, as an analysed syllabus gives them."""
    return ContentMap(
        subject="Electronics",
        course_outcomes=[f"Outcome {index}" for index in range(1, units + 1)],
        topics=[
            Topic(
                topic_id=f"u{unit}-t{index}",
                name=f"Unit {unit} topic {index}",
                unit=str(unit),
                source_pages=[1],
                supported_bloom_levels=list(BloomLevel),
            )
            for unit in range(1, units + 1)
            for index in range(2)
        ],
    )


def test_slots_take_the_outcome_of_the_unit_they_examine() -> None:
    """Unit N assesses CO N — that is how the department writes the paper."""
    blueprint = BlueprintBuilder().build(
        autonomous_semester_pattern(), _unit_content(), _manifest(with_visual=False)
    )

    assert all(slot.course_outcome for slot in blueprint.slots)
    assert not blueprint.warnings
    for slot in blueprint.slots:
        assert slot.course_outcome == f"Outcome {slot.unit}"


def test_a_cat_is_not_faulted_for_the_units_it_does_not_cover() -> None:
    """CAT-I examines units 1-3; warning about CO4 and CO5 would be noise."""
    from question_paper_gen.patterns import get_pattern

    blueprint = BlueprintBuilder().build(
        get_pattern("cat-1-75"), _unit_content(), _manifest(with_visual=False)
    )

    assert not blueprint.warnings
    marks: dict[str, int] = {}
    for slot in blueprint.slots:
        marks[slot.course_outcome or "-"] = (
            marks.get(slot.course_outcome or "-", 0) + slot.marks
        )
    # Units 1 and 2 in full carry 30 each, unit 3 by half carries 15.
    assert marks == {"Outcome 1": 30, "Outcome 2": 30, "Outcome 3": 15}


def test_uploaded_material_is_used_without_rejecting_internal_unit_labels() -> None:
    """The upload rows are authoritative even when topic labels do not match."""
    from question_paper_gen.patterns import get_pattern

    cat_two = BlueprintBuilder().build(
        get_pattern("cat-2-75"),
        _unit_content(units=3),
        _manifest(with_visual=False),
    )
    semester = BlueprintBuilder().build(
        autonomous_semester_pattern(),
        _unit_content(units=3),
        _manifest(with_visual=False),
    )

    assert {slot.unit for slot in cat_two.slots} == {"3", "4", "5"}
    assert {slot.unit for slot in semester.slots} == {"1", "2", "3", "4", "5"}


def test_cat_questions_are_numbered_continuously_and_keep_unit_ownership() -> None:
    from question_paper_gen.patterns import get_pattern

    expected_units = {
        "cat-1-75": ["1"] * 4 + ["2"] * 4 + ["3"] * 2
        + ["1"] * 2 + ["2"] * 2 + ["3"],
        "cat-2-75": ["3"] * 2 + ["4"] * 4 + ["5"] * 4
        + ["3"] + ["4"] * 2 + ["5"] * 2,
    }
    for pattern_id, units in (("cat-1-75", 3), ("cat-2-75", 5)):
        blueprint = BlueprintBuilder().build(
            get_pattern(pattern_id),
            _unit_content(units=units),
            _manifest(with_visual=False),
        )
        assert [slot.question_number for slot in blueprint.slots] == [
            str(number) for number in range(1, 16)
        ]
        assert [slot.unit for slot in blueprint.slots] == expected_units[pattern_id]


def test_no_outcome_warnings_when_the_course_defines_none() -> None:
    blueprint = BlueprintBuilder().build(
        autonomous_semester_pattern(), _content(), _manifest(with_visual=False)
    )

    assert not any("outcome" in warning for warning in blueprint.warnings)
    assert all(slot.course_outcome is None for slot in blueprint.slots)


def test_a_slot_may_ask_one_level_above_the_reported_ceiling() -> None:
    """The analyzer's ceiling errs low on expository sources; treat it as advice."""
    from question_paper_gen.blueprints import BLOOM_STRETCH_LEVELS

    assert BLOOM_STRETCH_LEVELS == 1
    ceiling_understand = Topic(
        topic_id="t",
        name="Gradient descent",
        unit="1",
        source_pages=[1],
        supported_bloom_levels=[BloomLevel.REMEMBER, BloomLevel.UNDERSTAND],
    )

    # One step up is still asked for; two steps is refused.
    assert (
        BlueprintBuilder._effective_bloom(BloomLevel.APPLY, ceiling_understand)
        == BloomLevel.APPLY
    )
    assert (
        BlueprintBuilder._effective_bloom(BloomLevel.ANALYZE, ceiling_understand)
        == BloomLevel.UNDERSTAND
    )


def test_a_paper_collapsed_onto_one_level_is_reported() -> None:
    """No single slot looked wrong in the 88-marks-at-Understand paper."""
    from question_paper_gen.blueprints import _cognitive_spread_warnings
    from question_paper_gen.models import BlueprintSlot, QuestionKind

    def slot(marks: int, level: BloomLevel, index: int) -> BlueprintSlot:
        return BlueprintSlot(
            slot_id=f"s{index}",
            question_number=str(index),
            section_id="part_a",
            marks=marks,
            bloom_level=level,
            question_kind=QuestionKind.LONG_ANSWER,
            topic_id="t",
            unit="1",
        )

    collapsed = _cognitive_spread_warnings(
        [
            slot(6, BloomLevel.REMEMBER, 1),
            slot(88, BloomLevel.UNDERSTAND, 2),
            slot(6, BloomLevel.APPLY, 3),
        ]
    )
    joined = " ".join(collapsed)
    assert "sit at the understand level" in joined
    assert "reach Analyze or above" in joined

    balanced = _cognitive_spread_warnings(
        [
            slot(20, BloomLevel.REMEMBER, 1),
            slot(20, BloomLevel.UNDERSTAND, 2),
            slot(35, BloomLevel.APPLY, 3),
            slot(15, BloomLevel.ANALYZE, 4),
            slot(10, BloomLevel.EVALUATE, 5),
        ]
    )
    assert balanced == []
