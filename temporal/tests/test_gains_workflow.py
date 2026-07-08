"""Workflow tests for GainsCheckWorkflow — real Temporal execution, mocked activities.

Time-skipping env + stub activities assert the workflow's orchestration: the serious
evaluation result (status, assessment, suggested_goal), forced vs auto tool choice,
the nudge path, and the max-rounds fallback. No network, no model, no Supabase.
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


@activity.defn(name="finalize_gains")
async def m_finalize(check_id, status, result=None, error=None):
    H.final = {"status": status, "result": result, "error": error}
    H.calls.append(("finalize_gains", status))


ACTIVITIES = [m_record, m_model_chat, m_finalize]


async def run_wf(user_input: dict) -> dict:
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue="gains-test", workflows=[GainsCheckWorkflow], activities=ACTIVITIES):
            return await env.client.execute_workflow(
                GainsCheckWorkflow.run,
                args=["check-123", user_input],
                id=f"gains-test-{uuid.uuid4()}",
                task_queue="gains-test",
            )


def _tool_call(args: dict) -> dict:
    return {"id": "call_1", "name": "submit_verdict", "arguments": json.dumps(args)}


def _resp_tools(*tcs: dict) -> dict:
    return {"content": None, "tool_calls": list(tcs), "finish_reason": "tool_calls", "usage": {"total": 10}}


def _resp_text() -> dict:
    return {"content": "let me think", "tool_calls": [], "finish_reason": "stop", "usage": {"total": 5}}


def _n(name: str) -> int:
    return sum(1 for c in H.calls if c[0] == name)


VERDICT = {"passed": True, "assessment": "Solid protein and calories.", "suggested_goal": "build_muscle", "suggestion_reason": "You're fueling well."}


async def test_guided_pass_returns_serious_evaluation():
    H.model_responses = [_resp_tools(_tool_call(VERDICT))]
    res = (await run_wf({"weight_kg": 95, "protein_g": 200, "persona": "gymbro"}))["result"]
    assert H.final["status"] == "done"
    assert res["passed"] is True
    assert res["status"] == "on_track"
    assert res["assessment"] == "Solid protein and calories."
    assert res["suggested_goal"] == "build_muscle"
    assert res["suggestion_reason"]
    # No joke fields leak into the result.
    assert "gif_url" not in res and "headline" not in res and "audio_b64" not in res
    stages = [c[1] for c in H.calls if c[0] == "record_gains_event"]
    assert "dispatched" in stages and "finalized" in stages


async def test_guided_not_tracking_status():
    H.model_responses = [_resp_tools(_tool_call({**VERDICT, "passed": False, "fail_kind": "not_tracking"}))]
    res = (await run_wf({"calories": None, "protein_g": None}))["result"]
    assert res["passed"] is False
    assert res["fail_kind"] == "not_tracking"
    assert res["status"] == "not_tracking"


async def test_guided_slacking_status():
    H.model_responses = [_resp_tools(_tool_call({**VERDICT, "passed": False, "fail_kind": "slacking"}))]
    res = (await run_wf({"weight_kg": 100, "protein_g": 80}))["result"]
    assert res["fail_kind"] == "slacking"
    assert res["status"] == "needs_work"


async def test_invalid_suggested_goal_defaults_to_recomp():
    H.model_responses = [_resp_tools(_tool_call({**VERDICT, "suggested_goal": "banana"}))]
    res = (await run_wf({"weight_kg": 90, "protein_g": 180}))["result"]
    assert res["suggested_goal"] == "recomp"


async def test_guided_forces_submit_tool_choice():
    H.model_responses = [_resp_tools(_tool_call(VERDICT))]
    await run_wf({"weight_kg": 90, "protein_g": 180})
    choices = [c[1] for c in H.calls if c[0] == "model_chat"]
    assert choices[0] == {"type": "function", "function": {"name": "submit_verdict"}}


async def test_guided_nudges_then_submits():
    H.model_responses = [_resp_text(), _resp_tools(_tool_call(VERDICT))]
    res = (await run_wf({"weight_kg": 90, "protein_g": 180}))["result"]
    assert res["passed"] is True
    assert _n("model_chat") == 2


async def test_guided_max_rounds_falls_back():
    H.model_responses = [_resp_text() for _ in range(MAX_ROUNDS)]
    res = (await run_wf({"weight_kg": 90, "protein_g": 180}))["result"]
    assert H.final["status"] == "done"  # never a bare error
    assert res["status"] == "not_tracking"
    assert res["suggested_goal"] == "recomp"
    assert _n("model_chat") == MAX_ROUNDS


async def test_agentic_free_reasoning_no_forced_tool():
    H.model_responses = [_resp_tools(_tool_call(VERDICT))]
    res = (await run_wf({"weight_kg": 95, "protein_g": 200, "mode": "agentic"}))["result"]
    assert res["mode"] == "agentic"
    assert res["status"] == "on_track"
    assert res["suggested_goal"] == "build_muscle"
    # Agentic does NOT force the tool.
    assert [c[1] for c in H.calls if c[0] == "model_chat"][0] == "auto"
