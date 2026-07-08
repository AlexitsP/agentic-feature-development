"""Study Planner — pure plan-builder units + workflow test (panel + synthesis, mocked model)."""
from __future__ import annotations

import json
import uuid

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from src.features.study_planner.manifest import MANIFEST
from src.features.study_planner.tools import SOURCES, build_plan_result, compute_input_completeness
from src.features.study_planner.workflow import StudyPlanWorkflow

FULL_INPUT = {
    "target_field": "medicine",
    "prior_qualification": "Gymnasiale Matura",
    "timeframe": "starting next year",
    "interests": "biology, helping people",
}
TWO_SOURCES = [SOURCES[0]["url"], SOURCES[1]["url"]]
PANEL = [
    {"key": "curriculum", "title": "Curriculum & pathway advisor", "headline": "Prep for the medicine aptitude test.", "points": ["Register for EMS", "Strengthen bio/chem"]},
    {"key": "study_skills", "title": "Study-skills coach", "headline": "Use retrieval practice.", "points": ["Spaced practice", "Active recall"]},
]
SYNTH = {
    "summary": "A focused runway to a Swiss medicine programme.",
    "weekly_steps": ["Register for the EMS aptitude test", "Build a bio/chem revision schedule", "Join a study group"],
    "how_to_study": ["Spaced repetition", "Active recall with past questions"],
    "resource_urls": TWO_SOURCES,
}


# ── pure builder units ────────────────────────────────────────────────────────────

def test_full_grounded_plan_is_well_grounded():
    r = build_plan_result(SYNTH, PANEL, "Encouraging Mentor", FULL_INPUT)
    assert r["confidence"]["tier"] == "well_grounded"
    assert len(r["resources"]) == 2
    assert r["how_to_study"] == SYNTH["how_to_study"]
    assert len(r["panel"]) == 2


def test_no_sources_is_speculative():
    r = build_plan_result({**SYNTH, "resource_urls": []}, PANEL, "Encouraging Mentor", FULL_INPUT)
    assert r["confidence"]["tier"] == "speculative"
    assert r["resources"] == []


def test_invented_source_dropped():
    r = build_plan_result({**SYNTH, "resource_urls": ["https://made-up.example/", SOURCES[0]["url"]]}, PANEL, "Encouraging Mentor", FULL_INPUT)
    assert [s["url"] for s in r["resources"]] == [SOURCES[0]["url"]]


def test_caps_weekly_steps_and_how_to_study():
    big = {**SYNTH, "weekly_steps": [f"s{i}" for i in range(10)], "how_to_study": [f"h{i}" for i in range(10)]}
    r = build_plan_result(big, PANEL, "Encouraging Mentor", FULL_INPUT)
    assert len(r["weekly_steps"]) == 6
    assert len(r["how_to_study"]) == 4


def test_thin_input_lowers_confidence():
    # Empty profile -> input_completeness 0 -> speculative even with good grounding.
    r = build_plan_result(SYNTH, PANEL, "Encouraging Mentor", {})
    assert r["confidence"]["tier"] == "speculative"


def test_input_completeness_bounds():
    assert compute_input_completeness({}) == 0.0
    assert compute_input_completeness(FULL_INPUT) == 1.0


def test_manifest_declares_claim_and_route():
    assert MANIFEST.claims[0].table == "study_plans"
    assert MANIFEST.route == "/plan"
    assert StudyPlanWorkflow in MANIFEST.workflows


# ── workflow (panel + synthesis, mocked model) ─────────────────────────────────────

class Harness:
    def __init__(self):
        self.calls: list[tuple] = []
        self.final: dict | None = None


H = Harness()


@pytest.fixture(autouse=True)
def _reset():
    global H
    H = Harness()
    yield


@activity.defn(name="record_plan_event")
async def m_record(plan_id, seq, stage, label, detail=None, tokens=None):
    H.calls.append(("record_plan_event", stage))


@activity.defn(name="model_chat")
async def m_model_chat(messages, tools, max_tokens=2048, tool_choice="auto"):
    # Order-independent: respond based on which tool was forced (advisors run in parallel).
    name = tool_choice["function"]["name"] if isinstance(tool_choice, dict) else "auto"
    H.calls.append(("model_chat", name))
    if name == "submit_advice":
        args = {"headline": "advice", "points": ["a", "b"]}
    else:  # submit_plan
        args = SYNTH
    return {"content": None, "tool_calls": [{"id": "c1", "name": name, "arguments": json.dumps(args)}], "finish_reason": "tool_calls", "usage": {"total": 10}}


@activity.defn(name="finalize_plan")
async def m_finalize(plan_id, status, result=None, error=None):
    H.final = {"status": status, "result": result, "error": error}
    H.calls.append(("finalize_plan", status))


ACTIVITIES = [m_record, m_model_chat, m_finalize]


async def run_wf(user_input: dict) -> dict:
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue="plan-test", workflows=[StudyPlanWorkflow], activities=ACTIVITIES):
            return await env.client.execute_workflow(
                StudyPlanWorkflow.run, args=["plan-1", user_input], id=f"plan-test-{uuid.uuid4()}", task_queue="plan-test"
            )


async def test_workflow_panel_then_synthesis_done():
    res = (await run_wf({**FULL_INPUT, "persona": "advisor"}))["result"]
    assert H.final["status"] == "done"
    assert res["confidence"]["tier"] == "well_grounded"
    assert res["how_to_study"] == SYNTH["how_to_study"]
    assert len(res["panel"]) == 2
    # Two advisor calls (forced submit_advice) + one synthesis (submit_plan).
    assert sum(1 for c in H.calls if c == ("model_chat", "submit_advice")) == 2
    assert sum(1 for c in H.calls if c == ("model_chat", "submit_plan")) == 1
    stages = [c[1] for c in H.calls if c[0] == "record_plan_event"]
    assert "dispatched" in stages and "synth" in stages and "finalized" in stages
