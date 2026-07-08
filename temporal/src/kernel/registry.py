"""Kernel: feature manifest + registry builders (ADR-0008).

A feature is a self-contained package that declares a `FeatureManifest`. The worker,
poller, and frontend build their registration / claim / route lists by iterating the
registry, so adding, removing, or disabling a feature touches only that feature's
package and a single `enabled` flag — never the bodies of `worker.py` or `poller.py`.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ClaimSpec:
    """A pending-row claim the poller runs: flip `table` rows pending->running and
    start `workflow` (its run id prefixed with `workflow_id_prefix`)."""

    table: str
    workflow: Any
    workflow_id_prefix: str


@dataclass(frozen=True)
class FeatureManifest:
    key: str
    title: str
    enabled: bool = True
    # ADR-0011: whether the feature needs an authenticated session. MUST match the
    # feature's DB RLS posture (owner-scoped ⟺ True; open-anon ⟺ False).
    requires_auth: bool = False
    workflows: tuple[Any, ...] = ()
    activities: tuple[Any, ...] = ()
    claims: tuple[ClaimSpec, ...] = ()
    route: str | None = None


def apply_feature_flags(
    features: list[FeatureManifest], allow_csv: str | None
) -> list[FeatureManifest]:
    """Override each manifest's `enabled` from an allowlist env value (ADR-0010).

    `allow_csv` empty/None → keep the built-in `enabled` flags. Otherwise a feature is
    enabled iff its key is in the comma-separated allowlist.
    """
    if not allow_csv or not allow_csv.strip():
        return list(features)
    allow = {s.strip() for s in allow_csv.split(",") if s.strip()}
    return [dataclasses.replace(f, enabled=(f.key in allow)) for f in features]


def enabled_features(features: list[FeatureManifest]) -> list[FeatureManifest]:
    return [f for f in features if f.enabled]


def _dedup(items: Any) -> list[Any]:
    out: list[Any] = []
    for it in items:
        if it not in out:
            out.append(it)
    return out


def build_workflows(features: list[FeatureManifest]) -> list[Any]:
    return _dedup(wf for f in enabled_features(features) for wf in f.workflows)


def build_activities(features: list[FeatureManifest]) -> list[Any]:
    """Deduped so kernel-shared activities (e.g. model_chat) register once."""
    return _dedup(act for f in enabled_features(features) for act in f.activities)


def build_claims(features: list[FeatureManifest]) -> list[ClaimSpec]:
    out: list[ClaimSpec] = []
    for f in enabled_features(features):
        out.extend(f.claims)
    return out


def build_routes(features: list[FeatureManifest]) -> list[tuple[str, str]]:
    return [(f.key, f.route) for f in enabled_features(features) if f.route]
