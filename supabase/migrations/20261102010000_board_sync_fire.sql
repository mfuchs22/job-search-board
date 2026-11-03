-- The page starts the board-sync cloud scheduled task directly (2026-11-02), replacing the mini's two-minute poller.
--
-- A Sync now row, a plan answer, or an item opened with no brief calls fire_board_sync(), which posts to the task's
-- /fire endpoint (Claude Code scheduled tasks, beta header experimental-cc-routine-2026-04-01) with the task's API
-- token. The run (Personal-OS Tools/board-sync-prompt.md) claims the request, folds the answers, drafts, and pushes.
-- It bills to the owner's Max plan like every scheduled task. The task also runs hourly from 07:00 to 22:00 ET as a net.
--
-- Quiet until two Vault secrets exist (SQL editor):
--   select vault.create_secret('https://api.anthropic.com/v1/claude_code/routines/<trig id>/fire', 'board_sync_fire_url');
--   select vault.create_secret('<the task''s API token>', 'board_sync_fire_token');
-- A plan answer or a brief request fires at most once every 3 minutes (a run in flight picks up rows that land while
-- it works, and the hourly run catches the rest); Sync now always fires. The task allows 30 fires an hour.
create extension if not exists pg_net;

create table if not exists public.cloud_fires (
  name     text primary key,
  fired_at timestamptz not null,
  reason   text
);
alter table public.cloud_fires enable row level security;
revoke all on table public.cloud_fires from PUBLIC;
revoke all on table public.cloud_fires from anon, authenticated;

create or replace function public.fire_board_sync(reason text, force boolean default false)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  u text;
  t text;
  last timestamptz;
begin
  select decrypted_secret into u from vault.decrypted_secrets where name = 'board_sync_fire_url';
  select decrypted_secret into t from vault.decrypted_secrets where name = 'board_sync_fire_token';
  if u is null or t is null then
    return;
  end if;
  select fired_at into last from public.cloud_fires where name = 'board-sync';
  if not force and last is not null and last > now() - interval '3 minutes' then
    return;
  end if;
  insert into public.cloud_fires (name, fired_at, reason) values ('board-sync', now(), reason)
    on conflict (name) do update set fired_at = excluded.fired_at, reason = excluded.reason;
  perform net.http_post(
    url := u,
    headers := jsonb_build_object(
      'Authorization', 'Bearer ' || t,
      'anthropic-beta', 'experimental-cc-routine-2026-04-01',
      'anthropic-version', '2023-06-01',
      'Content-Type', 'application/json'
    ),
    body := jsonb_build_object('text', reason),
    timeout_milliseconds := 30000
  );
end;
$$;
revoke all on function public.fire_board_sync(text, boolean) from PUBLIC;
revoke all on function public.fire_board_sync(text, boolean) from anon, authenticated;

create or replace function public.on_sync_request()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  perform public.fire_board_sync('Sync now from the board (request ' || new.id || ')', true);
  return new;
end;
$$;

create or replace function public.on_plan_input()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  perform public.fire_board_sync('Plan answer on the board for ' || coalesce(new.job_id, '?'));
  return new;
end;
$$;

create or replace function public.on_draft_asked()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  if new.draft_asked is not null and new.draft_asked is distinct from (case when tg_op = 'UPDATE' then old.draft_asked end) then
    perform public.fire_board_sync('Brief asked for on Today: ' || new.key);
  end if;
  return new;
end;
$$;

drop trigger if exists fire_on_sync_request on public.sync_requests;
create trigger fire_on_sync_request after insert on public.sync_requests
  for each row when (new.status = 'requested') execute function public.on_sync_request();

drop trigger if exists fire_on_plan_input on public.plan_inputs;
create trigger fire_on_plan_input after insert on public.plan_inputs
  for each row execute function public.on_plan_input();

drop trigger if exists fire_on_draft_asked on public.today_marks;
create trigger fire_on_draft_asked after insert or update of draft_asked on public.today_marks
  for each row execute function public.on_draft_asked();
