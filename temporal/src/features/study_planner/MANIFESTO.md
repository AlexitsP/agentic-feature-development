# Study Planner Manifesto (binding)

Rules for this feature package. They override generic root guidance here.

## File roles

| File | Role | May contain |
|---|---|---|
| `tools.py` | pure logic + declarations | `ADVISORS`, personas, `SOURCES`, `submit_advice`/`submit_plan` schemas, `build_plan_result`, `compute_input_completeness`. **No I/O, no Temporal.** |
| `workflow.py` | deterministic orchestration | `_execute` (parallel panel via `asyncio.gather` → head-advisor synthesis); no direct I/O — only `execute_activity`. Pure imports under `workflow.unsafe.imports_passed_through()`. |
| `activities.py` | non-deterministic I/O | Supabase writes (service role). |
| `manifest.py` | wiring | the `FeatureManifest` only. |

## Boundaries / forbidden imports

- ❌ **Never import another feature** (`program_evaluator`, etc.). Cross-feature data flows
  through run rows (ADR-0008). Note: this feature owns its **own** `SOURCES`/personas copy on
  purpose — do not reach into another feature's `tools.py` to share them.
- ❌ No feature logic in the workflow body beyond orchestration.
- ❌ No invented links — only `SOURCES` via `kernel.sources.resolve_sources`.
- ✅ Depend on `kernel.*` and `activities.model.model_chat` only.

## Invariants

- **`requires_auth=true` MUST match owner-scoped RLS.** `study_plans` is owner-scoped
  (`user_id default auth.uid()`); the frontend gates `/plan` behind an auth session (ADR-0011).
  These change together.
- The panel is dispatched **in parallel** (`asyncio.gather`); the head advisor's `submit_plan`
  is **forced**. Keep the panel small (2–3) for latency/cost.
- Confidence from `kernel.confidence.score_confidence` over observable signals (ADR-0009).
- Failures finalize a **generic** error (SEC-5). `weekly_steps` capped at 6, `how_to_study` at 4.

## Testing boundaries

- `build_plan_result` / `compute_input_completeness`: **pure unit tests** (tiers, source
  dropping, step caps, completeness).
- `StudyPlanWorkflow`: `TestWorkflowEnvironment` with a **mocked** `model_chat` that branches on
  the forced **tool name** (so the parallel advisor calls are order-independent) → asserts
  panel → synthesis → `done`.
- Owner-scoping (anon denied, `auth.uid()` capture, per-user isolation) is verified **live in a
  rolled-back transaction** — not in CI (see [TESTING.md](../../../../docs/TESTING.md)).
