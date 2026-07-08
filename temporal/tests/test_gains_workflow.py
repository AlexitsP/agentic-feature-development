"""Workflow tests for GainsCheckWorkflow — real Temporal execution, mocked activities.

Uses the time-skipping test environment so retries/timeouts don't slow the suite.
Every activity is replaced with a stub that records calls and returns scripted
values, so these assert the workflow's ORCHESTRATION: verdict routing, the meme-
quote override, the forced-vs-auto tool choice, the max-rounds fallback, and the
agentic reason->search->decide loop. No network, no model, no Supabase.
"""
from __future__ import annotations

import json
import uuid

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from src.workflows.gains_check import GainsCheckWorkflow, MAX_ROUNDS


class Harness:
    def __init__(self):
        self.model_responses: list[dict] = []
        self.calls: list[tuple] = []
        self.final: dict | None = None
        self.pass_gif = {
            "url": "http://gif/pass.gif", "source": "giphy", "query": "ronnie",
            "subject": "Ronnie Coleman", "quote": "YEAH BUDDY!", "fail_kind": None,
        }
        self.fail_gif = {"url": "http://gif/fail.gif", "source": "giphy", "query": "dog", "subject": None, "quote": None}
        self.legend = {
            "name": "Ronnie Coleman", "weight_kg": 137, "height_cm": 180, "body_fat_pct": 4,
            "gif_query": "Ronnie Coleman", "fun_fact": "8x Mr. Olympia", "image_url": "http://legend.gif", "matched": True,
        }
        self.search_result = {"url": "http://searched.gif", "source": "giphy", "query": ""}


# Module global so the activity stubs (which read `H` at call time) always see the
# current test's harness; the fixture swaps it out before each test.
H = Harness()


@pytest.fixture(autouse=True)
def _reset_harness():
    global H
    H = Harness()
    yield


@activity.defn(name="record_gains_event")
async def m_record(check_id, seq, stage, label, detail=None, tokens=None):
    H.calls.append(("record_gains_event", stage))


@activity.defn(name="model_chat")
async def m_model_chat(messages, tools, max_tokens=2048, tool_choice="auto"):
    H.calls.append(("model_chat", tool_choice))
    return H.model_responses.pop(0)


@activity.defn(name="fetch_verdict_gif")
async def m_fetch_gif(passed, fail_kind=None):
    H.calls.append(("fetch_verdict_gif", (passed, fail_kind)))
    if passed:
        return dict(H.pass_gif)
    g = dict(H.fail_gif)
    g["fail_kind"] = fail_kind or "not_tracking"
    return g


@activity.defn(name="search_gif")
async def m_search_gif(query):
    H.calls.append(("search_gif", query))
    r = dict(H.search_result)
    r["query"] = query
    return r


@activity.defn(name="synthesize_speech")
async def m_speech(text, style, hype):
    H.calls.append(("synthesize_speech", style))
    return "QVVESU8="


@activity.defn(name="finalize_gains")
async def m_finalize(check_id, status, result=None, error=None):
    H.final = {"status": status, "result": result, "error": error}
    H.calls.append(("finalize_gains", status))


ACTIVITIES = [m_record, m_model_chat, m_fetch_gif, m_search_gif, m_speech, m_finalize]


async def run_wf(user_input: dict) -> dict:
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue="gains-test", workflows=[GainsCheckWorkflow], activities=ACTIVITIES):
            return await env.client.execute_workflow(
                GainsCheckWorkflow.run,
                args=["check-123", user_input],
                id=f"gains-test-{uuid.uuid4()}",
                task_queue="gains-test",
            )


def _tool_call(name: str, args: dict) -> dict:
    return {"id": f"call_{name}", "name": name, "arguments": json.dumps(args)}


def _resp_tools(*tcs: dict) -> dict:
    return {"content": None, "tool_calls": list(tcs), "finish_reason": "tool_calls", "usage": {"prompt": 5, "completion": 5, "total": 10}}


def _resp_text(text: str = "let me think out loud") -> dict:
    return {"content": text, "tool_calls": [], "finish_reason": "stop", "usage": {"prompt": 5, "completion": 5, "total": 10}}


def _n(name: str) -> int:
    return sum(1 for c in H.calls if c[0] == name)


# ── Guided path ──────────────────────────────────────────────────────────────
async def test_guided_pass_overrides_headline_with_meme_quote():
    H.model_responses = [
        _resp_tools(_tool_call("submit_verdict", {
            "passed": True, "headline": "MODEL WROTE THIS", "spoken_line": "model line",
            "sound": "hype", "reason": "solid", "legend_quip": "you wish"}))
    ]
    out = await run_wf({"weight_kg": 95, "protein_g": 200, "persona": "gymbro"})
    res = out["result"]
    assert H.final["status"] == "done"
    assert res["passed"] is True
    # The guided pass headline/line are the GIF's meme quote, NOT the model's text.
    assert res["headline"] == "YEAH BUDDY!"
    assert res["spoken_line"] == "YEAH BUDDY!"
    assert res["gif_url"] == "http://gif/pass.gif"
    assert res["audio_b64"] == "QVVESU8="
    assert ("fetch_verdict_gif", (True, None)) in H.calls
    # Trace bookends were emitted.
    stages = [c[1] for c in H.calls if c[0] == "record_gains_event"]
    assert "dispatched" in stages and "finalized" in stages


async def test_guided_not_tracking_default_headline():
    H.model_responses = [
        _resp_tools(_tool_call("submit_verdict", {
            "passed": False, "fail_kind": "not_tracking", "headline": "",
            "spoken_line": "log it", "sound": "shame", "reason": "no data", "legend_quip": "q"}))
    ]
    res = (await run_wf({"calories": None, "protein_g": None, "persona": "sergeant"}))["result"]
    assert res["passed"] is False
    assert res["fail_kind"] == "not_tracking"
    assert res["headline"] == "YOU SHOULD"
    assert ("fetch_verdict_gif", (False, "not_tracking")) in H.calls


async def test_guided_slacking_default_headline():
    H.model_responses = [
        _resp_tools(_tool_call("submit_verdict", {
            "passed": False, "fail_kind": "slacking", "headline": "",
            "spoken_line": "more", "sound": "shame", "reason": "low protein", "legend_quip": "q"}))
    ]
    res = (await run_wf({"weight_kg": 100, "protein_g": 80, "persona": "wholesome"}))["result"]
    assert res["fail_kind"] == "slacking"
    assert res["headline"] == "DO BETTER"


async def test_guided_forces_submit_tool_choice():
    H.model_responses = [
        _resp_tools(_tool_call("submit_verdict", {
            "passed": True, "headline": "x", "spoken_line": "y", "sound": "hype", "reason": "r", "legend_quip": "q"}))
    ]
    await run_wf({"weight_kg": 90, "protein_g": 180})
    choices = [c[1] for c in H.calls if c[0] == "model_chat"]
    assert choices[0] == {"type": "function", "function": {"name": "submit_verdict"}}


async def test_guided_nudges_then_submits_when_first_turn_has_no_tool_call():
    H.model_responses = [
        _resp_text(),
        _resp_tools(_tool_call("submit_verdict", {
            "passed": True, "headline": "x", "spoken_line": "y", "sound": "hype", "reason": "r", "legend_quip": "q"})),
    ]
    res = (await run_wf({"weight_kg": 90, "protein_g": 180}))["result"]
    assert res["passed"] is True
    assert _n("model_chat") == 2


async def test_guided_max_rounds_falls_back_to_fun_verdict_not_error():
    H.model_responses = [_resp_text() for _ in range(MAX_ROUNDS)]
    out = await run_wf({"weight_kg": 90, "protein_g": 180})
    res = out["result"]
    assert H.final["status"] == "done"  # never a bare error
    assert res["headline"] == "RUN IT BACK"
    assert res["passed"] is False
    assert res["audio_b64"] == "QVVESU8="
    assert _n("model_chat") == MAX_ROUNDS


# ── Agentic path ─────────────────────────────────────────────────────────────
async def test_agentic_searches_then_submits_without_overriding_the_model():
    H.model_responses = [
        _resp_tools(_tool_call("search_gif", {"query": "ronnie yeah buddy"})),
        _resp_tools(_tool_call("submit_verdict", {
            "passed": True, "headline": "GET NASTY", "spoken_line": "LETS GO",
            "reason": "dialed in", "gif_url": "http://searched.gif", "voice_style": "excited",
            "legend_name": "Ronnie Coleman", "legend_comparison": "close to Ronnie",
            "legend_gif_url": "http://model-legend.gif"})),
    ]
    res = (await run_wf({"weight_kg": 95, "protein_g": 200, "persona": "gymbro", "mode": "agentic"}))["result"]
    assert res["mode"] == "agentic"
    assert res["passed"] is True
    assert res["headline"] == "GET NASTY"  # NOT overridden with a meme quote
    assert res["gif_url"] == "http://searched.gif"
    assert ("search_gif", "ronnie yeah buddy") in H.calls
    assert _n("search_gif") == 1
    # Agentic does NOT force the tool — the model decides when to search vs submit.
    assert [c[1] for c in H.calls if c[0] == "model_chat"][0] == "auto"
    assert ("synthesize_speech", "excited") in H.calls
