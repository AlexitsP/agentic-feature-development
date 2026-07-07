"""Bridge from a Supabase `insight_runs` row to a Temporal workflow.

The frontend inserts a `pending` run row; this poller (running inside the worker
process) atomically claims pending rows and starts EntityInsightWorkflow for each.
"""
from __future__ import annotations

import asyncio
import logging

import httpx
from temporalio.client import Client

from ..config import settings
from ..workflows.entity_insight import EntityInsightWorkflow
from ..workflows.gains_check import GainsCheckWorkflow

logger = logging.getLogger(__name__)

POLL_INTERVAL = 2.0


def _claim(table: str, select: str) -> list[dict]:
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
            params={"status": "eq.pending", "select": select},
            headers=headers,
            json={"status": "running"},
        )
        resp.raise_for_status()
        return resp.json()


async def poll_loop(client: Client, task_queue: str) -> None:
    logger.info("run poller started (interval=%ss)", POLL_INTERVAL)
    while True:
        try:
            for run in await asyncio.to_thread(_claim, "insight_runs", "id,entity_id"):
                await client.start_workflow(
                    EntityInsightWorkflow.run,
                    args=[run["id"], run["entity_id"]],
                    id=f"insight-{run['id']}",
                    task_queue=task_queue,
                )
                logger.info("started insight workflow run_id=%s", run["id"])

            for check in await asyncio.to_thread(_claim, "gains_checks", "id,input"):
                await client.start_workflow(
                    GainsCheckWorkflow.run,
                    args=[check["id"], check.get("input") or {}],
                    id=f"gains-{check['id']}",
                    task_queue=task_queue,
                )
                logger.info("started gains workflow check_id=%s", check["id"])
        except Exception:
            logger.exception("poller iteration failed")
        await asyncio.sleep(POLL_INTERVAL)
