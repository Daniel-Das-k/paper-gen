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
