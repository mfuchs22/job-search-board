-- Live Notion → board mirror (2026-10-22). Apply once, in the SQL editor or through the
-- connector's apply_migration. Do not `supabase db push`: this project's remote history
-- uses different version names.
--
-- notion_mirror_state is one row, written only by the notion-hook edge function.
-- watermark is the reconcile cursor (pages edited on or after it). verification_token is
-- the one-time Notion handshake: the owner reads it in the SQL editor (postgres bypasses RLS),
-- pastes it into Notion's Verify field and into NOTION_WEBHOOK_SECRET, then sets the
-- column back to null. No select policy, and the table is not in the realtime publication,
-- so the token never reaches the board page.
--
-- The cron job posts {"mode":"reconcile"} to the function every 5 minutes. The join on
-- vault.decrypted_secrets returns no row until both secrets exist, so the job is quiet
-- until then and the schedule does not contain the URL or the secret.
--
-- If CREATE EXTENSION fails, enable pg_cron and pg_net under Database → Extensions and
-- run this file again. Vault is already on for hosted projects; enable it the same way
-- if the cron later reports a missing vault schema.

create extension if not exists pg_cron;
create extension if not exists pg_net;

create table public.notion_mirror_state (
  id                  int primary key default 1 check (id = 1),
  watermark           timestamptz,
  verification_token  text,
  updated_at          timestamptz not null default now()
);
alter table public.notion_mirror_state enable row level security;
revoke all on table public.notion_mirror_state from PUBLIC;
revoke all on table public.notion_mirror_state from anon, authenticated;

-- unschedule(jobid) is the form every pg_cron on Supabase accepts. No row, no call.
select cron.unschedule(jobid)
from cron.job
where jobname = 'notion-mirror-reconcile';

select cron.schedule(
  'notion-mirror-reconcile',
  '*/5 * * * *',
  $cron$
  select net.http_post(
    url := u.decrypted_secret,
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'x-reconcile-secret', s.decrypted_secret
    ),
    body := '{"mode":"reconcile"}'::jsonb,
    timeout_milliseconds := 150000
  )
  from vault.decrypted_secrets u
  join vault.decrypted_secrets s on s.name = 'notion_reconcile_secret'
  where u.name = 'notion_hook_url';
  $cron$
);
