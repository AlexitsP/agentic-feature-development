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


CLAIM_BATCH = 50


def _claim(table: str, select: str = "id,input") -> list[dict]:
    """Atomically flip pending -> running for a table and return claimed rows.

    SEC-2: bound the batch so an anon-key insert flood can't spawn unbounded
    concurrent (paid) workflows. `limit`+`order` on a PATCH is rejected by PostgREST
    (it mangles the order column), so we do it in two steps: pick the oldest N pending
    ids with a GET (where order/limit work), then claim exactly those ids. The claim
    PATCH still filters `status=eq.pending`, so a row another worker grabbed between
    the two calls is simply not returned — claiming stays at-most-once.
    """
    key = settings.supabase_service_role_key
    base = settings.supabase_url.rstrip("/") + "/rest/v1"
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=15.0) as client:
        picked = client.get(
            f"{base}/{table}",
            params={
                "status": "eq.pending",
                "select": "id",
                "limit": str(CLAIM_BATCH),
                "order": "created_at.asc",
            },
            headers=headers,
        )
        picked.raise_for_status()
        ids = [row["id"] for row in picked.json()]
        if not ids:
            return []

        resp = client.patch(
            f"{base}/{table}",
            params={
                "id": f"in.({','.join(ids)})",
                "status": "eq.pending",
                "select": select,
            },
            headers={**headers, "Prefer": "return=representation"},
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
