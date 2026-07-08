# Onboarding

Welcome. This is a **temporary experiment repo** that runs an AI-driven feature-development
loop on a small full-stack app. This page gets you from a fresh clone to a running app and
your first change. For *why* things are shaped the way they are, read the
[ADRs](docs/adrs/); for *how the system fits together*, read the
[architecture docs](docs/architecture/product-architecture.md).

---

## Starting a session with your agent (paste this)

Claude Code **auto-loads `CLAUDE.md`** (the repo's governance base) when you open the repo, so the
base is already active. Paste the prompt below at the start of a session anyway, to **(a)** get an
explicit confirmation it loaded and **(b)** cover any agent/tool that doesn't auto-read `CLAUDE.md`.
If it can parrot back the guardrails and repo facts, you *know* it's operating under the base.

**Activation prompt:**
```
Before doing anything in this repo: read CLAUDE.md at the repo root and treat it as
binding. It points to docs/PLAYBOOK.md — the "Guardrails (MUST / MUST-NOT)" there are
binding too.

Confirm you've actually loaded them by replying with:
  1. the non-negotiable guardrails, one line each, and
  2. this repo's facts (LLM host, Supabase + ports, container runtime, merge strategy,
     RLS posture, deployment posture).

Then for the rest of this session operate under that governance:
  - read PLAYBOOK §3 before adding/changing a feature, §4 before debugging;
  - branch off main and open a PR for any change; never reuse a merged branch;
  - verify end-to-end (insert → poll done), not on compile/CI-green;
  - anything touching >1 component / a service / a security/data/deploy boundary → add an ADR.

If you cannot see CLAUDE.md, stop and tell me — do not proceed.
```

Once confirmed, keep day-to-day prompts short — the governance routes the agent for you:

**Add a feature:**
```
New agentic feature `<name>`: <one line of what it does>.
Follow CLAUDE.md + PLAYBOOK §3 and the guardrails. Tools it needs: <…>.
Terminal output / verdict schema: <…>. Namespace everything as `<name>`
(table, workflow, queue, route). Verify end-to-end, then open a PR.
```

**Debug:**
```
<symptom> (e.g. `make up` fails / migration 42501 / model won't call the tool).
Check PLAYBOOK §4 (the landmine table) first, per CLAUDE.md.
```

> Standing the kit up in a **fresh** repo (not this one) is a one-time adoption step, not a
> per-session prompt — see [`docs/PLAYBOOK.md`](docs/PLAYBOOK.md) §9.

---

## 1. What this is

A JSON-driven **Supabase + Temporal + Vite/React** stack with two agentic features built on it:

- **Entity Insights Assistant** (`/insights`) — an agent summarizes a business entity by
  running a bounded tool-use loop over Supabase data, streaming each step to the UI.
- **Gains Check** (`/gains`) — a fun demo: enter your bodyweight / body-fat / calories /
  protein and a coach agent judges whether you're "doing it right," fetches a hype/shame
  GIF, compares you to a bodybuilding legend, and speaks the verdict. It ships **two
  engines** you toggle per run:
  - **Guided** — a deterministic pipeline with one forced model decision (reliable, demo-safe).
  - **Agentic** — a genuine reason → search → decide loop where the model picks its own GIF
    searches, legend, headline, and voice (autonomous, more variable).

The core pattern for both: **the browser only ever talks to Supabase.** It inserts a row; a
worker-side poller claims it and starts a Temporal workflow; the workflow calls activities
(the model, tools, TTS); results and a live trace stream back via Supabase Realtime.

---

## 2. Prerequisites

| Tool | Why | Notes |
|---|---|---|
| **Docker** (Compose v2) | Runs Temporal + worker + frontend | On this machine that's **Rancher Desktop**, not Docker Desktop — see the gotcha below |
| **Supabase CLI** | `make up` runs `supabase start` (Postgres + API + Auth + Studio) | Required |
| **make** | Lifecycle wrappers | macOS/Linux built-in; on Windows use Git Bash |
| **Node 18+** | Frontend (Vite) | Runs in a container; only needed on the host for lint/build outside Docker |
| **Python 3.11** | Temporal worker + tests | Runs in a container; only needed on the host to run the test suite locally |
| **Azure CLI** (`az`) | Optional — Entra auth for Azure OpenAI | Falls back to an API key if absent/unauthorized |

You also need credentials for the external services the app calls (see [§4](#4-environment-variables)).

---

## 3. First run

```bash
cp .env.example .env          # then fill in the Azure/Giphy/Speech keys (see §4)
make up                       # supabase start + Temporal + worker + frontend
make supabase-status          # prints the local Supabase URLs + anon/service_role keys
```

`make up` injects the live Supabase keys into the running services for you (via
`scripts/supabase-env.sh`) — you don't hand-edit the anon/service_role values.

Then open:

| Service | URL |
|---|---|
| **Frontend** | http://localhost:3000 — try `/gains` and `/insights` |
| Temporal UI | http://localhost:8080 |
| Supabase Studio | http://localhost:**55323** |
| Supabase API | http://localhost:**55321** |
| Temporal gRPC | localhost:7234 |

Lifecycle: `make down` (stop) · `make reset` (wipe volumes + re-apply migrations/seed) ·
`make logs` / `make logs-temporal` / `make logs-frontend`. Add `USE_DEV=1` to `make up` for
live-reload mounts (`docker-compose.dev.yml`).

> ⚠️ **Two gotchas that will bite you first (both are real, both are why this fork differs
> from the template README):**
>
> 1. **Rancher Desktop, not Docker Desktop.** This machine's working Docker daemon is
>    Rancher's. If Docker commands hit the wrong daemon, run `docker context use default`.
> 2. **Supabase ports are remapped `543xx → 553xx`.** Windows reserves the `54268–54367`
>    range (WinNAT/Hyper-V), which collides with Supabase's defaults, so `supabase/config.toml`
>    uses `55321` (API), `55323` (Studio), etc. The upstream `README.md` still shows the
>    `543xx` defaults — trust `config.toml`/`make supabase-status`, not the README.

---

## 4. Environment variables

Everything lives in the **gitignored `.env`** (never commit it). `.env.example` documents each
key. What actually matters:

| Key | Needed for | If missing |
|---|---|---|
| `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_DEPLOYMENT` | The model — the verdict/summary itself | The features can't reason; **required** |
| `AZURE_OPENAI_AUTH` | `auto` (Entra→key fallback) \| `entra` \| `key` | Defaults to `auto` |
| `AZURE_OPENAI_API_KEY` | Key auth / the `auto` fallback | Only needed if Entra RBAC isn't granted (it currently isn't — see [ADR-0001](docs/adrs/0001-entity-insights-workflow-and-model-hosting.md)) |
| `GIPHY_API_KEY` | Live GIFs in Gains Check | Falls back to curated CDN GIFs / emoji. **Free Giphy demo keys are banned (403)** — get a real one at developers.giphy.com |
| `AZURE_SPEECH_KEY` / `AZURE_SPEECH_REGION` | Expressive neural TTS for the spoken verdict | Falls back to the browser's robotic `speechSynthesis` |

> `SUPABASE_URL` (worker, inside Docker → `host.docker.internal`) and `VITE_SUPABASE_URL`
> (browser, on the host → `localhost`) intentionally differ by run context. `make up` sets
> the right values; if you bypass make and run `docker compose up` directly, paste the values
> from `make supabase-status`.

---

## 5. Running the tests

Backend suite (pytest — pure logic + Temporal workflow tests with mocked activities):

```bash
cd temporal
pip install -e ".[dev]"
python -m pytest tests -v          # 28 tests, ~8s
```

Frontend (lint + production build — this is the type/quality gate, there is no FE unit runner yet):

```bash
cd frontend
npm ci
npm run lint
npm run build
```

> **Windows/Rancher note:** `docker run -v <host-path>:/app` bind mounts come up **empty** on
> this setup, so you can't just mount the source into a throwaway container. To run the
> backend suite in Docker, bake or `docker cp` the code into a container built from
> `temporal/Dockerfile`, then `pip install pytest pytest-asyncio pytest-json-report` and run
> pytest. On a host with Python 3.11, the plain commands above are simplest.

**CI** (`.github/workflows/pr-validation.yml`, runs on PRs to `main`): frontend lint & build +
the Temporal pytest suite. The Temporal job **fails if no tests exist** — a green "tests"
check that runs zero assertions is not allowed (see [ADR-0003](docs/adrs/0003-testing-strategy.md)).

---

## 6. Making a change

- Work happens on **PRs into `main`** (branch first — don't commit to `main` directly). PRs
  use the conventional-commit title + evidence-based verification format.
- The worker and frontend containers **do not hot-reload** in the base compose — after editing
  backend or frontend code, rebuild the relevant image (`docker compose build temporal-worker`
  / `frontend`) and restart it, or use `USE_DEV=1` for live-reload mounts.
- Any change that shapes more than one component, swaps a service, or moves a security/data/
  deploy boundary needs an **ADR** in [`docs/adrs/`](docs/adrs/).

---

## 7. Where the docs live

| You want… | Read |
|---|---|
| The shape of the whole system, request lifecycle, components | [`docs/architecture/product-architecture.md`](docs/architecture/product-architecture.md) |
| Why a decision was made (model hosting, engines, testing, deploy) | [`docs/adrs/`](docs/adrs/) |
| The detailed design of a feature slice | [`docs/specs/`](docs/specs/) |
| Data model / schema | [`DATABASE.md`](DATABASE.md), migrations in `supabase/migrations/` |

---

## 8. Gotcha checklist (bookmark this)

- [ ] Docker on the **`default`** context (Rancher), not Docker Desktop.
- [ ] Supabase at **`553xx`**, not `543xx` — believe `config.toml`, not the template README.
- [ ] `.env` filled and **never committed**; keys come from `make supabase-status`.
- [ ] A **real** `GIPHY_API_KEY` for live GIFs (demo keys are banned).
- [ ] Entra data-plane role isn't granted → the app uses the **API key fallback** (`auto` mode).
- [ ] Rebuild the worker/frontend image after code changes (no hot-reload without `USE_DEV=1`).
- [ ] The app is **local-only — not deployed anywhere** (see [ADR-0004](docs/adrs/0004-deployment-posture-local-only.md)).
