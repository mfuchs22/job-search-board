-- bot_actions: outreach the owner did outside the board, waiting to be folded into Notion (2026-11-02). the owner emailed
-- Chrissie Gorman Francona through the Grok career-coach bot and expected the line to resolve everywhere. Rows come
-- from the Grok bot (through the bot-action edge function, with a secret) and from the nightly Gmail read
-- (engine/bot_actions.py record). engine/bot_actions.py fold is the only thing that moves a row past `new`: it finds
-- the Network person, writes the touch to Notion (last touch, touch log, the next touch when the send fulfilled it),
-- and the notion-hook mirror, the vault pull and Today follow from Notion as they do for the board's own Done.
-- Nothing here sends anything. Service role only: RLS on, no policies, not in the realtime publication.

create table public.bot_actions (
  id          bigint generated always as identity primary key,
  created_at  timestamptz not null default now(),
  source      text not null,                 -- grok, gmail, claude
  ext_id      text,                          -- the sender's own id (a Gmail message id), for dedupe
  person      text not null,                 -- a Network page id, an email address, or a full name
  type        text not null default 'Email', -- a Network touch type: Email, Message, Call, Meeting, ...
  date        date not null default (now() at time zone 'America/New_York')::date,
  note        text,
  next_type   text,                          -- optional: set the next touch instead of the default
  next_action text,
  next_date   date,
  status      text not null default 'new' check (status in ('new', 'done', 'skipped', 'failed')),
  folded_at   timestamptz,
  result      text,                          -- one sentence: what the fold did, or why not
  unique (source, ext_id)
);

create index bot_actions_new on public.bot_actions (created_at) where status = 'new';

alter table public.bot_actions enable row level security;
revoke all on public.bot_actions from anon, authenticated;
