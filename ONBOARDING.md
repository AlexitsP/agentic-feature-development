# Onboarding

Welcome to **Plan my studies** — a Swiss higher-education advisor built as a **kernel +
feature-plugin platform**. This page gets you from a fresh clone to a running app and your
first change. For *why* things are shaped this way read the [ADRs](docs/adrs/); for *how the
system fits together* read the [architecture docs](docs/architecture/product-architecture.md);
for the full map read the [Documentation Index](docs/Documentation_Index.md).

---

## Starting a session with your agent (paste this)

Claude Code **auto-loads `CLAUDE.md`** (the repo's governance base). Paste the prompt below at
the start of a session to confirm it loaded and cover any tool that doesn't auto-read it.

**Activation prompt:**
```
Before doing anything in this repo: read CLAUDE.md at the repo root and treat it as
binding. It points to docs/PLAYBOOK.md — the "Guardrails (MUST / MUST-NOT)" there are
binding too.

Confirm you've loaded them by replying with:
  1. the non-negotiable guardrails, one line each, and
  2. this repo's facts (platform/kernel+plugin, LLM host, Supabase + ports,
     container runtime, merge strategy, auth/RLS posture, feature flags, deployment).

Then operate under that governance:
  - a feature = one self-contained temporal/src/features/<name>/ package + migration +
    a route + one registry line; worker/poller are registry-driven — don't hand-edit them;
    read the feature's MANIFESTO.md;
  - branch off main and open a PR; never reuse a merged branch;
  - requires_auth must match the table's RLS; confidence from observable signals only;
  - verify end-to-end (insert → poll done), not on compile/CI-green;
  - a kernel-contract / service / security-data-deploy change → add an ADR.

If you cannot see CLAUDE.md, stop and tell me — do not proceed.
```

**Add a feature:**
```
New feature `<name>`: <one line>. Follow CLAUDE.md + PLAYBOOK §3.
Drop a temporal/src/features/<name>/ package (manifest, workflow, activities, tools),
its migration, a frontend route, and one line in each registry. Decide requires_auth
(open-anon vs owner-scoped, matching the RLS). Verify end-to-end, then open a PR.
```

---

## 1. What this is

A **Supabase + Temporal + Vite/React** platform. A small **kernel** (`temporal/src/kernel/`:
registry, confidence, sources) hosts self-contained **features** (`temporal/src/features/<name>/`).
Today:

- **Program Evaluator** (`/evaluate`) — assesses a prospective student's fit and suggests Swiss
  study options (University / UAS / PH), grounded in official sources, with a confidence badge.
  **Owner-scoped** (the frontend signs in anonymously; no sign-up needed).
- **Study Planner** (`/plan`) — a multi-agent panel drafts a study plan + how-to-study.
  **Owner-scoped** (requires an auth session; the frontend signs in anonymously).

The core pattern: **the browser only ever talks to Supabase.** It inserts a `pending` row; a
worker-side poller claims it and starts the feature's Temporal workflow; the workflow calls the
model in an activity, computes a confidence badge, and streams the result + a live trace back
via Supabase Realtime. Worker/poller/frontend are **registry-driven** (ADR-0008).

---

## 2. Prerequisites

| Tool | Why | Notes |
|---|---|---|
| **Docker** (Compose v2) | Runs Temporal + worker + frontend | On this machine that's **Rancher Desktop**, not Docker Desktop — see the gotcha below |
| **Supabase CLI** | `make up` runs `supabase start` (Postgres + API + Auth + Studio) | Required |
| **make** | Lifecycle wrappers | On Windows use Git Bash |
| **Node 20+** | Frontend (Vite) | Containerized; needed on the host only for lint/build outside Docker |
| **Python 3.11** | Temporal worker + tests | Containerized; needed on the host only to run the test suite locally |
| **Azure CLI** (`az`) | Optional — Entra auth for Azure OpenAI | Falls back to an API key if absent/unauthorized |

You also need Azure OpenAI credentials (see [§4](#4-environment-variables)).

---

## 3. First run

```bash
cp .env.example .env          # fill the Azure OpenAI keys (see §4)
make up                       # supabase start + Temporal + worker + frontend
make supabase-status          # prints the local Supabase URLs + anon/service_role keys
```

`make up` injects the live Supabase keys into the running services (via `scripts/supabase-env.sh`).

Open the **frontend** — the launcher lists the enabled features (Program Evaluator, Study
Planner). Also: **Temporal UI** and **Supabase Studio** (ports per `config.toml` /
`make supabase-status`). Lifecycle: `make down` · `make reset` · `make logs` /
`make logs-temporal` / `make logs-frontend`; `USE_DEV=1 make up` for live-reload.

> ⚠️ **Two gotchas that bite first:**
> 1. **Rancher Desktop, not Docker Desktop.** If Docker hits the wrong daemon: `docker context use default`.
> 2. **Supabase ports are remapped on Windows** (the `543xx` range is reserved). `supabase/config.toml`
>    is authoritative — trust it and `make supabase-status`, not the upstream README defaults.

---

## 4. Environment variables

Everything lives in the **gitignored `.env`** (never commit it). What matters now:

| Key | Needed for | If missing |
|---|---|---|
| `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_DEPLOYMENT` | The model itself | Features can't reason; **required** |
| `AZURE_OPENAI_AUTH` | `auto` (Entra→key fallback) \| `entra` \| `key` | Defaults to `auto` |
| `AZURE_OPENAI_API_KEY` | Key auth / the `auto` fallback | Needed if Entra data-plane role isn't granted (see [ADR-0001](docs/adrs/0001-entity-insights-workflow-and-model-hosting.md)) |

> `SUPABASE_URL` (worker, inside Docker → `host.docker.internal`) and `VITE_SUPABASE_URL`
> (browser, on the host → `localhost`) intentionally differ by run context; `make up` sets both.
>
> **Auth-gated features** (owner-scoped, e.g. the Study Planner) need **anonymous sign-in enabled**
> — it's on in `config.toml` (`[auth] enable_anonymous_sign_ins = true`, ADR-0011). If you enable it
> on an already-running instance, restart Supabase auth to pick it up.

> Legacy note: earlier gains-era env (`GIPHY_API_KEY`, `AZURE_SPEECH_*`) is unused now — the
> gains feature was removed. `docker-compose.yml` may still pass them through harmlessly.

---

## 5. Running the tests

```bash
cd temporal && pip install -e ".[dev]" && python -m pytest tests -v   # pure units + Temporal workflow tests
cd frontend && npm ci && npm run lint && npm run build                # type/quality gate (no FE unit runner yet)
```

RLS/auth behavior is **not** in CI (no DB) — verify it **live in a rolled-back transaction**; see
[`docs/TESTING.md`](docs/TESTING.md) (the testing manifesto). CI (`pr-validation.yml`) runs both
suites on PRs to `main` and **fails if the Temporal suite disappears** ([ADR-0003](docs/adrs/0003-testing-strategy.md)).

> **Windows/Rancher note:** `docker run -v <host>:/app` bind mounts come up **empty** here.
> Run the backend suite on a host with Python 3.11, or `docker cp` the code into a container
> built from `temporal/Dockerfile`.

---

## 6. Making a change

- Work on **PRs into `main`** (branch first). Conventional-commit title + evidence-based verification.
- A **feature** is a self-contained `temporal/src/features/<name>/` package + migration + a
  frontend route + one line in each registry. Read the feature's `MANIFESTO.md`; **don't
  hand-edit `worker.py`/`poller.py`** (registry-driven).
- Base-compose containers **don't hot-reload** — rebuild the image (`docker compose build
  temporal-worker` / `frontend`) or use `USE_DEV=1`.
- A change to the **kernel contract**, a service, or a security/data/deploy boundary needs an
  **ADR** in [`docs/adrs/`](docs/adrs/).

---

## 7. Where the docs live

| You want… | Read |
|---|---|
| The map of everything | [`docs/Documentation_Index.md`](docs/Documentation_Index.md) |
| System shape, lifecycle, data model | [`docs/architecture/product-architecture.md`](docs/architecture/product-architecture.md) |
| Tech stack + versions | [`docs/TECH_STACK.md`](docs/TECH_STACK.md) |
| Testing manifesto | [`docs/TESTING.md`](docs/TESTING.md) |
| Why a decision was made | [`docs/adrs/`](docs/adrs/) |
| A feature's rules / contract | that feature's `README.md` + `MANIFESTO.md` |

---

## 8. Gotcha checklist (bookmark this)

- [ ] Docker on the **`default`** context (Rancher), not Docker Desktop.
- [ ] Supabase ports **remapped on Windows** — believe `config.toml` / `make supabase-status`.
- [ ] `.env` filled and **never committed**; keys come from `make supabase-status`.
- [ ] Entra data-plane role isn't granted → the app uses the **API key fallback** (`auto` mode).
- [ ] **Anonymous sign-in enabled** for owner-scoped features (Study Planner).
- [ ] `requires_auth` matches the table's RLS (open-anon ⟺ false; owner-scoped ⟺ true).
- [ ] Rebuild the worker/frontend image after code changes (no hot-reload without `USE_DEV=1`).
- [ ] The app is **local-only — not deployed anywhere** ([ADR-0004](docs/adrs/0004-deployment-posture-local-only.md)).
