-- Pipeline trace events for the Gains Check demo. The workflow emits one row per
-- hop (dispatch, model reasoning + tokens, tool call, verdict saved); the frontend
-- streams them via Realtime into a stepper.

create table if not exists gains_events (
  id         uuid primary key default gen_random_uuid(),
  check_id   uuid not null references gains_checks(id) on delete cascade,
  seq        int not null,
  stage      text not null,          -- dispatched | reasoning | tool | finalized
  label      text not null,          -- human label, e.g. "Azure OpenAI · gpt-5-mini"
  detail     jsonb,                  -- stage-specific detail (query, verdict, ...)
  tokens     int,                    -- model tokens used this hop (nullable)
  created_at timestamptz not null default now(),
  constraint uq_gains_event_seq unique (check_id, seq)
);

create index if not exists idx_gains_events_check on gains_events(check_id, seq);

alter table gains_events enable row level security;
create policy gains_events_anon_select on gains_events for select to anon using (true);

grant select on gains_events to anon, authenticated;
grant all privileges on gains_events to service_role;

alter publication supabase_realtime add table gains_events;
