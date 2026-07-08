"""The generic one-turn model activity, reused by every workflow.

Non-deterministic (the LLM call) so it lives in an activity, not a workflow. The
provider is isolated behind ModelClient, so swapping the LLM host is one file.
"""
from __future__ import annotations

from typing import Any

from temporalio import activity

from ..agents.model_client import ModelClient

# Reuse one client across activity invocations in this worker process so we do
# not re-attempt Entra (and re-fall-back to key) on every call.
_client: ModelClient | None = None


def _model() -> ModelClient:
    global _client
    if _client is None:
        _client = ModelClient()
    return _client


@activity.defn
def model_chat(
    messages: list[dict],
    tool_specs: list[dict],
    max_completion_tokens: int = 2048,
    tool_choice: Any = "auto",
) -> dict:
    """One model turn. Returns the assistant message as a plain dict.

    `tool_choice` may be "auto" or a forced choice, e.g.
    {"type": "function", "function": {"name": "submit_verdict"}}.
    """
    resp = _model().chat(
        messages,
        tools=tool_specs,
        tool_choice=tool_choice,
        max_completion_tokens=max_completion_tokens,
    )
    choice = resp.choices[0]
    msg = choice.message
    tool_calls = [
        {"id": tc.id, "name": tc.function.name, "arguments": tc.function.arguments}
        for tc in (msg.tool_calls or [])
    ]
    usage = getattr(resp, "usage", None)
    return {
        "content": msg.content,
        "tool_calls": tool_calls,
        "finish_reason": choice.finish_reason,
        "usage": {
            "prompt": usage.prompt_tokens,
            "completion": usage.completion_tokens,
            "total": usage.total_tokens,
        }
        if usage
        else None,
    }
