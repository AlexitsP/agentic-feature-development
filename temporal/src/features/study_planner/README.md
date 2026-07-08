# study_planner

The **Study Planner** feature (`type:feature`) — route `/plan`. Given a goal + situation, a
**multi-agent panel** (a curriculum/pathway advisor and a study-skills coach) runs **in
parallel**; a head advisor **synthesizes** one study plan — summary, weekly steps, a
**how-to-study** section, and official-source links — with a kernel confidence badge.

Posture: **owner-scoped** (`requires_auth=true`; `study_plans` uses `auth.uid() = user_id` RLS
from creation, ADR-0007). The frontend ensures an anonymous Supabase Auth session before use
(ADR-0011).

## Structure

- `manifest.py` — `FeatureManifest` (workflow, activities, `study_plans` claim, `/plan`, `requires_auth=True`).
- `workflow.py` — `StudyPlanWorkflow` (deterministic; parallel panel → forced `submit_plan` synthesis; generic-error finalize).
- `activities.py` — `finalize_plan` + `record_plan_event` (service-role writes).
- `tools.py` — `ADVISORS` panel, personas, `SOURCES` allowlist, `submit_advice`/`submit_plan` schemas, pure `build_plan_result`.
- Migration: `supabase/migrations/20260708200000_study_plans.sql` (owner-scoped).

## Governing doc

- [`MANIFESTO.md`](./MANIFESTO.md) — binding file roles, boundaries, forbidden imports, testing.

## Running unit tests

```bash
cd temporal && python -m pytest tests/test_study_planner.py -v
```
