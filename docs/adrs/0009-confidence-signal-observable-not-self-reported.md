# ADR-0009: Confidence signal from observable factors, not model self-report

- **Status:** Proposed
- **Date:** 2026-07-08
- **Deciders:** Patrik Alexits
- **Supersedes / Superseded by:** —

## Context

Education advice carries a duty of care: telling a prospective student the wrong program,
institution type, or admission requirement is real harm. Users need to see **how reliable**
a given answer is — the risk that it is hallucinated or driven by thin/bad context. The
obvious implementation — asking the LLM "how confident are you (0–100)?" — is actively
harmful: LLMs are poorly calibrated and will report high confidence on fabrications, which
launders a guess as certainty. A trustworthy signal must come from factors we can observe,
not the model's introspection.

## Decision

We compute a **confidence badge** as a **pure kernel function** over *observable* signals and
never from the model's self-reported confidence. Signals: `grounding` (recommendations backed
by an allowlisted/curated source ÷ total), `input_completeness` (provided key fields ÷
expected), `source_count`, `out_of_scope`, and optionally `critic_groundedness` (an
LLM-as-judge verifier's supported-claims ratio) and self-consistency agreement across
samples. The function returns a **tier** — 🟢 Well-grounded / 🟡 Partial / 🔴 Speculative —
a numeric score, and plain-language `reasons[]`. Non-🟢 results carry a "verify with
orientation.ch or your advisor" nudge. Initial thresholds (tunable): 🔴 if `out_of_scope` or
`grounding == 0` or `input_completeness < 0.25`; 🟢 if `grounding ≥ 0.8` **and**
`source_count ≥ 2` **and** `input_completeness ≥ 0.6`; 🟡 otherwise.

## Consequences

- **Easier / safer:** honest reliability signalling; the tier is deterministic and unit-
  testable (pure function); reusable by every feature as a kernel capability.
- **Depends on grounding:** the signal is only meaningful with a real source-allowlist (and,
  later, retrieval) — this reinforces the curated-source and eventual RAG direction.
- **Trade-offs:** optional critic-pass and self-consistency add model-call cost; thresholds
  need tuning against real examples.
- **New obligation:** present it as guidance, not a guarantee — tiers + reasons, never a
  false-precision percentage; tune thresholds as we gather examples.

## Alternatives considered

- **Model self-reported percentage:** rejected — miscalibrated and dangerous; it dresses a
  hallucination as certainty.
- **No confidence signal:** rejected — incompatible with the duty of care in education advice.
- **Token-logprob-only confidence:** rejected — reasoning models may not expose logprobs, and
  logprobs capture fluency, not whether a claim is grounded in real sources.

## Evidence

- Spec: `docs/specs/study-pathway-advisor.md` (Confidence Signal section).
- To be implemented: `temporal/src/kernel/confidence.py` with unit tests in
  `temporal/tests/`. Companion: ADR-0008 (platform + plugin architecture).
