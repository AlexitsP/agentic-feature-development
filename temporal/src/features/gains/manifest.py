"""Gains Check feature manifest (ADR-0008) — adapter over the existing gains code.

Declares the two gains workflows, their activities, and the two pending-row claims
with the SAME workflow-id prefixes the poller used before (`gains-`, `gains-plan-`),
so making the poller registry-driven preserves existing runtime behavior exactly.
"""
from __future__ import annotations

from ...activities import gains as gains_activities
from ...activities.model import model_chat
from ...kernel.registry import ClaimSpec, FeatureManifest
from ...workflows.gains_check import GainsCheckWorkflow
from ...workflows.gains_plan import GainsPlanWorkflow

MANIFEST = FeatureManifest(
    key="gains",
    title="Gains Check",
    enabled=True,
    workflows=(GainsCheckWorkflow, GainsPlanWorkflow),
    activities=(
        model_chat,
        gains_activities.finalize_gains,
        gains_activities.finalize_plan,
        gains_activities.record_gains_event,
        gains_activities.record_plan_event,
    ),
    claims=(
        ClaimSpec(table="gains_checks", workflow=GainsCheckWorkflow, workflow_id_prefix="gains-"),
        ClaimSpec(table="gains_plans", workflow=GainsPlanWorkflow, workflow_id_prefix="gains-plan-"),
    ),
    route="/gains",
)
