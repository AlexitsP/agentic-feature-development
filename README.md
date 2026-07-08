# 🦙 AlpacAI

**AlpacAI** — a **Swiss AI hub for learning** on **Supabase + Temporal + Vite/React + a hosted
LLM**, built as a **kernel + feature-plugin platform**: a small shared kernel (run lifecycle, model
access, live tracing, confidence scoring, source grounding, auth) hosts self-contained features.

Today it ships two features:

- **Program Evaluator** (`/evaluate`) — describe your situation; an agent assesses fit and
  suggests Swiss study options (field + institution type: University / UAS / PH), grounded in
  official Swiss sources, with an honest **confidence badge**.
- **Study Planner** (`/plan`) — a multi-agent **panel** (curriculum + study-skills coach →
  head-advisor synthesis) drafts a study plan **including how to study**, with sources + confidence.

> The stack began as a "Gains Check" fitness demo and was repurposed (ADR-0008); all gains code
> is gone. See [`docs/Documentation_Index.md`](docs/Documentation_Index.md) for everything.

## Run it locally

```bash
cp .env.example .env      # fill the Azure OpenAI keys (see .env.example)
make up                   # supabase start + Temporal + worker + frontend
make supabase-status      # local Supabase URLs + keys
```

Open the app (the launcher lists the features), then pick a tool. Full setup, prerequisites, and
the gotchas (Rancher context, Windows Supabase port remap, anon-auth for gated features) are in
**[`ONBOARDING.md`](ONBOARDING.md)**. Lifecycle: `make down` · `make reset` · `make logs`.

## How it works

The browser only ever talks to Supabase: it inserts a `pending` row; a worker-side poller
claims it and starts the feature's Temporal workflow; the workflow runs the model in activities,
computes a confidence badge, and streams the result + trace back via Supabase Realtime. Worker,
poller, and frontend are **registry-driven**, so adding/removing/toggling a feature touches only
that feature's package + one registry line. See
**[`docs/architecture/product-architecture.md`](docs/architecture/product-architecture.md)** and
the **[ADRs](docs/adrs/)**.

## Layout

- `frontend/` — Vite + React + TanStack Router. Launcher + nav render from `src/features/registry.ts`;
  each feature is a route in `src/routes/` (lazy-loaded), with `src/data/` (supabase, auth) and
  `src/components/` (e.g. `ConfidenceBadge`).
- `temporal/` — Python worker. **`src/kernel/`** (registry, confidence, sources) + **`src/features/<name>/`**
  (manifest, workflow, activities, tools) + `src/runs/poller.py`; tests in `tests/`.
- `supabase/` — `config.toml`, `migrations/*.sql` (per-feature tables), `seed.sql`.
- `docs/` — the [index](docs/Documentation_Index.md), architecture, ADRs, tech stack, testing
  manifesto, and the reuse **PLAYBOOK**. Each library also carries a `README.md` + `MANIFESTO.md`.

## Reusing the stack elsewhere

To bootstrap this stack in a fresh repo, use the portable **[`kit/`](kit/README.md)** +
**[`docs/PLAYBOOK.md`](docs/PLAYBOOK.md)** — not a copy of this app.
