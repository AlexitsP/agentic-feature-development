# ADR-0007: Owner-scoped RLS + auth (proposal for SEC-1)

**Status:** Proposed
**Date:** 2026-07-08
**Deciders:** Patrik Alexits (direction), Claude (proposal)
**Technical Story:** SEC-1 (High) — open RLS + no app auth; the gate for leaving local scope

## Context

The three run tables ship with **open, un-scoped RLS** and the frontend authenticates with the
**public anon key only** — there is no sign-in and no per-user boundary.

Concretely, in the current migrations:

- `gains_checks` and `gains_plans`: `anon` may `SELECT` *and* `INSERT` via
  `using (true)` / `with check (true)`, plus a blanket `grant select, insert ... to anon`
  (`supabase/migrations/20260707140000_gains_checks.sql:22-25`,
  `supabase/migrations/20260708120000_gains_plans.sql:22-25`).
- `gains_events` and `gains_plan_events`: `anon` may `SELECT` any row via `using (true)`
  (`supabase/migrations/20260707150000_gains_events.sql:20-22`,
  `supabase/migrations/20260708130000_gains_plan_events.sql:18-19`).
- The browser client is created with the anon key and no session gate
  (`frontend/src/data/supabase.ts:8-19`); `frontend/src/routes/gains.tsx` inserts pending rows
  and subscribes to Realtime with that key. There is no `signIn` / `getUser` / `session` usage
  anywhere in `frontend/src`.
- The worker writes results with the **service-role key**, which bypasses RLS entirely
  (`temporal/src/runs/poller.py:25`) — this is the intended privileged write path and is not part
  of the problem.

**Why this is fine today.** This is the documented local-only experiment default. Per
[ADR-0004](./0004-deployment-posture-local-only.md) the stack runs only on the operator's machine
at `localhost:3000`; it is not hosted, and CLAUDE.md records the same local-only posture. The data
is **non-sensitive, self-entered fitness numbers** (weight, body-fat %, calories, protein). With a
single local user and no public network exposure, "any anon can read/write any row" has no real
victim: there is exactly one user and one browser, and the DB is not reachable from the internet.
Open RLS keeps the demo's insert → poller → workflow → Realtime loop trivial to reason about.

**Why it becomes Critical if deployed.** The repo still ships Helm charts that wire the app for a
cluster (`charts/app/values.yaml`), so a deploy is a plausible future step, not hypothetical. The
moment this stack is reachable by more than one user — the intended Azure direction in ADR-0004, or
anyone applying the charts — open RLS means **every user can read and modify every other user's
rows**, and `with check (true)` lets any holder of the (client-shipped, therefore public) anon key
write arbitrary `pending` rows. There is no tenant boundary to add later "for free": it has to be
designed into the data model and policies. That is what this ADR proposes, as the explicit **gate
for leaving local scope**.

## Decision

> **Proposed, not accepted.** This records the intended design so a future multi-user/deploy
> decision has something to implement and review against. It does **not** change any code or
> migration now; the local-only default in ADR-0004 stands until superseded.

Introduce **Supabase Auth sign-in** and **owner-scoped RLS**, and make them the mandatory gate that
must be in place *before* the stack is exposed to more than one user.

**Data model.** Add a `user_id uuid not null default auth.uid()` column to `gains_checks`,
`gains_plans`, and `gains_events`. On the two run tables the default captures the signed-in caller
automatically on `INSERT` (no client change needed to set it). The event tables already carry a
parent FK (`check_id` / `plan_id`); scope them either by their own `user_id` or by a join to the
parent — the migration below adds `user_id` to `gains_events` for a uniform, index-friendly policy,
and scopes `gains_plan_events` through its `plan_id` parent to avoid a redundant column (it has no
FK today, so a join-based policy is added alongside a real FK).

**Policies.** Replace the blanket `anon` policies with **owner-scoped `authenticated` policies**:

- `select`/`insert` on the run tables gated by `auth.uid() = user_id`
  (insert also enforced via `with check`).
- `select` on the event tables gated by ownership of the parent run row.
- **Drop the blanket `anon` grants and `anon` policies.** `anon` should have no access to run data
  once auth is required.

**Worker unchanged.** The worker keeps writing with the service-role key, which bypasses RLS, so
result-writing and event emission are unaffected. It must set `user_id` when it inserts event rows
(copying it from the parent run row it is processing) so owner-scoped reads see the trace.

**Frontend.** Add a minimal Supabase Auth sign-in (email+password or magic link — `[auth]` is
already `enabled = true` with `enable_signup = true` in `supabase/config.toml`). Gate the `/gains`
route behind a session; `supabase-js` already persists/refreshes the session
(`frontend/src/data/supabase.ts:14-18`), so authenticated inserts and Realtime subscriptions carry
the user's JWT automatically. Inserts stop sending `user_id` explicitly and let the column default
resolve `auth.uid()`.

### Concrete migration path

Add **one new timestamped migration** (e.g. `supabase/migrations/20260709xxxxxx_owner_scoped_rls.sql`),
never edit the existing `gains_*` migrations. Sketch:

```sql
-- 1. Ownership column (defaults to the signed-in caller on insert)
alter table gains_checks add column if not exists user_id uuid not null default auth.uid();
alter table gains_plans  add column if not exists user_id uuid not null default auth.uid();
alter table gains_events add column if not exists user_id uuid not null default auth.uid();

-- 2. Give gains_plan_events a real parent FK (it has none today) for join-based scoping
alter table gains_plan_events
  add constraint fk_gains_plan_events_plan
  foreign key (plan_id) references gains_plans(id) on delete cascade;

-- 3. Drop the open anon policies + grants
drop policy if exists gains_checks_anon_select      on gains_checks;
drop policy if exists gains_checks_anon_insert      on gains_checks;
drop policy if exists gains_plans_anon_select       on gains_plans;
drop policy if exists gains_plans_anon_insert       on gains_plans;
drop policy if exists gains_events_anon_select      on gains_events;
drop policy if exists gains_plan_events_anon_select on gains_plan_events;
revoke select, insert on gains_checks, gains_plans from anon;
revoke select          on gains_events, gains_plan_events from anon;

-- 4. Owner-scoped policies for authenticated users
create policy gains_checks_owner_sel on gains_checks for select to authenticated
  using (auth.uid() = user_id);
create policy gains_checks_owner_ins on gains_checks for insert to authenticated
  with check (auth.uid() = user_id);
create policy gains_plans_owner_sel  on gains_plans  for select to authenticated
  using (auth.uid() = user_id);
create policy gains_plans_owner_ins  on gains_plans  for insert to authenticated
  with check (auth.uid() = user_id);
create policy gains_events_owner_sel on gains_events for select to authenticated
  using (auth.uid() = user_id);
create policy gains_plan_events_owner_sel on gains_plan_events for select to authenticated
  using (exists (
    select 1 from gains_plans p
    where p.id = gains_plan_events.plan_id and p.user_id = auth.uid()
  ));
```

**Existing rows / backfill.** For a local dev DB the pragmatic path is a `db reset` (there is no
production data to preserve — ADR-0004). If any run rows must be kept, backfill `user_id` from a
seeded auth user before adding the `not null` constraint. Because the demo has never had real users,
**requiring auth from the cutover** (no anonymous fallback) is preferred over a lenient migration:
partial owner scoping with an anon escape hatch would defeat the boundary.

### Related pre-prod hardening (noted, not designed here)

These are the *other* things that must be resolved on the same "leaving local scope" cutover. They
are out of scope for this ADR beyond flagging them:

- **SEC-4 — transport security.** The worker → Supabase call in-cluster is plaintext
  `http://supabase:8000` (`charts/app/values.yaml:108,110,209`). A multi-user/prod deploy needs
  HTTPS or mesh/mTLS on that hop so the service-role key and JWTs are not sent in the clear.
- **Frontend production image.** `frontend/Dockerfile` runs the **Vite dev server**
  (`CMD ["npm","run","dev", ...]`), which is not a production server. A deploy needs a multi-stage
  static build (build → serve via nginx/static host). Note this **bakes `VITE_*` at build time**:
  the anon key and Supabase URL are compiled into the client bundle, which is correct for the anon
  key (public by design) but means the build must never receive the service-role key.
- **Rate-limiting the anon → LLM path.** Partially addressed already: PR #20 (SEC-2) added an 8 KiB
  `input` size cap (`supabase/migrations/20260708160000_gains_input_size_cap.sql`) and a poller
  concurrency bound, limiting per-row denial-of-wallet. Requiring auth (this ADR) further narrows
  who can enqueue work; an edge/count rate-limit is still the complete answer for prod.

## Consequences

### Positive
- **A real tenant boundary.** With auth + `auth.uid() = user_id`, one user cannot read or write
  another's runs. This is the single change that makes a multi-user deploy safe with respect to
  SEC-1.
- The privileged write path is unchanged — the worker's service-role writes still bypass RLS, so no
  workflow code changes for result/event persistence.
- `default auth.uid()` means the frontend does not have to set `user_id`, reducing the chance of a
  client bug that mis-attributes rows.

### Negative
- **Adds a sign-in step** to what is currently a zero-friction demo; the `/gains` route becomes
  gated. Slightly more frontend work (auth UI, session handling, sign-out).
- The event tables need `user_id` propagation (or parent-join policies), and the worker must set
  `user_id` on event inserts — a small backend change.
- Requiring auth from the cutover breaks the "just open localhost:3000" flow unless a local seeded
  user is provided for dev.

### Neutral
- No effect while local-only: today's single-user demo behaves the same until this is adopted.
- `[auth]` is already enabled in `supabase/config.toml`, so no new service is introduced — this uses
  the existing Supabase Auth that ships with the local stack.

## Alternatives considered

- **Keep anon + local-only (status quo).** Correct *today* and explicitly chosen by ADR-0004. Kept
  as the default; this ADR only defines the gate for when that assumption no longer holds. Rejected
  as a *deploy* posture because open RLS on a reachable stack is Critical.
- **Edge rate-limit only (no auth, no owner scoping).** Bounds denial-of-wallet abuse but provides
  **no confidentiality/integrity boundary** — every user still reads/writes every row. Insufficient
  for multi-user; rejected as a substitute (it is complementary, see SEC-2/edge notes above).
- **Scope events by parent-join only (no `user_id` on `gains_events`).** Viable and avoids a column,
  but a per-row `user_id` gives simpler, index-friendly policies on the higher-traffic check-events
  table; chosen the hybrid above (column on `gains_events`, join on `gains_plan_events`).

## Related Decisions
- Supersedes the open-RLS assumption **only on deploy**; the local-only default remains
  [ADR-0004](./0004-deployment-posture-local-only.md). Adopting this ADR would accompany any ADR
  that accepts a concrete hosted target.
- Sits on the data substrate from
  [ADR-0001](./0001-entity-insights-workflow-and-model-hosting.md) and the run-row pattern kept in
  [ADR-0006](./0006-trim-to-gains-only-minimal-repo.md).

## Evidence
- Open RLS / grants: `supabase/migrations/20260707140000_gains_checks.sql:22-25`,
  `supabase/migrations/20260707150000_gains_events.sql:20-22`,
  `supabase/migrations/20260708120000_gains_plans.sql:22-25`,
  `supabase/migrations/20260708130000_gains_plan_events.sql:18-19`.
- Anon-key-only client, no session gate: `frontend/src/data/supabase.ts:8-19`;
  no auth usage in `frontend/src` (grep for `signIn`/`getUser`/`session` → none).
- Service-role worker write path (bypasses RLS): `temporal/src/runs/poller.py:25`.
- Auth already enabled in the local stack: `supabase/config.toml` `[auth] enabled = true`,
  `enable_signup = true`.
- Deployable charts exist / SEC-4 plaintext hop: `charts/app/values.yaml:108,110,209`.
- Dev-server production image: `frontend/Dockerfile` (`CMD ["npm","run","dev", ...]`).
- SEC-2 partial rate-limit already merged: `supabase/migrations/20260708160000_gains_input_size_cap.sql` (PR #20).
- Local-only posture: [ADR-0004](./0004-deployment-posture-local-only.md), CLAUDE.md.
