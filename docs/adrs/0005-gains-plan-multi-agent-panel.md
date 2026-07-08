# ADR-0005: Gains Plan — multi-agent panel (parallel specialists → synthesizer)

**Status:** Accepted
**Date:** 2026-07-08
**Deciders:** Patrik Alexits (direction), Claude (plumbing)
**Technical Story:** Gains Check "Plan" step — the result must be a collaboration of agents, not one call

## Context

The Gains Check wizard gained a 5th step: after the verdict, the user picks a goal
(recomposition / weight-loss / build-muscle / get-lean / free-text) and gets a starter plan. The
explicit requirement was that this result be **agentic — a collaboration of multiple agents /
sub-agents that give a research-based result**, not a single LLM call dressed up as a plan.

Two tensions to resolve:
1. **Genuine collaboration vs a single call.** One `submit_plan` call is simplest but is not what
   was asked for and reads as one model's opinion, not a panel.
2. **"Research-based" vs hallucinated links.** Models happily invent authoritative-looking URLs.
   A plan that cites dead or fake links is worse than one with none.

## Decision

Implement the plan as a **multi-agent panel** in `GainsPlanWorkflow` (own `gains_plans` feature
slice: table + workflow + `finalize_plan` + poller/worker wiring, same Supabase-substrate pattern
as the check — see [ADR-0001](./0001-entity-insights-workflow-and-model-hosting.md)).

1. **Fan out N specialist agents IN PARALLEL** (`asyncio.gather` over `model_chat` activities): a
   sports-nutrition dietitian, a strength & conditioning coach, and a habits/recovery coach. Each
   is a forced `submit_advice` call, told to ground its advice in established evidence and given a
   curated reference list. Wall-clock ≈ the slowest single agent, not the sum.
2. **A head-coach agent synthesizes** the panel's advice into one cohesive plan via a forced
   `submit_plan` call (summary, calorie/protein/training targets, weekly steps, resource links).
3. **Links are constrained in code:** the model may only choose `resource_urls` from a curated,
   link-verified `PLAN_RESOURCES` list; the workflow resolves the model's choices against it and
   drops anything not on the list. No invented URLs can reach the user.
4. The result carries a `panel` array (each agent's headline + points) so the collaboration is
   **visible** in the UI ("how this was made").

## Consequences

### Positive
- A real collaboration: three independent specialist perspectives, then a synthesis — matches the
  product intent and reads as a panel, not one voice.
- **Research-grounded and link-safe:** advice is evidence-framed and every cited link is real.
- **Parallel fan-out keeps it fast** (~30s end to end for 3 specialists + synthesis).
- Transparent: the per-agent breakdown is surfaced, so users see who contributed what.
- Reuses the existing substrate (poller, `model_chat`, finalize) — no new infrastructure.

### Negative
- **More model calls** (N + 1) → more tokens/cost and higher latency than a single call.
- **Token-budget sensitivity** (see Notes): reasoning models spend the completion budget on
  reasoning before emitting tool args, so each stage needs headroom — advisors run at 2048 and
  the synthesizer (larger input) at 4096. Under-budgeting silently yields empty tool args.
- The curated resource list must be maintained (and its links periodically re-checked).

### Neutral
- Panel roster is a small in-code list (`ADVISORS`); adding/removing a specialist is a one-line change.
- No plan-specific trace table yet; the UI shows a simple "panel is researching" state.

## Options Considered

### Option 1: Single forced `submit_plan` call
- **Pros:** simplest, cheapest, one round.
- **Cons:** not a collaboration; reads as one model's take. Rejected — fails the requirement.

### Option 2: Sequential specialist chain (nutrition → training → habits → synth)
- **Pros:** each agent can see the previous one's output.
- **Cons:** ~4× latency for little gain; specialists don't actually need each other's raw output —
  the synthesizer reconciles them. Rejected in favour of parallel.

### Option 3: Parallel specialist panel + synthesizer (chosen)
- **Pros:** genuine multi-agent collaboration, fast (parallel), synthesis reconciles conflicts.
- **Cons:** N+1 calls; token-budget tuning. Accepted.

### Option 4: Give the panel a live web-search tool for citations
- **Pros:** truly current, model-sourced research.
- **Cons:** external dependency, latency, and reliability/quality risk; harder to keep links safe.
  Deferred — the curated list gives link-safety now; web search can augment it later.

## Related Decisions
- Substrate + `model_chat` from [ADR-0001](./0001-entity-insights-workflow-and-model-hosting.md).
- Sits at the autonomous end of the [ADR-0002](./0002-gains-check-guided-vs-agentic-engine.md)
  reliability↔autonomy dial, but keeps link-safety deterministic (curated list) on purpose.

## Notes
Token headroom is the sharp edge: a forced tool call on a reasoning model returns **empty
arguments** if the completion budget is exhausted by reasoning first. Budget per stage by input
size (advisors 2048, synthesizer 4096). To extend: add specialists to `ADVISORS`, wire a
`web_search` tool for the panel, or add a `plan_events` trace table to stream each agent live like
the check's trace.
