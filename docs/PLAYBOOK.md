# Reuse Playbook — building agentic features on Supabase + Temporal

**Purpose:** reproduce this app's approach *precisely* in a new context, without re-deriving
the architecture or re-hitting the landmines. This is the "how we actually did it, do it again
faster" guide. It complements the [architecture](architecture/product-architecture.md) (shape)
and [ADRs](adrs/) (why); this page is the **procedure**.

Read it top-to-bottom once. After that, [§3 The Feature Recipe](#3-the-feature-recipe-repeat-per-feature)
and [§4 The Landmine Table](#4-the-landmine-table-read-before-you-debug) are the two sections you
reopen every time.

---

## 0. The one reusable idea

Every feature is the same durable loop. **Copy this, not the specifics of Gains Check:**

```
Browser  ──insert 'pending' row──▶  Supabase table
                                        │
                          poller claims (pending→running, atomic)
                                        ▼
                              Temporal workflow  ──▶  activities (model, tools, side-effects)
                                        │                     │
                       writes trace rows + final result ◀─────┘
                                        ▼
Browser  ◀──Realtime UPDATE/INSERT──  Supabase
```

**Invariant:** the browser only ever talks to Supabase (insert + subscribe). No bespoke API,
no exposed worker port, no CORS. Everything non-deterministic (model calls, HTTP, randomness,
TTS) lives in **activities**; the **workflow** is deterministic orchestration only. This is
[ADR-0001](adrs/0001-entity-insights-workflow-and-model-hosting.md). If you keep this invariant,
adding a feature is mechanical (§3).

**When to use this stack:** a user action needs a durable, multi-step, tool-using model run
with live progress. **When not to:** a single stateless LLM call with no progress UI — just use
a Supabase Edge Function; Temporal is overhead you won't need.

---

## 1. Stand up the base stack (once per machine)

Base template: an export of `Volaris-AI/project-template` (Supabase CLI + Temporal + Vite/React).

```bash
cp .env.example .env
make up                 # supabase start + Temporal + worker + frontend
make supabase-status    # prints local Supabase URLs + keys (make injects them)
```

Full detail + prerequisites is in [`ONBOARDING.md`](../ONBOARDING.md). The two things that will
cost you an hour if you don't know them up front are in [§4](#4-the-landmine-table-read-before-you-debug)
(Rancher context; Supabase port remap on Windows).

---

## 2. Wire the model (once per project)

Do this **before** any feature. Two files:

**`temporal/src/agents/model_client.py`** — `ModelClient` wrapping the `openai` SDK's
`AzureOpenAI`, **Entra-first with API-key fallback** (`AZURE_OPENAI_AUTH=auto`): try
`DefaultAzureCredential`/`get_bearer_token_provider`; on an auth error fall back to the key and
remember it. One call site regardless. Pin **`openai>=1.54,<2`** (v2 dropped the
`azure_ad_token_provider` construction path). See [ADR-0001](adrs/0001-entity-insights-workflow-and-model-hosting.md).

**`temporal/src/activities/insights.py::model_chat`** — the reusable one-model-turn activity.
Signature that matters:

```python
@activity.defn
def model_chat(messages: list[dict], tool_specs: list[dict],
               max_completion_tokens: int = 2048,
               tool_choice: Any = "auto") -> dict:      # ← tool_choice MUST be typed Any
    resp = _model().chat(messages, tools=tool_specs, tool_choice=tool_choice,
                         max_completion_tokens=max_completion_tokens)
    ...
    return {"content", "tool_calls": [{"id","name","arguments"}...], "finish_reason", "usage"}
```

Reasoning models (e.g. `gpt-5-mini`): use `max_completion_tokens` (not `max_tokens`), **no
`temperature`**, and give reasoning headroom (2048). `tool_choice: Any` is not cosmetic — see
the landmine table. This activity is reused verbatim by every feature; you rarely touch it again.

---

## 3. The Feature Recipe (repeat per feature)

Adding an agentic feature = these **7 edits**, always the same shape. Names below assume a
feature called `foo`; substitute freely.

### Step 1 — Migration `supabase/migrations/<ts>_foo.sql`
The run table + (optional) a trace table. **The three lines everyone forgets are the grants,
the `service_role` grant, and the realtime publication** — without them PostgREST returns
`42501 permission denied` and the UI never streams.

```sql
create table if not exists foo_runs (
  id uuid primary key default gen_random_uuid(),
  input jsonb not null default '{}',
  status text not null default 'pending',   -- pending | running | done | error
  result jsonb, error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint chk_foo_status check (status in ('pending','running','done','error'))
);
create index if not exists idx_foo_pending on foo_runs(status) where status = 'pending';

alter table foo_runs enable row level security;
create policy foo_anon_select on foo_runs for select to anon using (true);
create policy foo_anon_insert on foo_runs for insert to anon with check (true);
grant select, insert on foo_runs to anon, authenticated;   -- ← base template omits these
grant all privileges on foo_runs to service_role;          -- ← worker writes bypass RLS
alter publication supabase_realtime add table foo_runs;     -- ← required for the live UI
```

Add a `foo_events` trace table the same way if you want the live stepper (worker inserts ordered
`{run_id, seq, stage, label, detail, tokens}` rows).

### Step 2 — Poller entry `temporal/src/runs/poller.py`
Add one atomic claim + workflow start inside `poll_loop`. The claim is a **single** PATCH so two
workers can't double-claim:

```python
for run in await asyncio.to_thread(_claim, "foo_runs", "id,input"):
    await client.start_workflow(FooWorkflow.run, args=[run["id"], run.get("input") or {}],
                                id=f"foo-{run['id']}", task_queue=task_queue)
```
`_claim` already exists: `PATCH {table}?status=eq.pending&select=... {status:'running'}` with
`Prefer: return=representation`.

### Step 3 — Workflow `temporal/src/workflows/foo.py`
Deterministic orchestration. **Always wrap in a try/except that finalizes `error`** so a crash
never leaves a stuck `running` row:

```python
@workflow.run
async def run(self, run_id: str, user_input: dict) -> dict:
    try:
        return await self._execute(run_id, user_input)
    except Exception as exc:
        await workflow.execute_activity("finalize_foo", args=[run_id, "error", None, str(exc)[:500]], ...)
        return {"run_id": run_id, "error": str(exc)}
```
Inside `_execute`: bounded `for _ in range(MAX_ROUNDS)` loop over `model_chat`; append the
assistant message (with `tool_calls`) and a `{"role":"tool","tool_call_id","content"}` message
per tool result; emit a trace event per hop; on the terminal tool, finalize `done`. Import pure
helpers under `with workflow.unsafe.imports_passed_through():`.

### Step 4 — Activities `temporal/src/activities/foo.py`
All non-determinism: your tools (HTTP, DB reads, randomness), `record_foo_event`, `finalize_foo`
(PATCH the row `done`/`error` with the result). Reuse `insights.model_chat`.

### Step 5 — Register `temporal/src/worker.py`
Add `FooWorkflow` to `workflows=[...]` and every `foo.*` activity to `activities=[...]`. **Both
lists** — a missing activity registration fails only at runtime.

### Step 6 — Frontend route `frontend/src/routes/foo.tsx`
Insert the row (anon key), subscribe, backfill, render:
```ts
await supabase.from('foo_runs').insert({ input, status: 'pending' }).select().single();
// then in useEffect: channel.on('postgres_changes', {event:'UPDATE', table:'foo_runs', filter:`id=eq.${id}`}, ...)
//                     .on('postgres_changes', {event:'INSERT', table:'foo_events', filter:`run_id=eq.${id}`}, ...)
// AFTER subscribe, run a one-shot select to backfill events that landed before the channel was ready.
```

### Step 7 — Secrets `docker-compose.yml`
Pass any new secret to `temporal-worker`'s environment (and document it in `.env.example`). Never
send the service-role key or any provider key to the browser — the frontend uses the anon key only.

> **Verify each step end-to-end**, not just "it compiles": insert a row via the service key and
> poll the result (see §5). This is how every feature here was checked.

---

## 4. The Landmine Table (read before you debug)

Every one of these cost real time on this build. Skimming this table is the single biggest
time-saver for reuse.

| Symptom | Root cause | Fix |
|---|---|---|
| Docker commands hit the wrong daemon / nothing runs | Rancher Desktop, not Docker Desktop, owns the working daemon | `docker context use default` |
| `supabase start` fails: `dial tcp 127.0.0.1:543xx refused` | Windows reserves `54268–54367` (WinNAT/Hyper-V) | Remap Supabase ports `543xx→553xx` in `supabase/config.toml`; set `[analytics] enabled=false` |
| PostgREST `42501 permission denied for table` (as anon/service_role) | Base template creates tables **without API-role grants** | Add `grant select,insert ... to anon,authenticated; grant all ... to service_role;` in the migration |
| `openai` v2: "Missing credentials" when building `AzureOpenAI` with a token provider | v2 dropped the `azure_ad_token_provider` construction path | Pin `openai>=1.54,<2` |
| Temporal: `Unserializable type during conversion: <class 'object'>` | An activity param typed `object` (e.g. `tool_choice: object`) | Type it `Any` (`from typing import Any`) |
| Model "max rounds exceeded" / never calls the tool | Reasoning model thinks out loud instead of calling the function | Force `tool_choice={"type":"function","function":{"name":...}}` **and** nudge+continue on an empty tool-call turn; give 2048 token headroom |
| Model 400 on `temperature` / truncated output | Reasoning model rejects `temperature`, needs `max_completion_tokens` | Drop `temperature`; use `max_completion_tokens` |
| Giphy `403` with the public demo key | Free/demo Giphy keys are banned (2026) | Use a real `GIPHY_API_KEY`; keep a curated CDN fallback list so it never blanks |
| Poller starts a workflow twice for one row | Non-atomic claim (read then write) | One `PATCH status=eq.pending` returning representation = atomic claim |
| `docker run -v <host>:/app` mounts an **empty** dir (Windows/Rancher) | Git-Bash path → WSL bind mount doesn't bind | `docker cp` into a built image, or `USE_DEV=1` compose mounts; don't rely on ad-hoc `-v` |
| Code changes don't show up | Base compose bakes code into the image (no hot reload) | Rebuild the image (`docker compose build <svc>`) or run with `USE_DEV=1` |
| UI misses the first trace steps | Subscribed after the worker already inserted them | After `.subscribe()`, run a one-shot select to **backfill** and merge by `seq` |
| Post-merge commits vanish from `main` | PRs are **squash-merged**; pushing more to a merged branch orphans them | Branch fresh off `main` for each PR; never reuse a merged branch |
| CI "tests" pass but assert nothing | A job that skips when no test files exist | Make it **fail** if no `test_*.py` exist (see [ADR-0003](adrs/0003-testing-strategy.md)) |

---

## 5. Verify & test (the discipline that kept this honest)

- **End-to-end smoke, every feature:** a throwaway Node/script that inserts a `pending` row with
  the **service-role key** against the local REST API and polls `status` until `done`, printing
  the result + trace. This is how each feature and each fix was proven — not "CI is green."
- **Committed suite** ([ADR-0003](adrs/0003-testing-strategy.md)): pytest **unit tests** for pure
  logic (no network) + **Temporal workflow tests** using the time-skipping `WorkflowEnvironment`
  with **mocked activities** (assert orchestration, not the model). CI runs them and **fails if
  they disappear**. This is the reusable test pattern — copy `temporal/tests/` structure.
- **Frontend gate:** `eslint` + `vite build` (type-check via build). No FE unit runner yet.

---

## 6. Guided vs Agentic — the reusable autonomy dial

The same feature can be built two ways; pick per requirement (both shipped for Gains Check,
[ADR-0002](adrs/0002-gains-check-guided-vs-agentic-engine.md)):

- **Reliable / demo-safe:** **force** `tool_choice` to a single `submit_*` tool, put the decision
  rules in the prompt, and choose all sensory/branded output in **code** from curated data. The
  model classifies; code does the rest. Predictable, cheap.
- **Genuinely agentic:** expose **real tools** (`search_*`, `get_*`), leave `tool_choice="auto"`,
  and let the model run a reason→act→decide loop with **nothing overriding it**. Adaptive, but
  variable output.

Shipping **both behind a `input.mode` toggle** is cheap (same workflow skeleton, one branch) and
lets you demo the trade-off. Default to guided.

---

## 7. To scale (what to templatize next)

The 7 steps in §3 are ~identical every time — that's the scaling lever:

1. **A `scaffold-feature <name>` generator** that stamps the 5 files (migration, workflow,
   activity, poller entry, route) from the skeletons above, parameterized on the feature/table
   name. ~80% of a new feature is boilerplate this removes.
2. **Factor the run-loop** (claim → model_chat loop → tool dispatch → trace → finalize) into a
   small shared base so a workflow only declares its tools + terminal schema.
3. **A migration macro** for "run table + trace table + RLS + grants + realtime" so the
   easy-to-forget grant/publication lines can't be dropped.
4. Keep `model_chat` and `ModelClient` **provider-agnostic at the call site** so swapping Azure
   OpenAI for Bedrock/another host is one file, not a sweep.

Everything else (Realtime subscription shape, the trace stepper component, the finalize-on-error
pattern) is directly copy-pasteable.

---

## 8. Reality check (so estimates are honest)

This was built interactively (human directs, agent does the plumbing) as PRs into `main`. The
work was **not** dominated by writing feature code — it was the landmines in §4 (environment,
grants, provider quirks, serialization) and **end-to-end verification**. Budget accordingly: with
§4 pre-empted and §3 templatized, a new feature on an already-stood-up stack is hours, not days.
The dollar/token figures shown in the app's build-stats banner are whole-session Claude Code
usage (mostly cached context re-reads), not the cost of any single feature.

---

## Pointers

- [`ONBOARDING.md`](../ONBOARDING.md) — get the stack running.
- [`docs/architecture/product-architecture.md`](architecture/product-architecture.md) — the shape.
- [`docs/adrs/`](adrs/) — the binding decisions (hosting, engines, testing, deploy).
- [`docs/specs/`](specs/) — per-feature detailed designs.
