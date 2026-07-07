# Repository Guidelines

## Agent Contract (read first)

**Governance:** [`docs/PLAYBOOK.md`](docs/PLAYBOOK.md) is **BINDING**, especially its
**"Guardrails — MUST / MUST-NOT"** section. It is the stack-generic procedure for building
features here. Load the relevant part on demand — don't ingest the whole doc every turn:

- **Adding/changing a feature** → read PLAYBOOK **§3** (The Feature Recipe).
- **Debugging environment / provider / orchestration** → read PLAYBOOK **§4** (The Landmine Table).
- **A change touching more than one component, a service, or a security/data/deploy boundary** →
  check [`docs/adrs/`](docs/adrs/) and add an ADR.
- **Getting the stack running / local gotchas** → [`ONBOARDING.md`](ONBOARDING.md).
- **How the system fits together** → [`docs/architecture/product-architecture.md`](docs/architecture/product-architecture.md).

**Non-negotiables** (full list in the playbook's Guardrails section):
- Branch off `main`; open a PR; **never reuse a merged branch** (PRs are squash-merged, which
  orphans later commits pushed to the old branch).
- **Never commit `.env`/secrets**; the browser uses the Supabase **anon key only** — never the
  service-role or provider keys.
- New run/trace tables **must** include the anon+authenticated grants, the `service_role` grant,
  and the realtime publication — then verify PostgREST access.
- Workflows deterministic; **all** non-determinism in activities; wrap `run()` to finalize `error`.
- **Verify end-to-end** (insert a `pending` row → poll `done`), not on compile/CI-green.
- **Confirm before** provisioning cloud resources or other costly/outward-facing actions
  (this repo is **local-only** — see [ADR-0004](docs/adrs/0004-deployment-posture-local-only.md)).

**Local-run gotchas that will cost you an hour** (detail in ONBOARDING / PLAYBOOK §4): this
machine's Docker is **Rancher Desktop** (`docker context use default`), and Supabase ports are
remapped **`543xx → 553xx`** (`config.toml` is authoritative, not the README defaults).

## Project Structure & Module Organization
- Docs: repo root (`README.md`, `ONBOARDING.md`, `DATABASE.md`) plus `docs/` — `PLAYBOOK.md`
  (how to build features), `architecture/`, `adrs/`, `specs/`, and fill-in templates in `_templates/`.
- Supabase assets in `supabase/`: `config.toml` (CLI config), `migrations/*.sql` (ordered by
  timestamp), `seed.sql` (loads after migrations).
- Application code: `frontend/` (Vite + React + TanStack, JSON-driven UI engine under
  `src/engine/`; agentic features are custom routes under `src/routes/`) and `temporal/` (Python
  worker under `src/` — `workflows/`, `activities/`, `agents/`, `runs/poller.py`; tests in `tests/`).
- Keep new domain tables in **new** timestamped migration files — do not edit shipped ones.

## Build, Test, and Development Commands
- `make up` — start the stack (`supabase start` + Temporal + worker + frontend); `USE_DEV=1 make up`
  for live-reload mounts. `make down` / `make reset` / `make logs` / `make supabase-status`.
- `supabase db reset --config supabase/config.toml` — recreate the DB, apply all migrations + seed.
  Run before a PR to keep migrations green.
- Worker/frontend containers **do not hot-reload** in the base compose — rebuild the image
  (`docker compose build <svc>`) after code changes, or use `USE_DEV=1`.

## Coding Style & Naming Conventions
- SQL: snake_case, UUID PKs (`default gen_random_uuid()`), `created_at`/`updated_at`, `jsonb` for
  flexible payloads. Migrations `YYYYMMDDHHMMSS_description.sql`, idempotent where practical
  (`create table if not exists`).
- Python (Temporal): workflows deterministic; non-determinism in activities; import pure helpers
  under `with workflow.unsafe.imports_passed_through():`; type opaque activity params `Any`.

## Testing Guidelines
- **There is an automated suite** (see [ADR-0003](docs/adrs/0003-testing-strategy.md)):
  `cd temporal && pip install -e ".[dev]" && python -m pytest tests -v` — pure-logic unit tests +
  Temporal workflow tests (time-skipping env, mocked activities).
- **CI** (`.github/workflows/pr-validation.yml`) runs the pytest suite + frontend `lint`/`build`
  on PRs to `main`, and **fails if no tests exist** — do not reintroduce a skip.
- Frontend gate: `cd frontend && npm run lint && npm run build`.
- Also run `supabase db reset` to verify migrations/seeds, and smoke each feature end-to-end
  (insert a `pending` row with the service key → poll `done`).

## Logging Guidelines
- **One-line rule:** single-line log entries (grep-friendly). If a `docs/Logging.md` exists,
  follow it instead.

## Commit & Pull Request Guidelines
- Short imperative subjects (`feat:`/`fix:`/`docs:`/`test:` prefixes), ≤72 chars; context in the body.
- PR descriptions: purpose, summary of changes (tables/columns/constraints, migration filenames,
  seed impact), and **evidence-based verification** (what you ran, what it showed). Link issues.

## Security & Configuration Tips
- Never commit secrets. Keep provider/API keys and the Supabase service-role key **server-side
  only** (worker env); the browser uses the anon key. Keep prod/local configs separate; no
  hard-coded URLs/credentials in migrations or seeds.
