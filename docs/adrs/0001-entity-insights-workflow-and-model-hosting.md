# ADR-0001: Entity Insights workflow shape and model hosting

**Status:** Accepted
**Date:** 2026-07-07
**Deciders:** Patrik Alexits (direction), Claude (plumbing)
**Technical Story:** Entity Insights Assistant — `docs/specs/entity-insights-assistant.md`

## Context

We are building the first agentic feature on this stack (Supabase + Temporal +
Vite/React) and need to lock two architectural choices:

1. **Model hosting & auth** — how the app reaches a deployed LLM.
2. **Agentic workflow shape** — how a user action in the frontend drives a
   durable, tool-using model loop over Supabase data and streams progress back.

Constraints: this is a local experiment repo on Windows/Rancher; the frontend is
a declarative JSON UI engine; Supabase Realtime is available; we want an
end-to-end, defensible demonstration, not production hardening.

## Decision

**1. Model hosting = Azure OpenAI**, deployment `gpt-5-mini`
(`travel-stopper-openai`, Switzerland North). The client is
`temporal/src/agents/model_client.py`.

**2. Auth = Entra-first with API-key fallback** (`AZURE_OPENAI_AUTH=auto`): try
`DefaultAzureCredential`; on an auth failure or missing credential, fall back to
the API key if configured, and remember it. This works keyless where the caller
holds the `Cognitive Services OpenAI User` role, and via key otherwise — same
code, no branch at the call site.

**3. Workflow shape = Supabase substrate + Temporal (Approach A).** The frontend
talks only to Supabase. It inserts a run row; a worker-side poller claims pending
runs and starts `EntityInsightWorkflow`, which runs a bounded tool-use loop
(`model_chat` ↔ read-only Supabase tools), records each step, and writes a
validated structured result. The UI subscribes to step/result rows via Supabase
Realtime.

## Consequences

### Positive
- Browser ↔ Supabase only: no new HTTP service, no CORS, no exposed worker port.
- Step-streaming reuses Supabase Realtime — clean progressive UI.
- Temporal gives durability, retries, and a clear place for the agentic loop.
- Dual auth removes the RBAC blocker without abandoning the keyless goal.

### Negative
- The live panel must be a **custom React component** bridged into the JSON
  engine — the largest single effort item.
- A **DB→Temporal poller** adds a moving part and seconds of trigger latency;
  claiming must be atomic to avoid races.
- Two new **ephemeral run tables** brush against the spec's "no persistence"
  non-goal (mitigated: run-scoped, no history UI).
- `anon` insert/select on the run tables is a real (accepted, local-only)
  security surface.

### Neutral
- `ModelClient` gains tool-calling plumbing (new since Step 1's plain `chat`).
- Structured output enforced by JSON schema / Pydantic-validate-and-retry.

## Options Considered

### Model hosting
### Option 1: Azure OpenAI (chosen)
- **Pros:** `az` CLI present; repo already had `azure-openai.ts`; verified working
  (HTTP 200 from `gpt-5-mini`); matches wynne-lvl-3's proven pattern.
- **Cons:** Entra data-plane role not yet granted to the operator (key fallback
  covers it).

### Option 2: AWS Bedrock
- **Pros:** viable Claude hosting.
- **Cons:** no `aws` CLI or creds here; no existing code; more from-scratch.

### Auth
### Option 1: Entra-first + key fallback (auto) (chosen)
- **Pros:** keyless when RBAC allows; never blocked; one code path.
- **Cons:** one wasted Entra attempt per client when only the key works.

### Option 2: Key only / Option 3: Entra only
- **Cons:** key-only stores a long-lived secret; Entra-only is blocked today by
  missing `Cognitive Services OpenAI User` role.

### Workflow shape
### Option A: Supabase substrate + Temporal (chosen)
- **Pros:** in-grain with the stack; Realtime streaming; durable loop.
- **Cons:** custom FE component, poller bridge, two tables.

### Option B: Worker HTTP + SSE
- **Pros:** no tables/poller.
- **Cons:** new exposed service, CORS, bespoke streaming.

### Option C: Edge function, no Temporal
- **Pros:** simplest.
- **Cons:** abandons Temporal/durability and the workflow-shape goal.

## Related Decisions

- Supersedes the unwired `.github/tools/shared/src/azure-openai.ts` stub as the
  model entry point.
- Depends on the port remap for local Supabase (see project setup notes).

## Notes

If the `Cognitive Services OpenAI User` role is later granted to the operator (or
via a group), no code changes are needed — `auto` mode will use Entra and stop
falling back to the key. Set `AZURE_OPENAI_AUTH=key` in a containerized worker
that has no Entra credential to skip the wasted Entra attempt.
