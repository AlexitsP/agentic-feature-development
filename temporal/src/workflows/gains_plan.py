"""GainsPlanWorkflow: an agentic PANEL turns a goal + the user's stats into a research-based plan.

This is deliberately multi-agent (per the product intent): three specialist agents — a
sports-nutrition dietitian, a strength & conditioning coach, and a habits/recovery coach — are
dispatched IN PARALLEL, each grounding its advice in established evidence + a curated resource
list. A final head-coach agent then synthesizes the panel's advice into one cohesive plan and
cites resources (constrained in code to the curated list, so links are always real).

Same Supabase-substrate pattern as the check: a `gains_plans` pending row is claimed by the
poller and this workflow runs the panel, then finalizes the row.
"""
from __future__ import annotations

import asyncio
import json
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ..agents.tools.gains_tools import (
        ADVISOR_TOOLS,
        PLAN_TOOLS,
        get_persona,
        plan_resources_prompt,
        resolve_plan_resources,
    )

_ACTIVITY_TIMEOUT = timedelta(seconds=30)
_MODEL_TIMEOUT = timedelta(seconds=90)

GOAL_LABELS = {
    "recomp": "Body recomposition — lose fat while preserving/building muscle",
    "weight_loss": "Weight loss — calorie deficit with solid macros",
    "build_muscle": "Build muscle — lean bulk / hypertrophy",
    "get_lean": "Get lean — cut down to lower body fat",
    "custom": "Custom goal",
}

# The panel of specialist agents dispatched in parallel.
ADVISORS = [
    {
        "key": "nutrition",
        "title": "Sports-nutrition dietitian",
        "role": "a registered sports-nutrition dietitian",
        "brief": "Give an evidence-based calorie target and a protein target for this goal and their stats "
                 "(fill calorie_guidance and protein_guidance), plus 2-3 concrete diet pointers as points.",
    },
    {
        "key": "training",
        "title": "Strength & conditioning coach",
        "role": "a strength & conditioning coach",
        "brief": "Give the training emphasis for this goal (fill training_focus) and 3-4 concrete weekly "
                 "training actions as points.",
    },
    {
        "key": "habits",
        "title": "Habits & recovery coach",
        "role": "a habits, sleep and recovery coach",
        "brief": "Give 2-3 high-leverage sleep, recovery and adherence habits for this goal as points.",
    },
]


def _advisor_system(advisor: dict) -> str:
    return (
        f"You are {advisor['role']} on a coaching panel. {advisor['brief']} "
        "Ground everything in established exercise-science and nutrition evidence; be concise, "
        "realistic and safe (no crash diets or extreme advice). Trusted references you may rely on:\n"
        f"{plan_resources_prompt()}\n"
        "Call submit_advice exactly once."
    )


def _synth_system(persona: dict) -> str:
    return (
        f"You are {persona['voice']}, acting as the HEAD COACH. Your specialist panel (a dietitian, a "
        "strength coach, and a habits coach) has each given advice. Combine it into ONE cohesive, "
        "encouraging, research-based starter plan the user can begin THIS week. Use the panel's "
        "calorie/protein/training guidance; keep it realistic and safe.\n"
        "For resource_urls pick 2-4 links ONLY from this list (never invent a URL):\n"
        f"{plan_resources_prompt()}\n"
        "Call submit_plan exactly once."
    )


@workflow.defn
class GainsPlanWorkflow:
    @workflow.run
    async def run(self, plan_id: str, user_input: dict) -> dict:
        try:
            return await self._execute(plan_id, user_input)
        except Exception as exc:
            await workflow.execute_activity(
                "finalize_plan",
                args=[plan_id, "error", None, f"workflow error: {exc}"[:500]],
                start_to_close_timeout=_ACTIVITY_TIMEOUT,
            )
            return {"plan_id": plan_id, "error": str(exc)}

    async def _model(self, messages, tools, tool_name, max_tokens=1024):
        """One forced-tool model turn; returns (parsed tool args, total tokens used)."""
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
            max_tokens=2048,
        )
        return {
            "key": advisor["key"],
            "title": advisor["title"],
            "headline": args.get("headline") or "",
            "points": args.get("points") or [],
            "calorie_guidance": args.get("calorie_guidance") or "",
            "protein_guidance": args.get("protein_guidance") or "",
            "training_focus": args.get("training_focus") or "",
            "_tokens": tokens,
        }

    async def _execute(self, plan_id: str, user_input: dict) -> dict:
        persona = get_persona(user_input.get("persona"))
        goal = user_input.get("goal") or "custom"
        goal_label = GOAL_LABELS.get(goal, "Custom goal")
        goal_detail = (user_input.get("goal_detail") or "").strip()
        ctx = {k: user_input.get(k) for k in ("weight_kg", "body_fat_pct", "calories", "protein_g", "freeform", "passed", "fail_kind")}
        ctx_content = (
            f"Goal: {goal_label}."
            + (f" In their words: {goal_detail}." if goal_detail else "")
            + f" Their stats/verdict: {json.dumps(ctx)}."
        )

        seq = 0

        async def emit(stage: str, label: str, detail: object = None, tokens: int | None = None) -> None:
            nonlocal seq
            seq += 1
            await workflow.execute_activity(
                "record_plan_event",
                args=[plan_id, seq, stage, label, detail, tokens],
                start_to_close_timeout=_ACTIVITY_TIMEOUT,
            )

        await emit(
            "dispatched",
            "Temporal · GainsPlanWorkflow",
            {"panel_size": len(ADVISORS), "goal": goal_label},
        )

        # 1) Dispatch the specialist panel IN PARALLEL, then record each contribution.
        panel = await asyncio.gather(*[self._advisor(a, ctx_content) for a in ADVISORS])
        for p in panel:
            await emit("agent", f"Agent · {p['title']}", {"headline": (p["headline"] or "")[:90], "points": len(p["points"])}, p.get("_tokens"))

        # 2) Head coach synthesizes the panel into one plan.
        synth_args, synth_tokens = await self._model(
            [
                {"role": "system", "content": _synth_system(persona)},
                {"role": "user", "content": f"{ctx_content}\n\nPanel advice: {json.dumps(panel)}\n\nWrite the final plan."},
            ],
            PLAN_TOOLS,
            "submit_plan",
            max_tokens=4096,
        )
        await emit("synth", "Head coach · synthesis", {"resources": len(synth_args.get("resource_urls") or [])}, synth_tokens)

        # Fall back to the nutrition advisor's numbers if the synthesizer left them blank.
        nutri = next((p for p in panel if p["key"] == "nutrition"), {})
        train = next((p for p in panel if p["key"] == "training"), {})
        result = {
            "goal_label": goal_label,
            "persona": persona["label"],
            "summary": synth_args.get("summary") or "",
            "calorie_guidance": synth_args.get("calorie_guidance") or nutri.get("calorie_guidance") or "",
            "protein_guidance": synth_args.get("protein_guidance") or nutri.get("protein_guidance") or "",
            "training_focus": synth_args.get("training_focus") or train.get("training_focus") or "",
            "weekly_steps": synth_args.get("weekly_steps") or [],
            "resources": resolve_plan_resources(synth_args.get("resource_urls") or []),
            # Make the collaboration visible: what each agent contributed.
            "panel": [{"title": p["title"], "headline": p["headline"], "points": p["points"]} for p in panel],
        }
        await emit("finalized", "Supabase · plan saved", {"goal": goal_label, "steps": len(result["weekly_steps"])})
        await workflow.execute_activity(
            "finalize_plan", args=[plan_id, "done", result, None], start_to_close_timeout=_ACTIVITY_TIMEOUT
        )
        return {"plan_id": plan_id, "result": result}
