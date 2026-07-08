# CLAUDE.md — agent source of truth for this repo

**This file is the unified, standardized base every agent in this repo loads.** It is committed,
so every teammate's Claude reads the identical version — that is what keeps us standardized. Do
not fork or weaken it in a feature branch; changes go through a normal reviewed PR.

## Activation (governance)

[`docs/PLAYBOOK.md`](docs/PLAYBOOK.md) is **BINDING**, especially its **"Guardrails —
MUST / MUST-NOT"** section. It is the stack-generic procedure for building features here. Load the
relevant part on demand — don't ingest the whole doc every turn:

- **Adding/changing a feature** → read PLAYBOOK **§3** (The Feature Recipe).
- **Debugging environment / provider / orchestration** → read PLAYBOOK **§4** (The Landmine Table).
- **A change touching >1 component, a service, or a security/data/deploy boundary** → check
  [`docs/adrs/`](docs/adrs/) and add an ADR.
- **Getting the stack running** → [`ONBOARDING.md`](ONBOARDING.md).
- **How the system fits together** → [`docs/architecture/product-architecture.md`](docs/architecture/product-architecture.md).

## Non-negotiables (full list in the playbook's Guardrails section)

- Branch off `main`; open a PR; **never reuse a merged branch** (PRs are squash-merged → later
  commits on the old branch are orphaned).
- **Never commit `.env`/secrets**; the browser uses the Supabase **anon key only** — never the
  service-role or provider keys.
- New run/trace tables **must** include anon+authenticated grants, the `service_role` grant, and
  the realtime publication — then verify PostgREST access.
- Workflows deterministic; **all** non-determinism in activities; wrap `run()` to finalize `error`.
- **Verify end-to-end** (insert a `pending` row → poll `done`), not on compile/CI-green.
- **Confirm before** provisioning cloud resources or other costly/outward-facing actions.

## This repo's facts (so the agent doesn't guess)

- **LLM host:** Azure OpenAI, deployment `gpt-5-mini` (reasoning model → `max_completion_tokens`,
  no `temperature`, force `tool_choice`). Auth `AZURE_OPENAI_AUTH=auto` (Entra-first, API-key
  fallback). SDK pinned `openai>=1.54,<2`. Provider is isolated in `temporal/src/agents/model_client.py`.
- **Supabase:** local CLI. **Ports remapped `543xx → 553xx`** (API `55321`, Studio `55323`) —
  `supabase/config.toml` is authoritative, not README defaults. Keys come from `make supabase-status`.
- **Container runtime:** Rancher Desktop → `docker context use default`. Ad-hoc
  `docker run -v <host>:/app` bind mounts come up **empty** here — use `docker cp` or `USE_DEV=1`.
- **Merge strategy:** squash-merge (hence the never-reuse-a-merged-branch rule).
- **RLS posture:** the `anon` insert/select on run tables is an **experiment default** — tighten to
  owner-scoped RLS for anything real.
- **Deployment:** **local-only** (see [ADR-0004](docs/adrs/0004-deployment-posture-local-only.md)).
  The template's AKS/Helm + factory workflows are disabled.

## Working in parallel (several of us + our agents, one repo)

- **One feature = one vertical slice** (the ~7 files in PLAYBOOK §3) on **your own branch** off
  `main`. Keep PRs small and single-purpose; don't edit another in-flight feature's files.
- **Rebase on `main` before opening/merging** so migration-order and shared-file conflicts surface
  early, not at merge.
- **Shared chokepoint files** — `temporal/src/worker.py` (workflow/activity registration lists),
  `temporal/src/runs/poller.py` (claim loop), and the frontend route registry — are touched by
  every feature. Edits are **additive**: on a conflict, **keep both sides'** registrations/claims.
- **Migrations** are timestamped and ordered; after a rebase confirm ordering still makes sense, and
  **never renumber or edit a merged migration** — add a new one.
- **Namespace per feature:** prefix tables/workflows/task-queue usage/route names by the feature
  (`foo_runs`, `FooWorkflow`, `/foo`) so parallel features don't collide.

---

# Repository conventions

## Project structure
- Docs: repo root (`README.md`, `ONBOARDING.md`, `DATABASE.md`) + `docs/` (`PLAYBOOK.md`,
  `architecture/`, `adrs/`, `specs/`, `_templates/`).
- `supabase/`: `config.toml`, `migrations/*.sql` (timestamped), `seed.sql`.
- `frontend/` (Vite + React + TanStack; JSON UI engine in `src/engine/`; agentic features are
  custom routes in `src/routes/`) and `temporal/` (`src/` — `workflows/`, `activities/`, `agents/`,
  `runs/poller.py`; tests in `tests/`).

## Build / test / dev
- `make up` (`USE_DEV=1 make up` for live-reload) · `make down` · `make reset` · `make logs` ·
  `make supabase-status`.
- `supabase db reset --config supabase/config.toml` — recreate DB + migrations + seed; run before a PR.
- Containers **don't hot-reload** in base compose — rebuild the image after code changes or use `USE_DEV=1`.
- **Tests:** `cd temporal && pip install -e ".[dev]" && python -m pytest tests -v` (unit + Temporal
  workflow tests, mocked activities). Frontend: `cd frontend && npm run lint && npm run build`.
  CI runs both on PRs to `main` and **fails if no tests exist** — don't reintroduce a skip
  ([ADR-0003](docs/adrs/0003-testing-strategy.md)).

## Style
- SQL: snake_case, UUID PKs, `created_at`/`updated_at`, `jsonb` payloads. Migrations
  `YYYYMMDDHHMMSS_description.sql`, idempotent where practical.
- Python (Temporal): workflows deterministic; non-determinism in activities; import pure helpers
  under `with workflow.unsafe.imports_passed_through():`; type opaque activity params `Any`.

## Commits & PRs
- Short imperative subjects with `feat:`/`fix:`/`docs:`/`test:` prefixes, ≤72 chars.
- PR body: purpose, summary of changes (tables/columns/constraints, migration filenames, seed
  impact), and **evidence-based verification** (what you ran + what it showed).

## Logging & security
- Single-line log entries (grep-friendly).
- Never commit secrets. Provider/API keys and the service-role key are **server-side only** (worker
  env); the browser uses the anon key. No hard-coded URLs/credentials in migrations or seeds.
