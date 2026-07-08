# CLAUDE.md — agent source of truth for this repo

**This file is the unified, standardized base every agent in this repo loads.** It is committed,
so every teammate's Claude reads the identical version — that is what keeps us standardized. Do
not fork or weaken it in a feature branch; changes go through a normal reviewed PR.

This repo is **"Plan my studies"** — a Swiss higher-education advisor built as a **kernel +
feature-plugin platform** (Supabase + Temporal + Vite/React + Azure OpenAI). Start at
[`docs/Documentation_Index.md`](docs/Documentation_Index.md).

## Activation (governance)

[`docs/PLAYBOOK.md`](docs/PLAYBOOK.md) is **BINDING**, especially its **"Guardrails —
MUST / MUST-NOT"** section. Load the relevant part on demand:

- **Adding/changing a feature** → PLAYBOOK **§3** + the target feature's `MANIFESTO.md`.
- **Debugging environment / provider / orchestration** → PLAYBOOK **§4** (the Landmine Table).
- **A change touching the kernel contract, a service, or a security/data/deploy boundary** →
  check [`docs/adrs/`](docs/adrs/) and add an ADR.
- **Getting the stack running** → [`ONBOARDING.md`](ONBOARDING.md).
- **How the system fits together** → [`docs/architecture/product-architecture.md`](docs/architecture/product-architecture.md).

## Non-negotiables (full list in the playbook's Guardrails section)

- Branch off `main`; open a PR; **never reuse a merged branch** (PRs are squash-merged).
- **Never commit `.env`/secrets**; the browser uses the Supabase **anon key only** — never the
  service-role or provider keys.
- New run/trace tables include the right grants + policies (RLS posture below) and the realtime
  publication — then verify PostgREST access.
- Workflows deterministic; **all** non-determinism in activities; wrap `run()` to finalize a
  **generic** `error` (no raw exception to an anon-readable row — SEC-5).
- **Confidence is computed from observable signals, never the model's self-report** (ADR-0009).
- A feature's **`requires_auth` / `requiresAuth` MUST match its table's RLS** (owner-scoped ⟺
  true; open-anon ⟺ false) — ADR-0011.
- **Verify end-to-end** (insert a `pending` row → poll `done`), not on compile/CI-green.
- **Confirm before** provisioning cloud resources or other costly/outward-facing actions.

## This repo's facts (so the agent doesn't guess)

- **Platform:** kernel (`temporal/src/kernel/` — registry, confidence, sources) + features
  (`temporal/src/features/<name>/`). Features self-register via a `FeatureManifest`; worker,
  poller, and frontend build their lists from the registry (ADR-0008). Frontend mirrors this in
  `frontend/src/features/registry.ts`.
- **LLM host:** Azure OpenAI, deployment `gpt-5-mini` (reasoning model → `max_completion_tokens`,
  no `temperature`, force `tool_choice`). Auth `AZURE_OPENAI_AUTH=auto` (Entra-first, key
  fallback). Provider isolated in `temporal/src/agents/model_client.py` (SDK pinned `openai<2`).
- **Supabase:** local CLI. **Ports are remapped on Windows** — `supabase/config.toml` is
  authoritative (not README defaults); confirm live values with `make supabase-status`.
- **Container runtime:** Rancher Desktop → `docker context use default`. Base-compose containers
  **don't hot-reload** — rebuild the image or use `USE_DEV=1`.
- **Merge strategy:** squash-merge (hence never-reuse-a-merged-branch).
- **Auth / RLS posture:** owner-scoped RLS + Supabase Auth exist (ADR-0007); each feature is
  **open-anon** or **owner-scoped** and declares `requires_auth` to match. Anonymous sign-in is
  enabled for gated features (ADR-0011). Currently: `program_evaluator` open, `study_planner`
  owner-scoped. The worker writes with the service role (bypasses RLS).
- **Feature flags:** `FEATURES_ENABLED` (worker) / `VITE_ENABLED_FEATURES` (frontend) toggle
  features without code edits (ADR-0010).
- **Deployment:** **local-only** ([ADR-0004](docs/adrs/0004-deployment-posture-local-only.md)).
  Hardened Helm charts exist under `charts/app/` but are not deployed.

## Adding / changing a feature (the plug-in model)

- **A feature = one self-contained package** `temporal/src/features/<name>/` (manifest, workflow,
  activities, tools) + its migration + a frontend route + one line in each registry
  (`features/registry.py`, `frontend/src/features/registry.ts`). Read the feature's `MANIFESTO.md`.
- **Adding/removing/toggling a feature touches only its package + the registry line** — the
  worker (`worker.py`) and poller (`poller.py`) are **registry-driven**; do **not** hand-edit
  their bodies per feature. (This replaces the old "shared chokepoint files" rule.)
- **Features depend on the kernel; never on each other** (cross-feature data flows through run
  rows). The kernel never imports a feature. Changing the **kernel contract** is ADR-worthy.
- **Migrations** are timestamped and append-only; after a rebase confirm ordering; **never
  renumber or edit a merged migration** — add a new one. Owner-scoped tables use
  `user_id uuid default auth.uid()` + `auth.uid() = user_id` policies.
- **Namespace per feature:** prefix tables/workflows/route by the feature (`foo`, `FooWorkflow`,
  `/foo`, claim prefix `foo-`).

---

# Repository conventions

## Project structure
- Docs: repo root (`README.md`, `ONBOARDING.md`) + `docs/` (`Documentation_Index.md`, `TECH_STACK.md`,
  `TESTING.md`, `PLAYBOOK.md`, `architecture/`, `adrs/`, `specs/`). Each library has `README.md` + `MANIFESTO.md`.
- `supabase/`: `config.toml`, `migrations/*.sql` (timestamped), `seed.sql`.
- `frontend/`: Vite + React + TanStack Router; `src/features/registry.ts`, `src/routes/`,
  `src/data/`, `src/components/`.
- `temporal/`: `src/kernel/`, `src/features/<name>/`, `src/activities/model.py`,
  `src/agents/model_client.py`, `src/runs/poller.py`, `src/worker.py`; tests in `tests/`.

## Build / test / dev
- `make up` (`USE_DEV=1 make up` for live-reload) · `make down` · `make reset` · `make logs` ·
  `make supabase-status`.
- `supabase db reset --config supabase/config.toml` — recreate DB + migrations + seed.
- **Tests:** `cd temporal && pip install -e ".[dev]" && python -m pytest tests -v`. Frontend:
  `cd frontend && npm run lint && npm run build`. CI runs both and **fails if no tests exist**
  ([ADR-0003](docs/adrs/0003-testing-strategy.md)). RLS/auth is verified **live in a rolled-back
  tx** (not CI) — see [`docs/TESTING.md`](docs/TESTING.md).

## Style
- SQL: snake_case, UUID PKs, `created_at`/`updated_at`, `jsonb` payloads. Migrations
  `YYYYMMDDHHMMSS_description.sql`, idempotent where practical.
- Python (Temporal): workflows deterministic; non-determinism in activities; import pure helpers
  under `with workflow.unsafe.imports_passed_through():`. Keep feature `tools.py` pure (no I/O).
- Kernel package `__init__` stays import-light (feature workflows live under `src/features`, and
  Temporal's sandbox re-imports parent packages — eager heavy imports there trip the sandbox).

## Commits & PRs
- Short imperative subjects with `feat:`/`fix:`/`docs:`/`test:` prefixes, ≤72 chars.
- PR body: purpose, summary of changes, and **evidence-based verification** (what you ran + what
  it showed).

## Logging & security
- Single-line log entries (grep-friendly; the worker emits structured JSON).
- Never commit secrets. Provider/API keys and the service-role key are **server-side only**
  (worker env); the browser uses the anon key. No hard-coded URLs/credentials in migrations/seeds.
