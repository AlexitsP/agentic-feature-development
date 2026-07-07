"""Activities for the Entity Insights workflow.

Activities hold all the non-deterministic work: the model call, the read tools,
and the Supabase writes for steps and the final result. The workflow only
orchestrates them.
"""
from __future__ import annotations

import datetime as dt
import logging
from typing import Any

import httpx
from temporalio import activity

from ..agents.model_client import ModelClient
from ..agents.tools import supabase_tools as tools
from ..config import settings

logger = logging.getLogger(__name__)

# Reuse one client across activity invocations in this worker process so we do
# not re-attempt Entra (and re-fall-back to key) on every call.
_client: ModelClient | None = None


def _model() -> ModelClient:
    global _client
    if _client is None:
        _client = ModelClient()
    return _client


def _rest_base() -> str:
    return settings.supabase_url.rstrip("/") + "/rest/v1"


def _write_headers() -> dict[str, str]:
    key = settings.supabase_service_role_key
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


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


@activity.defn
def run_tool(name: str, args: dict) -> Any:
    """Dispatch a read-only data tool call."""
    if name == "get_entity":
        return tools.get_entity(args["entity_id"])
    if name == "get_entity_facts":
        return tools.get_entity_facts(args["entity_id"])
    raise ValueError(f"unknown tool: {name}")


@activity.defn
def record_step(run_id: str, seq: int, tool: str, args: dict, result_preview: Any) -> None:
    """Append a step row so the frontend can show progress via Realtime."""
    with httpx.Client(timeout=15.0) as client:
        resp = client.post(
            f"{_rest_base()}/insight_steps",
            headers={**_write_headers(), "Prefer": "return=minimal"},
            json={
                "run_id": run_id,
                "seq": seq,
                "tool": tool,
                "args": args,
                "result_preview": result_preview,
            },
        )
        resp.raise_for_status()


@activity.defn
def finalize_run(run_id: str, status: str, result: dict | None = None, error: str | None = None) -> None:
    """Mark a run done/error with its structured result."""
    with httpx.Client(timeout=15.0) as client:
        resp = client.patch(
            f"{_rest_base()}/insight_runs",
            params={"id": f"eq.{run_id}"},
            headers={**_write_headers(), "Prefer": "return=minimal"},
            json={
                "status": status,
                "result": result,
                "error": error,
                "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            },
        )
        resp.raise_for_status()
