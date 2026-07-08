-- SEC-2 (denial-of-wallet): cap the serialized size of the anon-writable `input`
-- jsonb on both run tables. Any holder of the public anon key can insert pending
-- rows that the poller auto-claims and dispatches to a paid Azure OpenAI workflow;
-- bounding the payload size limits per-row abuse. 8 KiB is ample for the real
-- payload (a handful of numbers + short freeform text).
--
-- length(input::text) is IMMUTABLE (usable in a check constraint); pg_column_size
-- is not. Wrapped in do-blocks so the migration is idempotent / re-runnable.

do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'chk_gains_checks_input_size'
  ) then
    alter table gains_checks
      add constraint chk_gains_checks_input_size
      check (length(input::text) <= 8192);
  end if;
end $$;

do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'chk_gains_plans_input_size'
  ) then
    alter table gains_plans
      add constraint chk_gains_plans_input_size
      check (length(input::text) <= 8192);
  end if;
end $$;
