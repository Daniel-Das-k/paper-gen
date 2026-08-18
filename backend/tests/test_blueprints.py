from question_paper_gen.blueprints import BlueprintBuilder
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
from question_paper_gen.patterns import default_college_pattern


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
        ],
    )


def test_blueprint_has_38_slots_and_preserves_internal_choices() -> None:
    blueprint = BlueprintBuilder().build(
        default_college_pattern(), _content(), _manifest(with_visual=True)
    )

    assert len(blueprint.slots) == 38
    assert sum(slot.marks for slot in blueprint.slots) == 80
    assert all(slot.source_pages for slot in blueprint.slots)
    assert sum(slot.requires_visual for slot in blueprint.slots) == 1
    visual_slot = next(slot for slot in blueprint.slots if slot.requires_visual)
    assert visual_slot.topic_id == "rectifier"
    assert visual_slot.visual_asset_id == "p1-image-1"
    assert [slot.question_kind.value for slot in blueprint.slots[18:20]] == [
        "assertion_reason",
        "assertion_reason",
    ]
    assert blueprint.slots[-1].choices_per_question == 2
    assert blueprint.slots[-1].answers_required == 1
    assert sum(slot.has_internal_choice for slot in blueprint.slots) == 9
    assert not any(
        slot.has_internal_choice
        for slot in blueprint.slots
        if slot.section_id == "section_a"
    )
    choice_numbers = {
        slot.question_number
        for slot in blueprint.slots
        if slot.has_internal_choice
    }
    assert choice_numbers == {"22", "23", "26", "28", "33", "34", "36", "37", "38"}
    assert all(
        slot.internal_choice_scope == "final_subpart"
        for slot in blueprint.slots
        if slot.section_id == "section_e"
    )


def test_blueprint_fails_closed_when_visual_is_unverified() -> None:
    blueprint = BlueprintBuilder().build(
        default_college_pattern(), _content(), _manifest(with_visual=False)
    )

    assert not any(slot.requires_visual for slot in blueprint.slots)
    assert not any("visual" in warning for warning in blueprint.warnings)


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
            Topic(
                topic_id="limited",
                name="Definitions",
                unit="2",
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
        default_college_pattern(), content, _manifest(with_visual=False)
    )
    rich_count = sum(slot.topic_id == "rich" for slot in blueprint.slots)
    limited_count = sum(slot.topic_id == "limited" for slot in blueprint.slots)

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

def test_same_topic_slots_receive_distinct_facets() -> None:
    blueprint = BlueprintBuilder().build(
        default_college_pattern(), _content(), _manifest(with_visual=False)
    )

    assert all(slot.facet for slot in blueprint.slots)
    by_topic: dict[str, list[str]] = {}
    for slot in blueprint.slots:
        by_topic.setdefault(slot.topic_id, []).append(slot.facet or "")
    for facets in by_topic.values():
        first_six = facets[:6]
        assert len(set(first_six)) == len(first_six)


def test_blueprint_rejects_sources_too_thin_for_the_pattern() -> None:
    import pytest

    from question_paper_gen.blueprints import BlueprintError

    thin_content = ContentMap(
        subject="Electronics",
        topics=_content().topics[:2],
    )

    with pytest.raises(BlueprintError, match="wider page range"):
        BlueprintBuilder().build(
            default_college_pattern(), thin_content, _manifest(with_visual=False)
        )

def test_subtopics_extend_capacity_for_coarse_topic_maps() -> None:
    coarse_content = ContentMap(
        subject="Mathematics - Calculus",
        topics=[
            Topic(
                topic_id=f"5.{index}",
                name=name,
                unit="5",
                source_pages=[1],
                subtopics=["definition", "standard results", "worked problems"],
                supported_bloom_levels=list(BloomLevel),
            )
            for index, name in enumerate(
                ["Continuity", "Differentiability", "Derivative applications"],
                start=1,
            )
        ],
    )

    blueprint = BlueprintBuilder().build(
        default_college_pattern(), coarse_content, _manifest(with_visual=False)
    )

    assert len(blueprint.slots) == 38
