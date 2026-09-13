-- Harden the Settings account-deletion RPC after the initial foundation migration.
-- The RPC intentionally remains SECURITY DEFINER so it can delete auth.users,
-- but only authenticated callers may execute it.

revoke execute on function public.delete_my_account() from anon, public;
grant execute on function public.delete_my_account() to authenticated;

alter function public.set_user_preferences_updated_at()
    set search_path = public;
