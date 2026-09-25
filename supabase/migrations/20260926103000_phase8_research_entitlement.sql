insert into public.billing_features(id,name,description,category)
values ('advanced_research','Research Workspaces & Advanced Research','Persistent research workspaces, custom dashboards, scorecards, cross-asset analysis and strategy diagnosis.','research')
on conflict (id) do update set name=excluded.name,description=excluded.description,category=excluded.category;
insert into public.billing_plan_features(plan_id,feature_id,enabled)
values ('free','advanced_research',false),('pro','advanced_research',true),('premium','advanced_research',true)
on conflict (plan_id,feature_id) do update set enabled=excluded.enabled;