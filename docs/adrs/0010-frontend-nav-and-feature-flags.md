# ADR-0010: Frontend navigation + env-driven feature flags

- **Status:** Accepted
- **Date:** 2026-07-08
- **Deciders:** Patrik Alexits (direction), Claude (proposal + implementation)
- **Supersedes / Superseded by:** —

## Context

Features are route-based plug-ins (ADR-0008). With more than one, users need to move between
them, not just the `/` launcher, and operators want to toggle features without editing code. The
frontend already **lazy-loads** each route — `vite.config.ts` sets
`TanStackRouterVite({ autoCodeSplitting: true })`, so the build emits per-route chunks
(`evaluate-*.js`, `plan-*.js`), and `main.tsx` sets `defaultPreload: 'intent'`. But the launcher
used `<a href>` (full page reload — defeats the SPA + preload), and `enabled` was a compile-time
constant with no toggle path.

## Decision

1. **Registry-driven navigation.** Render a header nav in the app shell (`__root.tsx`) from
   `enabledFeatures()`, and use TanStack **`<Link>`** in the nav and launcher (instead of
   `<a href>`) so navigation is client-side, preloads on intent, and uses the already-split lazy
   chunks.
2. **Env-driven feature flags.** A comma-separated allowlist env var toggles features without code
   edits — `VITE_ENABLED_FEATURES` (frontend) and `FEATURES_ENABLED` (worker). If unset, each
   manifest's built-in `enabled` applies. A shared pure helper (`apply_feature_flags` in the kernel;
   `enabledFeatures()` on the frontend) does the filtering, so semantics are testable and consistent
   across FE and BE.

## Consequences

- **Easier:** a nav entry appears automatically per plug-in; instant client-side navigation over the
  lazy chunks; ops can enable/disable features via env with no code change.
- FE and BE share the same allowlist semantics (one mental model).
- **Constrained:** env flags are read at build/start time — the frontend bakes `VITE_*` at build,
  the worker reads env at process start — so toggling is not runtime-hot. A remote config table is a
  future option if hot toggling is ever needed.
- The `enabled=false` default still marks a feature "not ready" when no allowlist is set.

## Alternatives considered

- **Keep `<a href>` + launcher only:** full reloads, no preload, degrades as features grow. Rejected.
- **Runtime remote feature flags (config table/service):** heavier; unnecessary for an internal
  experiment. Env flags are the pragmatic middle and can be superseded by remote flags later.
- **Hardcoded nav:** duplicates the registry and drifts. Registry-driven is single-source.

## Evidence

- Lazy loading already present: `frontend/vite.config.ts` (`autoCodeSplitting: true`); build emits
  `dist/assets/evaluate-*.js`, `plan-*.js`. Preload: `frontend/src/main.tsx` (`defaultPreload: 'intent'`).
- Implementation: `apply_feature_flags` in `temporal/src/kernel/registry.py`, used by
  `temporal/src/features/registry.py` (`FEATURES_ENABLED`); `frontend/src/features/registry.ts`
  (`VITE_ENABLED_FEATURES`); header nav + `<Link>` in `frontend/src/routes/__root.tsx` and the launcher.
- Plug-in registry: ADR-0008.
