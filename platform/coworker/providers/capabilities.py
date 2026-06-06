"""Per-model capability probe.

A heuristic table for now (refined as we probe real providers/endpoints). Accepts
either bare model names (`gpt-5.5`) or provider-qualified ones (`openai:gpt-5.5`).
"""

from __future__ import annotations

from .base import ModelCapabilities


def capabilities_for(model: str) -> ModelCapabilities:
    name = model.split(":", 1)[-1].lower()  # strip a provider prefix if present

    # Modern OpenAI GPT models: tools + vision + parallel tool calls + streaming.
    if name.startswith(("gpt-5", "gpt-4")):
        return ModelCapabilities(
            tools=True, vision=True, parallel_tool_calls=True, streaming=True
        )

    # OpenAI reasoning models: tools yes, parallel tool calls constrained.
    if name.startswith(("o1", "o3", "o4")):
        return ModelCapabilities(
            tools=True, vision=False, parallel_tool_calls=False, streaming=True
        )

    if name.startswith("deepseek"):
        return ModelCapabilities(
            tools=True, vision=False, parallel_tool_calls=True, streaming=True
        )

    # Conservative default for unknown models.
    return ModelCapabilities(
        tools=True, vision=False, parallel_tool_calls=False, streaming=True
    )
