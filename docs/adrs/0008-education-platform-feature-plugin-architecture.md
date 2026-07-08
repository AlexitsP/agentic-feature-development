# ADR-0008: Education advisor platform + feature-plugin architecture

- **Status:** Proposed
- **Date:** 2026-07-08
- **Deciders:** Patrik Alexits
- **Supersedes / Superseded by:** —

## Context

The repo is being repurposed from the "Gains Check" demo into an **education advisor
platform** for Swiss higher education (first feature: Program Evaluator; see
`docs/specs/study-pathway-advisor.md`, Approved). The product intent is a set of
capabilities — evaluator, study planner, "how to study", "inspire me" chat — that must be
independently **addable, removable, and toggleable** without editing unrelated code.

Today, adding a feature edits three shared chokepoints (called out in `CLAUDE.md`):
`temporal/src/worker.py` (workflow/activity registration lists), `temporal/src/runs/poller.py`
(the pending-row claim loop), and the frontend route registry. Every feature touches these,
which causes merge conflicts and makes disabling a feature a code edit rather than a config
change. This is the coupling the platform must remove. Constraints: internal experiment (no
real student data yet), stays on company Azure OpenAI in a Swiss/EU region for data
residency, and owner-scoped auth (ADR-0007) is a prerequisite before real data.

## Decision

We adopt a **kernel + feature-plugin architecture**. A small, stable **kernel** owns the
generic capabilities — run lifecycle (`pending → poller claim → workflow → finalize`), model
access (`model_chat` / `ModelClient`), realtime trace emission, confidence scoring
(ADR-0009), source-grounding/allowlist, and auth helpers. Each **feature** is a
self-contained package that declares a **manifest** (`{ key, title, enabled, tables,
workflow, activities, claim: { table, workflowIdPrefix }, route }`). The worker, poller, and
frontend build their registration / claim / route lists by **iterating a feature registry**
gated by a single `FEATURES` enablement config. Features depend only on the kernel; the
kernel never depends on a feature; features never import one another (cross-feature data
flows through run rows).

## Consequences

- **Easier:** adding a feature = drop a package + one registry entry (no edits to
  `worker.py`/`poller.py` bodies or other features); disabling = flip a config flag, which
  removes its workflow registration, poller claim, route, and UI entry.
- **New obligation:** the kernel contract must stay **small and stable** and carries its own
  tests; changes to it are ADR-worthy because every feature depends on it.
- **Constrained:** migrations stay per-feature and timestamped (SQL ordering can't be fully
  auto); cross-feature composition must go through run rows, not imports.
- **Prerequisite:** owner-scoped RLS + auth (ADR-0007) before any real student data.
- Retroactively justifies the heavier stack (Temporal + run-row substrate + realtime): it is
  now a platform hosting pluggable agentic features, not a single form→LLM app.

## Alternatives considered

- **Status quo (hardcoded registration):** rejected — every feature edits the shared
  chokepoints, causing conflicts and making toggling a code change.
- **A service per feature (microservices):** rejected — operational burden far exceeds the
  need for an internal experiment; the shared substrate is the point.
- **Feature flags without a kernel contract:** rejected — flags alone don't stop
  feature↔feature coupling; the stable kernel interface is what enables true plug-ins.

## Evidence

- Spec: `docs/specs/study-pathway-advisor.md` (Approved).
- To be implemented: `temporal/src/kernel/*` (registry, run lifecycle, builders) and
  `temporal/src/features/<name>/*`; frontend feature registry.
- Formalizes and removes the per-feature edit pattern described in `CLAUDE.md`
  ("shared chokepoint files"). Companion: ADR-0009 (confidence), ADR-0007 (auth prerequisite).
