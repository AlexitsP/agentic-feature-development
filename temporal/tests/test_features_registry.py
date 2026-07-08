"""The live feature registry (ADR-0008): all features register, and the gains
wire-up preserves existing runtime behavior exactly."""
from src.activities.model import model_chat
from src.features.program_evaluator.workflow import EvaluationWorkflow
from src.features.registry import FEATURES
from src.kernel.registry import build_activities, build_claims, build_workflows
from src.workflows.gains_check import GainsCheckWorkflow
from src.workflows.gains_plan import GainsPlanWorkflow


def test_all_feature_workflows_registered():
    wfs = build_workflows(FEATURES)
    assert GainsCheckWorkflow in wfs
    assert GainsPlanWorkflow in wfs
    assert EvaluationWorkflow in wfs


def test_claims_map_tables_to_workflows_and_prefixes():
    claims = {c.table: c for c in build_claims(FEATURES)}
    assert claims["gains_checks"].workflow is GainsCheckWorkflow
    assert claims["gains_plans"].workflow is GainsPlanWorkflow
    assert claims["program_evaluations"].workflow is EvaluationWorkflow


def test_model_chat_registered_exactly_once():
    # Shared by both features; the builder must dedup it for the worker.
    assert build_activities(FEATURES).count(model_chat) == 1


def test_gains_id_prefixes_preserve_existing_runtime_ids():
    # Behavior guard: the poller must still produce ids "gains-<id>" / "gains-plan-<id>"
    # so making it registry-driven does not orphan or collide with existing runs.
    claims = {c.table: c for c in build_claims(FEATURES)}
    assert f"{claims['gains_checks'].workflow_id_prefix}abc" == "gains-abc"
    assert f"{claims['gains_plans'].workflow_id_prefix}abc" == "gains-plan-abc"
    assert f"{claims['program_evaluations'].workflow_id_prefix}abc" == "eval-abc"


def test_all_manifests_enabled_by_default():
    assert [f.key for f in FEATURES if f.enabled] == ["gains", "program_evaluator"]
