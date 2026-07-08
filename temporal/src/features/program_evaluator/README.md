# program_evaluator

The **Program Evaluator** feature (`type:feature`) — route `/evaluate`. A prospective student
describes their situation; one forced-tool model turn assesses fit and suggests 1–3 Swiss
higher-education study options (field + institution type: University / UAS / PH), grounded in a
curated official-Swiss source allowlist, with a kernel confidence badge (ADR-0009).

Posture: **owner-scoped** (`requires_auth=true`; `program_evaluations` uses `auth.uid() = user_id`
RLS — ADR-0007). The frontend ensures an anonymous Supabase Auth session before inserting, so the
demo still needs no sign-up. See ADR-0011 for the auth-gate contract.

## Structure

- `manifest.py` — `FeatureManifest` (workflow, activities, `program_evaluations` claim, `/evaluate`, flags).
- `workflow.py` — `EvaluationWorkflow` (deterministic; forced `submit_evaluation`; generic-error finalize).
- `activities.py` — `finalize_evaluation` + `record_evaluation_event` (service-role writes).
- `tools.py` — personas, `SOURCES` allowlist, `submit_evaluation` schema, pure `build_evaluation_result`.
- Migration: `supabase/migrations/20260708170000_program_evaluations.sql`.

## Governing doc

- [`MANIFESTO.md`](./MANIFESTO.md) — binding file roles, boundaries, forbidden imports, testing.

## Running unit tests

```bash
cd temporal && python -m pytest tests/test_program_evaluator.py -v
```
