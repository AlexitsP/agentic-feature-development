"""Program Evaluator feature manifest (ADR-0008).

Declares everything the platform needs to wire this feature: its workflow, the
activities it uses (the shared `model_chat` + its own finalize/record), the pending-row
claim the poller should run, and its frontend route. The worker/poller/frontend consume
this via the feature registry — they are not edited per feature.
"""
from __future__ import annotations

from ...activities.model import model_chat
from ...kernel.registry import ClaimSpec, FeatureManifest
from . import activities
from .workflow import EvaluationWorkflow

MANIFEST = FeatureManifest(
    key="program_evaluator",
    title="Program Evaluator",
    enabled=True,
    requires_auth=True,  # ADR-0011: owner-scoped — matches program_evaluations RLS (ADR-0007)
    workflows=(EvaluationWorkflow,),
    activities=(model_chat, activities.finalize_evaluation, activities.record_evaluation_event),
    claims=(ClaimSpec(table="program_evaluations", workflow=EvaluationWorkflow, workflow_id_prefix="eval-"),),
    route="/evaluate",
)
