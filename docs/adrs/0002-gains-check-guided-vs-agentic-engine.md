# ADR-0002: Gains Check — Guided vs Agentic engine toggle

**Status:** Accepted
**Date:** 2026-07-07
**Deciders:** Patrik Alexits (direction), Claude (plumbing)
**Technical Story:** Gains Check demo — how "agentic" the verdict pipeline actually is

## Context

The first Gains Check implementation was described as "agentic," but on inspection it was
**mostly deterministic**: the model made a single **forced** `submit_verdict` call against
pass/fail rules spelled out in the prompt, and everything sensory (GIF, meme quote, rival
legend, voice) was chosen by code from curated data. That is a *pipeline with an LLM in it*,
not an agent — the model made ~one rule-constrained decision and never used a tool.

This is not a flaw: the entertainment-critical choices were deliberately pulled out of the
model's hands so a live demo is reliable (a pass **always** shows a real Ronnie/Arnold GIF, a
quote that matches the GIF, and never dead-ends). But it under-delivers on the point of the
experiment — showing genuine agent behaviour. We need both properties without picking one.

## Decision

Ship **two engines behind a per-run toggle** (`input.mode`, default `guided`):

- **Guided** (`GainsCheckWorkflow._execute`) — unchanged deterministic pipeline: one forced
  `submit_verdict` call; code picks the GIF/quote/legend/voice from curated data.
- **Agentic** (`GainsCheckWorkflow._execute_agentic`) — a genuine reason → search → decide
  loop. The model gets a real `search_gif` tool it chooses when/how to call, `submit_verdict`
  is **not** forced, and nothing overrides it: it judges pass/fail on its own reasoning, picks
  the GIF search terms and URL, picks the rival legend from a roster and writes the
  comparison, writes the headline and spoken line, and chooses the neural-TTS voice style.

The frontend exposes the toggle with an on-page explainer of each engine, badges the verdict
(`🎛️ Guided` / `🤖 Agentic`), and labels the legend as the "coach's pick" in agentic mode.
Both engines finalize a fun fallback verdict rather than erroring if the model never submits.

## Consequences

### Positive
- Demonstrates the reliability↔autonomy spectrum **side by side** on identical inputs.
- Guided stays the safe default for live demos; Agentic shows a real tool-use trajectory
  (verified: 2–3 model rounds with model-authored GIF searches, model-picked legends with
  lean-mass reasoning, model-written headlines, model-chosen voice).
- No new infrastructure — same workflow, activities, tables, and trace stepper serve both.

### Negative
- Agentic can produce **off-brand output** (an odd GIF, a strange rival, an unexpected verdict)
  — the honest price of autonomy, and the reason Guided is the default.
- Two code paths in one workflow to maintain; the agentic path appends tool-result messages
  and must keep the loop/`tool_choice` contract correct.
- Legend stats in agentic mode are looked up from the roster by (fuzzy) name — a model typo in
  the name degrades the comparison table to blanks.

### Neutral
- `result.mode` distinguishes the paths downstream; `gains_events` shows the extra rounds, so
  the difference is visible in the UI trace.

## Options Considered

### Option 1: Guided only (status quo)
- **Pros:** maximally reliable and cheap; every pass on-brand.
- **Cons:** not genuinely agentic — the point of the experiment is lost.

### Option 2: Agentic only (replace guided)
- **Pros:** real agent behaviour; simpler mental model (one path).
- **Cons:** unreliable for a live demo; off-brand GIFs/verdicts; loses the guaranteed
  Ronnie/Arnold-on-a-pass property the user explicitly asked for.

### Option 3: Both, behind a toggle (chosen)
- **Pros:** keeps the reliable default *and* demonstrates true autonomy; lets viewers compare.
- **Cons:** two paths to maintain (accepted — they share ~everything but the decision layer).

## Related Decisions
- Builds on [ADR-0001](./0001-entity-insights-workflow-and-model-hosting.md) (Supabase-substrate +
  Temporal shape, `model_chat` activity, Azure OpenAI hosting) — both engines reuse it.

## Notes
The agentic system prompt gives the model the legend roster and the allowed voice styles but no
pass/fail formula. If reliability of the agentic path needs tightening later, prefer prompt
constraints over re-introducing code overrides — the whole point is that the model decides.
