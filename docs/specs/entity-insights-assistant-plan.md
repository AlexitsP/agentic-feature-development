# Entity Insights Assistant — Implementation Plan

**Status:** Draft (for review)
**Spec:** `docs/specs/entity-insights-assistant.md`
**Created:** 2026-07-07

## Chosen approach (proposed)

Use **Supabase as the substrate** and **Temporal as the agentic engine**, so the
browser only ever talks to Supabase (no new HTTP service, no CORS), and the
"show steps as they happen" requirement is served by **Supabase Realtime**.

```
Frontend (entity detail)
  │  1. insert a run row (status=pending) via supabase-js
  ▼
Supabase: insight_runs / insight_steps
  ▲   ▲                         │  2. worker poller claims pending runs
  │   │ 5. Realtime: steps+result│     (status=running) and starts a workflow
  │   └─────────────────────────┼──────────────┐
  │ 4. FE subscribes (Realtime)  ▼              │
  │                     Temporal: EntityInsightWorkflow
  │                              │  3. tool-use loop via ModelClient
  │                              ▼
  │                     Azure OpenAI gpt-5-mini
  │                              │  tool calls
  └───────────── writes steps ── Supabase read tools (get_entity, get_entity_facts)
```

### Workflow shape
`EntityInsightWorkflow(entity_id)` runs a **bounded tool-use loop** (max N rounds):
1. `model_chat` activity → `ModelClient.chat(messages, tools=…)`; returns either
   tool calls or a final structured answer.
2. For each tool call, run the matching read activity; append result to messages;
   `record_step` activity writes a row to `insight_steps`.
3. On final answer, validate against the structured schema, write to
   `insight_runs.result`, set `status=done`. On error/timeout: `status=error`
   with a message.

### Tools (read-only, service-role Supabase)
- `get_entity(entity_id)` → current `entity_versions.data` + `entity_type`.
- `get_entity_facts(entity_id)` → `entity_facts` joined to `fact_types`
  (`label, value, unit`).

### Data (ephemeral, run-scoped — not a saved-insights feature)
Migration adds two tables + Realtime publication:
- `insight_runs(id, entity_id, status, result jsonb, error text, created_at)`
- `insight_steps(id, run_id, seq, tool, args jsonb, result_preview jsonb, created_at)`
RLS: `anon` may `select` (for Realtime) and `insert` into `insight_runs`; writes
to steps/result are service-role only.

## Task breakdown

### Phase 1 — Backend agentic loop
- [ ] `supabase/migrations/<ts>_insight_runs.sql` — tables, RLS, realtime publication.
- [ ] `temporal/src/agents/tools/supabase_tools.py` — `get_entity`, `get_entity_facts` (httpx to PostgREST, service role) + OpenAI tool schemas.
- [ ] `temporal/src/agents/model_client.py` — add `chat(..., tools=...)` support (tool-calls in/out) if not already covered.
- [ ] `temporal/src/workflows/entity_insight.py` — `EntityInsightWorkflow` + activities (`model_chat`, tool activities, `record_step`, `finalize`).
- [ ] Register workflow + activities in `temporal/src/worker.py`.

### Phase 2 — Trigger + transport
- [ ] `temporal/src/runs/poller.py` — claim `status=pending` runs, start the workflow; run alongside the worker.
- [ ] Supabase RPC or direct insert path for the FE to create a run.

### Phase 3 — Frontend
- [ ] `frontend/src/components/engine/insights/EngineInsightsPanel.tsx` — custom engine component: create run, subscribe to `insight_steps` via Realtime, render steps + final answer + error.
- [ ] Register it in the component registry; add it to `frontend/src/pages/entity-detail.json`.

### Testing
- [ ] Unit: tools' shapes for present/absent data; loop terminates at max rounds; structured-output validation.
- [ ] Integration: `EntityInsightWorkflow` via `TestWorkflowEnvironment` against a seeded entity (mock model activity).
- [ ] Manual E2E: trigger from UI, watch steps stream, verify grounding + "insufficient data" path + error path.

---

## Self-critique

### Critique (weaknesses in the above)
- **FE engine mismatch.** The UI is a *declarative JSON engine*; a live,
  Realtime-subscribed, stateful panel is inherently imperative. It must be a
  custom React component bridged into the engine registry — more than a JSON
  edit. This is the single biggest effort/risk item and is under-specified above.
- **DB→Temporal bridge via a poller** adds a moving part and polling latency
  (seconds), and a claim race if ever run in parallel (needs an atomic
  `update … where status='pending'`).
- **Two new tables** sit close to the spec's "no persistence" non-goal. Framing
  them as ephemeral run state (no history UI, could be TTL-cleaned) keeps us
  honest, but it is a judgment call worth the ADR.
- **RLS + Realtime for `anon`.** Letting `anon` insert runs and select steps is
  fine for a local experiment but is a real security surface; must be stated, not
  slipped in.

### Alternatives considered
- **B. Worker HTTP endpoint + SSE.** FE → FastAPI on the worker → start workflow;
  stream steps via SSE. No DB tables, no poller. Cost: a new exposed service +
  CORS + a worker port; streaming code is more bespoke than Realtime. *Rejected
  for now* — more infra than the Supabase-native path, less in-grain.
- **C. Edge Function runs the loop synchronously (no Temporal).** Simplest, but
  throws away Temporal/durability and the very "workflow shape" the ADR is meant
  to capture. *Rejected* — defeats a goal.
- **A (chosen).** Best fit for the stack and the streaming UX; concentrated risk
  in the FE component and the poller bridge.

### Gaps / open questions to resolve before/at ADR
- [ ] Does `ModelClient.chat` already need tool-calling plumbing built out? (Yes —
      Step 1 shipped plain `chat`; tool-calls are new work. Call this out.)
- [ ] Poller vs. Postgres `pg_net` webhook vs. Temporal Schedule for the trigger —
      pick the simplest that's reliable locally (proposed: poller).
- [ ] Exact structured-output enforcement (OpenAI `response_format`/JSON schema
      vs. Pydantic-validate-and-retry) for `gpt-5-mini`.
- [ ] Realtime publication + RLS specifics for the two tables.
- [ ] How much tool-result to store in `result_preview` (size/PII bound).

### Recommendation
Proceed with **Approach A**, but treat the **frontend Realtime panel** and the
**poller bridge** as the two highest-risk tasks and build a thin backend slice
(Phase 1) first to de-risk the model tool-use loop before wiring transport/UI.
Record the workflow shape + trigger choice + model-hosting/auth in the ADR
(Step 4).
