from question_paper_gen.models import ContentMap, Topic
from question_paper_gen.subject_profiles import (
    SubjectFamily,
    infer_subject_profile,
)


def _content(subject: str, topic: str) -> ContentMap:
    return ContentMap(
        subject=subject,
        topics=[
            Topic(
                topic_id="topic",
                name=topic,
                unit="1",
                source_pages=[1],
            )
        ],
    )


def test_mathematics_profile_is_inferred_from_topics() -> None:
    profile = infer_subject_profile(
        _content("Applied Quantitative Studies", "Modulo arithmetic and equations")
    )

    assert profile.family == SubjectFamily.MATHEMATICS
    assert "recompute" in profile.guidance.lower()


def test_computing_profile_is_inferred_from_subject() -> None:
    profile = infer_subject_profile(
        _content("Computer Science", "Operating system scheduling algorithms")
    )

    assert profile.family == SubjectFamily.COMPUTING
    assert "trace" in profile.guidance.lower()


def test_unknown_subject_uses_general_profile() -> None:
    profile = infer_subject_profile(
        _content("Interdisciplinary Studies", "Foundational concepts")
    )

    assert profile.family == SubjectFamily.GENERAL
