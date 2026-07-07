"""Activities for the Gains Check workflow: fetch a GIF and finalize the row."""
from __future__ import annotations

import datetime as dt
from typing import Any

import httpx
from temporalio import activity

from ..agents.tools import gains_tools
from ..config import settings


def _rest_base() -> str:
    return settings.supabase_url.rstrip("/") + "/rest/v1"


def _write_headers() -> dict[str, str]:
    key = settings.supabase_service_role_key
    return {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}


@activity.defn
def search_gif(query: str) -> dict[str, Any]:
    return gains_tools.search_gif(query)


@activity.defn
def record_gains_event(
    check_id: str, seq: int, stage: str, label: str, detail: Any = None, tokens: int | None = None
) -> None:
    """Append a pipeline trace event for the frontend stepper."""
    with httpx.Client(timeout=15.0) as client:
        resp = client.post(
            f"{_rest_base()}/gains_events",
            headers={**_write_headers(), "Prefer": "return=minimal"},
            json={
                "check_id": check_id,
                "seq": seq,
                "stage": stage,
                "label": label,
                "detail": detail,
                "tokens": tokens,
            },
        )
        resp.raise_for_status()


@activity.defn
def finalize_gains(check_id: str, status: str, result: dict | None = None, error: str | None = None) -> None:
    with httpx.Client(timeout=15.0) as client:
        resp = client.patch(
            f"{_rest_base()}/gains_checks",
            params={"id": f"eq.{check_id}"},
            headers={**_write_headers(), "Prefer": "return=minimal"},
            json={
                "status": status,
                "result": result,
                "error": error,
                "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            },
        )
        resp.raise_for_status()
