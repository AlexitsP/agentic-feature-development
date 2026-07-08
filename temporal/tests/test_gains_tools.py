"""Unit tests for the pure Gains Check logic — no network, no Temporal server.

These cover the deterministic decisions the guided pipeline makes in code
(legend matching, fail-kind routing, persona lookup) and the GIF fallback
layering, i.e. exactly the spots real bugs have already appeared.
"""
from __future__ import annotations

import pytest

from src.agents.tools import gains_tools as gt
from src.activities import gains as gains_activities


# ── get_persona ──────────────────────────────────────────────────────────────
def test_get_persona_known_and_default():
    assert gt.get_persona("sergeant")["label"] == "Drill Sergeant"
    assert gt.get_persona("WHOLESOME")["label"] == "Wholesome Coach"
    assert gt.get_persona(None)["label"] == "Gym Bro"       # default
    assert gt.get_persona("nonsense")["label"] == "Gym Bro"  # unknown -> default


# ── shame_query (fail-kind routing) ──────────────────────────────────────────
def test_shame_query_routes_by_kind():
    assert gt.shame_query("slacking") in gt.SHAME_QUERIES["slacking"]
    assert gt.shame_query("not_tracking") in gt.SHAME_QUERIES["not_tracking"]
    # unknown / None fall back to the not_tracking bucket
    assert gt.shame_query(None) in gt.SHAME_QUERIES["not_tracking"]
    assert gt.shame_query("bogus") in gt.SHAME_QUERIES["not_tracking"]


# ── fallback_gif_url (curated last-resort URLs) ──────────────────────────────
def test_fallback_gif_url():
    assert gt.fallback_gif_url("Ronnie Coleman") in gt.FALLBACK_GIFS["Ronnie Coleman"]
    assert gt.fallback_gif_url("slacking") in gt.FALLBACK_GIFS["slacking"]
    assert gt.fallback_gif_url("no-such-bucket") is None


# ── search_gif (network mocked) ──────────────────────────────────────────────
class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_search_gif_no_key(monkeypatch):
    monkeypatch.setattr(gt.settings, "giphy_api_key", "")
    out = gt.search_gif("anything")
    assert out == {"url": None, "source": "no-key", "query": "anything"}


def test_search_gif_happy_path(monkeypatch):
    monkeypatch.setattr(gt.settings, "giphy_api_key", "KEY")
    payload = {"data": [{"images": {"downsized_medium": {"url": "http://x/g.gif"}}}]}
    monkeypatch.setattr(gt.httpx, "get", lambda *a, **k: _FakeResp(payload))
    out = gt.search_gif("ronnie")
    assert out["url"] == "http://x/g.gif"
    assert out["source"] == "giphy"


def test_search_gif_empty_retries_broader_query(monkeypatch):
    monkeypatch.setattr(gt.settings, "giphy_api_key", "KEY")
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(params["q"])
        # First (specific) query is empty; the broadened query has a hit.
        if params["q"] == "very specific":
            return _FakeResp({"data": []})
        return _FakeResp({"data": [{"images": {"original": {"url": "http://x/b.gif"}}}]})

    monkeypatch.setattr(gt.httpx, "get", fake_get)
    out = gt.search_gif("very specific", fallback_query="broad")
    assert out["url"] == "http://x/b.gif"
    assert calls == ["very specific", "broad"]  # retried once, broader


def test_search_gif_swallows_errors(monkeypatch):
    monkeypatch.setattr(gt.settings, "giphy_api_key", "KEY")

    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(gt.httpx, "get", boom)
    out = gt.search_gif("q")
    assert out["url"] is None
    assert out["source"].startswith("error:")


# ── fetch_verdict_gif activity: fallback layering + subject/quote matching ────
def test_fetch_verdict_gif_uses_fallback_when_search_empty(monkeypatch):
    # Force the live search to return nothing so the curated fallback kicks in.
    monkeypatch.setattr(gt, "search_gif", lambda *a, **k: {"url": None, "source": "empty", "query": "q"})
    out = gains_activities.fetch_verdict_gif(True)
    assert out["url"] in gt.FALLBACK_GIFS[out["subject"]]
    assert out["source"] == "fallback"
    # On a pass, the quote must belong to the SAME subject as the GIF.
    assert out["quote"] in gt.HYPE_SUBJECTS[out["subject"]]["quotes"]


def test_fetch_verdict_gif_fail_kind_fallback(monkeypatch):
    monkeypatch.setattr(gt, "search_gif", lambda *a, **k: {"url": None, "source": "empty", "query": "q"})
    out = gains_activities.fetch_verdict_gif(False, "slacking")
    assert out["fail_kind"] == "slacking"
    assert out["url"] in gt.FALLBACK_GIFS["slacking"]
    assert out["subject"] is None
    assert out["quote"] is None
