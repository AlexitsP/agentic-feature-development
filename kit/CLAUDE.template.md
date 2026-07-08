<!--
  Governance base template. Copy to the NEW repo's root as `CLAUDE.md`, fill the
  "Repo facts" block, and delete any guardrail that genuinely doesn't apply.
  Also add a one-line `AGENTS.md` pointing here (so non-Claude tools find it).
  Keep this the ONE full base — do not duplicate its substance elsewhere.
-->
# CLAUDE.md — agent source of truth for <PROJECT>

This committed file is the unified base every agent in this repo loads. It is **BINDING**.

## Activation (governance)

`docs/PLAYBOOK.md` is **BINDING**, especially its **"Guardrails — MUST / MUST-NOT"** section.
Load the relevant part on demand — don't ingest the whole doc every turn:

- **Scaffolding a fresh/empty repo** → PLAYBOOK **Phase 0**.
- **Adding/changing a feature** → PLAYBOOK **§3** (The Feature Recipe).
- **Debugging environment / provider / orchestration** → PLAYBOOK **§4** (The Landmine Table).
- **A change touching >1 component, a service, or a security/data/deploy boundary** → check
  `docs/adrs/` and add an ADR.

## Non-negotiables (full list in the playbook's Guardrails section)

- Branch off `main`; open a PR; **never reuse a merged branch**.
- **Never commit `.env`/secrets**; the browser uses the Supabase **anon key only**.
- New run/trace tables **must** include anon+authenticated grants, the `service_role` grant, and
  the realtime publication — then verify PostgREST access.
- Workflows deterministic; **all** non-determinism in activities; wrap `run()` to finalize `error`.
- **Verify end-to-end** (insert → poll `done`), not on compile/CI-green.
- **Confirm before** provisioning cloud resources or other costly/outward-facing actions.

## Repo facts (FILL ONCE so the agent doesn't guess)

- **LLM host / model / auth:** <e.g. Azure OpenAI `gpt-5-mini`, Entra + key fallback, SDK pin>.
- **Supabase:** <local CLI | cloud>; ports <default | remapped>; keys from <where>.
- **Container runtime:** <Docker Desktop | Rancher `default`>; bind-mount caveats.
- **Merge strategy:** <squash | merge | rebase> (drives the branch-reuse rule).
- **RLS posture for real users:** <owner-scoped | experiment anon default>.
- **Deployment:** <target | local-only — confirm before provisioning>.

## Working in parallel (a team + their agents, one repo)

- One feature = one vertical slice on **your own branch**; small, single-purpose PRs; rebase on
  `main` before merge.
- **Shared chokepoints** (worker registration lists, the poller, the route registry) → **additive**
  edits; on conflict keep **both** sides' registrations/claims.
- Namespace tables/workflows/queues/routes by feature; never renumber/edit a merged migration.

## Conventions

<Fill from PLAYBOOK / your ONBOARDING: build & test commands, SQL/Python style, commit & PR
format (evidence-based verification), single-line logging, and secrets handling — provider/API
keys and the service-role key are server-side only; the browser uses the anon key.>
