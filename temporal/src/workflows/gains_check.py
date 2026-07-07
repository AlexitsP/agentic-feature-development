"""GainsCheckWorkflow: judge tracked fitness inputs, fetch a GIF, return a verdict.

Reuses the generic `model_chat` activity. The agent decides pass/fail, fetches a
hype or shame GIF via search_gif, then calls submit_verdict.
"""
from __future__ import annotations

import json
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ..agents.tools.gains_tools import TOOLS

MAX_ROUNDS = 5
_ACTIVITY_TIMEOUT = timedelta(seconds=30)

_SYSTEM = (
    "You are a loud, funny bodybuilding coach (think Ronnie Coleman / Arnold). "
    "You are given a user's tracked fitness numbers as JSON: weight_kg, body_fat_pct, "
    "calories, protein_g. Decide if they are TRACKING and DOING IT RIGHT.\n"
    "- NOT TRACKING (fail) if calories or protein_g is missing, null, or 0. Then headline "
    "'YOU SHOULD', sound 'shame', a scolding spoken_line, and a gif query like "
    "'angry dog barking' or 'disappointed'.\n"
    "- If tracking, judge: protein_g >= 1.6 * weight_kg is solid (if weight is missing, "
    ">= 140 g is solid); calories should be > 0; body_fat_pct should be plausible (0-60). "
    "If solid -> pass: headline 'YEAH BUDDY!' or 'LIGHTWEIGHT BABY!', sound 'hype', a "
    "hype spoken_line (a Ronnie Coleman / Arnold catchphrase), gif query like "
    "'Ronnie Coleman yeah buddy' or 'Arnold Schwarzenegger flex'.\n"
    "ALWAYS: first call search_gif with your chosen query, then call submit_verdict "
    "with gif_url set to the url it returned (empty string if none). Keep it fun."
)


@workflow.defn
class GainsCheckWorkflow:
    @workflow.run
    async def run(self, check_id: str, user_input: dict) -> dict:
        try:
            return await self._execute(check_id, user_input)
        except Exception as exc:
            await workflow.execute_activity(
                "finalize_gains",
                args=[check_id, "error", None, f"workflow error: {exc}"[:500]],
                start_to_close_timeout=_ACTIVITY_TIMEOUT,
            )
            return {"check_id": check_id, "error": str(exc)}

    async def _execute(self, check_id: str, user_input: dict) -> dict:
        messages: list[dict] = [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": f"Here are my numbers: {json.dumps(user_input)}"},
        ]
        steps: list[dict] = []
        model_retry = RetryPolicy(maximum_attempts=3)
        seq = 0

        async def emit(stage: str, label: str, detail: object = None, tokens: int | None = None) -> None:
            nonlocal seq
            seq += 1
            await workflow.execute_activity(
                "record_gains_event",
                args=[check_id, seq, stage, label, detail, tokens],
                start_to_close_timeout=_ACTIVITY_TIMEOUT,
            )

        await emit(
            "dispatched",
            "Temporal · GainsCheckWorkflow",
            {"via": "poller claim", "task_queue": "main"},
        )

        for rnd in range(MAX_ROUNDS):
            resp = await workflow.execute_activity(
                "model_chat",
                args=[messages, TOOLS, 1024],
                start_to_close_timeout=timedelta(seconds=90),
                retry_policy=model_retry,
            )
            usage = resp.get("usage") or {}
            await emit(
                "reasoning",
                "Azure OpenAI · gpt-5-mini",
                {"round": rnd + 1, "finish_reason": resp.get("finish_reason")},
                usage.get("total"),
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
                result = {
                    "passed": False,
                    "headline": "HMM",
                    "spoken_line": resp.get("content") or "Try again.",
                    "gif_url": None,
                    "sound": "shame",
                    "reason": "No verdict produced.",
                    "steps": steps,
                }
                await emit("finalized", "Supabase · verdict saved", {"passed": False})
                await workflow.execute_activity(
                    "finalize_gains", args=[check_id, "done", result, None], start_to_close_timeout=_ACTIVITY_TIMEOUT
                )
                return {"check_id": check_id, "result": result}

            for tc in tool_calls:
                name = tc["name"]
                try:
                    args = json.loads(tc["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}

                if name == "submit_verdict":
                    result = {
                        "passed": bool(args.get("passed")),
                        "headline": args.get("headline") or ("YEAH BUDDY!" if args.get("passed") else "YOU SHOULD"),
                        "spoken_line": args.get("spoken_line") or "",
                        "gif_url": args.get("gif_url") or None,
                        "sound": args.get("sound") or ("hype" if args.get("passed") else "shame"),
                        "reason": args.get("reason") or "",
                        "steps": steps,
                    }
                    await emit(
                        "finalized",
                        "Supabase · verdict saved",
                        {"passed": result["passed"], "headline": result["headline"]},
                    )
                    await workflow.execute_activity(
                        "finalize_gains", args=[check_id, "done", result, None], start_to_close_timeout=_ACTIVITY_TIMEOUT
                    )
                    return {"check_id": check_id, "result": result}

                gif = await workflow.execute_activity(
                    "search_gif", args=[args.get("query", "")], start_to_close_timeout=_ACTIVITY_TIMEOUT
                )
                steps.append({"tool": name, "args": args, "result": gif})
                await emit(
                    "tool",
                    "Giphy · search_gif",
                    {"query": args.get("query"), "source": gif.get("source"), "found": bool(gif.get("url"))},
                )
                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": json.dumps(gif)})

        await workflow.execute_activity(
            "finalize_gains", args=[check_id, "error", None, "max rounds exceeded"], start_to_close_timeout=_ACTIVITY_TIMEOUT
        )
        return {"check_id": check_id, "error": "max rounds exceeded"}
