"""Regression tests for the poller claim (SEC-2 bound) — the two-step select-then-patch.

Guards the bug where `limit`+`order` on a PATCH made PostgREST reject the claim with
"column ... does not exist" (400): the PATCH must NOT carry an `order`, and the batch
is bounded by selecting ids first.
"""
import src.runs.poller as poller


class _Resp:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


def test_claim_selects_ids_then_patches_those_ids(monkeypatch):
    calls: dict = {}

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, params=None, headers=None):
            calls["get"] = params
            return _Resp([{"id": "aaaaaaaa-0000-0000-0000-000000000001"}, {"id": "aaaaaaaa-0000-0000-0000-000000000002"}])

        def patch(self, url, params=None, headers=None, json=None):
            calls["patch"] = params
            return _Resp([{"id": "aaaaaaaa-0000-0000-0000-000000000001", "input": {}}])

    monkeypatch.setattr(poller.httpx, "Client", _Client)
    rows = poller._claim("program_evaluations")

    # GET does the bounded, ordered pick (allowed on GET).
    assert calls["get"]["limit"] == str(poller.CLAIM_BATCH)
    assert calls["get"]["order"] == "created_at.asc"
    # PATCH claims exactly those ids, still filtered to pending, and — the bug guard —
    # carries NO `order` (that is what PostgREST rejected on a PATCH).
    assert calls["patch"]["id"].startswith("in.(")
    assert calls["patch"]["status"] == "eq.pending"
    assert "order" not in calls["patch"]
    assert "limit" not in calls["patch"]
    assert len(rows) == 1


def test_claim_skips_patch_when_nothing_pending(monkeypatch):
    calls = {"patched": False}

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, params=None, headers=None):
            return _Resp([])

        def patch(self, url, params=None, headers=None, json=None):
            calls["patched"] = True
            return _Resp([])

    monkeypatch.setattr(poller.httpx, "Client", _Client)
    rows = poller._claim("gains_checks")
    assert rows == []
    assert calls["patched"] is False
