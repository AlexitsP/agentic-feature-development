# Stack Playbook — agentic features on Supabase + Temporal + Vite/React

**Purpose:** reproduce this *stack's* approach precisely in a new context, at larger scope and
scale, without re-deriving the architecture or re-hitting the landmines. This is a
**stack-and-lessons guide**, deliberately **not tied to any specific app** — the worked example
that this repo happens to implement is demoted to a single pointer at the end. If you are
starting another product on the same (or a similar) stack — Supabase (Postgres + PostgREST +
Realtime) + Temporal + Vite/React + a hosted LLM — start here.

Read it top-to-bottom once. After that, [§3 The Feature Recipe](#3-the-feature-recipe-repeat-per-feature)
and [§4 The Landmine Table](#4-the-landmine-table-read-before-you-debug) are the two sections you
reopen for every feature.

---

## 0. The one reusable idea

Every agentic feature on this stack is the same durable loop. **Copy this loop, not any one
feature:**

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

**Invariant:** the browser only ever talks to Supabase (insert + subscribe). No bespoke API, no
exposed worker port, no CORS. Everything non-deterministic (model calls, HTTP, randomness,
external services) lives in **activities**; the **workflow** is deterministic orchestration only.

**When to use this stack:** a user action needs a durable, multi-step, tool-using model run with
live progress. **When not to:** a single stateless LLM call with no progress UI — use a Supabase
Edge Function; Temporal is overhead you won't need. Keep both kinds in the same product by using
this loop only where durability/steps/streaming actually earn their cost.

---

## Guardrails — MUST / MUST-NOT (binding)

The non-negotiables distilled from the rest of this doc. A consumer repo activates these by
declaring this section binding in its root agent file (see
[§9 Adopt in a new repo](#9-adopt-in-a-new-repo-the-activation-kit)). If a rule genuinely doesn't
apply to a given product, delete it explicitly — don't silently ignore it.

**MUST**
- **Read [§3](#3-the-feature-recipe-repeat-per-feature) before adding a feature; read
  [§4](#4-the-landmine-table-read-before-you-debug) before debugging** an environment / provider /
  orchestration failure.
- **Branch off `main` for every change and open a PR.** Squash-merge orphans any commits pushed to
  an already-merged branch — never reuse one.
- In every new run/trace-table migration, include the **anon + authenticated grants, the
  `service_role` grant, and `alter publication supabase_realtime add table`** — and confirm
  PostgREST access before moving on.
- Keep **workflows deterministic**; put **all** non-determinism (model calls, HTTP, randomness,
  external services) in **activities**.
- Wrap each workflow `run()` in a try/except that **finalizes the row `error`** — never leave a
  stuck `running`.
- **Register both** the workflow and every activity in the worker.
- For reasoning-tier models: use a **completion-token budget, omit `temperature`, and force
  `tool_choice`** (or nudge+continue) so the model actually calls the terminal tool.
- Type Temporal params **`Any`** when they carry a union/opaque value (e.g. `tool_choice`).
- **Verify features end-to-end** (insert a `pending` row → poll until `done`), not on
  compile/lint/CI-green alone.
- Keep the **LLM provider isolated behind the model client** so the host is swappable in one file.

**MUST NOT**
- **Never commit `.env` or any secret.** Never send the service-role key or a provider key to the
  browser — the frontend uses the **anon key only**.
- **Never let the browser talk to anything but Supabase** (no bespoke API, no exposed worker port).
- **Never edit a shipped migration** — add a new timestamped one.
- **Never rely on ad-hoc `docker run -v <host>:/app`** on Windows/WSL runtimes (mounts come up
  empty) — `docker cp` or use the dev-mount override.
- **Never mark work "done" on compile/CI-green** without an end-to-end check.
- **Never provision paid cloud resources or take costly/outward-facing actions without explicit
  confirmation.**

---

## 1. Stand up the base stack (once per machine)

The base is the shared template (Supabase CLI + Temporal + Vite/React). Getting it running:

```bash
cp .env.example .env
make up                 # supabase start + Temporal + worker + frontend
make supabase-status    # prints local Supabase URLs + keys (make injects them)
```

Prerequisites and the full local setup live in the onboarding guide for whichever product you're
in. The two things that cost an hour if you don't know them up front are in
[§4](#4-the-landmine-table-read-before-you-debug) (container runtime context; Supabase port
collisions on Windows).

---

## 2. Wire the model (once per project)

Do this **before** any feature. Two files, reused by every feature after:

**A model client** (`temporal/src/agents/model_client.py` here) — wrap the provider SDK behind
one class with **credential-first, key-fallback** auth so the call site never branches on how you
authenticated. Keep the provider isolated to this one file so swapping the LLM host later is a
single-file change, not a sweep. (This build used Azure OpenAI + Entra/`DefaultAzureCredential`
with an API-key fallback; pin the SDK — `openai>=1.54,<2` here — because major versions change
the construction path.)

**A generic one-turn activity** (`model_chat`) — the reusable unit every workflow calls:

```python
@activity.defn
def model_chat(messages: list[dict], tool_specs: list[dict],
               max_completion_tokens: int = 2048,
               tool_choice: Any = "auto") -> dict:      # ← tool_choice MUST be typed Any
    resp = _model().chat(messages, tools=tool_specs, tool_choice=tool_choice,
                         max_completion_tokens=max_completion_tokens)
    return {"content", "tool_calls": [{"id","name","arguments"}...], "finish_reason", "usage"}
```

**Reasoning-model caveats** (apply to any reasoning-tier model, not just this one): use a
completion-token budget (not `max_tokens`), **omit `temperature`**, and give reasoning headroom.
`tool_choice: Any` is not cosmetic — see the landmine table. This activity is provider- and
feature-agnostic; you rarely touch it again.

---

## 3. The Feature Recipe (repeat per feature)

Adding any agentic feature = these **7 edits**, always the same shape regardless of what the
feature does. Names below use a placeholder feature `foo`; substitute freely.

### Step 1 — Migration `supabase/migrations/<ts>_foo.sql`
A run table + (optional) a trace table. **The three lines everyone forgets are the API-role
grants, the `service_role` grant, and the realtime publication** — without them PostgREST returns
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

Add a `foo_events` trace table the same way for a live stepper (worker inserts ordered
`{run_id, seq, stage, label, detail, tokens}` rows). **Note the RLS posture is a
local/experiment default** (anon can insert/select) — tighten it for anything real (see §7).

### Step 2 — Poller entry `temporal/src/runs/poller.py`
Add one atomic claim + workflow start inside `poll_loop`. The claim is a **single** PATCH so two
workers can't double-claim:

```python
for run in await asyncio.to_thread(_claim, "foo_runs", "id,input"):
    await client.start_workflow(FooWorkflow.run, args=[run["id"], run.get("input") or {}],
                                id=f"foo-{run['id']}", task_queue=task_queue)
```
`_claim` is generic: `PATCH {table}?status=eq.pending&select=... {status:'running'}` with
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
All non-determinism: your tools (HTTP, DB reads, randomness, external services), a
`record_foo_event`, and a `finalize_foo` (PATCH the row `done`/`error` with the result). Reuse
the generic `model_chat`.

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
Pass any new secret to the worker's environment (and document it in `.env.example`). Never send
the service-role key or any provider key to the browser — the frontend uses the anon key only.

> **Verify each step end-to-end**, not just "it compiles": insert a row with the service key and
> poll the result (see §5).

---

## 4. The Landmine Table (read before you debug)

Every one of these is a **stack-level** trap (environment, provider, orchestration, or delivery)
— none is specific to a particular app's domain. Skimming this table is the single biggest
time-saver for reuse.

| Symptom | Root cause | Fix |
|---|---|---|
| Docker commands hit the wrong daemon / nothing runs | Two container runtimes installed; the wrong one owns the daemon | Select the working context (e.g. `docker context use default` for Rancher Desktop) |
| `supabase start` fails: `dial tcp 127.0.0.1:543xx refused` | Windows reserves `54268–54367` (WinNAT/Hyper-V), colliding with Supabase defaults | Remap Supabase ports `543xx→553xx` in `supabase/config.toml`; set `[analytics] enabled=false` |
| PostgREST `42501 permission denied for table` (as anon/service_role) | The template creates tables **without API-role grants** | Add `grant select,insert ... to anon,authenticated; grant all ... to service_role;` in the migration |
| Provider SDK: "Missing credentials" / broken construction after an upgrade | A major SDK version changed the auth/construction path | Pin the SDK to a known-good major (`openai>=1.54,<2` here) |
| Temporal: `Unserializable type during conversion: <class 'object'>` | An activity/workflow param typed `object` (e.g. `tool_choice: object`) | Type it `Any` (`from typing import Any`) — Temporal's converter can't serialize bare `object` |
| Model "max rounds exceeded" / never calls the tool | A reasoning model "thinks out loud" instead of calling the function | Force `tool_choice={"type":"function","function":{"name":...}}` **and** nudge+continue on an empty tool-call turn; give token headroom |
| Model 400 on `temperature` / truncated output | Reasoning models reject `temperature` and need a completion-token budget | Drop `temperature`; use `max_completion_tokens` |
| A third-party API you call from an activity rejects your key | Free/demo/public tiers get revoked (e.g. `403`) | Use a real key **and** keep a deterministic fallback so the feature degrades gracefully instead of blanking |
| Poller starts a workflow twice for one row | Non-atomic claim (read then write) | One `PATCH status=eq.pending` returning representation = atomic claim |
| `docker run -v <host>:/app` mounts an **empty** dir (Windows/WSL runtimes) | Git-Bash path → WSL bind mount doesn't bind | `docker cp` into a built image, or use dev-mount compose overrides; don't rely on ad-hoc `-v` |
| Code changes don't show up | Base compose bakes code into the image (no hot reload) | Rebuild the image (`docker compose build <svc>`) or run with the dev-mount override |
| UI misses the first trace steps | Subscribed after the worker already inserted them | After `.subscribe()`, run a one-shot select to **backfill** and merge by `seq` |
| Post-merge commits vanish from `main` | PRs are **squash-merged**; pushing more to a merged branch orphans them | Branch fresh off `main` for each PR; never reuse a merged branch |
| CI "tests" pass but assert nothing | A job that skips when no test files exist | Make it **fail** if no tests exist |

---

## 5. Verify & test (the discipline that keeps it honest)

- **End-to-end smoke, every feature:** a throwaway script that inserts a `pending` row with the
  **service-role key** against the local REST API and polls `status` until `done`, printing the
  result + trace. Prove each feature and each fix this way — not "CI is green."
- **Committed suite (the reusable pattern):** unit tests for pure logic (no network) + **Temporal
  workflow tests** using the time-skipping `WorkflowEnvironment` with **mocked activities** (assert
  orchestration, not the model). Wire CI to run them and **fail if they disappear** — a green
  "tests" check that runs zero assertions is worse than none.
- **Frontend gate:** lint + production build (type-check via build) at minimum.

---

## 6. The autonomy dial (a design choice, per feature)

The same feature can be built anywhere on a reliability↔autonomy spectrum. Pick per requirement,
and consider shipping both behind a `mode` flag on the run row:

- **Reliable / demo-safe:** **force** `tool_choice` to a single `submit_*` tool, put the decision
  rules in the prompt, and choose all branded/sensory output in **code** from curated data. The
  model classifies; code does the rest. Predictable, cheap, on-brand.
- **Genuinely agentic:** expose **real tools** (`search_*`, `get_*`), leave `tool_choice="auto"`,
  and let the model run a reason→act→decide loop with **nothing overriding it**. Adaptive, but
  variable output.

Both use the identical §3 skeleton — the only difference is whether `tool_choice` is forced and
whether code overrides the model's choices. Default to the reliable end and open up per feature.

---

## 7. Scaling to a larger product (many features, a team, real users)

The 7 steps in §3 are ~identical every time — that repetition is the scaling lever, but scale
also introduces concerns the single-feature recipe doesn't cover:

**Kill the boilerplate**
1. A **`scaffold-feature <name>`** generator that stamps the 5 files (migration, workflow,
   activity, poller entry, route) from the skeletons above. ~80% of a new feature is boilerplate
   this removes.
2. **Factor the run-loop** (claim → `model_chat` loop → tool dispatch → trace → finalize) into a
   shared base so a workflow only declares its tools + terminal schema.
3. A **migration macro/snippet** for "run table + trace table + RLS + grants + realtime" so the
   easy-to-forget grant/publication lines can't be dropped.

**Orchestration at scale**
4. **Partition work across task queues** (per feature or per priority) and scale worker replicas
   independently; don't let a slow feature starve others on one queue.
5. **Poller throughput:** a single ~2s poll loop is fine for a demo; at volume, batch-claim,
   shard by a hash of the row id across workers, or replace the poll with a push
   (LISTEN/NOTIFY or a queue) to cut trigger latency and DB load.
6. **Version workflows** (Temporal `patched`/versioning) so in-flight runs survive deploys —
   mandatory once runs are long-lived and you ship often.

**Data, security, cost**
7. **Tighten RLS beyond the local default:** the anon-insert/anon-select posture in §3 is an
   experiment convenience. For real users scope rows to an authenticated owner and drop the
   blanket anon policies.
8. **Secrets:** move provider/API keys out of `.env`/compose into a real secret store per
   environment; keep the service-role key server-only, always.
9. **Trace tables as a platform concern:** `*_events` grows fast — add retention/TTL, and treat
   the per-hop token usage as the basis for cost dashboards and budget alerts.
10. **Standardize observability:** one trace schema across all features means one stepper
    component and one dashboard, not N.

Everything else (Realtime subscription shape, the trace stepper, the finalize-on-error pattern,
the atomic claim) is directly copy-pasteable across features and products.

---

## 8. Reality check (so estimates are honest)

On this stack the work is **not** dominated by writing feature code — it's the §4 landmines
(environment, grants, provider quirks, serialization, delivery) and **end-to-end verification**.
Budget accordingly: with §4 pre-empted and §3 templatized, a new feature on an already-stood-up
stack is hours, not days. The first feature on a *fresh* stack is dominated by §1–§2 and the
landmines, so front-load those.

---

## 9. Adopt in a new repo (the activation kit)

**A doc in `docs/` binds nothing on its own** — a fresh agent only auto-loads the repo's *root*
agent file. Activation (making an agent obey this playbook) is the **consumer repo's job**. Make
it trivial and consistent:

1. **Copy `docs/PLAYBOOK.md`** into the new repo's `docs/`.
2. **Add the block below to the repo's root `AGENTS.md`** (the file agents auto-load; for Claude
   Code you may name it `CLAUDE.md` — keep one canonical file). This is what turns the playbook
   from reference into governance.
3. **Fill the blanks** (`<PROJECT>`, ports/paths) and delete any guardrail that genuinely doesn't
   apply. Keep the substance in the playbook — the root file stays a thin, binding pointer so the
   rules live and version in one place.

```markdown
# <PROJECT> — Agent Contract

**Governance:** `docs/PLAYBOOK.md` is BINDING, especially its "Guardrails — MUST / MUST-NOT"
section. Load the relevant part before acting — don't ingest the whole doc every turn:
- Adding/changing a feature      → read PLAYBOOK §3 (The Feature Recipe).
- Debugging env/provider/orchestration → read PLAYBOOK §4 (The Landmine Table).
- Change touching >1 component, a service, or a security/data/deploy boundary → check
  `docs/adrs/` and add an ADR.

**Non-negotiables (full list in the playbook's Guardrails section):**
- Branch off `main`; open a PR; never reuse a merged branch.
- Never commit `.env`/secrets; the browser uses the Supabase anon key only.
- New run/trace tables: include anon+authenticated grants, the service_role grant, and the
  realtime publication — then verify PostgREST access.
- Workflows deterministic; all non-determinism in activities; wrap run() to finalize `error`.
- Verify end-to-end (insert → poll `done`), not on CI-green.
- Confirm before provisioning cloud resources or other costly/outward-facing actions.

**Stack:** Supabase + Temporal + Vite/React + a hosted LLM. Local run + gotchas: ONBOARDING and
PLAYBOOK §1/§4.
```

That keeps activation a **paste + two blanks**, not a rewrite — and the responsibility boundary
stays exactly where it belongs: the playbook carries the knowledge and guardrails; the consumer
repo declares them binding.

---

## Worked example (this repo)

This repository is one concrete implementation of the above (two features on the stack). For a
filled-in version of every step and the specific decisions taken:

- [`docs/architecture/product-architecture.md`](architecture/product-architecture.md) — the shape, wired up.
- [`docs/adrs/`](adrs/) — the binding decisions (model hosting, the reliability-vs-autonomy dial as shipped, testing, deployment posture).
- [`docs/specs/`](specs/) — per-feature detailed designs.
- [`ONBOARDING.md`](../ONBOARDING.md) — get this repo's stack running.
