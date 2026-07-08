-- Program Evaluator (education advisor platform, ADR-0008): a run row carries the
-- prospective student's situation; the EvaluationWorkflow assesses higher-education fit,
-- suggests study options grounded in official Swiss sources, and finalizes the row with a
-- confidence badge (inside `result`).

create table if not exists program_evaluations (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid,                         -- owner; nullable during the internal experiment
  input       jsonb not null default '{}',  -- {interests, prior_qualification, strong_subjects, target_field, canton, language, freeform, persona}
  status      text not null default 'pending',  -- pending | running | done | error
  result      jsonb,                         -- {assessment, suggested_options[], resources[], persona, confidence}
  error       text,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  constraint chk_program_eval_status check (status in ('pending','running','done','error')),
  constraint chk_program_eval_input_size check (length(input::text) <= 8192)
);

create index if not exists idx_program_evaluations_status on program_evaluations(status) where status = 'pending';

alter table program_evaluations enable row level security;

-- Internal experiment (synthetic profiles only): anon may create + read (for Realtime).
-- Owner-scoped RLS (auth.uid() = user_id) is GATED on ADR-0007 and is a prerequisite
-- before any real student data. The worker writes with the service role (bypasses RLS).
create policy program_evaluations_anon_select on program_evaluations for select to anon using (true);
create policy program_evaluations_anon_insert on program_evaluations for insert to anon with check (true);

grant select, insert on program_evaluations to anon, authenticated;
grant all privileges on program_evaluations to service_role;

alter publication supabase_realtime add table program_evaluations;

-- Trace events for the live stepper (same shape as the gains_* events tables).
create table if not exists program_evaluation_events (
  id            uuid primary key default gen_random_uuid(),
  evaluation_id uuid not null references program_evaluations(id) on delete cascade,
  seq           int not null,
  stage         text not null,          -- dispatched | reasoning | finalized
  label         text not null,
  detail        jsonb,
  tokens        int,
  created_at    timestamptz not null default now(),
  constraint uq_program_eval_event_seq unique (evaluation_id, seq)
);

create index if not exists idx_program_evaluation_events on program_evaluation_events(evaluation_id, seq);

alter table program_evaluation_events enable row level security;
create policy program_evaluation_events_anon_select on program_evaluation_events for select to anon using (true);

grant select on program_evaluation_events to anon, authenticated;
grant all privileges on program_evaluation_events to service_role;

alter publication supabase_realtime add table program_evaluation_events;
