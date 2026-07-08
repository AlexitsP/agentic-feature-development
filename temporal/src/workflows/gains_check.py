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
    from ..agents.tools.gains_tools import AGENTIC_TOOLS, TOOLS, VOICE_STYLES, get_persona

MAX_ROUNDS = 5
MAX_ROUNDS_AGENTIC = 6
_ACTIVITY_TIMEOUT = timedelta(seconds=30)


def _agentic_system_prompt(persona: dict) -> str:
    return (
        f"You are {persona['voice']}, judging a lifter's tracked fitness numbers "
        "(weight_kg, body_fat_pct, calories, protein_g; any may be missing). The input may instead "
        "carry a `freeform` natural-language description of how they eat and train — if so, interpret "
        "it yourself.\n"
        "Think for YOURSELF — there is no fixed formula. Use your own judgment about what good "
        "macros look like for someone's bodyweight and goals. If they logged no calories or "
        "protein, they aren't really tracking (fail, fail_kind='not_tracking'). If they log real "
        "numbers but they're weak, that's slacking (fail, fail_kind='slacking'). Otherwise pass.\n"
        "You have a search_gif tool — use it to find a GIF that fits your verdict; YOU pick the "
        "search terms. You may call it several times.\n"
        "When you're done searching, call submit_verdict exactly once with your verdict, the gif_url "
        "you chose (paste a URL a search returned), and the voice_style for how it should be spoken. "
        "Stay fully in character."
    )


def _system_prompt(persona: dict) -> str:
    return (
        f"You are {persona['voice']}. "
        "You are given a user's tracked fitness numbers as JSON: weight_kg, body_fat_pct, "
        "calories, protein_g. Decide if they are TRACKING and DOING IT RIGHT.\n"
        "- NOT TRACKING (fail, fail_kind='not_tracking') if calories or protein_g is missing, "
        "null, or 0 — they aren't even logging. Then headline 'YOU SHOULD', sound 'shame', and a "
        "scolding spoken_line.\n"
        "- TRACKING BUT SLACKING (fail, fail_kind='slacking') if they DID log real numbers but "
        "they're weak: protein_g < 1.6 * weight_kg (or < 140 g if weight is missing), or calories "
        "are implausibly low. Then headline 'DO BETTER', sound 'shame', a spoken_line that pushes "
        "them to step it up.\n"
        "- DOING IT RIGHT (pass): protein_g >= 1.6 * weight_kg is solid; if weight_kg is missing "
        "or 0, judge on protein alone and >= 140 g is a solid PASS. calories > 0. Then pass: "
        "headline 'YEAH BUDDY!' or 'LIGHTWEIGHT BABY!', sound 'hype', a hype spoken_line (a "
        "catchphrase in your voice).\n"
        "IMPORTANT: missing weight_kg or body_fat_pct is NOT a failure by itself — only calories "
        "and protein_g matter for whether they're tracking, and protein is the bar for doing it "
        "right. Do NOT mark someone 'slacking' merely because weight or body fat is missing; if "
        "calories > 0 and protein_g >= 140, that is a PASS.\n"
        "If instead a `freeform` field is present (a natural-language description of how they eat "
        "and train), interpret it to estimate calories/protein/bodyweight and judge the SAME way — "
        "only mark 'not_tracking' if they clearly aren't tracking their food at all.\n"
        "Always set fail_kind on a fail. Call submit_verdict exactly once with your decision. Stay in character."
    )


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

    async def _execute(self, check_id: str, user_input: dict) -> dict:
        persona = get_persona(user_input.get("persona"))
        messages: list[dict] = [
            {"role": "system", "content": _system_prompt(persona)},
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
            {"via": "poller claim", "task_queue": "main", "persona": persona["label"]},
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
                        "content": "Call submit_verdict now with your final decision.",
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
                fail_kind = args.get("fail_kind") if not passed else None
                if not passed and fail_kind not in ("not_tracking", "slacking"):
                    fail_kind = "not_tracking"
                default_headline = "YEAH BUDDY!" if passed else ("DO BETTER" if fail_kind == "slacking" else "YOU SHOULD")
                result = {
                    "passed": passed,
                    "fail_kind": fail_kind,
                    "headline": args.get("headline") or default_headline,
                    "spoken_line": args.get("spoken_line") or "",
                    "gif_url": None,
                    "sound": args.get("sound") or ("hype" if passed else "shame"),
                    "reason": args.get("reason") or "",
                    "persona": persona["label"],
                    "steps": steps,
                }

                # Deterministic themed GIF: Ronnie/Arnold on a pass; on a fail the
                # GIF depends on the kind (angry dog vs disappointed "come on").
                gif = await workflow.execute_activity(
                    "fetch_verdict_gif", args=[passed, fail_kind], start_to_close_timeout=_ACTIVITY_TIMEOUT
                )
                result["gif_url"] = gif.get("url")
                # On a pass, the headline + spoken line are a meme quote from the
                # SAME legend as the GIF (Ronnie or Arnold), not the model's text.
                if passed and gif.get("quote"):
                    result["headline"] = gif["quote"]
                    result["spoken_line"] = gif["quote"]
                steps.append({"tool": "fetch_verdict_gif", "args": {"passed": passed, "fail_kind": fail_kind}, "result": gif})
                await emit(
                    "tool",
                    "Giphy · fetch GIF",
                    {"query": gif.get("query"), "source": gif.get("source"), "subject": gif.get("subject"), "found": bool(gif.get("url"))},
                )

                style = persona["hype_style"] if passed else persona["shame_style"]
                audio_b64 = await workflow.execute_activity(
                    "synthesize_speech",
                    args=[result["spoken_line"], style, passed],
                    start_to_close_timeout=timedelta(seconds=30),
                )
                result["audio_b64"] = audio_b64
                await emit(
                    "speech",
                    "Azure Speech · neural TTS",
                    {
                        "voice": "en-US-DavisNeural",
                        "style": style,
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

        # Max rounds exceeded (rare — the verdict tool is forced). Rather than a
        # bare error, hand back a fun canned verdict so the demo never dead-ends.
        return await self._fallback_verdict(check_id, persona, steps, emit)

    async def _fallback_verdict(self, check_id, persona, steps, emit) -> dict:
        gif = await workflow.execute_activity(
            "fetch_verdict_gif", args=[False, "slacking"], start_to_close_timeout=_ACTIVITY_TIMEOUT
        )
        spoken = "The coach got distracted counting reps. Log it clean and run it back!"
        result = {
            "passed": False,
            "fail_kind": "slacking",
            "headline": "RUN IT BACK",
            "spoken_line": spoken,
            "gif_url": gif.get("url"),
            "sound": "shame",
            "reason": "The coach couldn't lock in a verdict — punch in your numbers and check again.",
            "persona": persona["label"],
            "steps": steps,
        }
        audio_b64 = await workflow.execute_activity(
            "synthesize_speech", args=[spoken, persona["shame_style"], False], start_to_close_timeout=timedelta(seconds=30)
        )
        result["audio_b64"] = audio_b64
        await emit("finalized", "Supabase · fallback verdict saved", {"passed": False, "headline": result["headline"]})
        await workflow.execute_activity(
            "finalize_gains", args=[check_id, "done", result, None], start_to_close_timeout=_ACTIVITY_TIMEOUT
        )
        return {"check_id": check_id, "result": result}

    # ── Agentic path ─────────────────────────────────────────────────────────
    # The model gets a real tool (search_gif) it chooses when/how to call, and
    # submit_verdict is NOT forced — so this is a genuine reason -> search -> decide
    # loop. Nothing here overrides the model: it picks the GIFs, the legend, the
    # comparison, the headline, the spoken line, and the voice style itself.
    async def _execute_agentic(self, check_id: str, user_input: dict) -> dict:
        persona = get_persona(user_input.get("persona"))
        numbers = {k: user_input.get(k) for k in ("weight_kg", "body_fat_pct", "calories", "protein_g", "freeform")}
        messages: list[dict] = [
            {"role": "system", "content": _agentic_system_prompt(persona)},
            {"role": "user", "content": f"Here are my tracked numbers: {json.dumps(numbers)}. Judge me."},
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
            "Temporal · GainsCheckWorkflow (agentic)",
            {"via": "poller claim", "task_queue": "main", "mode": "agentic", "persona": persona["label"]},
        )

        for rnd in range(MAX_ROUNDS_AGENTIC):
            resp = await workflow.execute_activity(
                "model_chat",
                # No forced tool_choice — the model decides whether to search or submit.
                args=[messages, AGENTIC_TOOLS, 2048],
                start_to_close_timeout=timedelta(seconds=90),
                retry_policy=model_retry,
            )
            usage = resp.get("usage") or {}
            await emit(
                "reasoning",
                "Azure OpenAI · gpt-5-mini",
                {"round": rnd + 1, "finish_reason": resp.get("finish_reason"), "mode": "agentic"},
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
                messages.append(
                    {"role": "user", "content": "Use search_gif if you want a GIF, then call submit_verdict with your final decision."}
                )
                continue

            submit_args: dict | None = None
            for tc in tool_calls:
                try:
                    args = json.loads(tc["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}

                if tc["name"] == "search_gif":
                    query = str(args.get("query") or "")
                    gif = await workflow.execute_activity(
                        "search_gif", args=[query], start_to_close_timeout=_ACTIVITY_TIMEOUT
                    )
                    steps.append({"tool": "search_gif", "args": {"query": query}, "result": gif})
                    await emit(
                        "tool",
                        "Giphy · search_gif",
                        {"query": gif.get("query"), "source": gif.get("source"), "found": bool(gif.get("url"))},
                    )
                    messages.append({"role": "tool", "tool_call_id": tc["id"], "content": json.dumps(gif)})
                elif tc["name"] == "submit_verdict":
                    submit_args = args

            if submit_args is not None:
                return await self._finalize_agentic(check_id, persona, submit_args, steps, emit)

        return await self._fallback_agentic(check_id, persona, steps, emit)

    async def _finalize_agentic(self, check_id, persona, args, steps, emit) -> dict:
        passed = bool(args.get("passed"))
        fail_kind = args.get("fail_kind") if not passed else None
        if not passed and fail_kind not in ("not_tracking", "slacking"):
            fail_kind = "not_tracking"

        voice_style = args.get("voice_style")
        if voice_style not in VOICE_STYLES:
            voice_style = persona["hype_style"] if passed else persona["shame_style"]

        default_headline = "YEAH BUDDY!" if passed else ("DO BETTER" if fail_kind == "slacking" else "YOU SHOULD")
        result = {
            "passed": passed,
            "fail_kind": fail_kind,
            "mode": "agentic",
            "headline": args.get("headline") or default_headline,
            "spoken_line": args.get("spoken_line") or "",
            "gif_url": args.get("gif_url") or None,
            "sound": "hype" if passed else "shame",
            "reason": args.get("reason") or "",
            "persona": persona["label"],
            "steps": steps,
        }

        audio_b64 = await workflow.execute_activity(
            "synthesize_speech", args=[result["spoken_line"], voice_style, passed], start_to_close_timeout=timedelta(seconds=30)
        )
        result["audio_b64"] = audio_b64
        await emit(
            "speech",
            "Azure Speech · neural TTS",
            {"voice": "en-US-DavisNeural", "style": voice_style, "bytes": (len(audio_b64) * 3 // 4) if audio_b64 else 0},
        )
        await emit("finalized", "Supabase · verdict saved", {"passed": passed, "headline": result["headline"]})
        await workflow.execute_activity(
            "finalize_gains", args=[check_id, "done", result, None], start_to_close_timeout=_ACTIVITY_TIMEOUT
        )
        return {"check_id": check_id, "result": result}

    async def _fallback_agentic(self, check_id, persona, steps, emit) -> dict:
        gif = await workflow.execute_activity(
            "fetch_verdict_gif", args=[False, "slacking"], start_to_close_timeout=_ACTIVITY_TIMEOUT
        )
        spoken = "The coach got lost in thought. Run it back!"
        result = {
            "passed": False,
            "fail_kind": "slacking",
            "mode": "agentic",
            "headline": "RUN IT BACK",
            "spoken_line": spoken,
            "gif_url": gif.get("url"),
            "sound": "shame",
            "reason": "The coach couldn't lock in a verdict — check again.",
            "persona": persona["label"],
            "steps": steps,
            "legend": None,
        }
        result["audio_b64"] = await workflow.execute_activity(
            "synthesize_speech", args=[spoken, persona["shame_style"], False], start_to_close_timeout=timedelta(seconds=30)
        )
        await emit("finalized", "Supabase · fallback verdict saved", {"passed": False, "headline": result["headline"]})
        await workflow.execute_activity(
            "finalize_gains", args=[check_id, "done", result, None], start_to_close_timeout=_ACTIVITY_TIMEOUT
        )
        return {"check_id": check_id, "result": result}
