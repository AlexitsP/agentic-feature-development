"""StudyPlanWorkflow: a multi-agent panel drafts a study plan for a goal.

Deterministic workflow (non-determinism in the reused `model_chat` activity). The
specialist panel runs in parallel, each grounded in the source allowlist; a head advisor
synthesises one plan (summary, weekly steps, how-to-study, sources); the pure builder
attaches the kernel confidence badge. Same run-row substrate as the evaluator.
"""
from __future__ import annotations

import asyncio
import json
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from .tools import (
        ADVISOR_TOOLS,
        ADVISORS,
        PLAN_TOOLS,
        build_plan_result,
        get_persona,
        sources_prompt,
    )

_ACTIVITY_TIMEOUT = timedelta(seconds=30)
_MODEL_TIMEOUT = timedelta(seconds=90)
_GENERIC_ERROR = "Plan generation failed — please try again."

_PROFILE_KEYS = ("target_field", "institution_type", "prior_qualification", "timeframe", "interests", "canton", "freeform")


def _advisor_system(advisor: dict) -> str:
    return (
        f"You are {advisor['role']} on a study-planning panel. {advisor['brief']} "
        "Be concise, realistic and safe. Ground everything in established evidence and the official "
        "Swiss sources below (never invent a URL):\n"
        f"{sources_prompt()}\n"
        "Call submit_advice exactly once."
    )


def _synth_system(persona: dict) -> str:
    return (
        f"You are {persona['voice']}, acting as the head advisor. Your specialist panel has given "
        "advice. Combine it into ONE cohesive, realistic study plan the student can start this week: "
        "a short summary, 4-6 concrete weekly steps, and 2-4 evidence-based how-to-study pointers. "
        "For resource_urls pick 2-4 links ONLY from this official list (never invent a URL):\n"
        f"{sources_prompt()}\n"
        "Call submit_plan exactly once."
    )


@workflow.defn
class StudyPlanWorkflow:
    @workflow.run
    async def run(self, plan_id: str, user_input: dict) -> dict:
        try:
            return await self._execute(plan_id, user_input)
        except Exception:
            workflow.logger.exception("study plan workflow failed")
            await workflow.execute_activity(
                "finalize_plan", args=[plan_id, "error", None, _GENERIC_ERROR], start_to_close_timeout=_ACTIVITY_TIMEOUT
            )
            return {"plan_id": plan_id, "error": "internal error"}

    async def _model(self, messages, tools, tool_name, max_tokens=2048):
        resp = await workflow.execute_activity(
            "model_chat",
            args=[messages, tools, max_tokens, {"type": "function", "function": {"name": tool_name}}],
            start_to_close_timeout=_MODEL_TIMEOUT,
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        tokens = (resp.get("usage") or {}).get("total")
        for tc in resp.get("tool_calls") or []:
            if tc["name"] == tool_name:
                try:
                    return json.loads(tc["arguments"] or "{}"), tokens
                except json.JSONDecodeError:
                    return {}, tokens
        return {}, tokens

    async def _advisor(self, advisor: dict, ctx_content: str) -> dict:
        args, tokens = await self._model(
            [
                {"role": "system", "content": _advisor_system(advisor)},
                {"role": "user", "content": ctx_content},
            ],
            ADVISOR_TOOLS,
            "submit_advice",
        )
        return {
            "key": advisor["key"],
            "title": advisor["title"],
            "headline": args.get("headline") or "",
            "points": args.get("points") or [],
            "_tokens": tokens,
        }

    async def _execute(self, plan_id: str, user_input: dict) -> dict:
        persona = get_persona(user_input.get("persona"))
        profile = {k: user_input.get(k) for k in _PROFILE_KEYS}
        ctx_content = f"Study goal + situation: {json.dumps(profile)}. Draft a plan."

        seq = 0

        async def emit(stage, label, detail=None, tokens=None):
            nonlocal seq
            seq += 1
            await workflow.execute_activity(
                "record_plan_event", args=[plan_id, seq, stage, label, detail, tokens], start_to_close_timeout=_ACTIVITY_TIMEOUT
            )

        await emit("dispatched", "Temporal · StudyPlanWorkflow", {"panel_size": len(ADVISORS)})

        # 1) Panel in parallel.
        panel = await asyncio.gather(*[self._advisor(a, ctx_content) for a in ADVISORS])
        for p in panel:
            await emit("agent", f"Agent · {p['title']}", {"points": len(p["points"])}, p.get("_tokens"))

        # 2) Head advisor synthesises the plan.
        synth_args, synth_tokens = await self._model(
            [
                {"role": "system", "content": _synth_system(persona)},
                {"role": "user", "content": f"{ctx_content}\n\nPanel advice: {json.dumps(panel)}\n\nWrite the final plan."},
            ],
            PLAN_TOOLS,
            "submit_plan",
            max_tokens=4096,
        )
        await emit("synth", "Head advisor · synthesis", {"steps": len(synth_args.get("weekly_steps") or [])}, synth_tokens)

        result = build_plan_result(synth_args, panel, persona["label"], user_input)
        await emit("finalized", "Supabase · plan saved", {"tier": result["confidence"]["tier"]})
        await workflow.execute_activity(
            "finalize_plan", args=[plan_id, "done", result, None], start_to_close_timeout=_ACTIVITY_TIMEOUT
        )
        return {"plan_id": plan_id, "result": result}
