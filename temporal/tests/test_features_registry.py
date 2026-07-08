"""The live feature registry (ADR-0008): the enabled features register correctly."""
from src.activities.model import model_chat
from src.features.program_evaluator.workflow import EvaluationWorkflow
from src.features.registry import FEATURES
from src.kernel.registry import build_activities, build_claims, build_workflows


def test_evaluator_workflow_registered():
    assert EvaluationWorkflow in build_workflows(FEATURES)


def test_claims_map_table_to_workflow_and_prefix():
    claims = {c.table: c for c in build_claims(FEATURES)}
    assert claims["program_evaluations"].workflow is EvaluationWorkflow
    assert f"{claims['program_evaluations'].workflow_id_prefix}abc" == "eval-abc"


def test_model_chat_registered_once():
    assert build_activities(FEATURES).count(model_chat) == 1


def test_enabled_features():
    assert [f.key for f in FEATURES if f.enabled] == ["program_evaluator", "study_planner"]
