"""Study Planner feature manifest (ADR-0008)."""
from __future__ import annotations

from ...activities.model import model_chat
from ...kernel.registry import ClaimSpec, FeatureManifest
from . import activities
from .workflow import StudyPlanWorkflow

MANIFEST = FeatureManifest(
    key="study_planner",
    title="Study Planner",
    enabled=True,
    requires_auth=True,  # ADR-0011: study_plans is owner-scoped (ADR-0007)
    workflows=(StudyPlanWorkflow,),
    activities=(model_chat, activities.finalize_plan, activities.record_plan_event),
    claims=(ClaimSpec(table="study_plans", workflow=StudyPlanWorkflow, workflow_id_prefix="plan-"),),
    route="/plan",
)
