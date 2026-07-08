"""Feature-plugin registry (ADR-0008): enable/disable/add touches only the registry."""
import dataclasses

from src.kernel.registry import (
    ClaimSpec,
    FeatureManifest,
    build_activities,
    build_claims,
    build_routes,
    build_workflows,
    enabled_features,
)


# Identity-compared stand-ins for workflow classes / activity callables.
class WfEval:  # noqa: D401
    ...


class WfPlan:
    ...


def act_shared():
    ...


def act_plan():
    ...


def _features() -> list[FeatureManifest]:
    return [
        FeatureManifest(
            key="evaluator",
            title="Program Evaluator",
            enabled=True,
            workflows=(WfEval,),
            activities=(act_shared,),
            claims=(ClaimSpec("program_evaluations", WfEval, "eval-"),),
            route="/evaluate",
        ),
        FeatureManifest(
            key="planner",
            title="Study Planner",
            enabled=False,  # disabled by default
            workflows=(WfPlan,),
            activities=(act_shared, act_plan),
            claims=(ClaimSpec("study_plans", WfPlan, "plan-"),),
            route="/plan",
        ),
    ]


def test_only_enabled_features_register():
    f = _features()
    assert [m.key for m in enabled_features(f)] == ["evaluator"]
    assert build_workflows(f) == [WfEval]
    assert build_claims(f) == [ClaimSpec("program_evaluations", WfEval, "eval-")]
    assert build_routes(f) == [("evaluator", "/evaluate")]


def test_enabling_a_feature_adds_it_without_touching_others():
    f = _features()
    f[1] = dataclasses.replace(f[1], enabled=True)  # flip only the flag
    assert build_workflows(f) == [WfEval, WfPlan]
    assert build_routes(f) == [("evaluator", "/evaluate"), ("planner", "/plan")]
    assert len(build_claims(f)) == 2


def test_activities_deduped_across_features():
    f = [dataclasses.replace(m, enabled=True) for m in _features()]
    acts = build_activities(f)
    assert acts.count(act_shared) == 1
    assert set(acts) == {act_shared, act_plan}


def test_adding_a_new_feature_is_purely_additive():
    f = _features()
    before = build_workflows(f)
    f.append(
        FeatureManifest(key="inspire", title="Inspire Me", enabled=True, workflows=(WfPlan,), route="/inspire")
    )
    after = build_workflows(f)
    assert after[: len(before)] == before  # existing registrations unchanged
    assert WfPlan in after
    assert ("inspire", "/inspire") in build_routes(f)
