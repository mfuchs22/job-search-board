-- Opportunities and meetings: read mirrors of Notion, which is the home for a Pursue role's process state
-- (2026-09-17). `opportunities` replaces the `stages` table: stage, outcome, next step, human path and the links to
-- people, meetings, company and tasks all live on the Notion page now.
--
-- Two writers, both copying what Notion holds: the engine (push_board.py, a full refresh from notion_sync.py) and
-- the opportunity-write edge function (only the one page Notion just accepted). The page reads, never writes.
create table public.opportunities (
  id         text primary key,   -- the board record id (jobs.id), the join key; Notion's "Job ID"
  page_id    text not null,      -- Notion page id
  payload    jsonb not null,
  updated_at timestamptz not null default now()
);
alter table public.opportunities enable row level security;
revoke all on public.opportunities from anon;
create policy "owner reads opportunities" on public.opportunities for select to authenticated using ((select public.is_board_owner()));

create table public.meetings (
  id         text primary key,   -- Notion page id
  payload    jsonb not null,
  updated_at timestamptz not null default now()
);
alter table public.meetings enable row level security;
revoke all on public.meetings from anon;
create policy "owner reads meetings" on public.meetings for select to authenticated using ((select public.is_board_owner()));

alter publication supabase_realtime add table public.opportunities;
alter publication supabase_realtime add table public.meetings;
