# ADR-0011: Per-feature auth gate (`requiresAuth`)

- **Status:** Accepted
- **Date:** 2026-07-08
- **Deciders:** Patrik Alexits (direction), Claude (proposal + implementation)
- **Supersedes / Superseded by:** —

## Context

Features are plug-ins (ADR-0008); owner-scoped RLS + Supabase Auth exist (ADR-0007). But
whether a feature needs an authenticated session was **hardcoded per route** — `plan.tsx`
called `ensureSession()`, `evaluate.tsx` did not — so the auth gate was implicit, inconsistent,
and not toggleable. Some features are fine anonymous during the local experiment; others (with
owner-scoped tables) must have a session. That distinction should be a declared, toggleable
property of each feature, and it is the right long-term model as more plug-ins are added.

## Decision

Add a per-feature **`requiresAuth`** flag to the feature manifest (frontend `requiresAuth`,
backend `requires_auth`). The frontend ensures a Supabase Auth session before using a feature
**iff** its `requiresAuth` is true (via a shared `ensureSessionIf(required)` helper); routes read
the flag from the registry rather than hardcoding it.

**Contract:** `requiresAuth` **must match the feature's DB RLS posture** — an owner-scoped table
(ADR-0007) ⟺ `requiresAuth = true`; an open-anon table ⟺ `requiresAuth = false`. The flag drives
the frontend; RLS is the enforcement; a mismatch means broken inserts (anon insert into an
owner-scoped table is rejected), so the two are changed together.

Initial values: `program_evaluator = false` (open-anon; runs on the local experiment without
auth), `study_planner = true` (owner-scoped from creation).

## Consequences

- **Toggleable, declarative per-feature gating** — flip one flag (plus the matching migration) to
  gate or ungate a feature; no per-route auth code.
- New features declare their auth posture up front, next to their `enabled`/flags.
- **New obligation:** keep `requiresAuth` and the table's RLS consistent. This is the single most
  likely footgun; treat them as one change.
- **Known divergence to reconcile:** ADR-0007 (#37) added owner-scoped RLS to `program_evaluations`
  as a standing migration, while the running experiment keeps it open (the migration was not applied
  live). Per ADR-0004/0007, owner-scoping is the **cutover gate** for leaving local scope — so the
  experiment runs `program_evaluator` open (`requiresAuth=false`), and going multi-user means
  flipping it to `true` and taking auth live together. (Whether #37 should be a standing migration
  vs. a cutover-only step is a separate cleanup.)

## Alternatives considered

- **Hardcode `ensureSession` per route (status quo).** Implicit, inconsistent, not toggleable. Rejected.
- **Global auth for the whole app.** Can't run some features open during the local experiment;
  removes the per-feature control the platform is built for. Rejected.
- **Derive `requiresAuth` automatically from RLS.** RLS posture isn't introspectable at build time;
  an explicit declared flag (kept consistent by contract) is simpler and testable. Rejected.

## Evidence

- Backend: `FeatureManifest.requires_auth` in `temporal/src/kernel/registry.py`; set on
  `features/study_planner/manifest.py` (true) and `features/program_evaluator/manifest.py` (false).
- Frontend: `requiresAuth` in `frontend/src/features/registry.ts`; `ensureSessionIf` in
  `frontend/src/data/auth.ts`; routes `evaluate.tsx` / `plan.tsx` call it declaratively.
- Auth mechanism + owner-scoping: ADR-0007. Plug-in registry + flags: ADR-0008, ADR-0010.
