-- Gains Check: fun agentic demo. A run row carries the tracked inputs; the
-- agent judges "are you doing it right?", fetches a hype/shame GIF on the fly,
-- and returns a verdict the frontend renders (GIF + TTS line + flashing text).

create table if not exists gains_checks (
  id          uuid primary key default gen_random_uuid(),
  input       jsonb not null default '{}',   -- {weight_kg, body_fat_pct, calories, protein_g}
  status      text not null default 'pending',  -- pending | running | done | error
  result      jsonb,                         -- {passed, headline, spoken_line, gif_url, sound, reason, steps}
  error       text,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  constraint chk_gains_status check (status in ('pending','running','done','error'))
);

create index if not exists idx_gains_checks_status on gains_checks(status) where status = 'pending';

alter table gains_checks enable row level security;

-- Local experiment: anon may create a check and read results (for Realtime).
-- The worker writes with the service role, which bypasses RLS.
create policy gains_checks_anon_select on gains_checks for select to anon using (true);
create policy gains_checks_anon_insert on gains_checks for insert to anon with check (true);

grant select, insert on gains_checks to anon, authenticated;
grant all privileges on gains_checks to service_role;

alter publication supabase_realtime add table gains_checks;
