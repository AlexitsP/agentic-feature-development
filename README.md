# 💪 Gains Check

A small, fully agentic demo app on **Supabase + Temporal + Vite/React + a hosted LLM**.

Enter your tracked fitness numbers (or just describe them in plain words) and a coach agent judges
whether you're doing it right — with a live pipeline trace, GIFs, and coach personas. Then pick a
goal and a **panel of agents** (nutrition · training · recovery specialists → a head coach)
drafts a research-based starter plan with resource links.

The whole flow is a 6-step wizard at **`/gains`** (the app's only page): Engine → Coach → Your
numbers → Result → Goal → Plan.

## Run it locally

```bash
cp .env.example .env      # fill the Azure OpenAI + Giphy keys (see .env.example)
make up                   # supabase start + Temporal + worker + frontend
make supabase-status      # local Supabase URLs + keys
```

Then open **http://localhost:3000** (redirects to `/gains`). Full setup, prerequisites, and the
gotchas (Rancher context, Windows Supabase port remap) are in **[`ONBOARDING.md`](ONBOARDING.md)**.

Lifecycle: `make down` · `make reset` · `make logs` · `make logs-temporal` / `make logs-frontend`.

## How it works

The browser only ever talks to Supabase: it inserts a `pending` row; a worker-side poller claims
it and starts a Temporal workflow; the workflow runs the model + tools in activities and streams
the result + trace back via Supabase Realtime. See
**[`docs/architecture/product-architecture.md`](docs/architecture/product-architecture.md)** for
the shape, and **[`docs/adrs/`](docs/adrs/)** for the decisions.

## Layout

- `frontend/` — Vite + React + TanStack Router; the app is `src/routes/gains.tsx`.
- `temporal/` — Python worker: `workflows/` (`gains_check`, `gains_plan`), `activities/`
  (`gains`, `model`), `agents/` (model client + tools), `runs/poller.py`; tests in `tests/`.
- `supabase/` — `config.toml`, `migrations/` (the `gains_*` tables), `seed.sql`.
- `docs/` — architecture, ADRs, the reuse **PLAYBOOK**, and the portable `kit/` for standing this
  stack up in a new repo.

## Reusing the stack elsewhere

To bootstrap this stack in a fresh repo, use the portable kit — **[`kit/README.md`](kit/README.md)**
and **[`docs/PLAYBOOK.md`](docs/PLAYBOOK.md)** — not a copy of this app.
