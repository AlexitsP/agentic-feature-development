# ADR-0006: Trim to a Gains-only minimal repo

**Status:** Accepted
**Date:** 2026-07-08
**Deciders:** Patrik Alexits (direction), Claude (plumbing)
**Technical Story:** Strip the template scaffold down to just the app we ship

## Context

The repo began as an export of a general template that shipped far more than the app we actually
built: a JSON-driven UI engine with demo pages + a sidebar, an Entity Insights feature, example
workflows, and a large GitHub "software factory" (agents, tools, dashboards, deploy/pipeline
workflows). Once **Gains Check** became the product, all of that was dead weight — extra surface to
read, maintain, and reason about that has nothing to do with the app.

## Decision

Trim to a **Gains-only minimal repo**. Keep exactly what the app needs; delete the rest.

**Kept:** Gains Check (check + multi-agent plan) — `gains_check.py`, `gains_plan.py`,
`activities/gains.py`, `activities/model.py` (the relocated generic `model_chat`),
`agents/model_client.py`, `agents/tools/gains_tools.py`, the `runs/poller.py` bridge; the four
`gains_*` migrations; the Vite/React frontend reduced to a minimal shell + the `/gains` route
(`/` redirects there); `pr-validation.yml` (the CI gate); and the docs + reuse kit.

**Removed:** the JSON UI engine, demo pages/registry/components and the sidebar; the Entity
Insights feature (`entity_insight.py`, `insights.py`, `supabase_tools.py`, the entity/insight
migrations + seed); the example workflow + `supabase_core`/`notifications` activities; the entire
`.github` factory (agents, tools, e2e-dashboard, scripts, `factory.yml`, `copilot-instructions`,
CODEOWNERS, and all non-`pr-validation` workflows); and the template's entity-model root docs.

**Key move:** the generic `model_chat` activity lived in `insights.py` and is reused by both Gains
workflows — it was relocated to `activities/model.py` before `insights.py` was deleted, so nothing
breaks.

## Consequences

### Positive
- The repo is now **only the app**: two workflows, one frontend route, four migrations, one CI job.
  Far easier to read, run, and hand to someone.
- No dead/disabled machinery implying capabilities that aren't wired.
- Faster CI and smaller surface for review.

### Negative
- **Entity Insights is gone.** ADR-0001's *feature* no longer exists in the tree (its model-hosting
  and Supabase-substrate *decisions* still stand — reused by Gains). ADR-0001 and some `docs/`
  pages (architecture, the insights spec) now read as **historical** for a removed feature; kept
  intentionally as record, not current state.
- The template's factory/deploy tooling is deleted here — re-adopting it means pulling it from the
  upstream template again.

### Neutral
- `db reset` now applies only the four `gains_*` migrations with an empty seed.
- The docs + reuse kit (PLAYBOOK, ADRs, ONBOARDING, kit/) are kept — they're the portable value
  and aren't part of the running app.

## Options Considered

- **Keep everything (status quo):** rejected — the non-app scaffold is exactly the "trash" this
  ADR removes.
- **FE declutter only:** rejected — leaves the unused backend, Entity Insights, and the factory.
- **Gains-only minimal repo (chosen):** the app + its essentials + docs; everything else deleted.

## Related Decisions
- Removes the Entity Insights feature from [ADR-0001](./0001-entity-insights-workflow-and-model-hosting.md)
  (its hosting/substrate decisions remain in force via Gains).
- Keeps the multi-agent plan panel from [ADR-0005](./0005-gains-plan-multi-agent-panel.md).

## Notes
To reproduce the stack elsewhere from scratch, use the reuse kit (`kit/` + `docs/PLAYBOOK.md`),
not this trimmed tree — the kit is stack-generic; this repo is now one worked app.
