"""The feature registry (ADR-0008): the single list the worker, poller, and frontend
iterate. Adding a feature = drop a package + one line here; disabling = flip its
manifest's `enabled` flag or omit its key from the FEATURES_ENABLED allowlist (ADR-0010).
"""
from __future__ import annotations

import os

from ..kernel.registry import FeatureManifest, apply_feature_flags
from .program_evaluator.manifest import MANIFEST as PROGRAM_EVALUATOR
from .study_planner.manifest import MANIFEST as STUDY_PLANNER

# All registered features. `FEATURES_ENABLED` (comma-separated keys) overrides the
# built-in `enabled` flags at process start; unset → use the manifests' own flags.
FEATURES: list[FeatureManifest] = apply_feature_flags(
    [PROGRAM_EVALUATOR, STUDY_PLANNER],
    os.environ.get("FEATURES_ENABLED"),
)
