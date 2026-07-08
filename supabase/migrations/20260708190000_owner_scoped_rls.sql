-- ADR-0007: replace the experiment-open anon RLS with owner-scoped, authenticated
-- access. Each run row is owned by the authenticated user who created it (user_id
-- defaults to auth.uid()); a user may only see/insert their own rows. The worker keeps
-- writing with the service role (which bypasses RLS). Anonymous Supabase Auth users
-- each get their own auth.uid(), so the app still works without a full sign-up flow
-- while giving real per-user isolation (closes SEC-1's blanket-anon read/write).

-- program_evaluations already has a (nullable, defaultless) user_id from its create
-- migration, so ADD COLUMN IF NOT EXISTS would skip and leave no default. Set the
-- default explicitly so authenticated inserts auto-capture the caller (and the
-- with-check below passes without the client sending user_id).
alter table program_evaluations add column if not exists user_id uuid;
alter table program_evaluations alter column user_id set default auth.uid();

drop policy if exists program_evaluations_anon_select on program_evaluations;
drop policy if exists program_evaluations_anon_insert on program_evaluations;

create policy program_evaluations_owner_select on program_evaluations
  for select to authenticated using (auth.uid() = user_id);
create policy program_evaluations_owner_insert on program_evaluations
  for insert to authenticated with check (auth.uid() = user_id);

revoke select, insert on program_evaluations from anon;
grant select, insert on program_evaluations to authenticated;

-- Trace events are owned transitively via their parent evaluation (join-based policy).
drop policy if exists program_evaluation_events_anon_select on program_evaluation_events;
create policy program_evaluation_events_owner_select on program_evaluation_events
  for select to authenticated using (
    exists (
      select 1 from program_evaluations e
      where e.id = program_evaluation_events.evaluation_id
        and e.user_id = auth.uid()
    )
  );
revoke select on program_evaluation_events from anon;
grant select on program_evaluation_events to authenticated;
