-- Entity Insights Assistant: ephemeral run + step tables (ADR-0001).
-- Run-scoped state for the agentic loop; not a saved-insights history feature.

create table if not exists insight_runs (
  id          uuid primary key default gen_random_uuid(),
  entity_id   uuid not null references entities(id) on delete cascade,
  question    text,
  status      text not null default 'pending',  -- pending | running | done | error
  result      jsonb,
  error       text,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  constraint chk_insight_status check (status in ('pending','running','done','error'))
);

create table if not exists insight_steps (
  id             uuid primary key default gen_random_uuid(),
  run_id         uuid not null references insight_runs(id) on delete cascade,
  seq            int not null,
  tool           text not null,
  args           jsonb not null default '{}',
  result_preview jsonb,
  created_at     timestamptz not null default now(),
  constraint uq_insight_step_seq unique (run_id, seq)
);

create index if not exists idx_insight_steps_run on insight_steps(run_id, seq);
create index if not exists idx_insight_runs_status on insight_runs(status) where status = 'pending';

-- RLS. Local experiment: anon may create a run and read runs/steps (needed for
-- Realtime). The worker writes with the service role, which bypasses RLS.
alter table insight_runs enable row level security;
alter table insight_steps enable row level security;

create policy insight_runs_anon_select on insight_runs for select to anon using (true);
create policy insight_runs_anon_insert on insight_runs for insert to anon with check (true);
create policy insight_steps_anon_select on insight_steps for select to anon using (true);

-- Stream inserts/updates to the frontend via Supabase Realtime.
alter publication supabase_realtime add table insight_runs;
alter publication supabase_realtime add table insight_steps;

-- API-role privileges. The base template created its core tables without
-- granting the PostgREST roles, so neither the frontend (anon) nor the worker
-- (service_role) could read them. Grant what this feature and its demo need.
grant select on entities, entity_versions, entity_facts, fact_types to anon, authenticated, service_role;
grant select, insert on insight_runs to anon, authenticated;
grant select on insight_steps to anon, authenticated;
grant all privileges on insight_runs to service_role;
grant all privileges on insight_steps to service_role;
