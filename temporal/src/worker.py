from __future__ import annotations
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from temporalio.client import Client
from temporalio.worker import Worker

from .config import settings
from .activities import gains, model
from .workflows.gains_check import GainsCheckWorkflow
from .workflows.gains_plan import GainsPlanWorkflow
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
        workflows=[GainsCheckWorkflow, GainsPlanWorkflow],
        activities=[
            model.model_chat,
            gains.finalize_gains,
            gains.finalize_plan,
            gains.record_plan_event,
            gains.record_gains_event,
        ],
        activity_executor=activity_executor,
    )

    logger.info("Worker started", extra={"task_queue": settings.temporal_task_queue})
    # Run the worker and the insight-run poller together.
    await asyncio.gather(worker.run(), poll_loop(client, settings.temporal_task_queue))


if __name__ == "__main__":
    asyncio.run(main())
