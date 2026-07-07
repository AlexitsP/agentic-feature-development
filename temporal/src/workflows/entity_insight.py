"""EntityInsightWorkflow: a bounded, durable tool-use loop over one entity.

The workflow is deterministic orchestration only; the model call, data tools, and
Supabase writes live in activities. The model gathers data via read tools and
returns its final answer by calling the `submit_insight` tool.
"""
from __future__ import annotations

import json
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ..agents.tools.supabase_tools import TOOLS

MAX_ROUNDS = 6

_SYSTEM = (
    "You produce a concise, plain-language summary of a single business entity. "
    "Use ONLY data returned by the tools; never invent values. "
    "Steps: (1) call get_entity, (2) call get_entity_facts, (3) call submit_insight "
    "exactly once. In submit_insight set data_completeness to 'full' if you had both "
    "entity data and facts, 'partial' if some was missing, or 'insufficient' if the "
    "entity was not found. Keep the summary to 2-4 sentences."
)

_ACTIVITY_TIMEOUT = timedelta(seconds=30)


def _preview(result: object) -> object:
    text = json.dumps(result)
    if len(text) > 2000:
        return {"truncated": True, "preview": text[:2000]}
    return result


@workflow.defn
class EntityInsightWorkflow:
    @workflow.run
    async def run(self, run_id: str, entity_id: str) -> dict:
        try:
            return await self._execute(run_id, entity_id)
        except Exception as exc:  # surface hard failures to the run row / UI
            await workflow.execute_activity(
                "finalize_run",
                args=[run_id, "error", None, f"workflow error: {exc}"[:500]],
                start_to_close_timeout=_ACTIVITY_TIMEOUT,
            )
            return {"run_id": run_id, "error": str(exc)}

    async def _execute(self, run_id: str, entity_id: str) -> dict:
        messages: list[dict] = [
            {"role": "system", "content": _SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Summarize the entity with id {entity_id}. "
                    "Gather its data with the tools first, then call submit_insight."
                ),
            },
        ]
        model_retry = RetryPolicy(maximum_attempts=3)
        seq = 0

        for _ in range(MAX_ROUNDS):
            resp = await workflow.execute_activity(
                "model_chat",
                args=[messages, TOOLS, 2048],
                start_to_close_timeout=timedelta(seconds=90),
                retry_policy=model_retry,
            )
            tool_calls = resp.get("tool_calls") or []

            assistant_msg: dict = {"role": "assistant", "content": resp.get("content")}
            if tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": tc["arguments"]},
                    }
                    for tc in tool_calls
                ]
            messages.append(assistant_msg)

            if not tool_calls:
                # Model replied without the submit tool; treat text as a partial answer.
                result = {
                    "summary": resp.get("content") or "",
                    "notable_facts": [],
                    "data_completeness": "partial",
                }
                await workflow.execute_activity(
                    "finalize_run",
                    args=[run_id, "done", result, None],
                    start_to_close_timeout=_ACTIVITY_TIMEOUT,
                )
                return {"run_id": run_id, "result": result}

            for tc in tool_calls:
                name = tc["name"]
                try:
                    args = json.loads(tc["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}

                if name == "submit_insight":
                    seq += 1
                    await workflow.execute_activity(
                        "record_step",
                        args=[run_id, seq, name, args, args],
                        start_to_close_timeout=_ACTIVITY_TIMEOUT,
                    )
                    await workflow.execute_activity(
                        "finalize_run",
                        args=[run_id, "done", args, None],
                        start_to_close_timeout=_ACTIVITY_TIMEOUT,
                    )
                    return {"run_id": run_id, "result": args}

                result = await workflow.execute_activity(
                    "run_tool",
                    args=[name, args],
                    start_to_close_timeout=_ACTIVITY_TIMEOUT,
                )
                seq += 1
                await workflow.execute_activity(
                    "record_step",
                    args=[run_id, seq, name, args, _preview(result)],
                    start_to_close_timeout=_ACTIVITY_TIMEOUT,
                )
                messages.append(
                    {"role": "tool", "tool_call_id": tc["id"], "content": json.dumps(result)}
                )

        await workflow.execute_activity(
            "finalize_run",
            args=[run_id, "error", None, "max reasoning rounds exceeded"],
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
        )
        return {"run_id": run_id, "error": "max reasoning rounds exceeded"}
