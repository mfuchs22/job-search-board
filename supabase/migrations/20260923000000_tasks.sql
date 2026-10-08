-- Career tasks: a read mirror of the owner's Notion Tasks database (Area career, not Complete), which stays the
-- only task list (2026-09-06 rule). Two writers, both copying what Notion holds: the engine (push_board.py, a full
-- refresh from notion_sync.py) and the task-write edge function (only the one page Notion just accepted). The
-- board's To-dos tab (2026-09-22) reads it beside the role next steps and the people touches; the page never writes.
create table public.tasks (
  id         text primary key,   -- Notion page id
  payload    jsonb not null,
  updated_at timestamptz not null default now()
);
alter table public.tasks enable row level security;
revoke all on public.tasks from anon;
create policy "owner reads tasks" on public.tasks for select to authenticated using ((select public.is_board_owner()));

alter publication supabase_realtime add table public.tasks;
