-- Trace events for the Gains Plan panel, so the frontend can show the multi-agent
-- steps + token usage live (same shape as gains_events for the check).

create table if not exists gains_plan_events (
  id          uuid primary key default gen_random_uuid(),
  plan_id     uuid not null,
  seq         int not null,
  stage       text not null,
  label       text not null,
  detail      jsonb,
  tokens      int,
  created_at  timestamptz not null default now()
);

create index if not exists idx_gains_plan_events_plan on gains_plan_events(plan_id, seq);

alter table gains_plan_events enable row level security;
create policy gains_plan_events_anon_select on gains_plan_events for select to anon using (true);
grant select on gains_plan_events to anon, authenticated;
grant all privileges on gains_plan_events to service_role;
alter publication supabase_realtime add table gains_plan_events;
