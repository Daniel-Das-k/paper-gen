import re
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.providers.bedrock import BedrockModelProfile

from question_paper_gen.ai import (
    _bedrock_structured_output_profile,
    summarize_model_failure,
)


def test_bedrock_profile_forces_typed_output_tool() -> None:
    provider_profile = BedrockModelProfile(
        bedrock_supports_tool_choice=False,
        bedrock_send_back_thinking_parts=True,
    )

    profile = _bedrock_structured_output_profile(provider_profile)

    assert profile.bedrock_supports_tool_choice
    assert profile.bedrock_send_back_thinking_parts


def test_unexpected_model_behavior_summary_includes_safe_reason() -> None:
    error = UnexpectedModelBehavior(
        "Exceeded maximum retries (2) for output validation"
    )

    summary = summarize_model_failure(error)

    assert "UnexpectedModelBehavior" in summary
    assert "Exceeded maximum retries (2) for output validation" in summary


def test_invented_course_outcomes_are_dropped() -> None:
    """The model fills `course_outcomes` whether asked to or not — drop the guesses.

    Left alone this produces convincing strings no Board of Studies approved,
    which is worse than an empty column because it looks official.
    """
    from question_paper_gen.ai import DocumentAnalyzer
    from question_paper_gen.models import ContentMap, Topic

    approved = [
        "Apply normalization techniques to design relational schemas",
        "Construct SQL queries for a given information requirement",
    ]
    content = ContentMap(
        subject="DBMS",
        topics=[
            Topic(
                topic_id="t1",
                name="Normalization",
                unit="1",
                source_pages=[1],
                course_outcomes=["Learn the basics of normalization"],
            ),
            Topic(
                topic_id="t2",
                name="SQL",
                unit="2",
                source_pages=[2],
                course_outcomes=[approved[1]],
            ),
        ],
    )

    kept = DocumentAnalyzer._enforce_course_outcomes(content, approved)
    assert kept.course_outcomes == approved
    assert kept.topics[0].course_outcomes == []          # invented -> dropped
    assert kept.topics[1].course_outcomes == [approved[1]]  # approved -> kept

    # With no approved list, nothing survives.
    bare = DocumentAnalyzer._enforce_course_outcomes(content, None)
    assert bare.course_outcomes == []
    assert all(topic.course_outcomes == [] for topic in bare.topics)


def test_syllabus_extraction_shape_matches_a_real_course_page() -> None:
    """MA19156 Linear Algebra and Calculus, R2019 — five units, five outcomes."""
    from question_paper_gen.ai import SyllabusExtraction

    extraction = SyllabusExtraction.model_validate(
        {
            "subject_code": "MA19156",
            "subject_name": "LINEAR ALGEBRA AND CALCULUS",
            "regulation": "R2019",
            "units": [
                {"number": "I", "title": "MATRICES AND QUADRATIC FORMS", "topics": "…"},
                {"number": "II", "title": "VECTOR SPACES", "topics": "…"},
                {"number": "III", "title": "INNER PRODUCT SPACES", "topics": "…"},
                {
                    "number": "IV",
                    "title": "DIFFERENTIAL CALCULUS- FUNCTIONS OF SEVERAL VARIABLES",
                    "topics": "…",
                },
                {"number": "V", "title": "MULTIPLE INTEGRAL", "topics": "…"},
            ],
            "course_outcomes": [
                "Apply the concept of Eigen values and eigen vectors, "
                "diagonalization of a matrix for solving problems.",
                "Use concepts of basis and dimension in vector spaces in "
                "solving problems.",
                "Construct orthonormal basis using inner products and "
                "decompose matrices.",
                "Analyze, sketch and study the properties of different curves "
                "and to handle functions of several variables and problems of "
                "maxima and minima.",
                "Evaluate surface area and volume using multiple integrals.",
            ],
            "extraction_confident": True,
        }
    )

    assert len(extraction.units) == 5
    assert len(extraction.course_outcomes) == 5
    # One unit per outcome is the convention these papers are built around.
    assert len(extraction.units) == len(extraction.course_outcomes)
    # Every outcome opens with a Bloom action verb, as accreditation requires.
    # Punctuation has to be stripped: CO4 reads "Analyze, sketch and study…".
    openers = [
        re.sub(r"[^a-z]", "", outcome.split()[0].lower())
        for outcome in extraction.course_outcomes
    ]
    assert openers == ["apply", "use", "construct", "analyze", "evaluate"]


def test_syllabus_extraction_can_report_that_it_is_unsure() -> None:
    from question_paper_gen.ai import SyllabusExtraction

    extraction = SyllabusExtraction.model_validate(
        {"extraction_confident": False, "problem": "page lists three courses"}
    )

    assert extraction.course_outcomes == []
    assert not extraction.extraction_confident
    assert extraction.problem


def test_topic_units_come_from_the_upload_not_the_model() -> None:
    """One file per unit means the unit is known; a guess would misroute the CO."""
    from question_paper_gen.ai import DocumentAnalyzer
    from question_paper_gen.models import (
        ContentMap,
        DocumentManifest,
        DocumentQuality,
        PageContent,
        Topic,
    )

    pages = [
        PageContent(
            page_number=number,
            width=600,
            height=800,
            text="Explained instructional content." * 3,
            rendered_image_path=f"/tmp/page-{number}.png",
            unit="1" if number <= 4 else "2" if number <= 8 else "3",
        )
        for number in range(1, 14)
    ]
    manifest = DocumentManifest(
        document_id="doc",
        original_filename="merged.pdf",
        sha256="a" * 64,
        source_pdf_path="/tmp/merged.pdf",
        artifact_directory="/tmp",
        pages=pages,
        visual_assets=[],
        quality=DocumentQuality(
            passed=True, page_count=13, text_character_count=1300
        ),
    )
    content = ContentMap(
        subject="Data Structures",
        topics=[
            Topic(topic_id="t1", name="Lists", unit="Chapter One", source_pages=[1, 2]),
            Topic(topic_id="t2", name="Stacks", unit="99", source_pages=[5, 6, 7]),
            # Straddles the unit 2/3 boundary: the majority wins.
            Topic(topic_id="t3", name="Trees", unit="?", source_pages=[8, 9, 10]),
        ],
    )

    resolved = DocumentAnalyzer._enforce_topic_units(content, manifest)

    assert [topic.unit for topic in resolved.topics] == ["1", "2", "3"]


def test_topic_units_are_left_alone_for_a_single_file_upload() -> None:
    """Without per-unit uploads there is nothing to correct against."""
    from question_paper_gen.ai import DocumentAnalyzer
    from question_paper_gen.models import (
        ContentMap,
        DocumentManifest,
        DocumentQuality,
        PageContent,
        Topic,
    )

    manifest = DocumentManifest(
        document_id="doc",
        original_filename="notes.pdf",
        sha256="a" * 64,
        source_pdf_path="/tmp/notes.pdf",
        artifact_directory="/tmp",
        pages=[
            PageContent(
                page_number=1,
                width=600,
                height=800,
                text="Content.",
                rendered_image_path="/tmp/p1.png",
            )
        ],
        visual_assets=[],
        quality=DocumentQuality(passed=True, page_count=1, text_character_count=8),
    )
    content = ContentMap(
        subject="Data Structures",
        topics=[Topic(topic_id="t1", name="Lists", unit="2", source_pages=[1])],
    )

    assert DocumentAnalyzer._enforce_topic_units(content, manifest) == content


def test_evidence_chunk_ownership_beats_ambiguous_merged_page_citations() -> None:
    """A topic follows its uploaded PDF even when printed page numbers restart."""
    from question_paper_gen.ai import DocumentAnalyzer
    from question_paper_gen.models import (
        ContentMap,
        DocumentManifest,
        DocumentQuality,
        PageContent,
        Topic,
    )

    manifest = DocumentManifest(
        document_id="doc",
        original_filename="merged.pdf",
        sha256="a" * 64,
        source_pdf_path="/tmp/merged.pdf",
        artifact_directory="/tmp",
        pages=[
            PageContent(
                page_number=number,
                width=600,
                height=800,
                text=f"Explained instructional content for page {number}.",
                rendered_image_path=f"/tmp/page-{number}.png",
                unit="3" if number <= 2 else "4",
            )
            for number in range(1, 5)
        ],
        visual_assets=[],
        quality=DocumentQuality(passed=True, page_count=4, text_character_count=160),
    )
    content = ContentMap(
        subject="Data Structures",
        topics=[
            Topic(
                topic_id="t1",
                name="Trees",
                unit="Chapter One",
                source_pages=[1],
                evidence_chunk_ids=["p3-c1"],
            )
        ],
    )

    resolved = DocumentAnalyzer._enforce_topic_units(content, manifest)

    assert resolved.topics[0].unit == "4"


def _pdf_of(directory, pages: int, label: str = "page"):
    import fitz

    document = fitz.open()
    for number in range(pages):
        document.new_page().insert_text((72, 100), f"{label} {number + 1}")
    path = directory / f"{label}-{pages}.pdf"
    document.save(path)
    document.close()
    return path


def test_a_small_source_is_attached_whole(tmp_path) -> None:
    import fitz

    from question_paper_gen.ai import bounded_pdf_attachment

    data, sent, total = bounded_pdf_attachment(_pdf_of(tmp_path, 20))

    assert (sent, total) == (20, 20)
    with fitz.open(stream=data, filetype="pdf") as attached:
        assert attached.page_count == 20


def test_an_oversized_source_is_sampled_to_what_the_context_affords(tmp_path) -> None:
    """Two limits bite: the provider's page cap and the model's context window."""
    import fitz

    from question_paper_gen.ai import (
        PROVIDER_MAX_PDF_PAGES,
        bounded_pdf_attachment,
        max_attached_pdf_pages,
    )

    budget = max_attached_pdf_pages()
    assert budget <= PROVIDER_MAX_PDF_PAGES

    data, sent, total = bounded_pdf_attachment(_pdf_of(tmp_path, 260))

    assert total == 260
    assert sent == budget
    with fitz.open(stream=data, filetype="pdf") as attached:
        assert attached.page_count <= budget


def test_pdf_attachment_can_be_reduced_for_a_context_retry(tmp_path) -> None:
    import fitz

    from question_paper_gen.ai import bounded_pdf_attachment

    data, sent, total = bounded_pdf_attachment(
        _pdf_of(tmp_path, 80), page_limit=12
    )

    assert (sent, total) == (12, 80)
    with fitz.open(stream=data, filetype="pdf") as attached:
        assert attached.page_count == 12


def test_sampling_keeps_every_unit_visible(tmp_path) -> None:
    """Truncating to the first 100 pages would blind the model to later units."""
    import collections
    import re

    import fitz

    from question_paper_gen.ai import bounded_pdf_attachment

    document = fitz.open()
    for unit, count in (("1", 60), ("2", 50), ("3", 30)):
        for number in range(count):
            document.new_page().insert_text(
                (72, 100), f"UNIT {unit} page {number + 1}"
            )
    path = tmp_path / "merged.pdf"
    document.save(path)
    document.close()

    from question_paper_gen.ai import max_attached_pdf_pages

    data, sent, total = bounded_pdf_attachment(path)
    assert (sent, total) == (max_attached_pdf_pages(), 140)

    with fitz.open(stream=data, filetype="pdf") as attached:
        units = collections.Counter(
            match.group(1)
            for page in attached
            if (match := re.search(r"UNIT (\d)", page.get_text()))
        )

    # Every unit is represented, roughly in proportion to its share of the source.
    assert set(units) == {"1", "2", "3"}
    assert units["1"] > units["2"] > units["3"]
    expected_unit_three = sent * 30 // 140
    assert units["3"] >= max(1, expected_unit_three - 1)


def test_the_page_budget_follows_the_configured_model(tmp_path, monkeypatch) -> None:
    """A wider-context analysis model can carry more of the source in one call."""
    import importlib

    import fitz

    source = _pdf_of(tmp_path, 260, "wide")

    monkeypatch.setenv("BEDROCK_CONTEXT_TOKENS", "1000000")
    import question_paper_gen.ai as ai_module

    importlib.reload(ai_module)
    try:
        # A wider window buys pages up to the provider's own ceiling.
        assert ai_module.max_attached_pdf_pages() == ai_module.PROVIDER_MAX_PDF_PAGES
        data, sent, total = ai_module.bounded_pdf_attachment(source)
        assert (sent, total) == (ai_module.PROVIDER_MAX_PDF_PAGES, 260)
        with fitz.open(stream=data, filetype="pdf") as attached:
            assert attached.page_count == ai_module.PROVIDER_MAX_PDF_PAGES
    finally:
        monkeypatch.delenv("BEDROCK_CONTEXT_TOKENS", raising=False)
        importlib.reload(ai_module)


def test_the_budget_never_fills_the_whole_context_window() -> None:
    """A request estimated at exactly the limit is how 202,387 tokens happened."""
    from question_paper_gen.ai import (
        DEFAULT_CONTEXT_TOKENS,
        DEFAULT_RESERVED_TOKENS,
        DEFAULT_TOKENS_PER_PDF_PAGE,
        max_attached_pdf_pages,
    )

    estimated = (
        max_attached_pdf_pages() * DEFAULT_TOKENS_PER_PDF_PAGE
        + DEFAULT_RESERVED_TOKENS
    )
    assert estimated < DEFAULT_CONTEXT_TOKENS


def test_a_nonsense_page_budget_falls_back_to_the_derived_one(monkeypatch) -> None:
    import importlib

    monkeypatch.setenv("MAX_ATTACHED_PDF_PAGES", "not-a-number")
    import question_paper_gen.ai as ai_module

    importlib.reload(ai_module)
    try:
        assert 1 <= ai_module.max_attached_pdf_pages() <= ai_module.PROVIDER_MAX_PDF_PAGES
    finally:
        monkeypatch.delenv("MAX_ATTACHED_PDF_PAGES", raising=False)
        importlib.reload(ai_module)


def test_connection_failures_are_retried_not_surfaced() -> None:
    """A dropped connection mid-analysis must fall back, not fail the paper.

    These carry no HTTP status code, so they have to be matched by message —
    without that a large analysis request that drops in flight ends the run.
    """
    from botocore.exceptions import (
        ConnectionClosedError,
        ConnectTimeoutError,
        EndpointConnectionError,
        ReadTimeoutError,
    )

    from question_paper_gen.ai import _is_transient_model_error

    for error in (
        ConnectionClosedError(endpoint_url="https://bedrock-runtime.amazonaws.com"),
        ReadTimeoutError(endpoint_url="https://bedrock-runtime.amazonaws.com"),
        ConnectTimeoutError(endpoint_url="https://bedrock-runtime.amazonaws.com"),
        EndpointConnectionError(endpoint_url="https://bedrock-runtime.amazonaws.com"),
    ):
        assert _is_transient_model_error(error), type(error).__name__


def test_input_too_long_is_recognized_even_inside_an_exception_group() -> None:
    from question_paper_gen.ai import _is_input_too_long_error

    grouped = ExceptionGroup(
        "request failed",
        [Exception("ValidationException: Input is too long for requested model.")],
    )

    assert _is_input_too_long_error(grouped)
    assert not _is_input_too_long_error(Exception("Access denied"))


def test_visual_assessment_must_match_its_own_source_page_and_topic() -> None:
    from question_paper_gen.ai import DocumentAnalyzer
    from question_paper_gen.models import (
        ContentMap,
        Topic,
        VisualAsset,
        VisualType,
    )

    content = ContentMap(
        subject="Data Structures",
        topics=[
            Topic(
                topic_id="mst",
                name="Minimum Spanning Tree",
                unit="3",
                subtopics=["Spanning tree", "Prim's algorithm"],
                source_pages=[21],
            )
        ],
    )
    real_diagram = VisualAsset(
        asset_id="p21-image-2",
        page_number=21,
        asset_type=VisualType.DIAGRAM,
        image_path="/tmp/mst.jpeg",
        caption="Connected Graph and Spanning Tree",
    )
    wrong_banner = VisualAsset(
        asset_id="p116-image-3",
        page_number=116,
        asset_type=VisualType.DIAGRAM,
        image_path="/tmp/banner.jpeg",
        topic="Minimum Spanning Tree",
        visible_labels=["Cost = 7", "Cost = 8"],
        question_eligible=True,
        confidence=0.92,
    )

    assert DocumentAnalyzer._visual_matches_source_topic(real_diagram, content)
    assert not DocumentAnalyzer._visual_matches_source_topic(wrong_banner, content)


def test_bedrock_timeout_env_values_are_safe_and_configurable(monkeypatch) -> None:
    from question_paper_gen.ai import _env_int

    monkeypatch.setenv("BEDROCK_CONNECT_TIMEOUT_SECONDS", "180")
    monkeypatch.setenv("BEDROCK_READ_TIMEOUT_SECONDS", "900")
    assert max(30, _env_int("BEDROCK_CONNECT_TIMEOUT_SECONDS", 120)) == 180
    assert max(60, _env_int("BEDROCK_READ_TIMEOUT_SECONDS", 600)) == 900

    monkeypatch.setenv("BEDROCK_CONNECT_TIMEOUT_SECONDS", "invalid")
    assert _env_int("BEDROCK_CONNECT_TIMEOUT_SECONDS", 120) == 120


def test_a_rejected_request_is_not_retried() -> None:
    """Retrying a request the model refused on its merits only wastes calls."""
    from question_paper_gen.ai import _is_transient_model_error

    assert not _is_transient_model_error(
        Exception("ValidationException: A maximum of 100 PDF pages may be provided")
    )
    assert not _is_transient_model_error(
        Exception("ValidationException: the model identifier is invalid")
    )
