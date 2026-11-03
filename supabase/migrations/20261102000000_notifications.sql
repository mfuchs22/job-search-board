-- Messages for the owner from the routines, replacing the Discord #job-search posts (2026-11-02). engine/notify.py
-- inserts a row; his career coach bot (Grok) reads them through the notify-feed edge function, which checks a
-- shared secret, and stamps read_at. The board may show them later; the owner can read them now.
create table public.notifications (
  id          bigint generated always as identity primary key,
  created_at  timestamptz not null default now(),
  source      text not null,                       -- the routine: job-board-refresh, pursue-mail-check, ...
  channel     text not null default 'job-search',
  text        text not null,
  ping        boolean not null default false,      -- worth interrupting him for
  read_at     timestamptz                          -- set by notify-feed when the bot takes it
);
create index notifications_created_at on public.notifications (created_at);
alter table public.notifications enable row level security;
revoke all on public.notifications from anon;
create policy "owner reads notifications" on public.notifications for select to authenticated
  using ((select public.is_board_owner()));
