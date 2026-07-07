# ADR-0004: Deployment posture — local-only for now

**Status:** Accepted
**Date:** 2026-07-07
**Deciders:** Patrik Alexits (direction), Claude (plumbing)
**Technical Story:** Whether to host the app for a shareable link

## Context

A shareable public link was requested. But this app is a **multi-service, stateful backend**,
not a static site: a hosted link means running the frontend **plus** a Temporal server + its
Postgres + the Python worker + a Supabase instance (currently the dev-oriented CLI), with a
real secrets store (Azure OpenAI key, Azure Speech key, Giphy key, Supabase service-role key —
the last must never reach the browser) and a real ~$/day cost while it runs.

Two hard constraints applied: hosting needs the **operator's Azure subscription** and an
interactive `az login` (which the agent cannot perform), and the repo is an explicit
**temporary experiment**. The template's `deploy-*.yml` / AKS-Helm workflows target a cluster,
registry, Helm values, and secrets this fork never configured (hence disabled) — so there is no
turnkey path already wired.

After weighing options, the operator chose **not to deploy now** and to keep the app local.

## Decision

**Remain local-only.** The app runs on the operator's machine (Rancher Desktop) at
`localhost:3000`; it is **not hosted anywhere**. No cloud resources are provisioned; the
template's AKS/Helm deploy workflows stay **disabled**.

If deployment is revisited, the **intended path is Azure Container Apps + Supabase Cloud**:
frontend + Temporal + worker on Container Apps, Supabase moved to hosted Supabase Cloud (so we
don't self-host the DB stack), secrets in the platform's secret store, and the anon key (only)
in the browser. This is recorded as the direction, **not** an accepted build.

## Consequences

### Positive
- **Zero cloud cost and zero new attack surface** — no public Supabase/Temporal, no exposed
  service-role key, no secrets in a hosted environment.
- Nothing to tear down or forget-and-get-billed-for; matches the "temporary experiment" nature.

### Negative
- **No shareable link** — the app can only be seen by running the stack locally. Sharing means
  a screen-share or reproducing the local setup (see `ONBOARDING.md`).
- The deployment path is unexercised, so a future deploy is net-new work, not a button press.

### Neutral
- Everything needed to run is already documented (onboarding + architecture); hosting is an
  additive step, not a rewrite.

## Options Considered

### Option 1: Azure Container Apps + Supabase Cloud
- **Pros:** managed, real HTTPS link, no self-hosted DB stack; the sensible target if we host.
- **Cons:** needs the operator's subscription + `az login` + ongoing cost + secrets wiring.
  Recorded as the intended direction, not built.

### Option 2: Single Azure VM (docker compose)
- **Pros:** fastest lift-and-shift; mirrors local; cheapest.
- **Cons:** least secure (public Supabase/Temporal, TLS to sort out); a snowflake VM.

### Option 3: AKS via the template Helm charts
- **Cons:** heaviest; needs cluster/registry/values/secrets none of which exist here; overkill
  for a demo.

### Option 4: Stay local-only (chosen)
- **Pros:** no cost, no risk, no credentials needed; fits the experiment.
- **Cons:** no public link.

## Related Decisions
- The stack topology being deployed (or not) is from
  [ADR-0001](./0001-entity-insights-workflow-and-model-hosting.md).

## Notes
To revisit: supersede this ADR with one that accepts a concrete target, after the operator
confirms subscription, budget, and access. The blocker is organizational (Azure account +
cost), not technical.
