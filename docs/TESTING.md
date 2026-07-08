# Testing Manifesto

How we test **AlpacAI**. The binding decision is
[ADR-0003](./adrs/0003-testing-strategy.md); this document is the practical manifesto.
Per-feature testing rules live in each library's `MANIFESTO.md`.

## Principles

1. **Test the orchestration and the pure logic — not the model.** The LLM is mocked; we assert
   what our code does with its output, never the model's wording.
2. **Deterministic, fast, isolated.** No network, no live Supabase, no real Azure in the test
   suite. Same input → same output.
3. **A regression test is mandatory after a bug** — especially bugs CI didn't catch (see
   "What CI can't reach").
4. **CI fails loud if the suite disappears** (ADR-0003): the Temporal job errors if no
   `test_*.py` exist, so a green "tests" check can never mean "zero assertions".
5. **Confidence is unit-testable and always tested** — `score_confidence` is a pure function
   (ADR-0009); every feature asserts its tiers.

## The layers

```
        live RLS checks (manual, rolled-back tx) — auth/ownership
      Temporal workflow tests (TestWorkflowEnvironment, mocked activities)
    pure unit tests (kernel + each feature's tools/result-builder)  ← the bulk
  frontend: eslint + vite build (type/compile safety)
```

### 1. Pure unit tests (Python, the bulk)
`temporal/tests/test_*.py`. Cover the kernel (`test_confidence.py`, `test_sources.py`,
`test_registry.py`) and each feature's pure surface (result builder, input completeness,
source-allowlist dropping, manifest wiring). Fast, no I/O.

### 2. Temporal workflow tests
Real workflow execution via `temporalio.testing.WorkflowEnvironment.start_time_skipping()`
with **stubbed activities** (the mocked `model_chat` returns canned tool-calls). Asserts the
orchestration: forced tool choice, nudge-then-submit, max-rounds fallback, parallel panel →
synthesis, `done`/`error` finalization (generic error message per SEC-5). Pattern to copy:
`temporal/tests/test_program_evaluator.py` / `test_study_planner.py`.

> Tip for panels: mock `model_chat` to branch on the **forced tool name** (`tool_choice`), so
> parallel advisor calls are order-independent.

### 3. Frontend
CI runs `npm run lint` + `npm run build`. The build is the type/compile gate (esbuild). There
is **no** frontend unit/e2e runner yet — a known gap (see "Gaps"). New deps must update
`package-lock.json` or `npm ci` fails.

### 4. Live RLS / auth checks (not in CI)
RLS and auth behavior can't be reached by pytest (no DB in CI). Verify **live in a rolled-back
transaction** so the running DB is untouched — apply the migration + policies inside
`BEGIN … ROLLBACK`, then assert: `anon` is `permission denied`; an authenticated insert
captures `auth.uid()`; user A cannot read user B's rows. (This is how ADR-0007 and the Study
Planner's owner-scoping were verified.)

## Running

```bash
# Backend (from temporal/)
pip install -e ".[dev]" && python -m pytest tests -v

# Frontend (from frontend/)
npm run lint && npm run build

# End-to-end sanity (needs the running stack): insert a pending row, poll for done
# e.g. POST /rest/v1/<feature_table> {status:pending} → GET ...?id=eq.<id> until status=done
```

## Verify end-to-end before shipping

Per PLAYBOOK, a feature is "done" only when a run goes **pending → done** against the live
stack (insert a row, watch the trace, confirm the result + confidence). CI green ≠ works.
Running the app for real has repeatedly caught latent bugs CI could not (a PostgREST
`limit`+`order`-on-PATCH rejection; a `DEFAULT auth.uid()` skipped by `ADD COLUMN IF NOT
EXISTS`). See "What CI can't reach".

## What CI can't reach (verify manually)

- **The poller loop** against a live PostgREST (claim semantics).
- **RLS / auth** behavior (owner scoping, anon denial) — use the rolled-back-tx check.
- **A real model call** and the true confidence tier on live data.
- **Migrations applied to a live DB** — CI never runs them.

## Gaps (tracked)

- No frontend unit/component/e2e tests (only lint+build). Adding a runner (Vitest/Playwright)
  is the top testing gap.
- No coverage gating.
