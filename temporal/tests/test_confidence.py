"""Kernel confidence scoring (ADR-0009) — observable signals, never model self-report."""
from src.kernel.confidence import ConfidenceSignals, score_confidence


def test_no_grounding_is_speculative():
    c = score_confidence(ConfidenceSignals(input_completeness=0.9, grounding=0.0, source_count=0))
    assert c.tier == "speculative"
    assert c.badge.startswith("🔴")


def test_sparse_input_is_speculative():
    c = score_confidence(ConfidenceSignals(input_completeness=0.1, grounding=0.9, source_count=3))
    assert c.tier == "speculative"


def test_out_of_scope_is_speculative():
    c = score_confidence(
        ConfidenceSignals(input_completeness=1.0, grounding=1.0, source_count=5, out_of_scope=True)
    )
    assert c.tier == "speculative"


def test_full_grounded_is_well_grounded():
    c = score_confidence(ConfidenceSignals(input_completeness=0.8, grounding=0.9, source_count=3))
    assert c.tier == "well_grounded"
    assert c.badge.startswith("🟢")
    assert 0.0 <= c.score <= 1.0


def test_partial_when_few_sources():
    c = score_confidence(ConfidenceSignals(input_completeness=0.8, grounding=0.9, source_count=1))
    assert c.tier == "partial"


def test_partial_when_weak_grounding():
    c = score_confidence(ConfidenceSignals(input_completeness=0.8, grounding=0.5, source_count=3))
    assert c.tier == "partial"


def test_non_well_grounded_has_verify_nudge():
    c = score_confidence(ConfidenceSignals(input_completeness=0.8, grounding=0.5, source_count=3))
    assert any("Verify" in r for r in c.reasons)


def test_observable_signals_override_any_apparent_certainty():
    # A result a model would "feel" 100% sure about, but with nothing grounded and a
    # near-empty profile, must still be speculative — signals win, not the model.
    c = score_confidence(ConfidenceSignals(input_completeness=0.05, grounding=0.0, source_count=0))
    assert c.tier == "speculative"


def test_signals_have_no_self_report_field():
    # Guardrail: the contract must not expose a place to inject a model's own score.
    assert "confidence" not in ConfidenceSignals.__dataclass_fields__
    assert "self_report" not in ConfidenceSignals.__dataclass_fields__
