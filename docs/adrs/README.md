# Architecture Decision Records (ADRs)

This directory records the significant architectural decisions made on this project, **why** they were made, and what we traded away. ADRs are the reference point for reviews: when we evaluate a change, a spec, or a deploy, we check it against these records to confirm we are still making the right decisions — and we add or supersede a record when we make a new one.

## Why we keep these

Architectural decisions (data model, orchestration engine, deployment topology, external edge, auth boundaries) are easy to execute in code and impossible to review later if they were never written down. That is the failure mode these records exist to prevent: a review has nothing to check against if the decision was never articulated. Record the decision when you make it, not after something built on top of it breaks.

## Process

- **One decision per file**, named `NNNN-short-slug.md`, numbered sequentially.
- Use [`TEMPLATE.md`](./TEMPLATE.md). Keep each record short and concrete; cite **evidence** (commit hashes, PR numbers, file paths, live resource names).
- **Status** is one of: `Proposed` · `Accepted` · `Superseded by ADR-NNNN` · `Deprecated`.
- An ADR is **immutable once Accepted** — to change a decision, write a new ADR that supersedes it and update the old one's status. Do not silently rewrite history.
- **When to write one:** any decision that is costly to reverse, shapes more than one component, picks one technology/pattern over alternatives, or changes a security/data/deploy boundary. When in doubt, write it.
- **Who:** the Factory Architect owns ADR authorship for designs it produces; the Tech Reviewer should flag any PR that makes an architectural decision without a corresponding ADR (see the maintenance note at the bottom).

## Index

| ADR | Title | Status |
|---|---|---|
| [0001](./0001-entity-insights-workflow-and-model-hosting.md) | Entity Insights workflow shape and model hosting | Accepted |
| [0002](./0002-gains-check-guided-vs-agentic-engine.md) | Gains Check — Guided vs Agentic engine toggle | Accepted |
| [0003](./0003-testing-strategy.md) | Testing strategy — unit + Temporal workflow tests, CI fails loud | Accepted |
| [0004](./0004-deployment-posture-local-only.md) | Deployment posture — local-only for now | Accepted |
| [0005](./0005-gains-plan-multi-agent-panel.md) | Gains Plan — multi-agent panel (parallel specialists → synthesizer) | Accepted |
| [0006](./0006-trim-to-gains-only-minimal-repo.md) | Trim to a Gains-only minimal repo | Accepted |
| [0007](./0007-owner-scoped-rls-and-auth.md) | Owner-scoped RLS + auth (proposal for SEC-1) | Proposed |
| [0008](./0008-education-platform-feature-plugin-architecture.md) | Education advisor platform + feature-plugin architecture | Proposed |
| [0009](./0009-confidence-signal-observable-not-self-reported.md) | Confidence signal from observable factors, not model self-report | Proposed |

## Maintenance note

Keeping this index honest is the whole point. Factory policy enforcement:
- Tech Reviewer ADR-gate: a PR that adds/changes infra, swaps a library/service, introduces a new service, or changes a deploy/security/data boundary must link an ADR (or `docs/adrs/`) in the PR. If missing, request changes and add `needs-adr`.
- Factory Architect ADR authorship: when an architecture design/spec introduces or changes a decision, the Architect publishes the corresponding ADR(s) in `docs/adrs/` using `TEMPLATE.md`.
- Copilot implementation rule: when approved implementation changes introduce an architectural decision, include/update the ADR in `docs/adrs/` and reference it in the PR.
- Accepted ADRs are immutable. Changed decisions must be recorded via a new superseding ADR plus status/history updates to the prior ADR.
