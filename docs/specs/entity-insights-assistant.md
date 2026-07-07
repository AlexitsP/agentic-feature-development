# Entity Insights Assistant Specification

**Status:** In Review
**Owner:** Patrik Alexits
**Created:** 2026-07-07
**Last Updated:** 2026-07-07

## Overview

An assistant that, from an entity's detail page, produces a plain-language read
on that entity. A Temporal workflow runs the deployed Azure OpenAI model
(`gpt-5-mini`) in a bounded tool-use loop: the model calls typed tools that read
the entity's own data from Supabase, then returns a structured insight. The UI
shows each step of the run as it happens, so the answer is transparent and
trustworthy. This is the first end-to-end demonstration of the model-integration
layer wired in [ADR pending] and `temporal/src/agents/model_client.py`.

## Goals

- Give users a fast, plain-language summary of a single entity grounded only in
  that entity's real data.
- Make the assistant's reasoning transparent: show every lookup and the data it
  returned, progressively, ending in the final answer.
- Prove the full stack end-to-end: Frontend → backend trigger → Temporal
  workflow → Azure OpenAI model → Supabase tools → Frontend visualization.

## Non-Goals

- Cross-entity or portfolio-level analysis (single entity only).
- Writing to or modifying entity data (read-only tools).
- New authentication or role model beyond what the app already has.
- Persisting past insights for later retrieval (candidate for a phase 2).
- Production hardening (rate limits, cost controls, multi-tenant isolation).

## User Stories

### As an operations user, I want a plain-language summary of an entity, so I can grasp its state without reading raw tables

**Acceptance Criteria:**
- [ ] I can start an insight from an entity's detail page in one click.
- [ ] Within a few seconds I get a plain-language summary plus the entity's most
      notable facts.
- [ ] The result uses only this entity's real data — no invented values; if the
      data is thin, the assistant says so rather than guessing.

### As a user, I want to see how the assistant reached its answer, so I can trust it

**Acceptance Criteria:**
- [ ] I can see each step the assistant took: which tool it called and what data
      came back.
- [ ] Steps appear progressively as the run proceeds, ending with the final
      structured answer.
- [ ] If the run fails, I see a clear error message and a suggested next step —
      never an indefinite spinner.

## Technical Design

> Spec altitude only. The concrete **workflow shape**, the **frontend→backend
> trigger mechanism**, the **tool set**, and the **step-streaming transport** are
> architectural choices recorded in the accompanying ADR (Step 4) and detailed in
> the plan (Step 3).

### Architecture

Frontend (Vite/React JSON-driven UI engine) triggers an insight run; a backend
surface starts a Temporal workflow; the workflow drives the model in a tool-use
loop via `ModelClient`; tools read Supabase (PostgREST/service role); each step
and the final structured result are surfaced back to the UI. Durability and
retries come from Temporal.

### Data Model

Reads existing tables only — no schema changes:
- `entities` — identity of the entity being summarized.
- `entity_versions` — current version `data` (JSONB) for the entity.
- `entity_facts` + `fact_types` — notable numeric facts and their labels/units.

### API Design

A trigger endpoint ("start an insight for entity X") and a way for the UI to
observe steps + final result. Exact transport (edge function / worker API /
Supabase-backed queue + realtime) is an ADR decision.

Structured result shape (returned by the workflow):
- `summary` — plain-language text.
- `notable_facts` — list of `{label, value, unit}` drawn from real data.
- `data_completeness` — one of `full | partial | insufficient`.
- `steps` — ordered `{tool, args, result_preview}` for transparency.

### UI/UX Design

An "Insights" affordance on the entity detail page. On click: a panel shows the
question, then a live-updating list of steps (tool → returned data), then the
final summary + notable facts. A clear error state on failure.

## Implementation Plan

> High-level only; the detailed, critiqued plan is Step 3.

### Phase 1: Backend loop
- [ ] Read-only Supabase tools (`get_entity`, `get_entity_facts`).
- [ ] Temporal workflow/activity running `ModelClient` in a bounded tool-use loop
      with structured output.

### Phase 2: Trigger + transport
- [ ] Frontend→backend trigger and step/result observation (per ADR).

### Phase 3: Frontend
- [ ] Entity-detail "Insights" panel: progressive steps + final answer + errors.

## Testing Strategy

- Unit tests: tools return correct shapes for present/absent data; the tool-use
  loop terminates within a max-rounds bound; structured-output validation.
- Integration test: workflow against a seeded entity via `TestWorkflowEnvironment`.
- Manual E2E: start an insight from the UI, watch steps stream, verify the
  summary matches seeded data and the "insufficient data" path.

## Rollout Plan

Ships behind the local/dev stack only (experiment repo). Delivered as a single
reviewable PR against `main`. No production deployment.

## Metrics & Success Criteria

- End-to-end run completes from the UI in under ~10s for a seeded entity.
- 100% of returned `notable_facts` values trace to real Supabase rows (no
  fabrication) in manual review.
- Every run renders its steps in the UI; failures render an actionable error.

## Dependencies

- Model-integration layer: `temporal/src/agents/model_client.py` (Step 1, done).
- Azure OpenAI deployment `gpt-5-mini` reachable (Entra-first, key fallback).
- Local Supabase with the entity schema + at least one seeded entity + facts.
- Running Temporal worker.

## Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Model fabricates facts not in the data | High | Medium | Tools are the only data source; prompt forbids values not returned by tools; `data_completeness` + manual grounding check |
| Reasoning model burns token budget before answering | Medium | Medium | Generous `max_completion_tokens`; bounded tool rounds; surface partial/timeout state |
| FE→BE trigger/transport adds complexity | Medium | Medium | Decide the simplest viable option in the ADR; keep phase 2 thin |
| Entra RBAC still not granted at demo time | Low | Medium | Key fallback already verified working end-to-end |

## Open Questions

- [ ] Trigger/transport: Supabase-backed request row + realtime, a worker HTTP
      endpoint, or a Supabase edge function? (ADR)
- [ ] Should "insufficient data" still return a summary, or refuse? (Proposed:
      return a brief summary that names the gap.)
- [ ] How much of each tool result to preview in the UI steps.

## References

- Spec template: `Dev day 1 & 2 resources/SPEC_TEMPLATE.md`
- Model client: `temporal/src/agents/model_client.py`
- ADR (workflow shape + model hosting): to be written in Step 4
- Reference patterns: `wynne-lvl-3` operations-factory agents; spec-kit
  spec/plan discipline; AI-DLC human-gated stages
