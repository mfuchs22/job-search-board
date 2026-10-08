-- Networking contacts: a read mirror of the owner's Notion Network database, which stays the home (2026-09-15).
-- Two writers, both copying what Notion holds: the engine (push_board.py, a full refresh from network_notion.py)
-- and the network-write edge function (only the one page Notion just accepted). The page reads, never writes.
create table public.contacts (
  id         text primary key,   -- Notion page id
  payload    jsonb not null,
  updated_at timestamptz not null default now()
);
alter table public.contacts enable row level security;
revoke all on public.contacts from anon;
create policy "owner reads contacts" on public.contacts for select to authenticated using ((select public.is_board_owner()));

alter publication supabase_realtime add table public.contacts;
