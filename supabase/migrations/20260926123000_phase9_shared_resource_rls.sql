-- Phase 9 follow-up: enforce shared-resource permissions at the data layer.

create or replace function private.user_workspace_permission(p_workspace_id uuid)
returns text
language sql
stable
security definer
set search_path=''
as $$
  select case
    when max(case rs.permission when 'ADMIN' then 3 when 'EDIT' then 2 when 'VIEW' then 1 else 0 end) = 3 then 'ADMIN'
    when max(case rs.permission when 'ADMIN' then 3 when 'EDIT' then 2 when 'VIEW' then 1 else 0 end) = 2 then 'EDIT'
    when max(case rs.permission when 'ADMIN' then 3 when 'EDIT' then 2 when 'VIEW' then 1 else 0 end) = 1 then 'VIEW'
    else null
  end
  from public.resource_shares rs
  where rs.resource_type='WORKSPACE'
    and rs.resource_id=p_workspace_id
    and (select private.user_is_org_member(rs.organization_id));
$$;
revoke execute on function private.user_workspace_permission(uuid) from public,anon;
grant execute on function private.user_workspace_permission(uuid) to authenticated;

-- Workspaces and child research artifacts.
drop policy if exists research_workspaces_own on public.research_workspaces;
create policy research_workspaces_select_shared on public.research_workspaces for select to authenticated
using ((select auth.uid())=user_id or (select private.user_workspace_permission(id)) is not null);
create policy research_workspaces_insert_owner on public.research_workspaces for insert to authenticated
with check ((select auth.uid())=user_id);
create policy research_workspaces_update_shared on public.research_workspaces for update to authenticated
using ((select auth.uid())=user_id or (select private.user_workspace_permission(id)) in ('EDIT','ADMIN'))
with check ((select auth.uid())=user_id or (select private.user_workspace_permission(id)) in ('EDIT','ADMIN'));
create policy research_workspaces_delete_shared on public.research_workspaces for delete to authenticated
using ((select auth.uid())=user_id or (select private.user_workspace_permission(id)) in ('EDIT','ADMIN'));

drop policy if exists research_workspace_assets_own on public.research_workspace_assets;
create policy research_workspace_assets_select_shared on public.research_workspace_assets for select to authenticated
using ((select auth.uid())=user_id or (select private.user_workspace_permission(workspace_id)) is not null);
create policy research_workspace_assets_insert_shared on public.research_workspace_assets for insert to authenticated
with check ((select auth.uid())=user_id and ((select private.user_workspace_permission(workspace_id)) in ('EDIT','ADMIN') or exists(select 1 from public.research_workspaces w where w.id=workspace_id and w.user_id=(select auth.uid()))));
create policy research_workspace_assets_update_shared on public.research_workspace_assets for update to authenticated
using ((select auth.uid())=user_id and ((select private.user_workspace_permission(workspace_id)) in ('EDIT','ADMIN') or exists(select 1 from public.research_workspaces w where w.id=workspace_id and w.user_id=(select auth.uid()))))
with check ((select auth.uid())=user_id and ((select private.user_workspace_permission(workspace_id)) in ('EDIT','ADMIN') or exists(select 1 from public.research_workspaces w where w.id=workspace_id and w.user_id=(select auth.uid()))));
create policy research_workspace_assets_delete_shared on public.research_workspace_assets for delete to authenticated
using ((select auth.uid())=user_id and ((select private.user_workspace_permission(workspace_id)) in ('EDIT','ADMIN') or exists(select 1 from public.research_workspaces w where w.id=workspace_id and w.user_id=(select auth.uid()))));

drop policy if exists research_workspace_dashboards_own on public.research_workspace_dashboards;
create policy research_workspace_dashboards_select_shared on public.research_workspace_dashboards for select to authenticated
using ((select auth.uid())=user_id or (select private.user_workspace_permission(workspace_id)) is not null);
create policy research_workspace_dashboards_insert_shared on public.research_workspace_dashboards for insert to authenticated
with check ((select auth.uid())=user_id and ((select private.user_workspace_permission(workspace_id)) in ('EDIT','ADMIN') or exists(select 1 from public.research_workspaces w where w.id=workspace_id and w.user_id=(select auth.uid()))));
create policy research_workspace_dashboards_update_shared on public.research_workspace_dashboards for update to authenticated
using ((select auth.uid())=user_id and ((select private.user_workspace_permission(workspace_id)) in ('EDIT','ADMIN') or exists(select 1 from public.research_workspaces w where w.id=workspace_id and w.user_id=(select auth.uid()))))
with check ((select auth.uid())=user_id and ((select private.user_workspace_permission(workspace_id)) in ('EDIT','ADMIN') or exists(select 1 from public.research_workspaces w where w.id=workspace_id and w.user_id=(select auth.uid()))));
create policy research_workspace_dashboards_delete_shared on public.research_workspace_dashboards for delete to authenticated
using ((select auth.uid())=user_id and ((select private.user_workspace_permission(workspace_id)) in ('EDIT','ADMIN') or exists(select 1 from public.research_workspaces w where w.id=workspace_id and w.user_id=(select auth.uid()))));

drop policy if exists research_workspace_links_own on public.research_workspace_links;
create policy research_workspace_links_select_shared on public.research_workspace_links for select to authenticated
using ((select auth.uid())=user_id or (select private.user_workspace_permission(workspace_id)) is not null);
create policy research_workspace_links_insert_shared on public.research_workspace_links for insert to authenticated
with check ((select auth.uid())=user_id and ((select private.user_workspace_permission(workspace_id)) in ('EDIT','ADMIN') or exists(select 1 from public.research_workspaces w where w.id=workspace_id and w.user_id=(select auth.uid()))));
create policy research_workspace_links_delete_shared on public.research_workspace_links for delete to authenticated
using ((select auth.uid())=user_id and ((select private.user_workspace_permission(workspace_id)) in ('EDIT','ADMIN') or exists(select 1 from public.research_workspaces w where w.id=workspace_id and w.user_id=(select auth.uid()))));

drop policy if exists research_scorecards_own on public.research_scorecards;
create policy research_scorecards_select_shared on public.research_scorecards for select to authenticated
using ((select auth.uid())=user_id or (select private.user_workspace_permission(workspace_id)) is not null);
create policy research_scorecards_insert_shared on public.research_scorecards for insert to authenticated
with check ((select auth.uid())=user_id and ((select private.user_workspace_permission(workspace_id)) in ('EDIT','ADMIN') or exists(select 1 from public.research_workspaces w where w.id=workspace_id and w.user_id=(select auth.uid()))));
create policy research_scorecards_update_shared on public.research_scorecards for update to authenticated
using ((select auth.uid())=user_id and ((select private.user_workspace_permission(workspace_id)) in ('EDIT','ADMIN') or exists(select 1 from public.research_workspaces w where w.id=workspace_id and w.user_id=(select auth.uid()))))
with check ((select auth.uid())=user_id and ((select private.user_workspace_permission(workspace_id)) in ('EDIT','ADMIN') or exists(select 1 from public.research_workspaces w where w.id=workspace_id and w.user_id=(select auth.uid()))));
create policy research_scorecards_delete_shared on public.research_scorecards for delete to authenticated
using ((select auth.uid())=user_id and ((select private.user_workspace_permission(workspace_id)) in ('EDIT','ADMIN') or exists(select 1 from public.research_workspaces w where w.id=workspace_id and w.user_id=(select auth.uid()))));

drop policy if exists research_automation_rules_own on public.research_automation_rules;
create policy research_automation_rules_select_shared on public.research_automation_rules for select to authenticated
using ((select auth.uid())=user_id or (select private.user_workspace_permission(workspace_id)) is not null);
create policy research_automation_rules_insert_shared on public.research_automation_rules for insert to authenticated
with check ((select auth.uid())=user_id and ((select private.user_workspace_permission(workspace_id)) in ('EDIT','ADMIN') or exists(select 1 from public.research_workspaces w where w.id=workspace_id and w.user_id=(select auth.uid()))));
create policy research_automation_rules_update_shared on public.research_automation_rules for update to authenticated
using ((select auth.uid())=user_id and ((select private.user_workspace_permission(workspace_id)) in ('EDIT','ADMIN') or exists(select 1 from public.research_workspaces w where w.id=workspace_id and w.user_id=(select auth.uid()))))
with check ((select auth.uid())=user_id and ((select private.user_workspace_permission(workspace_id)) in ('EDIT','ADMIN') or exists(select 1 from public.research_workspaces w where w.id=workspace_id and w.user_id=(select auth.uid()))));
create policy research_automation_rules_delete_shared on public.research_automation_rules for delete to authenticated
using ((select auth.uid())=user_id and ((select private.user_workspace_permission(workspace_id)) in ('EDIT','ADMIN') or exists(select 1 from public.research_workspaces w where w.id=workspace_id and w.user_id=(select auth.uid()))));

drop policy if exists research_cross_asset_runs_own on public.research_cross_asset_runs;
create policy research_cross_asset_runs_select_shared on public.research_cross_asset_runs for select to authenticated
using ((select auth.uid())=user_id or (select private.user_workspace_permission(workspace_id)) is not null);
create policy research_cross_asset_runs_insert_shared on public.research_cross_asset_runs for insert to authenticated
with check ((select auth.uid())=user_id and ((select private.user_workspace_permission(workspace_id)) in ('EDIT','ADMIN') or exists(select 1 from public.research_workspaces w where w.id=workspace_id and w.user_id=(select auth.uid()))));

-- Shared watchlists.
drop policy if exists "watchlists_select_own" on public.watchlists;
create policy "watchlists_select_shared" on public.watchlists for select to authenticated
using ((select auth.uid())=user_id or exists(select 1 from public.resource_shares rs where rs.resource_type='WATCHLIST' and rs.resource_id=watchlists.id and (select private.user_is_org_member(rs.organization_id))));
drop policy if exists "watchlists_update_own" on public.watchlists;
create policy "watchlists_update_shared" on public.watchlists for update to authenticated
using ((select auth.uid())=user_id or exists(select 1 from public.resource_shares rs where rs.resource_type='WATCHLIST' and rs.resource_id=watchlists.id and rs.permission in ('EDIT','ADMIN') and (select private.user_is_org_member(rs.organization_id))))
with check ((select auth.uid())=user_id);
drop policy if exists "watchlists_delete_own" on public.watchlists;
create policy "watchlists_delete_shared" on public.watchlists for delete to authenticated
using ((select auth.uid())=user_id or exists(select 1 from public.resource_shares rs where rs.resource_type='WATCHLIST' and rs.resource_id=watchlists.id and rs.permission in ('EDIT','ADMIN') and (select private.user_is_org_member(rs.organization_id))));
create policy "watchlist_items_select_shared" on public.watchlist_items for select to authenticated
using (exists(select 1 from public.watchlists w where w.id=watchlist_items.watchlist_id and ((select auth.uid())=w.user_id or exists(select 1 from public.resource_shares rs where rs.resource_type='WATCHLIST' and rs.resource_id=w.id and (select private.user_is_org_member(rs.organization_id))))));
create policy "watchlist_items_insert_shared" on public.watchlist_items for insert to authenticated
with check (exists(select 1 from public.watchlists w where w.id=watchlist_items.watchlist_id and ((select auth.uid())=w.user_id or exists(select 1 from public.resource_shares rs where rs.resource_type='WATCHLIST' and rs.resource_id=w.id and rs.permission in ('EDIT','ADMIN') and (select private.user_is_org_member(rs.organization_id))))));
create policy "watchlist_items_update_shared" on public.watchlist_items for update to authenticated
using (
  exists (
    select 1 from public.watchlists w
    where w.id=watchlist_items.watchlist_id
      and (
        (select auth.uid())=w.user_id
        or exists (
          select 1 from public.resource_shares rs
          where rs.resource_type='WATCHLIST'
            and rs.resource_id=w.id
            and rs.permission in ('EDIT','ADMIN')
            and (select private.user_is_org_member(rs.organization_id))
        )
      )
  )
)
with check (
  exists (
    select 1 from public.watchlists w
    where w.id=watchlist_items.watchlist_id
      and (
        (select auth.uid())=w.user_id
        or exists (
          select 1 from public.resource_shares rs
          where rs.resource_type='WATCHLIST'
            and rs.resource_id=w.id
            and rs.permission in ('EDIT','ADMIN')
            and (select private.user_is_org_member(rs.organization_id))
        )
      )
  )
);
create policy "watchlist_items_delete_shared" on public.watchlist_items for delete to authenticated
using (exists(select 1 from public.watchlists w where w.id=watchlist_items.watchlist_id and ((select auth.uid())=w.user_id or exists(select 1 from public.resource_shares rs where rs.resource_type='WATCHLIST' and rs.resource_id=w.id and rs.permission in ('EDIT','ADMIN') and (select private.user_is_org_member(rs.organization_id))))));

-- Shared reports / research runs / snapshots.
drop policy if exists "research_history_select_own" on public.research_history;
create policy "research_history_select_shared" on public.research_history for select to authenticated
using ((select auth.uid())=user_id or exists(select 1 from public.resource_shares rs where rs.resource_type='REPORT' and rs.resource_id=research_history.id and (select private.user_is_org_member(rs.organization_id))));
drop policy if exists research_runs_own on public.research_runs;
create policy research_runs_select_shared on public.research_runs for select to authenticated
using ((select auth.uid())=user_id or exists(select 1 from public.resource_shares rs where rs.resource_type='RESEARCH_RUN' and rs.resource_id=research_runs.id and (select private.user_is_org_member(rs.organization_id))));
drop policy if exists research_snapshots_own on public.research_snapshots;
create policy research_snapshots_select_shared on public.research_snapshots for select to authenticated
using ((select auth.uid())=user_id or exists(select 1 from public.resource_shares rs where rs.resource_type='SNAPSHOT' and rs.resource_id=research_snapshots.id and (select private.user_is_org_member(rs.organization_id))));

drop policy if exists research_snapshots_insert_own on public.research_snapshots;
create policy research_snapshots_insert_own on public.research_snapshots for insert to authenticated
with check ((select auth.uid())=user_id);
drop policy if exists research_snapshots_update_own on public.research_snapshots;
create policy research_snapshots_update_own on public.research_snapshots for update to authenticated
using ((select auth.uid())=user_id) with check ((select auth.uid())=user_id);
drop policy if exists research_snapshots_delete_own on public.research_snapshots;
create policy research_snapshots_delete_own on public.research_snapshots for delete to authenticated
using ((select auth.uid())=user_id);

drop policy if exists "watchlists_update_shared" on public.watchlists;
create policy "watchlists_update_shared" on public.watchlists for update to authenticated
using ((select auth.uid())=user_id or exists(select 1 from public.resource_shares rs where rs.resource_type='WATCHLIST' and rs.resource_id=watchlists.id and rs.permission in ('EDIT','ADMIN') and (select private.user_is_org_member(rs.organization_id))))
with check ((select auth.uid())=user_id or exists(select 1 from public.resource_shares rs where rs.resource_type='WATCHLIST' and rs.resource_id=watchlists.id and rs.permission in ('EDIT','ADMIN') and (select private.user_is_org_member(rs.organization_id))));
