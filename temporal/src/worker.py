from __future__ import annotations
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from temporalio.client import Client
from temporalio.worker import Worker

from .config import settings
from .logging_config import configure_logging
from .features import FEATURES
from .kernel.registry import build_activities, build_claims, build_workflows
from .runs.poller import poll_loop

configure_logging(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    logger.info(
        "Connecting to Temporal",
        extra={"address": settings.temporal_address, "namespace": settings.temporal_namespace},
    )
    client = await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)

    activity_executor = ThreadPoolExecutor(max_workers=20)
    # Workflows, activities, and poller claims are data-driven from the enabled feature
    # manifests (ADR-0008) — adding or disabling a feature does not edit this file.
    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=build_workflows(FEATURES),
        activities=build_activities(FEATURES),
        activity_executor=activity_executor,
    )

    logger.info(
        "Worker started",
        extra={
            "task_queue": settings.temporal_task_queue,
            "features": [f.key for f in FEATURES if f.enabled],
        },
    )
    # Run the worker and the run-row poller together.
    await asyncio.gather(worker.run(), poll_loop(client, settings.temporal_task_queue, build_claims(FEATURES)))


if __name__ == "__main__":
    asyncio.run(main())
