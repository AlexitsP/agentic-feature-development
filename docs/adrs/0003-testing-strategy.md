# ADR-0003: Testing strategy — unit + Temporal workflow tests, CI fails loud

**Status:** Accepted
**Date:** 2026-07-07
**Deciders:** Patrik Alexits (direction), Claude (plumbing)
**Technical Story:** Turning a decorative "tests" check into a real gate

## Context

The `pr-validation.yml` "Temporal worker tests" job **passed green while running zero
assertions**: `temporal/tests/` held only a `.gitkeep`, and the job's script printed
"skipped — no test files present" and exited 0. Meanwhile `vite build` stood in as the
frontend "test." So CI signalled "tested" when it verified only that the code **compiled and
linted** — a verdict that always returns fail, a broken legend match, or a dead GIF-fallback
URL would all have passed clean. All real verification to date was ad-hoc scripts driving the
live stack, which are uncommitted, need real API keys, and guard nothing against regressions.

The logic most worth testing is deterministic and has already produced real bugs — e.g. the
legend-matching metric that collapsed every user onto the leanest legend, and the Temporal
`tool_choice` serialization error.

## Decision

Add a real suite and make CI honest:

1. **Backend unit tests** (`temporal/tests/test_gains_tools.py`, pytest, no network/server) for
   the pure logic: `pick_closest_legend` (incl. the weight-vs-body-fat regression),
   `legend_by_name`, `get_persona`, `shame_query`, `fallback_gif_url`, `search_gif` fallback
   layering (mocked `httpx`), and `fetch_verdict_gif` curated fallback.
2. **Temporal workflow tests** (`temporal/tests/test_gains_workflow.py`) using the
   **time-skipping `WorkflowEnvironment`** with **mocked activities**. They assert the
   *orchestration*, not the model: guided meme-quote override, `not_tracking`/`slacking`
   default headlines, the **forced** `submit_verdict` tool choice, the nudge-then-submit path,
   the max-rounds fun fallback (finalizes `done`, never a bare error), and the agentic
   reason→search→decide loop (auto tool choice, no override, legend lookup + GIF fallback).
3. **CI fails loud:** the Temporal job runs `pytest` and **exits 1 if no `test_*.py` exist**,
   instead of silently skipping.
4. Tooling: add `pytest-asyncio` + `asyncio_mode=auto` to `temporal/pyproject.toml`.

Scope for now is **backend unit + workflow** — the highest value per effort, needs no browser
or deployed environment. Frontend unit tests and committed Playwright E2E are explicitly
deferred (see Options / Notes).

## Consequences

### Positive
- The "Temporal worker tests" check now actually tests (28 tests, ~8s) and **fails on a
  regression** — proven in CI on the introducing PR.
- Workflow branching is covered without a real model, network, or Supabase — fast and
  deterministic. The `tool_choice`/serialization class of bug is now caught automatically.
- Mocked activities double as executable documentation of each workflow's contract.

### Negative
- Local runs on this **Windows/Rancher** box are awkward: `docker run -v <host>:/app` bind
  mounts come up empty, so running the suite in Docker needs `docker cp` into a built image
  (documented in `ONBOARDING.md`). CI (Linux) is unaffected.
- The time-skipping test server downloads a binary on first run (needs internet; fine in CI).
- Coverage is backend-only: the frontend and the true BE→FE path are still unguarded by CI.

### Neutral
- `result`/trace payloads are JSON, so tests assert on dict shape, not typed models.

## Options Considered

### Option 1: No tests / keep the skip (status quo)
- **Cons:** the check lies; regressions ship silently. Rejected.

### Option 2: E2E-only (Playwright against the local stack)
- **Pros:** exercises the real BE→FE path.
- **Cons:** slow, flaky, needs the whole stack + real keys in CI; poor at pinning down *unit*
  logic like the matching metric. Deferred, not chosen as the first tier.

### Option 3: Backend unit + Temporal workflow tests (chosen)
- **Pros:** fast, hermetic, targets where real bugs have appeared; no browser/deploy needed.
- **Cons:** doesn't cover the frontend or the integrated path (accepted for now).

## Related Decisions
- Tests the workflow shape from [ADR-0001](./0001-entity-insights-workflow-and-model-hosting.md)
  and both engines from [ADR-0002](./0002-gains-check-guided-vs-agentic-engine.md).

## Notes
Next tiers when wanted: frontend unit tests (vitest + testing-library for `verdictTheme`, mode/
persona threading) and a committed Playwright smoke against the local stack (one "enter numbers
→ verdict renders" flow per engine) so CI exercises BE→FE end to end.
