"""EvaluationWorkflow: assess a student's higher-education fit and suggest study options.

Deterministic workflow (all non-determinism is in the reused `model_chat` activity and
the feature's finalize/record activities). Forces the `submit_evaluation` tool for a
reliable structured result, builds the result via the pure builder (which attaches the
confidence badge from the kernel), streams trace events, and finalizes the run row.
"""
from __future__ import annotations

import json
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from .tools import (
        SUBMIT_EVALUATION_TOOLS,
        build_evaluation_result,
        get_persona,
        sources_prompt,
    )

MAX_ROUNDS = 5
_ACTIVITY_TIMEOUT = timedelta(seconds=30)
_MODEL_TIMEOUT = timedelta(seconds=90)
_GENERIC_ERROR = "Evaluation failed — please try again."

_PROFILE_KEYS = (
    "interests",
    "prior_qualification",
    "strong_subjects",
    "target_field",
    "canton",
    "language",
    "freeform",
)


def _system_prompt(persona: dict) -> str:
    return (
        f"You are {persona['voice']}, advising a prospective student on Swiss higher education. "
        "Assess their fit and readiness, then suggest 1-3 concrete study options — each a field of "
        "study plus an institution type: 'university', 'uas' (University of Applied Sciences / "
        "Fachhochschule), or 'ph' (University of Teacher Education). Ground every suggestion in what "
        "the student told you; be realistic and safe. If they gave little information, say so plainly "
        "rather than guessing. Cite 1-4 links, choosing ONLY from this official source list (never "
        "invent a URL):\n"
        f"{sources_prompt()}\n"
        "If the request is not about choosing a higher-education study option, set out_of_scope=true. "
        "Call submit_evaluation exactly once."
    )


@workflow.defn
class EvaluationWorkflow:
    @workflow.run
    async def run(self, evaluation_id: str, user_input: dict) -> dict:
        try:
            return await self._execute(evaluation_id, user_input)
        except Exception:
            workflow.logger.exception("program evaluation workflow failed")
            await workflow.execute_activity(
                "finalize_evaluation",
                args=[evaluation_id, "error", None, _GENERIC_ERROR],
                start_to_close_timeout=_ACTIVITY_TIMEOUT,
            )
            return {"evaluation_id": evaluation_id, "error": "internal error"}

    async def _emit(self, evaluation_id, seq, stage, label, detail=None, tokens=None) -> None:
        await workflow.execute_activity(
            "record_evaluation_event",
            args=[evaluation_id, seq, stage, label, detail, tokens],
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
        )

    async def _finalize(self, evaluation_id, seq, result) -> dict:
        await self._emit(
            evaluation_id, seq, "finalized", "Supabase · evaluation saved",
            {"tier": result["confidence"]["tier"], "options": len(result["suggested_options"])},
        )
        await workflow.execute_activity(
            "finalize_evaluation",
            args=[evaluation_id, "done", result, None],
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
        )
        return {"evaluation_id": evaluation_id, "result": result}

    async def _execute(self, evaluation_id: str, user_input: dict) -> dict:
        persona = get_persona(user_input.get("persona"))
        profile = {k: user_input.get(k) for k in _PROFILE_KEYS}
        messages: list[dict] = [
            {"role": "system", "content": _system_prompt(persona)},
            {"role": "user", "content": f"Here is my situation: {json.dumps(profile)}. Evaluate my options."},
        ]
        model_retry = RetryPolicy(maximum_attempts=3)
        seq = 1
        await self._emit(evaluation_id, seq, "dispatched", "Temporal · EvaluationWorkflow", {"persona": persona["label"]})

        for rnd in range(MAX_ROUNDS):
            resp = await workflow.execute_activity(
                "model_chat",
                args=[messages, SUBMIT_EVALUATION_TOOLS, 2048, {"type": "function", "function": {"name": "submit_evaluation"}}],
                start_to_close_timeout=_MODEL_TIMEOUT,
                retry_policy=model_retry,
            )
            seq += 1
            await self._emit(
                evaluation_id, seq, "reasoning", "Azure OpenAI · gpt-5-mini",
                {"round": rnd + 1}, (resp.get("usage") or {}).get("total"),
            )
            tool_calls = resp.get("tool_calls") or []
            assistant_msg: dict = {"role": "assistant", "content": resp.get("content")}
            if tool_calls:
                assistant_msg["tool_calls"] = [
                    {"id": tc["id"], "type": "function", "function": {"name": tc["name"], "arguments": tc["arguments"]}}
                    for tc in tool_calls
                ]
            messages.append(assistant_msg)
            if not tool_calls:
                messages.append({"role": "user", "content": "Call submit_evaluation now with your evaluation."})
                continue
            for tc in tool_calls:
                if tc["name"] != "submit_evaluation":
                    continue
                try:
                    args = json.loads(tc["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = build_evaluation_result(args, persona["label"], user_input)
                seq += 1
                return await self._finalize(evaluation_id, seq, result)

        # Model never submitted — honest low-confidence fallback so the run never dead-ends.
        result = build_evaluation_result({}, persona["label"], user_input)
        return await self._finalize(evaluation_id, seq + 1, result)
