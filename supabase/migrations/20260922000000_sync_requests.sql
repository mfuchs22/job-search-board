-- A sync requested from the board page. The owner inserts one row from the Sync button (with an optional
-- note that becomes a feedback-log line); the board-sync worker on the always-on host claims it, folds the
-- verdicts, rebuilds, pushes, and writes the outcome back. The page shows the newest row in its banner.
create table public.sync_requests (
  id           bigint generated always as identity primary key,
  requested_at timestamptz not null default now(),
  requested_by text,
  note         text,
  status       text not null default 'requested',   -- requested | running | done | failed
  host         text,                                 -- which machine took it
  started_at   timestamptz,
  finished_at  timestamptz,
  result       text                                  -- plain language, shown on the page
);
alter table public.sync_requests enable row level security;
revoke all on public.sync_requests from anon;
create policy "owner reads sync_requests"   on public.sync_requests for select to authenticated using ((select public.is_board_owner()));
create policy "owner inserts sync_requests" on public.sync_requests for insert to authenticated
  with check ((select public.is_board_owner()) and status = 'requested');
alter publication supabase_realtime add table public.sync_requests;
