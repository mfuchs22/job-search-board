-- Startups: the Boston startup scene as its own screen on the board (2026-09-23). The engine
-- (engine/startups.py) writes one `startups` row per company from MGMT Boston's public board joined
-- with the vault's research tables; the page writes `startup_verdicts` as the signed-in owner.
-- Same access pattern as jobs/verdicts: RLS on, owner-only through is_board_owner(), no deletes
-- through the API, realtime on both.

create table public.startups (
  id         text primary key,          -- MGMT slug
  name       text,
  payload    jsonb not null,
  updated_at timestamptz not null default now()
);

create table public.startup_verdicts (
  id    text primary key,               -- the startup id
  v     text,                           -- Interesting | Watch | Pass | ''
  note  text,
  flag  boolean not null default false,
  ts    timestamptz not null,
  name  text
);

alter table public.startups         enable row level security;
alter table public.startup_verdicts enable row level security;
revoke all on public.startups, public.startup_verdicts from anon;

create policy "owner reads startups"          on public.startups         for select to authenticated using ((select public.is_board_owner()));
create policy "owner reads startup_verdicts"  on public.startup_verdicts for select to authenticated using ((select public.is_board_owner()));
create policy "owner inserts startup_verdicts" on public.startup_verdicts for insert to authenticated with check ((select public.is_board_owner()));
create policy "owner updates startup_verdicts" on public.startup_verdicts for update to authenticated using ((select public.is_board_owner())) with check ((select public.is_board_owner()));

alter publication supabase_realtime add table public.startups, public.startup_verdicts;
