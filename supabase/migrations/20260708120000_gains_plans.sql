-- Gains Plan: after a verdict, the user picks a goal and an agent drafts a basic
-- starter plan (targets + weekly steps + curated resource links). Same run-row
-- pattern as gains_checks: browser inserts pending -> poller -> workflow -> result.

create table if not exists gains_plans (
  id          uuid primary key default gen_random_uuid(),
  input       jsonb not null default '{}',   -- {goal, goal_detail, weight_kg, body_fat_pct, calories, protein_g, freeform, passed, fail_kind, persona, mode}
  status      text not null default 'pending',  -- pending | running | done | error
  result      jsonb,                         -- {goal_label, summary, calorie_guidance, protein_guidance, training_focus, weekly_steps[], resources[{title,url}]}
  error       text,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  constraint chk_gains_plan_status check (status in ('pending','running','done','error'))
);

create index if not exists idx_gains_plans_status on gains_plans(status) where status = 'pending';

alter table gains_plans enable row level security;

-- Local experiment: anon may create a plan request and read results (for Realtime).
-- The worker writes with the service role, which bypasses RLS.
create policy gains_plans_anon_select on gains_plans for select to anon using (true);
create policy gains_plans_anon_insert on gains_plans for insert to anon with check (true);

grant select, insert on gains_plans to anon, authenticated;
grant all privileges on gains_plans to service_role;

alter publication supabase_realtime add table gains_plans;
