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
    "'YOU SHOULD', sound 'shame', and a scolding spoken_line.\n"
    "- If tracking, judge: protein_g >= 1.6 * weight_kg is solid (if weight is missing, "
    ">= 140 g is solid); calories should be > 0; body_fat_pct should be plausible (0-60). "
    "If solid -> pass: headline 'YEAH BUDDY!' or 'LIGHTWEIGHT BABY!', sound 'hype', a "
    "hype spoken_line (a Ronnie Coleman / Arnold catchphrase).\n"
    "Call submit_verdict exactly once with your decision. Keep it fun."
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

        # Pick a random legend to stack the user up against.
        legend = await workflow.execute_activity(
            "pick_legend", start_to_close_timeout=_ACTIVITY_TIMEOUT
        )
        messages.append(
            {
                "role": "user",
                "content": (
                    f"Also compare me to {legend['name']} — contest weight {legend['weight_kg']} kg, "
                    f"~{legend['body_fat_pct']}% body fat, height {legend['height_cm']} cm "
                    f"({legend['fun_fact']}). In legend_quip, tell me in a funny way how close "
                    "(or hilariously far) my numbers are to theirs."
                ),
            }
        )
        await emit(
            "legend",
            f"Legend · {legend['name']}",
            {"name": legend["name"], "found": bool(legend.get("image_url"))},
        )

        for rnd in range(MAX_ROUNDS):
            resp = await workflow.execute_activity(
                "model_chat",
                # Force the verdict tool so the reasoning model can't just "think
                # out loud" and skip it, and give it headroom for reasoning tokens.
                args=[messages, TOOLS, 2048, {"type": "function", "function": {"name": "submit_verdict"}}],
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
                # The model replied with prose instead of calling the tool; nudge
                # it and loop rather than giving up (reasoning models sometimes
                # "think out loud" for a turn before calling the function).
                messages.append(
                    {
                        "role": "user",
                        "content": "Call submit_verdict now with your final decision, including legend_quip.",
                    }
                )
                continue

            for tc in tool_calls:
                name = tc["name"]
                try:
                    args = json.loads(tc["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}

                if name != "submit_verdict":
                    continue

                passed = bool(args.get("passed"))
                result = {
                    "passed": passed,
                    "headline": args.get("headline") or ("YEAH BUDDY!" if passed else "YOU SHOULD"),
                    "spoken_line": args.get("spoken_line") or "",
                    "gif_url": None,
                    "sound": args.get("sound") or ("hype" if passed else "shame"),
                    "reason": args.get("reason") or "",
                    "steps": steps,
                    "legend": {
                        "name": legend["name"],
                        "weight_kg": legend["weight_kg"],
                        "height_cm": legend["height_cm"],
                        "body_fat_pct": legend["body_fat_pct"],
                        "fun_fact": legend["fun_fact"],
                        "image_url": legend.get("image_url"),
                        "quip": args.get("legend_quip") or "",
                    },
                }

                # Deterministic themed GIF: Ronnie/Arnold on a pass, a dog on a fail.
                gif = await workflow.execute_activity(
                    "fetch_verdict_gif", args=[passed], start_to_close_timeout=_ACTIVITY_TIMEOUT
                )
                result["gif_url"] = gif.get("url")
                # On a pass, the headline + spoken line are a meme quote from the
                # SAME legend as the GIF (Ronnie or Arnold), not the model's text.
                if passed and gif.get("quote"):
                    result["headline"] = gif["quote"]
                    result["spoken_line"] = gif["quote"]
                steps.append({"tool": "fetch_verdict_gif", "args": {"passed": passed}, "result": gif})
                await emit(
                    "tool",
                    "Giphy · fetch GIF",
                    {"query": gif.get("query"), "source": gif.get("source"), "subject": gif.get("subject"), "found": bool(gif.get("url"))},
                )

                audio_b64 = await workflow.execute_activity(
                    "synthesize_speech",
                    args=[result["spoken_line"], passed],
                    start_to_close_timeout=timedelta(seconds=30),
                )
                result["audio_b64"] = audio_b64
                await emit(
                    "speech",
                    "Azure Speech · neural TTS",
                    {
                        "voice": "en-US-DavisNeural",
                        "style": "excited" if passed else "angry",
                        "bytes": (len(audio_b64) * 3 // 4) if audio_b64 else 0,
                    },
                )
                await emit(
                    "finalized",
                    "Supabase · verdict saved",
                    {"passed": passed, "headline": result["headline"]},
                )
                await workflow.execute_activity(
                    "finalize_gains", args=[check_id, "done", result, None], start_to_close_timeout=_ACTIVITY_TIMEOUT
                )
                return {"check_id": check_id, "result": result}

        await workflow.execute_activity(
            "finalize_gains", args=[check_id, "error", None, "max rounds exceeded"], start_to_close_timeout=_ACTIVITY_TIMEOUT
        )
        return {"check_id": check_id, "error": "max rounds exceeded"}
