"""Activities for the Study Planner: append trace events + finalize the run row
(study_plans / study_plan_events) via Supabase PostgREST with the service role."""
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
def record_plan_event(
    plan_id: str, seq: int, stage: str, label: str, detail: Any = None, tokens: int | None = None
) -> None:
    with httpx.Client(timeout=15.0) as client:
        resp = client.post(
            f"{_rest_base()}/study_plan_events",
            headers={**_write_headers(), "Prefer": "return=minimal"},
            json={"plan_id": plan_id, "seq": seq, "stage": stage, "label": label, "detail": detail, "tokens": tokens},
        )
        resp.raise_for_status()


@activity.defn
def finalize_plan(plan_id: str, status: str, result: dict | None = None, error: str | None = None) -> None:
    with httpx.Client(timeout=15.0) as client:
        resp = client.patch(
            f"{_rest_base()}/study_plans",
            params={"id": f"eq.{plan_id}"},
            headers={**_write_headers(), "Prefer": "return=minimal"},
            json={
                "status": status,
                "result": result,
                "error": error,
                "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            },
        )
        resp.raise_for_status()
