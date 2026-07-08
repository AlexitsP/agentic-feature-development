"""The feature registry (ADR-0008): the single list the worker, poller, and frontend
iterate. Adding a feature = drop a package + one line here; disabling = flip its
manifest's `enabled` flag. No other code changes.
"""
from __future__ import annotations

from ..kernel.registry import FeatureManifest
from .gains.manifest import MANIFEST as GAINS
from .program_evaluator.manifest import MANIFEST as PROGRAM_EVALUATOR

FEATURES: list[FeatureManifest] = [
    GAINS,
    PROGRAM_EVALUATOR,
]
