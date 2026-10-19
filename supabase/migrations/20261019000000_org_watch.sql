-- org_watch: the owner's own list of the people that matter at a firm, edited on the org card (2026-10-19).
-- The card starts from the people the vault and the network know (org_chart.py flags); a row here hides one
-- of them (state 'hidden') or adds someone (state 'added': a name from the chart, or anyone off the site,
-- with an optional note). state '' restores the default. One row per company and person.
-- Same access pattern as verdicts: RLS on, owner-only through is_board_owner(), no deletes through the
-- API, realtime on.

create table public.org_watch (
  id      text primary key,               -- company_key || '|' || lower(name)
  company text not null,                  -- the board company_key (board_meta org_charts key)
  name    text not null,
  state   text not null default '' check (state in ('', 'hidden', 'added')),
  note    text,
  ts      timestamptz not null
);

alter table public.org_watch enable row level security;
revoke all on public.org_watch from anon;

create policy "owner reads org_watch"   on public.org_watch for select to authenticated using ((select public.is_board_owner()));
create policy "owner inserts org_watch" on public.org_watch for insert to authenticated with check ((select public.is_board_owner()));
create policy "owner updates org_watch" on public.org_watch for update to authenticated using ((select public.is_board_owner())) with check ((select public.is_board_owner()));

alter publication supabase_realtime add table public.org_watch;
