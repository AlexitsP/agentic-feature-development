-- Demo seed for the Entity Insights Assistant.
insert into fact_types (key, label, description, unit) values
  ('mrr',          'Monthly Recurring Revenue', 'Current MRR',            'USD'),
  ('active_users', 'Active Users',              'Count of active users', 'count')
on conflict (key) do nothing;

do $$
declare eid uuid;
begin
  insert into entities (entity_type, source_record_id)
    values ('company', 'demo-acme')
    on conflict (entity_type, source_record_id) do update set updated_at = now()
    returning id into eid;

  insert into entity_versions (entity_id, version_number, data, is_current)
    values (eid, 1, '{"name":"Acme Corp","stage":"growth","segment":"SMB"}'::jsonb, true)
    on conflict (entity_id, version_number) do nothing;

  insert into entity_facts (entity_id, fact_type_id, value)
    select eid, ft.id, v.val
    from fact_types ft
    join (values ('mrr', 42000::numeric), ('active_users', 1875::numeric)) as v(key, val)
      on v.key = ft.key
    on conflict (entity_id, fact_type_id, dimension_id) do nothing;
end $$;
