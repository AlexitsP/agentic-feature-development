# Tech Stack

Every technology in **AlpacAI**, its version, and why it's here. Versions are the
source-of-truth manifests (`frontend/package.json`, `temporal/pyproject.toml`,
`supabase/config.toml`, `docker-compose.yml`).

## At a glance

```
Browser (Vite/React SPA)  ──►  Supabase (Postgres + PostgREST + Realtime + Auth)
                                    ▲
                                    │ service role (write)
              Temporal worker (Python) ──► Azure OpenAI (gpt-5-mini)
              └ poller + workflows + activities, orchestrated by Temporal server
```

## Frontend (`frontend/`)

| Tech | Version | Why |
|---|---|---|
| **Vite** | 5 | Fast dev server + build; `autoCodeSplitting` gives per-route lazy chunks. |
| **React** | 18 | UI. |
| **TanStack Router** | 1.x | File-based routes (`src/routes/`), typed links, `defaultPreload: 'intent'`. Each feature = a route, code-split. |
| **TanStack Query** | 5.x | Server-state/data fetching primitives. |
| **Tailwind CSS** | 4 | Styling. |
| **shadcn/ui + Radix** | — | Component primitives. |
| **@supabase/supabase-js** | 2.x | Anon-key client: inserts run rows, subscribes to Realtime, anonymous Auth (`ensureSession`). |
| **TypeScript / ESLint** | 5.x / 8.x | Types + lint. |

## Backend — Temporal worker (`temporal/`)

| Tech | Version | Why |
|---|---|---|
| **Python** | 3.11 | Worker language. |
| **temporalio** | 1.5.0 (pinned) | Durable workflow orchestration; deterministic workflows, non-determinism in activities. |
| **openai** | pinned (`>=1.54,<2` → exact) | Azure OpenAI SDK. v2 dropped the `azure_ad_token_provider` construction path, hence `<2`. |
| **azure-identity** | pinned | `DefaultAzureCredential` for Entra-first auth. |
| **httpx** | pinned | Supabase PostgREST calls from activities/poller. |
| **pydantic / pydantic-settings** | 2.7.x | Typed settings (`config.py`). |
| **pytest (+ asyncio, json-report)** | — | Tests (unit + Temporal `TestWorkflowEnvironment`). |

## Data & realtime — Supabase (`supabase/`)

| Tech | Notes |
|---|---|
| **Postgres** | 17 (local). Migrations in `supabase/migrations/` (timestamped, append-only). |
| **PostgREST** | The de-facto API (`/rest/v1`). RLS + grants explicit per migration. |
| **Realtime** | Tables published to `supabase_realtime`; the UI subscribes to `postgres_changes`. |
| **Auth (gotrue)** | Owner-scoped RLS (ADR-0007); **anonymous sign-in** enabled for gated features (ADR-0011). |
| **Supabase CLI** | Runs the local stack (`supabase start`). Ports remapped to `553xx`/`554xx` on Windows; keys are per-instance (read via `make supabase-status`). |

## LLM

| Tech | Notes |
|---|---|
| **Azure OpenAI** | Deployment `gpt-5-mini` (a reasoning model → `max_completion_tokens`, no temperature, forced `tool_choice`). Reached **only from the worker**, isolated behind `ModelClient` (`temporal/src/agents/model_client.py`). Auth `auto` = Entra-first, API-key fallback. Company-hosted (Swiss/EU region) for data residency. |

## Infra / ops

| Tech | Notes |
|---|---|
| **Docker (Rancher Desktop)** | Runs Temporal + the worker; `docker context use default`. |
| **docker-compose** | `docker-compose.yml` (base) + `docker-compose.dev.yml` (bind-mount live-reload via `USE_DEV=1`). |
| **Helm charts** | `charts/app/` — hardened (securityContext, dev/test/prod profiles). **Not deployed** — local-only (ADR-0004). |
| **GitHub Actions** | `.github/workflows/pr-validation.yml` — frontend lint+build + Temporal pytest; least-privilege; fails if the test suite disappears (ADR-0003). |
| **Make** | `make up` / `down` / `reset` / `logs` / `supabase-status` — the dev entrypoints. |

## What we deliberately do **not** use

- **No bespoke API server** — the browser talks only to Supabase (ADR-0001).
- **No provider/service-role keys in the browser** — anon key only; server secrets live in the worker env.
- **No model self-reported confidence** — the badge is computed from observable signals (ADR-0009).
