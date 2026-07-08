"""GainsCheckWorkflow: evaluate tracked fitness inputs and suggest a goal.

The model returns a genuine evaluation (assessment + pass/fail + fail_kind) plus a
suggested goal the user can accept (jumping into the Plan step preselected) or
override. Personas set the tone; the substance is a real assessment — no GIFs,
meme quotes, or TTS. Reuses the generic `model_chat` activity.
"""
from __future__ import annotations

import json
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ..agents.tools.gains_tools import AGENTIC_TOOLS, TOOLS, get_persona

MAX_ROUNDS = 5
MAX_ROUNDS_AGENTIC = 5
_ACTIVITY_TIMEOUT = timedelta(seconds=30)
_GOALS = ("recomp", "weight_loss", "build_muscle", "get_lean")


def _system_prompt(persona: dict) -> str:
    return (
        f"You are {persona['voice']} — keep that tone, but give a GENUINELY USEFUL evaluation. "
        "You are given a user's tracked fitness numbers as JSON (weight_kg, body_fat_pct, calories, "
        "protein_g; any may be missing), or a `freeform` natural-language description to interpret.\n"
        "Decide if they are TRACKING and DOING IT RIGHT:\n"
        "- passed=false, fail_kind='not_tracking' if calories or protein are missing/zero (not logging).\n"
        "- passed=false, fail_kind='slacking' if they log real numbers but they're weak "
        "(protein_g < 1.6*weight_kg, or < 140 g if weight missing; or implausibly low calories).\n"
        "- passed=true otherwise (protein solid, calories > 0). Missing weight/body-fat is NOT a "
        "failure by itself.\n"
        "Write a real `assessment` (2-4 sentences: what's solid, what's lacking, where they stand). "
        "Then set `suggested_goal` to the ONE goal that best fits them "
        "(recomp | weight_loss | build_muscle | get_lean) and `suggestion_reason` (why, from their "
        "numbers). Call submit_verdict exactly once."
    )


def _agentic_system_prompt(persona: dict) -> str:
    return (
        f"You are {persona['voice']} — keep that tone, but give a GENUINELY USEFUL evaluation. "
        "Judge the user's tracked fitness numbers (weight_kg, body_fat_pct, calories, protein_g; any "
        "may be missing), or a `freeform` description to interpret. Think for YOURSELF — no fixed "
        "formula. Not logging calories/protein → fail_kind='not_tracking'; logging but weak → "
        "'slacking'; otherwise pass.\n"
        "Write a real `assessment` (2-4 sentences), then set `suggested_goal` "
        "(recomp | weight_loss | build_muscle | get_lean) and `suggestion_reason`. "
        "Call submit_verdict exactly once."
    )


def _build_result(args: dict, persona_label: str, mode: str | None = None) -> dict:
    passed = bool(args.get("passed"))
    fail_kind = args.get("fail_kind") if not passed else None
    if not passed and fail_kind not in ("not_tracking", "slacking"):
        fail_kind = "not_tracking"
    status = "on_track" if passed else ("needs_work" if fail_kind == "slacking" else "not_tracking")
    goal = args.get("suggested_goal")
    if goal not in _GOALS:
        goal = "recomp"
    result = {
        "passed": passed,
        "fail_kind": fail_kind,
        "status": status,
        "assessment": args.get("assessment") or "",
        "suggested_goal": goal,
        "suggestion_reason": args.get("suggestion_reason") or "",
        "persona": persona_label,
    }
    if mode:
        result["mode"] = mode
    return result


@workflow.defn
class GainsCheckWorkflow:
    @workflow.run
    async def run(self, check_id: str, user_input: dict) -> dict:
        try:
            if (user_input.get("mode") or "guided").lower() == "agentic":
                return await self._execute_agentic(check_id, user_input)
            return await self._execute(check_id, user_input)
        except Exception as exc:
            await workflow.execute_activity(
                "finalize_gains",
                args=[check_id, "error", None, f"workflow error: {exc}"[:500]],
                start_to_close_timeout=_ACTIVITY_TIMEOUT,
            )
            return {"check_id": check_id, "error": str(exc)}

    async def _emit(self, check_id, seq, stage, label, detail=None, tokens=None):
        await workflow.execute_activity(
            "record_gains_event",
            args=[check_id, seq, stage, label, detail, tokens],
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
        )

    async def _finalize(self, check_id, seq, result) -> dict:
        await self._emit(check_id, seq, "finalized", "Supabase · evaluation saved", {"status": result["status"]})
        await workflow.execute_activity(
            "finalize_gains", args=[check_id, "done", result, None], start_to_close_timeout=_ACTIVITY_TIMEOUT
        )
        return {"check_id": check_id, "result": result}

    async def _execute(self, check_id: str, user_input: dict) -> dict:
        persona = get_persona(user_input.get("persona"))
        messages: list[dict] = [
            {"role": "system", "content": _system_prompt(persona)},
            {"role": "user", "content": f"Here are my numbers: {json.dumps(user_input)}"},
        ]
        model_retry = RetryPolicy(maximum_attempts=3)
        seq = 0
        seq += 1
        await self._emit(check_id, seq, "dispatched", "Temporal · GainsCheckWorkflow", {"persona": persona["label"]})

        for rnd in range(MAX_ROUNDS):
            resp = await workflow.execute_activity(
                "model_chat",
                args=[messages, TOOLS, 2048, {"type": "function", "function": {"name": "submit_verdict"}}],
                start_to_close_timeout=timedelta(seconds=90),
                retry_policy=model_retry,
            )
            seq += 1
            await self._emit(check_id, seq, "reasoning", "Azure OpenAI · gpt-5-mini",
                             {"round": rnd + 1}, (resp.get("usage") or {}).get("total"))
            tool_calls = resp.get("tool_calls") or []
            assistant_msg: dict = {"role": "assistant", "content": resp.get("content")}
            if tool_calls:
                assistant_msg["tool_calls"] = [
                    {"id": tc["id"], "type": "function", "function": {"name": tc["name"], "arguments": tc["arguments"]}}
                    for tc in tool_calls
                ]
            messages.append(assistant_msg)
            if not tool_calls:
                messages.append({"role": "user", "content": "Call submit_verdict now with your evaluation."})
                continue
            for tc in tool_calls:
                if tc["name"] != "submit_verdict":
                    continue
                try:
                    args = json.loads(tc["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = _build_result(args, persona["label"])
                seq += 1
                return await self._finalize(check_id, seq, result)

        return await self._fallback(check_id, persona["label"], seq + 1, None)

    async def _execute_agentic(self, check_id: str, user_input: dict) -> dict:
        persona = get_persona(user_input.get("persona"))
        numbers = {k: user_input.get(k) for k in ("weight_kg", "body_fat_pct", "calories", "protein_g", "freeform")}
        messages: list[dict] = [
            {"role": "system", "content": _agentic_system_prompt(persona)},
            {"role": "user", "content": f"Here are my tracked numbers: {json.dumps(numbers)}. Evaluate me."},
        ]
        model_retry = RetryPolicy(maximum_attempts=3)
        seq = 0
        seq += 1
        await self._emit(check_id, seq, "dispatched", "Temporal · GainsCheckWorkflow (agentic)",
                         {"mode": "agentic", "persona": persona["label"]})

        for rnd in range(MAX_ROUNDS_AGENTIC):
            resp = await workflow.execute_activity(
                "model_chat",
                # No forced tool choice — the model reasons freely, then submits.
                args=[messages, AGENTIC_TOOLS, 2048],
                start_to_close_timeout=timedelta(seconds=90),
                retry_policy=model_retry,
            )
            seq += 1
            await self._emit(check_id, seq, "reasoning", "Azure OpenAI · gpt-5-mini",
                             {"round": rnd + 1, "mode": "agentic"}, (resp.get("usage") or {}).get("total"))
            tool_calls = resp.get("tool_calls") or []
            assistant_msg: dict = {"role": "assistant", "content": resp.get("content")}
            if tool_calls:
                assistant_msg["tool_calls"] = [
                    {"id": tc["id"], "type": "function", "function": {"name": tc["name"], "arguments": tc["arguments"]}}
                    for tc in tool_calls
                ]
            messages.append(assistant_msg)
            if not tool_calls:
                messages.append({"role": "user", "content": "Call submit_verdict now with your evaluation."})
                continue
            for tc in tool_calls:
                if tc["name"] != "submit_verdict":
                    continue
                try:
                    args = json.loads(tc["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = _build_result(args, persona["label"], mode="agentic")
                seq += 1
                return await self._finalize(check_id, seq, result)

        return await self._fallback(check_id, persona["label"], seq + 1, "agentic")

    async def _fallback(self, check_id, persona_label, seq, mode) -> dict:
        # Model never submitted (rare) — honest fallback so the demo never dead-ends.
        result = {
            "passed": False,
            "fail_kind": "not_tracking",
            "status": "not_tracking",
            "assessment": "Couldn't lock in an evaluation this time — check your numbers and run it again.",
            "suggested_goal": "recomp",
            "suggestion_reason": "A balanced default while you re-run the check.",
            "persona": persona_label,
        }
        if mode:
            result["mode"] = mode
        return await self._finalize(check_id, seq, result)
