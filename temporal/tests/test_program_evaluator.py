"""Program Evaluator — pure result-builder unit tests + workflow tests (mocked model).

Mirrors the gains workflow test harness: real Temporal execution via a time-skipping
env with stubbed activities; no network, model, or Supabase.
"""
from __future__ import annotations

import json
import uuid

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from src.features.program_evaluator.manifest import MANIFEST
from src.features.program_evaluator.tools import (
    SOURCES,
    build_evaluation_result,
    compute_input_completeness,
)
from src.features.program_evaluator.workflow import MAX_ROUNDS, EvaluationWorkflow

FULL_INPUT = {
    "interests": "biology and helping people",
    "prior_qualification": "gymnasiale Matura",
    "strong_subjects": "biology, chemistry",
    "target_field": "medicine",
    "canton": "Zurich",
    "language": "de",
}
TWO_SOURCES = [SOURCES[0]["url"], SOURCES[1]["url"]]
OPTIONS = [
    {"field": "Medicine", "institution_type": "university", "reason": "Strong sciences + clear goal."},
    {"field": "Nursing", "institution_type": "uas", "reason": "Applied, people-focused alternative."},
]


# ── pure result-builder unit tests ───────────────────────────────────────────────

def test_full_grounded_result_is_well_grounded():
    r = build_evaluation_result(
        {"assessment": "Strong fit for the sciences.", "suggested_options": OPTIONS, "source_urls": TWO_SOURCES},
        "Encouraging Mentor",
        FULL_INPUT,
    )
    assert r["confidence"]["tier"] == "well_grounded"
    assert len(r["suggested_options"]) == 2
    assert len(r["resources"]) == 2


def test_no_sources_is_speculative():
    r = build_evaluation_result(
        {"assessment": "x", "suggested_options": OPTIONS, "source_urls": []}, "Encouraging Mentor", FULL_INPUT
    )
    assert r["confidence"]["tier"] == "speculative"
    assert r["resources"] == []


def test_thin_input_lowers_confidence():
    r = build_evaluation_result(
        {"assessment": "x", "suggested_options": OPTIONS, "source_urls": TWO_SOURCES},
        "Encouraging Mentor",
        {"interests": "unsure"},  # 1/6 fields
    )
    assert r["confidence"]["tier"] == "speculative"


def test_invalid_institution_type_defaults_to_university():
    r = build_evaluation_result(
        {"assessment": "x", "suggested_options": [{"field": "Law", "institution_type": "banana", "reason": "y"}], "source_urls": TWO_SOURCES},
        "Encouraging Mentor",
        FULL_INPUT,
    )
    assert r["suggested_options"][0]["institution_type"] == "university"


def test_invented_source_dropped():
    r = build_evaluation_result(
        {"assessment": "x", "suggested_options": OPTIONS, "source_urls": ["https://totally-made-up.example/", SOURCES[0]["url"]]},
        "Encouraging Mentor",
        FULL_INPUT,
    )
    assert [s["url"] for s in r["resources"]] == [SOURCES[0]["url"]]


def test_input_completeness_bounds():
    assert compute_input_completeness({}) == 0.0
    assert compute_input_completeness(FULL_INPUT) == 1.0
    assert compute_input_completeness({"freeform": "I like biology"}) >= 0.5


def test_manifest_declares_claim_and_route():
    assert MANIFEST.claims[0].table == "program_evaluations"
    assert MANIFEST.route == "/evaluate"
    assert EvaluationWorkflow in MANIFEST.workflows


# ── workflow tests (real Temporal execution, mocked activities) ───────────────────

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


@activity.defn(name="record_evaluation_event")
async def m_record(evaluation_id, seq, stage, label, detail=None, tokens=None):
    H.calls.append(("record_evaluation_event", stage))


@activity.defn(name="model_chat")
async def m_model_chat(messages, tools, max_tokens=2048, tool_choice="auto"):
    H.calls.append(("model_chat", tool_choice))
    return H.model_responses.pop(0)


@activity.defn(name="finalize_evaluation")
async def m_finalize(evaluation_id, status, result=None, error=None):
    H.final = {"status": status, "result": result, "error": error}
    H.calls.append(("finalize_evaluation", status))


ACTIVITIES = [m_record, m_model_chat, m_finalize]


async def run_wf(user_input: dict) -> dict:
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue="eval-test", workflows=[EvaluationWorkflow], activities=ACTIVITIES):
            return await env.client.execute_workflow(
                EvaluationWorkflow.run,
                args=["eval-123", user_input],
                id=f"eval-test-{uuid.uuid4()}",
                task_queue="eval-test",
            )


def _tool_call(args: dict) -> dict:
    return {"id": "call_1", "name": "submit_evaluation", "arguments": json.dumps(args)}


def _resp_tools(*tcs: dict) -> dict:
    return {"content": None, "tool_calls": list(tcs), "finish_reason": "tool_calls", "usage": {"total": 12}}


def _resp_text() -> dict:
    return {"content": "thinking", "tool_calls": [], "finish_reason": "stop", "usage": {"total": 4}}


def _n(name: str) -> int:
    return sum(1 for c in H.calls if c[0] == name)


async def test_workflow_grounded_evaluation_done():
    H.model_responses = [_resp_tools(_tool_call({"assessment": "Strong fit.", "suggested_options": OPTIONS, "source_urls": TWO_SOURCES}))]
    res = (await run_wf({**FULL_INPUT, "persona": "advisor"}))["result"]
    assert H.final["status"] == "done"
    assert res["confidence"]["tier"] == "well_grounded"
    assert res["persona"] == "Straight-talking Advisor"
    stages = [c[1] for c in H.calls if c[0] == "record_evaluation_event"]
    assert "dispatched" in stages and "finalized" in stages


async def test_workflow_forces_submit_tool_choice():
    H.model_responses = [_resp_tools(_tool_call({"assessment": "x", "suggested_options": OPTIONS, "source_urls": TWO_SOURCES}))]
    await run_wf(FULL_INPUT)
    choices = [c[1] for c in H.calls if c[0] == "model_chat"]
    assert choices[0] == {"type": "function", "function": {"name": "submit_evaluation"}}


async def test_workflow_nudges_then_submits():
    H.model_responses = [_resp_text(), _resp_tools(_tool_call({"assessment": "x", "suggested_options": OPTIONS, "source_urls": TWO_SOURCES}))]
    res = (await run_wf(FULL_INPUT))["result"]
    assert res["confidence"]["tier"] == "well_grounded"
    assert _n("model_chat") == 2


async def test_workflow_max_rounds_falls_back_speculative():
    H.model_responses = [_resp_text() for _ in range(MAX_ROUNDS)]
    res = (await run_wf(FULL_INPUT))["result"]
    assert H.final["status"] == "done"  # never a bare error
    assert res["confidence"]["tier"] == "speculative"  # no options, no sources
    assert res["suggested_options"] == []
    assert _n("model_chat") == MAX_ROUNDS
