# Study Planner Specification

**Status:** Approved
**Owner:** Patrik Alexits
**Created:** 2026-07-08
**Last Updated:** 2026-07-08

> Spec-driven + TDD. Second feature plug-in of the SLH AI Hub platform, built on
> the existing kernel (ADR-0008 registry, ADR-0009 confidence) and owner-scoped auth
> (ADR-0007). The architecture is already decided; this spec defines the feature's
> behavior and its testable contract.

## Overview

Given a study goal (a field/program, optionally carried over from the Program Evaluator)
plus the student's situation, a **multi-agent panel** drafts a concrete, research-based
**study plan** — including a **"how to study"** facet — grounded in the curated official
Swiss source allowlist, with a kernel-computed **confidence badge**. This is the SLH AI Hub
study-planning payload; it flips the disabled `How to Study` launcher stub into a real
feature.

## Goals

- Turn a goal + profile into an actionable **study plan**: target/summary, milestones or
  weekly steps to get started, and **how-to-study** guidance (study-skills / learning
  science), grounded in official Swiss sources.
- Reuse the kernel end-to-end (run-row lifecycle, `model_chat`, tracing, `score_confidence`,
  source allowlist) and register as a pure plug-in (`FeatureManifest`) — no worker/poller edits.
- Be **owner-scoped from creation** (ADR-0007): `study_plans` carry `user_id default
  auth.uid()` with authenticated owner policies (no experiment-open anon defaults for a new table).

## Non-Goals

- Retrieval over a live catalogue (v1 uses the curated static allowlist; RAG is additive later).
- Replacing the Program Evaluator — the Planner is a *second* feature; a goal may be typed
  directly or handed over from an evaluation.
- Real student data / production deploy (internal experiment; synthetic profiles only).

## Users & User Stories

### As a prospective student, I want a concrete study plan for my goal, so I know what to do next

**Acceptance Criteria:**
- [ ] I enter a goal (field of study + institution type, or free text) and my situation
      (prior qualification, timeframe, constraints), and start a plan in one action.
- [ ] Within a few seconds I get: a short plan summary, 4–6 concrete **weekly/starter steps**,
      a **how-to-study** section (2–4 study-skills pointers), and links **only** to official
      Swiss sources — with a **confidence badge**.
- [ ] If I give little information, the plan says so and its confidence drops (no fabrication).

### As a developer, I want the Planner to be a pure plug-in, so adding it changes nothing else

**Acceptance Criteria:**
- [ ] The Planner registers via a `FeatureManifest`; worker/poller/frontend pick it up from
      the registry with no edits to their bodies.
- [ ] The disabled `How to Study` stub becomes this enabled feature; no other feature changes.

## Technical Design

> Spec altitude — architecture is ADR-0008/0009 + ADR-0007. This defines the feature shape.

### Workflow (multi-agent panel → synthesis)
`StudyPlanWorkflow` (deterministic; non-determinism in the reused `model_chat` activity):
1. Dispatch a small **panel** of advisor agents **in parallel**, each grounded in the source
   allowlist: **curriculum/pathway advisor**, **study-skills (how-to-study) coach**, and
   (optionally) an **admissions/timeline advisor**. Each returns structured advice via a
   `submit_advice` tool.
2. A **head advisor** synthesizes the panel into one plan via a forced `submit_plan` tool:
   `summary`, `weekly_steps[]`, `how_to_study[]`, `resource_urls[]` (allowlist-constrained).
3. Build the result with the pure builder (resolves sources + attaches `score_confidence`
   from observable signals), emit trace events, finalize the run row. Honest low-confidence
   fallback if the model never submits.

### Data Model (owner-scoped from the start, ADR-0007)
- `study_plans` — `{ id, user_id uuid default auth.uid(), input jsonb, status, result jsonb,
  error, created_at, updated_at }`, `chk` status + input-size cap.
- `study_plan_events` — trace steps (FK `plan_id` → `study_plans`, cascade).
- **RLS:** authenticated owner policies (`auth.uid() = user_id`; events via parent join);
  no anon policies. Worker writes via service role (bypasses RLS).

### Confidence
Same rubric as the Evaluator (ADR-0009): grounding (allowlisted sources cited / total),
input completeness (goal + profile fields provided), source count. Tiered 🟢/🟡/🔴; no
model self-report.

### UI/UX
A `/plan` route: a short wizard (goal + situation → running with live trace → plan). Result
shows summary, weekly steps, a **How to study** block, official-source links, and the
confidence badge. Launcher: the `How to Study` stub entry becomes this enabled feature.

## Testing Strategy (TDD — write first)

### Unit (pure)
- Plan result builder: coerces panel/synthesis tool-args into the contract; caps
  weekly_steps/how_to_study; drops invented sources (allowlist); safe defaults for missing
  fields; confidence tier from grounding + input completeness.
- Input-completeness helper for the planner's expected fields.
- Manifest declares the `study_plans` claim + `/plan` route + workflow.

### Integration
- `StudyPlanWorkflow` via `TestWorkflowEnvironment` with a mocked `model_chat`: panel
  dispatched, head-coach synthesis, finalizes `done` with a grounded plan + confidence;
  thin input → 🔴/🟡; model error → `error` with a generic message (SEC-5); model never
  submits → low-confidence fallback.

### RLS (live, not CI)
- Owner-scoped isolation on `study_plans` verified the same way as ADR-0007 (rolled-back tx):
  anon denied; insert captures `auth.uid()`; user A cannot read user B's plans.

## Implementation Plan (TDD-ordered)

### Phase 1 — backend (this slice)
- [ ] Red tests: result builder, input completeness, manifest, workflow (mocked model).
- [ ] Implement `features/study_planner/` (tools, workflow, activities, manifest) + migration
      `study_plans`/`study_plan_events` (owner-scoped); register in `features/registry.py`.

### Phase 2 — frontend
- [ ] `/plan` route (wizard + how-to-study + confidence badge); flip the launcher stub.

## Dependencies
- Kernel (`src/kernel/*`), the reused `model_chat` activity, ADR-0007 auth pattern, the
  Program Evaluator as the template. Company Azure OpenAI (`gpt-5-mini`).

## Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Model invents programs/steps/sources | High | Medium | Source allowlist; grounding lowers confidence; "verify with counselor" nudge |
| Panel adds latency/cost (N+1 model calls) | Medium | Medium | Small panel (2–3), parallel dispatch, generous timeouts |
| Weak forced-tool reliability | Medium | Medium | Forced `submit_plan`; result builder tolerates missing fields |

## Open Questions
- [ ] Panel size for v1: 2 (curriculum + study-skills) or 3 (+ admissions/timeline)?
- [ ] Does the Planner accept a handoff from an evaluation (prefill goal), or standalone-only for v1?

## References
- Spec conventions: `docs/specs/TEMPLATE.md`, `docs/specs/study-pathway-advisor.md`
- Kernel + first feature: `src/kernel/*`, `src/features/program_evaluator/*`
- ADRs: 0008 (plugin), 0009 (confidence), 0007 (owner-scoped RLS + auth)
