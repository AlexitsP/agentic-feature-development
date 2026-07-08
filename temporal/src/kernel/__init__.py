"""Feature-plugin kernel (ADR-0008/0009): shared capabilities features build on.

Features depend on the kernel; the kernel never depends on a feature.
"""
from .confidence import Confidence, ConfidenceSignals, Tier, score_confidence
from .registry import (
    ClaimSpec,
    FeatureManifest,
    build_activities,
    build_claims,
    build_routes,
    build_workflows,
    enabled_features,
)
from .sources import grounding_ratio, resolve_sources

__all__ = [
    "Confidence",
    "ConfidenceSignals",
    "Tier",
    "score_confidence",
    "resolve_sources",
    "grounding_ratio",
    "ClaimSpec",
    "FeatureManifest",
    "enabled_features",
    "build_workflows",
    "build_activities",
    "build_claims",
    "build_routes",
]
