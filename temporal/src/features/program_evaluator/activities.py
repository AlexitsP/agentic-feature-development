"""Activities for the Program Evaluator: append trace events + finalize the run row.

Mirrors the run-row substrate pattern: writes to `program_evaluation_events` and
`program_evaluations` via Supabase PostgREST with the server-side service role.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

import httpx
from temporalio import activity

from ...config import settings


def _rest_base() -> str:
    return settings.supabase_url.rstrip("/") + "/rest/v1"


def _write_headers() -> dict[str, str]:
    key = settings.supabase_service_role_key
    return {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}


@activity.defn
def record_evaluation_event(
    evaluation_id: str, seq: int, stage: str, label: str, detail: Any = None, tokens: int | None = None
) -> None:
    with httpx.Client(timeout=15.0) as client:
        resp = client.post(
            f"{_rest_base()}/program_evaluation_events",
            headers={**_write_headers(), "Prefer": "return=minimal"},
            json={
                "evaluation_id": evaluation_id,
                "seq": seq,
                "stage": stage,
                "label": label,
                "detail": detail,
                "tokens": tokens,
            },
        )
        resp.raise_for_status()


@activity.defn
def finalize_evaluation(
    evaluation_id: str, status: str, result: dict | None = None, error: str | None = None
) -> None:
    with httpx.Client(timeout=15.0) as client:
        resp = client.patch(
            f"{_rest_base()}/program_evaluations",
            params={"id": f"eq.{evaluation_id}"},
            headers={**_write_headers(), "Prefer": "return=minimal"},
            json={
                "status": status,
                "result": result,
                "error": error,
                "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            },
        )
        resp.raise_for_status()
