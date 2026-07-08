"""Kernel: confidence scoring from observable signals (ADR-0009).

The badge a feature shows is computed here from things we can *observe* — how much
of the answer is backed by known sources, how complete the user's input was, how
many sources were cited — NOT from the model's self-reported confidence, which is
miscalibrated and would launder a guess as certainty. `score_confidence` is a pure
function: no model call, deterministic, unit-testable.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Tier = Literal["well_grounded", "partial", "speculative"]

_BADGES: dict[Tier, str] = {
    "well_grounded": "🟢 Well-grounded",
    "partial": "🟡 Partial",
    "speculative": "🔴 Speculative",
}

# Shown on anything short of well-grounded.
_VERIFY_NUDGE = "Verify with orientation.ch or your study advisor before deciding."


@dataclass(frozen=True)
class ConfidenceSignals:
    """Observable inputs to the score — all model-independent by design.

    There is deliberately no field for the model's self-reported confidence.
    """

    input_completeness: float  # provided key fields / expected, 0..1
    grounding: float  # recommendations backed by a known source / total, 0..1
    source_count: int  # distinct allowlisted sources cited
    out_of_scope: bool = False
    critic_groundedness: float | None = None  # optional verifier ratio, 0..1


@dataclass(frozen=True)
class Confidence:
    tier: Tier
    score: float  # 0..1, for display/sorting only — never a precision guarantee
    badge: str
    reasons: list[str]


def _clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else float(x)


def _blend(ic: float, g: float, sc: int, critic: float | None) -> float:
    base = 0.45 * g + 0.30 * ic + 0.25 * (min(sc, 3) / 3)
    if critic is not None:
        base = 0.7 * base + 0.3 * _clamp01(critic)
    return round(_clamp01(base), 2)


def _result(tier: Tier, score: float, reasons: list[str]) -> Confidence:
    if tier != "well_grounded":
        reasons = [*reasons, _VERIFY_NUDGE]
    return Confidence(tier=tier, score=score, badge=_BADGES[tier], reasons=reasons)


def score_confidence(signals: ConfidenceSignals) -> Confidence:
    """Map observable signals to a tiered badge. Thresholds per ADR-0009 (tunable)."""
    ic = _clamp01(signals.input_completeness)
    g = _clamp01(signals.grounding)
    sc = max(0, int(signals.source_count))

    # Speculative gates — any one triggers, regardless of how "sure" a model sounded.
    if signals.out_of_scope:
        return _result("speculative", 0.10, ["The request falls outside education-advice scope."])
    if g <= 0:
        return _result("speculative", 0.15, ["No part of the answer is backed by a known source."])
    if ic < 0.25:
        return _result("speculative", 0.20, ["Too little information was provided to assess reliably."])

    score = _blend(ic, g, sc, signals.critic_groundedness)

    # Well-grounded needs strong grounding AND multiple sources AND a reasonably full profile.
    if g >= 0.8 and sc >= 2 and ic >= 0.6:
        return _result(
            "well_grounded",
            score,
            [
                f"{round(g * 100)}% of recommendations cite official sources ({sc} sources).",
                "Enough profile information was provided to assess.",
            ],
        )

    # Otherwise partial — name specifically what held it back.
    reasons: list[str] = []
    if g < 0.8:
        reasons.append("Some recommendations could not be tied to an official source.")
    if sc < 2:
        reasons.append(f"Only {sc} official source{'s' if sc != 1 else ''} cited.")
    if ic < 0.6:
        reasons.append("Limited profile information was provided.")
    return _result("partial", score, reasons or ["Only partially grounded."])
