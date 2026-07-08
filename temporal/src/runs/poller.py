"""Bridge from a Supabase pending row to a Temporal workflow.

The frontend inserts a `pending` run row; this poller (running inside the worker
process) atomically claims pending rows and starts the matching workflow. The set of
`(table -> workflow)` claims is data-driven from the enabled feature manifests
(ADR-0008), so adding a feature adds a claim without editing this loop.
"""
from __future__ import annotations

import asyncio
import logging

import httpx
from temporalio.client import Client

from ..config import settings
from ..kernel.registry import ClaimSpec

logger = logging.getLogger(__name__)

POLL_INTERVAL = 2.0


def _claim(table: str, select: str = "id,input") -> list[dict]:
    """Atomically flip pending -> running for a table and return claimed rows."""
    key = settings.supabase_service_role_key
    base = settings.supabase_url.rstrip("/") + "/rest/v1"
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    with httpx.Client(timeout=15.0) as client:
        resp = client.patch(
            f"{base}/{table}",
            # SEC-2: bound rows claimed per iteration so an anon-key insert flood
            # cannot spawn unbounded concurrent (paid) workflows. Oldest first.
            params={
                "status": "eq.pending",
                "select": select,
                "limit": "50",
                "order": "created_at.asc",
            },
            headers=headers,
            json={"status": "running"},
        )
        resp.raise_for_status()
        return resp.json()


async def poll_loop(client: Client, task_queue: str, claims: list[ClaimSpec]) -> None:
    logger.info("run poller started (interval=%ss, claims=%d)", POLL_INTERVAL, len(claims))
    while True:
        try:
            for spec in claims:
                for row in await asyncio.to_thread(_claim, spec.table):
                    await client.start_workflow(
                        spec.workflow.run,
                        args=[row["id"], row.get("input") or {}],
                        id=f"{spec.workflow_id_prefix}{row['id']}",
                        task_queue=task_queue,
                    )
                    logger.info("started workflow table=%s id=%s", spec.table, row["id"])
        except Exception:
            logger.exception("poller iteration failed")
        await asyncio.sleep(POLL_INTERVAL)
