-- Study Planner (ADR-0008 plug-in). Owner-scoped from creation (ADR-0007): a run row is
-- owned by the authenticated user who created it; a user only sees/inserts their own. The
-- worker writes results with the service role (bypasses RLS). No experiment-open anon
-- policies — this table is born post-ADR-0007.

create table if not exists study_plans (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid default auth.uid(),
  input       jsonb not null default '{}',   -- {target_field, institution_type, prior_qualification, timeframe, interests, canton, freeform, persona}
  status      text not null default 'pending',
  result      jsonb,                          -- {summary, weekly_steps[], how_to_study[], resources[], panel[], persona, confidence}
  error       text,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  constraint chk_study_plan_status check (status in ('pending','running','done','error')),
  constraint chk_study_plan_input_size check (length(input::text) <= 8192)
);

create index if not exists idx_study_plans_status on study_plans(status) where status = 'pending';

alter table study_plans enable row level security;
create policy study_plans_owner_select on study_plans for select to authenticated using (auth.uid() = user_id);
create policy study_plans_owner_insert on study_plans for insert to authenticated with check (auth.uid() = user_id);
grant select, insert on study_plans to authenticated;
grant all privileges on study_plans to service_role;
alter publication supabase_realtime add table study_plans;

create table if not exists study_plan_events (
  id         uuid primary key default gen_random_uuid(),
  plan_id    uuid not null references study_plans(id) on delete cascade,
  seq        int not null,
  stage      text not null,
  label      text not null,
  detail     jsonb,
  tokens     int,
  created_at timestamptz not null default now(),
  constraint uq_study_plan_event_seq unique (plan_id, seq)
);

create index if not exists idx_study_plan_events on study_plan_events(plan_id, seq);

alter table study_plan_events enable row level security;
create policy study_plan_events_owner_select on study_plan_events for select to authenticated using (
  exists (select 1 from study_plans p where p.id = study_plan_events.plan_id and p.user_id = auth.uid())
);
grant select on study_plan_events to authenticated;
grant all privileges on study_plan_events to service_role;
alter publication supabase_realtime add table study_plan_events;
