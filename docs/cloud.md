# Running in the cloud

Since 2026-11-02 the engine runs without an always-on machine. Every routine is a Claude Code cloud scheduled task (claude.ai/code/routines). Each task checks out both repos side by side, and the runs bill to the owner's Claude subscription. Nothing polls. The page starts the one task that must react within minutes (board-sync) through Supabase.

## What a run needs

- **Both repos checked out side by side**: this one and the notes repo that holds the vault (`<notes repo>/Projects/job-search`). With no `config.json`, `common.load_config()` falls back to `cloud_config()`. That function finds the vault beside this repo, or at `$JOBS_VAULT`, and reads its non-secret settings from `<vault>/meta/engine.json`.
- **Environment variables** on the cloud environment:
  - `SUPABASE_SECRET_KEY`: the `sb_secret_...` key.
  - `NOTION_TOKEN`: the integration token.
  - `SYNC_HOST=the cloud`: names the host in banner and log lines, and sends sync results to `notifications`.
- **Network access** to:
  - `*.supabase.co`
  - `api.notion.com`
  - the job boards and career pages the posting check reads (`boards-api.greenhouse.io`, `api.lever.co`, `api.ashbyhq.com`, employer sites).
  - Google News and EDGAR for the company watch.

  The simplest setting is Full. LinkedIn refuses datacenter IPs, so the posting check runs with `--cap-linkedin 0` and never tries it.
- **Setup script**:

  ```bash
  pip install -q markdown
  ln -sf "$(command -v python3)" /usr/local/bin/py
  ```
- **Connectors** on the tasks that read mail or calendars: Gmail, and Google Calendar where the playbook asks for it.

## Notifications

`engine/notify.py <source> [--ping]` (text on stdin) writes one row to `notifications`. The owner's bot reads the `notify-feed` edge function with the `x-feed-secret` header. Each message it takes is stamped `read_at`; `?peek=1` reads without stamping. Deploy the function with `supabase functions deploy notify-feed --no-verify-jwt --use-api`, and set `NOTIFY_FEED_SECRET` first.

## The page starts board-sync

Migration `20261102010000_board_sync_fire.sql` puts triggers on three events:

- a `sync_requests` insert (Sync now): always fires.
- a `plan_inputs` insert (a plan answer): fires at most once every 3 minutes.
- a `today_marks.draft_asked` stamp (an item opened with no brief): fires at most once every 3 minutes.

Each trigger calls `fire_board_sync()`, which posts to the board-sync task's `/fire` endpoint through `pg_net`. The triggers stay quiet until two Vault secrets exist:

```sql
select vault.create_secret('https://api.anthropic.com/v1/claude_code/routines/<trigger id>/fire', 'board_sync_fire_url');
select vault.create_secret('<the task''s API token, made under Edit > API in the task>', 'board_sync_fire_token');
```

The task's playbook (in the notes repo, `Tools/board-sync-prompt.md`) runs three commands:

- `py engine/sync_worker.py --all --no-draft`: claims every waiting request, folds verdicts, builds, pushes, and commits the vault.
- `py engine/draft_now.py --inline`: folds plan answers and prints the drafting work instead of starting a second Claude.
- the drafting work itself, in the same session.

The task also runs hourly through the day as a net.

## Limits worth knowing

- Scheduled tasks run at most hourly, and the `/fire` endpoint allows 30 fires an hour per task.
- A session takes a minute or two to start, so Sync now lands in minutes, not seconds.
- Runs that write the vault commit straight to its default branch, the way the always-on machine did. They pull with rebase first, and their schedules are hours apart.
