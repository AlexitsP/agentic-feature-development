# Study Pathway Advisor — Kernel + Evaluator (v0) Specification

**Status:** Approved
**Owner:** Patrik Alexits
**Created:** 2026-07-08
**Last Updated:** 2026-07-08

> Spec-driven + TDD. This spec is the contract; the test list in **Testing Strategy**
> is written first (red), then implemented (green). Concrete architecture is deferred
> to the accompanying ADRs (see **References**) per house convention.

## Overview

Repurpose this agentic stack from the "Gains Check" demo into an **education advisor
platform** for Swiss learners. This first increment delivers two things at once,
because you cannot prove one without the other:

1. A small, stable **feature-plugin kernel** — the generic run lifecycle, model access,
   live tracing, **confidence scoring**, source-grounding, and auth — that individual
   features plug into and can be toggled on/off without editing anything outside their
   own scope.
2. The **first plug-in feature — the Program Evaluator**: a prospective student describes
   their situation; an agent assesses it against real Swiss higher-education options and
   suggests suitable **fields of study, degree programs, and institution types**
   (University · University of Applied Sciences (Fachhochschule) · University of Teacher
   Education (PH)), **with a visible confidence badge** stating how grounded and reliable
   the answer is.

A follow-on plug-in (the Study Planner, incl. a "how to study" facet) and others
("inspire me" topic chat, pre-higher-ed pathway choice) are explicitly out of scope here
but must be addable later by dropping in a feature package — proving the kernel.

## Goals

- Establish a **kernel/feature boundary** where a feature is a self-contained package
  that self-registers; adding, removing, or disabling a feature touches **only** that
  feature's files plus a single declarative registry entry.
- Ship the **Program Evaluator** feature end-to-end on that kernel: prospective-student
  input → evaluation → suggested higher-ed fields/programs/institution types grounded in a
  curated set of official Swiss sources.
- Make every answer carry a **confidence badge** computed from *observable* signals
  (grounding, input completeness, source coverage) — never the model's self-report.
- Keep the substrate honest for an **internal experiment**: no real student PII, a
  documented data boundary, and a clear gate for what must be true before real data.

## Non-Goals

- Real student data / production deployment (see **Compliance & Data Boundary**).
- The Study Planner, "how to study", "inspire me" chat, or pre-higher-ed pathway choice —
  future plug-ins; this increment only proves they *can* be added without core edits.
- Retrieval-augmented generation over a live school-catalogue knowledge base (v1 uses a
  curated static source list; RAG is a later, additive capability).
- Replacing the model provider — stays on company Azure OpenAI (data residency; see
  ADR-0008). The one-file provider abstraction is a separate resilience task.
- Comedic personas (Gym Bro / Drill Sergeant). Tone becomes professional counselor styles.

## Success Metrics

- Adding a second (stub) feature to the registry registers its workflow + poller claim +
  route with **zero edits** to `worker.py` / `poller.py` bodies or existing features.
- 100% of pathway recommendations cite only sources from the curated allowlist (no
  invented URLs), verified in review and enforced in code.
- Every evaluation renders a confidence badge; a result with no grounding sources or a
  near-empty student profile is classified **Low** confidence, never High.

## Users & User Stories

### As a prospective higher-ed student (or advisor), I want an assessment of which study program and institution type fit me, so I can make an informed choice

**Acceptance Criteria:**
- [ ] I can enter my situation either as structured fields (interests, prior qualification
      (e.g. gymnasiale Matura / Berufsmaturität), strong subjects, target field, canton,
      language region, constraints) **or** as free text, and start an evaluation in one action.
- [ ] Within a few seconds I get: a plain-language assessment, 1–3 **suggested study
      options** (a field of study + institution type — University / University of Applied
      Sciences (Fachhochschule) / University of Teacher Education (PH), optionally naming
      concrete programs), each with a short reason grounded in what I entered, and links
      **only** to official sources.
- [ ] If I gave very little information, the assistant says so and lowers its confidence
      rather than guessing.

### As any user of a result, I want a confidence badge, so I know how much to trust it

**Acceptance Criteria:**
- [ ] Each result shows a tiered badge — **🟢 Well-grounded / 🟡 Partial / 🔴 Speculative**
      — with a one-line reason and, on 🟡/🔴, a "verify with orientation.ch or your school
      counselor" nudge.
- [ ] The tier is derived from observable signals (below), **not** from the model stating
      its own confidence.

### As a developer, I want features to be plug-ins, so I can add/remove capability without touching the core

**Acceptance Criteria:**
- [ ] A feature is one package declaring a manifest; the worker and poller build their
      registration/claim lists by iterating the feature registry.
- [ ] Disabling a feature (config flag) removes its workflow registration, its poller
      claim, its route, and its UI entry — with no other code change.
- [ ] Adding a feature package + registry entry wires it end-to-end with no edits to
      existing features or to `worker.py` / `poller.py` bodies.

## Functional Requirements

### Must Have (P0)
- **Kernel contract** exposing: run lifecycle (`pending → poller claim → workflow →
  finalize`), `model_chat` access, trace-event emission, `score_confidence()`,
  source-allowlist resolution, and owner-scoped auth helpers.
- **Feature registry + manifest**: `{ key, title, enabled, tables, workflow, activities,
  claim: { table, workflowIdPrefix }, route }`. Worker/poller/frontend read the registry.
- **Pathway Evaluator feature**: input model, evaluation workflow, tool schema
  (`submit_evaluation`), curated Swiss source allowlist, professional persona/tones.
- **Confidence scoring** as a pure kernel function over observable signals.
- **Feature enablement** via a single `FEATURES` config (env or config file).

### Should Have (P1)
- A **critic/verifier** pass (LLM-as-judge) contributing a groundedness signal to
  confidence.
- A stub "second feature" retained in the repo (disabled by default) as a living proof of
  the plugin contract and a regression guard.

### Nice to Have (P2)
- Self-consistency sampling (N samples → agreement) feeding confidence.

## Confidence Signal (testable contract)

`score_confidence(signals) -> { tier, score, reasons[] }`, a **pure function** (no model
call). Inputs are observable:

| Signal | Definition |
|---|---|
| `input_completeness` | provided key fields / expected key fields (0–1) |
| `grounding` | recommendations backed by an allowlisted source / total recommendations (0–1) |
| `source_count` | number of distinct allowlisted sources cited |
| `out_of_scope` | query fell outside the education-advice domain (bool) |
| `critic_groundedness` *(P1)* | verifier's supported-claims ratio (0–1) |

Tiering (initial thresholds, tunable): **🔴 Speculative** if `out_of_scope`, or
`grounding == 0`, or `input_completeness < 0.25`; **🟢 Well-grounded** if
`grounding ≥ 0.8` **and** `source_count ≥ 2` **and** `input_completeness ≥ 0.6`;
**🟡 Partial** otherwise. `reasons[]` explains the tier in plain language. **The model's
self-reported confidence is never an input.**

## Technical Design

> Spec altitude. The kernel↔feature interface shapes, the registry mechanism, the
> confidence internals, and the trace transport are recorded in ADR-0008 (platform +
> plugin) and ADR-0009 (confidence); auth is ADR-0007.

### Architecture
Frontend renders enabled features from a registry. A student starts an evaluation → a
`pending` run row → the kernel poller (iterating registered claim specs) starts the
feature's Temporal workflow → the workflow drives the model via the kernel `model_chat`,
constrains links to the feature's source allowlist, computes confidence via the kernel,
emits trace events, and finalizes the run row. The frontend streams steps + renders the
result and badge via realtime. Durability/retries come from the kernel's Temporal base.

### Dependency rule
Features depend on the kernel; the kernel never depends on a feature; features never
import each other (cross-feature data flows through run rows). This is what makes features
independently pluggable.

### Data Model (owner-scoped, per feature)
Each feature owns its timestamped migration. Evaluator tables:
- `program_evaluations` — `{ id, user_id, input jsonb, status, result jsonb, confidence
  jsonb, error, created_at, updated_at }`
- `program_evaluation_events` — trace steps (same shape as today's `*_events`).
- **RLS:** owner-scoped (`auth.uid() = user_id`) per ADR-0007 — **prerequisite before any
  real data**; for the internal experiment, synthetic profiles only.

### UI/UX
A feature launcher lists enabled features. The Evaluator is a short wizard (situation →
running with live trace → result). The result panel shows the assessment, suggested
pathways with reasons + official links, and the **confidence badge** with its reason.
Professional counselor tones selectable (encouraging mentor / straight-talking advisor /
detailed analyst).

## Compliance & Data Boundary (internal experiment)

Right-sized for an internal experiment — cheap habits now, documented gate for later:
- **Synthetic/test profiles only**; no real student PII collected or stored.
- **No PII in logs or trace events.**
- **Stays on company Azure OpenAI in a Swiss/EU region** (data residency; prompts stay in
  the controlled tenant, not a public API).
- Documented **gate before real student data**: ADR-0007 owner-scoped auth shipped, a
  retention/consent policy, and an nLPD/FADP review. (Not legal advice — a real review is
  required before real data.)

## Testing Strategy (TDD — write these first, red → green)

### Unit (pure, fast — the TDD core)
- `score_confidence`: fabricated/no-source result → 🔴; sparse profile → 🔴/🟡; full
  profile + ≥2 allowlisted sources + high grounding → 🟢; `out_of_scope` → 🔴; model
  self-report is ignored even if present.
- Source allowlist resolver: unknown/invented URLs dropped; only allowlisted links kept;
  dedup preserved.
- Evaluator result builder: coerces model tool-args into the result contract; missing
  fields default safely; suggested pathways constrained to the known enum.
- **Feature registry / plugin contract**: the worker-registration builder produces exactly
  the workflows/activities of *enabled* features; the poller claim-spec builder yields one
  claim per enabled feature; disabling a feature removes it from both; adding a stub
  feature adds it to both — all without touching `worker.py`/`poller.py` bodies.

### Integration
- Evaluator workflow against a seeded/synthetic input via Temporal `TestWorkflowEnvironment`
  with a mocked `model_chat`: happy path finalizes `done` with a grounded result + a
  confidence tier; the "thin input" path finalizes with 🔴/🟡; a model error finalizes
  `error` with a generic message (no leaked internals — SEC-5).

### E2E (manual, local stack)
- Start an evaluation from the UI, watch steps stream, verify suggested pathways cite only
  allowlisted sources and the badge matches the input richness. Toggle the stub feature
  off/on and confirm its route/claim/registration appear and disappear.

## Implementation Plan (TDD-ordered)

### Phase 0 — Spec & decisions
- [ ] This spec approved; ADR-0008 (platform + plugin), ADR-0009 (confidence) written;
      ADR-0007 (auth) confirmed as prerequisite for real data.

### Phase 1 — Kernel (test-first)
- [ ] Red tests for `score_confidence`, allowlist resolver, registry/worker/poller builders.
- [ ] Implement the kernel: run-lifecycle helpers, registry + manifest type, confidence,
      allowlist, data-driven worker/poller builders. Green.

### Phase 2 — Evaluator feature (test-first)
- [ ] Red tests for the result builder + the evaluation workflow (mocked model).
- [ ] Implement `features/pathway_evaluator/` (manifest, migration, workflow, tools,
      source allowlist, personas). Green.

### Phase 3 — Frontend + proof-of-plugin
- [ ] Feature launcher + Evaluator wizard + confidence badge, rendered from the registry.
- [ ] Add a disabled stub feature; add a test asserting enable/disable wiring.

## Dependencies

- **ADR-0007** owner-scoped RLS + auth — prerequisite before real student data.
- Kernel reuses today's proven substrate: run-row pattern, `model_chat`/`ModelClient`,
  realtime trace events, the `resolve_plan_resources` allowlist mechanism.
- Company Azure OpenAI (`gpt-5-mini`) reachable; local Supabase + Temporal worker.

## Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Model invents schools/requirements/deadlines | High | Medium | Curated source allowlist; prompt forbids un-grounded specifics; confidence lowers on thin grounding; "verify with counselor" nudge |
| Weak/forced tool-calling reliability | Medium | Medium | Keep forced-tool guided path; JSON-mode fallback; result builder tolerates missing fields |
| Kernel contract churn breaks all features | Medium | Medium | Keep the contract small + stable; lock it in ADR-0009; contract has its own tests |
| "Confidence" read as a precise guarantee | Medium | Medium | Tiers + plain-language reasons, no fake %; explicit verify nudge |
| Scope creep into real student data | High | Low | Documented data boundary + gate; synthetic profiles only |

## Open Questions

- [x] **First audience** — **higher-education program selection** (decided 2026-07-08).
      Pre-higher-ed pathway choice becomes a future additive plug-in.
- [ ] Taxonomy granularity for v0: institution type (University / UAS / PH) + field of
      study — is naming concrete programs in scope, or institution-type + field only?
- [ ] Which official sources seed the allowlist (swissuniversities.ch, orientation.ch
      higher-ed section, berufsberatung.ch, university admission pages, SERI …).
- [ ] Is the "second feature" a real Study Planner stub or a throwaway proof feature?

## References

- Spec conventions: `docs/specs/TEMPLATE.md`, `docs/specs/entity-insights-assistant.md`
- Kernel reuse: `temporal/src/agents/model_client.py`, `temporal/src/runs/poller.py`,
  `temporal/src/agents/tools/gains_tools.py` (`resolve_plan_resources`)
- Prerequisite: `docs/adrs/0007-owner-scoped-rls-and-auth.md`
- To be written: ADR-0008 (education platform + feature-plugin architecture), ADR-0009
  (confidence signal)
