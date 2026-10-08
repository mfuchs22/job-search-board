-- Job board schema. The engine writes jobs and board_meta with the secret key (bypasses RLS);
-- the page writes verdicts and stages as the signed-in owner. No personal data lives in this file:
-- the owner's email is seeded once from the SQL editor, never from git:
--   insert into public.board_owners (email) values ('<owner email>');

create table public.board_owners (
  email text primary key
);
alter table public.board_owners enable row level security;  -- no policies: readable only via the definer function

create or replace function public.is_board_owner()
returns boolean
language sql stable security definer
set search_path = public
as $$
  select exists (select 1 from public.board_owners where email = (auth.jwt() ->> 'email'))
     and coalesce((auth.jwt() ->> 'is_anonymous')::boolean, false) = false;
$$;
revoke all on function public.is_board_owner() from public;
grant execute on function public.is_board_owner() to authenticated;

-- Engine-written
create table public.jobs (
  id          text primary key,
  company_key text,
  payload     jsonb not null,
  updated_at  timestamptz not null default now()
);
create table public.board_meta (
  key        text primary key,   -- summary | companies | paths
  payload    jsonb not null,
  updated_at timestamptz not null default now()
);

-- Page-written
create table public.verdicts (
  id      text primary key,
  v       text,                  -- Pursue | Maybe | Pass | ''
  cal     text,
  note    text,
  ts      timestamptz not null,
  title   text,
  company text
);
create table public.stages (
  id      text primary key,
  stage   text,
  outcome text,
  next    text,
  ts      timestamptz not null,
  title   text,
  company text
);

alter table public.jobs       enable row level security;
alter table public.board_meta enable row level security;
alter table public.verdicts   enable row level security;
alter table public.stages     enable row level security;

-- The anon role gets a permission error rather than an empty result.
revoke all on public.jobs, public.board_meta, public.verdicts, public.stages, public.board_owners from anon;

create policy "owner reads jobs"       on public.jobs       for select to authenticated using ((select public.is_board_owner()));
create policy "owner reads board_meta" on public.board_meta for select to authenticated using ((select public.is_board_owner()));

create policy "owner reads verdicts"   on public.verdicts for select to authenticated using ((select public.is_board_owner()));
create policy "owner inserts verdicts" on public.verdicts for insert to authenticated with check ((select public.is_board_owner()));
create policy "owner updates verdicts" on public.verdicts for update to authenticated using ((select public.is_board_owner())) with check ((select public.is_board_owner()));

create policy "owner reads stages"     on public.stages for select to authenticated using ((select public.is_board_owner()));
create policy "owner inserts stages"   on public.stages for insert to authenticated with check ((select public.is_board_owner()));
create policy "owner updates stages"   on public.stages for update to authenticated using ((select public.is_board_owner())) with check ((select public.is_board_owner()));
-- No delete policies: the page never deletes; the engine bypasses RLS.

-- Realtime: verdicts/stages keep two open tabs in step; jobs/board_meta let a build refresh an open page.
alter publication supabase_realtime add table public.verdicts, public.stages, public.jobs, public.board_meta;
