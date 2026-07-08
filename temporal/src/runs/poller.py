"""Bridge from a Supabase pending row to a Temporal workflow.

The frontend inserts a `pending` run row; this poller (running inside the worker
process) atomically claims pending rows and starts the matching workflow.
"""
from __future__ import annotations

import asyncio
import logging

import httpx
from temporalio.client import Client

from ..config import settings
from ..workflows.gains_check import GainsCheckWorkflow
from ..workflows.gains_plan import GainsPlanWorkflow

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


async def poll_loop(client: Client, task_queue: str) -> None:
    logger.info("run poller started (interval=%ss)", POLL_INTERVAL)
    while True:
        try:
            for check in await asyncio.to_thread(_claim, "gains_checks", "id,input"):
                await client.start_workflow(
                    GainsCheckWorkflow.run,
                    args=[check["id"], check.get("input") or {}],
                    id=f"gains-{check['id']}",
                    task_queue=task_queue,
                )
                logger.info("started gains workflow check_id=%s", check["id"])

            for plan in await asyncio.to_thread(_claim, "gains_plans", "id,input"):
                await client.start_workflow(
                    GainsPlanWorkflow.run,
                    args=[plan["id"], plan.get("input") or {}],
                    id=f"gains-plan-{plan['id']}",
                    task_queue=task_queue,
                )
                logger.info("started gains plan workflow plan_id=%s", plan["id"])
        except Exception:
            logger.exception("poller iteration failed")
        await asyncio.sleep(POLL_INTERVAL)
