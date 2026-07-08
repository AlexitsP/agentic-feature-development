# Program Evaluator Manifesto (binding)

Rules for this feature package. They override generic root guidance here.

## File roles

| File | Role | May contain |
|---|---|---|
| `tools.py` | pure logic + declarations | personas, `SOURCES` allowlist, tool schema, `build_evaluation_result`, `compute_input_completeness`. **No I/O, no Temporal.** |
| `workflow.py` | deterministic orchestration | the `@workflow.run` loop; no direct I/O — only `execute_activity`. Imports pure helpers under `workflow.unsafe.imports_passed_through()`. |
| `activities.py` | non-deterministic I/O | Supabase writes (service role). |
| `manifest.py` | wiring | the `FeatureManifest` only. |

## Boundaries / forbidden imports

- ❌ **Never import another feature** (`study_planner`, etc.). Cross-feature data flows through
  run rows, not imports (ADR-0008).
- ❌ No feature logic in the workflow body beyond orchestration; put decisions in `tools.py`.
- ❌ No secrets/URLs invented at runtime — links come only from `SOURCES` via
  `kernel.sources.resolve_sources`.
- ✅ Depend on `kernel.*` and the shared `activities.model.model_chat` only.

## Invariants

- **`requires_auth` MUST match the table's RLS.** This feature is `false` ⟺ `program_evaluations`
  is open-anon. Flipping to owner-scoped means flipping the flag **and** the migration together
  (ADR-0011).
- Confidence comes from `kernel.confidence.score_confidence` over observable signals — **never**
  the model's self-report (ADR-0009).
- Failures finalize a **generic** error message (no raw exception to the anon-readable row — SEC-5).
- Institution types constrained to `university | uas | ph`; invalid → defaults to `university`.

## Testing boundaries

- `build_evaluation_result` / `compute_input_completeness`: **pure unit tests** (tiers, enum
  coercion, invented-source dropping, completeness bounds).
- `EvaluationWorkflow`: `TestWorkflowEnvironment` with a **mocked** `model_chat` (forced tool,
  nudge-then-submit, max-rounds fallback, grounded→done). No live DB/model.
- Owner-scoping is N/A here (open-anon); if flipped, verify RLS live in a rolled-back tx (see
  [TESTING.md](../../../../docs/TESTING.md)).
