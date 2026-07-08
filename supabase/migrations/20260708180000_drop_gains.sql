-- Repurpose to the "Plan my studies" app: the Gains Check feature is removed.
-- Drop its tables (this also removes them from the realtime publication). Append-only
-- migration — the original gains_* create migrations remain as history.

drop table if exists gains_plan_events cascade;
drop table if exists gains_events cascade;
drop table if exists gains_plans cascade;
drop table if exists gains_checks cascade;
