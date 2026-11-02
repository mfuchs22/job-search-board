-- the owner's Google calendars on the board's Calendar tab (2026-11-02). Apply once, in the SQL editor or through the
-- connector's apply_migration. Do not `supabase db push`: this project's remote history uses different version names.
--
-- Both tables are written only by the gcal-sync edge function (service role). The page reads them, owner only, and
-- shows the events grey, title only, on Day and Week. Nothing here holds a calendar's address: those stay in the
-- function's GCAL_ICS secret.
--   gcal_calendars  one row per calendar in GCAL_ICS, in its order. is_default is on before the owner picks; ok and error
--                   say how the last read went; synced_at moves every run, and that is what the page listens for.
--   gcal_events     one row per event or occurrence, one week back to seven weeks ahead. starts and ends are UTC ISO
--                   for a timed event and YYYY-MM-DD for an all-day one (ends exclusive). Only the title is kept.
--
-- The cron job posts to the function every 15 minutes. The join on vault.decrypted_secrets returns no row until both
-- secrets (gcal_sync_url, gcal_sync_secret) exist, so the job is quiet until then.

create table public.gcal_calendars (
  id          text primary key,
  name        text not null,
  ord         int not null default 0,
  is_default  boolean not null default false,
  ok          boolean,
  error       text,
  events      int,
  synced_at   timestamptz
);

create table public.gcal_events (
  id           text primary key,
  calendar_id  text not null references public.gcal_calendars(id) on delete cascade,
  title        text not null default '',
  starts       text not null,
  ends         text,
  all_day      boolean not null default false,
  synced_at    timestamptz not null
);
create index gcal_events_calendar_synced on public.gcal_events (calendar_id, synced_at);

alter table public.gcal_calendars enable row level security;
alter table public.gcal_events enable row level security;
create policy "owner reads gcal_calendars" on public.gcal_calendars for select to authenticated using ((select public.is_board_owner()));
create policy "owner reads gcal_events"    on public.gcal_events    for select to authenticated using ((select public.is_board_owner()));

-- Only the calendars table is published: one change per calendar per run, never one per event.
alter publication supabase_realtime add table public.gcal_calendars;

create extension if not exists pg_cron;
create extension if not exists pg_net;

select cron.unschedule(jobid)
from cron.job
where jobname = 'gcal-sync';

select cron.schedule(
  'gcal-sync',
  '*/15 * * * *',
  $cron$
  select net.http_post(
    url := u.decrypted_secret,
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'x-sync-secret', s.decrypted_secret
    ),
    body := '{}'::jsonb,
    timeout_milliseconds := 120000
  )
  from vault.decrypted_secrets u
  join vault.decrypted_secrets s on s.name = 'gcal_sync_secret'
  where u.name = 'gcal_sync_url';
  $cron$
);
