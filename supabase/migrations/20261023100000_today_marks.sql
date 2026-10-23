-- today_marks: the owner's own order and his picks on the Today page (2026-10-23). Before this, picking an option on a
-- Today card either staged nothing (a "send this" pick only opened the brief) or staged a write that cleared the
-- item, so a card left Today before anything was sent ("you can sign off on an approach, and then it goes away, and
-- you haven't actually done the thing yet"). One row per Today key (role:<job id>, person:<contact id>,
-- task:<task id>, plan:<job id>):
--   rank       his place for it at the top (1 first); null leaves it to the computed ranking
--   choice..   the option he picked and when; the card stays as "Doing" until done_at
--   done_at    set when the thing is done: his Done or I sent it reached Notion through Sync, a terminal pick
--              (snooze, close, bench...) was sent, or the record shows the touch or send landed (the nightly mail
--              read). done_how says which. The Completed section on Today lists the last seven days.
-- Nothing in the engine writes it. Same access pattern as org_watch: RLS on, owner-only through is_board_owner(),
-- no deletes through the API, realtime on.

create table public.today_marks (
  key       text primary key,
  rank      int,
  choice    text,
  label     text,
  act       text,
  pick_for  text,          -- the item's version when picked (its next step, or "plan vN")
  picked_at timestamptz,
  done_at   timestamptz,
  done_how  text,
  title     text,          -- the card's name, for the Completed list once the item itself is gone
  ts        timestamptz not null default now()
);

alter table public.today_marks enable row level security;
revoke all on public.today_marks from anon;

create policy "owner reads today_marks"   on public.today_marks for select to authenticated using ((select public.is_board_owner()));
create policy "owner inserts today_marks" on public.today_marks for insert to authenticated with check ((select public.is_board_owner()));
create policy "owner updates today_marks" on public.today_marks for update to authenticated using ((select public.is_board_owner())) with check ((select public.is_board_owner()));

alter publication supabase_realtime add table public.today_marks;
