"""Unit tests for the pure Gains Check logic — no network, no Temporal server."""
from __future__ import annotations

from src.agents.tools import gains_tools as gt


def test_get_persona_known_and_default():
    assert gt.get_persona("sergeant")["label"] == "Drill Sergeant"
    assert gt.get_persona("WHOLESOME")["label"] == "Wholesome Coach"
    assert gt.get_persona(None)["label"] == "Gym Bro"       # default
    assert gt.get_persona("nonsense")["label"] == "Gym Bro"  # unknown -> default


def test_resolve_plan_resources_keeps_only_known_urls_and_dedupes():
    known = gt.PLAN_RESOURCES[0]["url"]
    out = gt.resolve_plan_resources([known, known, "https://not-in-the-list.example/"])
    # invented URLs dropped, known URL kept once (deduped)
    assert out == [{"title": gt.PLAN_RESOURCES[0]["title"], "url": known}]


def test_resolve_plan_resources_ignores_unknown_and_empty():
    assert gt.resolve_plan_resources([]) == []
    assert gt.resolve_plan_resources(["https://nope.example/", ""]) == []


def test_plan_resources_prompt_lists_every_curated_url():
    prompt = gt.plan_resources_prompt()
    for r in gt.PLAN_RESOURCES:
        assert r["url"] in prompt
