from __future__ import annotations
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from temporalio.client import Client
from temporalio.worker import Worker

from .config import settings
from .activities import supabase_core, notifications, insights, gains
from .workflows.example.approval_workflow import ApprovalWorkflow
from .workflows.entity_insight import EntityInsightWorkflow
from .workflows.gains_check import GainsCheckWorkflow
from .runs.poller import poll_loop

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    logger.info("Connecting to Temporal", extra={"address": settings.temporal_address, "namespace": settings.temporal_namespace})
    client = await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)

    activity_executor = ThreadPoolExecutor(max_workers=20)
    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[ApprovalWorkflow, EntityInsightWorkflow, GainsCheckWorkflow],
        activities=[
            supabase_core.create_entity,
            supabase_core.update_entity_scd2,
            supabase_core.get_entity,
            supabase_core.append_event,
            supabase_core.create_relationship,
            notifications.send_email,
            notifications.send_notification,
            insights.model_chat,
            insights.run_tool,
            insights.record_step,
            insights.finalize_run,
            gains.search_gif,
            gains.fetch_verdict_gif,
            gains.finalize_gains,
            gains.record_gains_event,
            gains.synthesize_speech,
        ],
        activity_executor=activity_executor,
    )

    logger.info("Worker started", extra={"task_queue": settings.temporal_task_queue})
    # Run the worker and the insight-run poller together.
    await asyncio.gather(worker.run(), poll_loop(client, settings.temporal_task_queue))


if __name__ == "__main__":
    asyncio.run(main())
