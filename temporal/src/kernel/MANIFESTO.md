# Kernel Manifesto (binding)

The kernel is the platform's stable core. These rules override generic guidance for this
package.

## What the kernel IS

Generic, domain-agnostic capabilities shared by all features: the feature registry + builders,
confidence scoring, and source-allowlist resolution. Pure where possible; no I/O except what a
feature explicitly wires.

## Forbidden imports / dependencies

- ❌ **The kernel MUST NOT import from `src.features.*`** — ever. Dependencies point features →
  kernel, never the reverse. (Enforced by convention; a violation is a design bug.)
- ❌ No feature-specific data in the kernel: **no Swiss source lists, no personas, no
  institution types, no prompt text.** Those belong to the feature that owns them.
- ❌ No hard dependency on Temporal, httpx, or the LLM SDK in the pure modules
  (`confidence.py`, `sources.py`, `registry.py` are import-light and testable without them).

## Public contract (change = ADR-worthy)

Every feature depends on these shapes; changing them ripples across all features, so a change
requires an ADR and updates to every feature + its tests.

- `FeatureManifest(key, title, enabled=True, requires_auth=False, workflows, activities, claims, route)`.
- `ClaimSpec(table, workflow, workflow_id_prefix)`.
- `build_workflows/activities/claims/routes(features)` — operate over **enabled** features;
  activities are de-duped (shared `model_chat` registers once).
- `apply_feature_flags(features, allow_csv)` — env allowlist overrides `enabled`; empty/None →
  built-in flags.
- `score_confidence(ConfidenceSignals(input_completeness, grounding, source_count, out_of_scope,
  critic_groundedness?))` → `Confidence(tier, score, badge, reasons)`.
  **`ConfidenceSignals` has no field for a model's self-reported confidence, and must never
  gain one** (ADR-0009).
- `resolve_sources(urls, allowlist)` / `grounding_ratio(cited, allowlist)`.

## Testing boundaries

- All three modules are **pure** → plain pytest unit tests, no TestBed/Temporal/DB.
- The confidence tiers and the "signals override apparent certainty" property are always tested
  (`tests/test_confidence.py`). The registry builders' enabled/dedup/flag behavior is tested
  (`tests/test_registry.py`).
