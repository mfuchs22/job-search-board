# Build your own board with an AI coding agent

This repo is complete enough that a coding agent (Claude Code, Codex, Cursor, or a chat model with the files pasted in) can stand up a working copy for you and adapt it to your search. This page is the brief to give it. You do not need to be a programmer; you need an afternoon, a few accounts, and the willingness to answer the agent's questions in plain words.

## What you are building

A page you open every morning on your phone or laptop that shows the roles worth your time, lets you say yes, maybe or no on each in one tap, tracks the ones you are pursuing through to an offer, and keeps the people, the to-dos and the documents in one place. Behind it: a script that collects postings from your job-alert emails, a model that reads each posting against your rubric, and a database the page talks to.

Open the [demo](https://mfuchs22.github.io/job-search-board/) first and click through every tab. Decide which tabs you want. Inbox, Shortlist, In Process and Passed are the core; Startups, Network, To-dos and Map are each optional and can be left out or added later.

## Accounts you will need

| For | Service | Cost |
|---|---|---|
| The database and sign-in | [Supabase](https://supabase.com) (free tier is plenty) | free |
| Hosting the page | GitHub Pages, Vercel, Netlify, or any static host | free |
| The alert mail | A Gmail label that your LinkedIn, Indeed and other alerts land in | free |
| The model | Claude Code (or another coding agent) for the build, and for the morning read of new postings | your subscription |
| People and opportunities (optional) | Notion, if you want the Network and In Process pages to be editable from Notion as well as the board | free |

## The prompt to give the agent

Clone or download this repo, open your agent in that folder, and paste this. Fill in the bracketed parts.

```
I want my own copy of this job-search board, adapted to my search. Work in this folder.

Read, in this order, before changing anything: README.md, docs/schema.md, docs/board-prd.md,
docs/deep-pass.md, docs/rubric-template.md, docs/routines.md, engine/common.py, engine/build.py,
web/README.md, and the top 120 lines of web/index.html. Then tell me in plain language how the
pieces fit and what you will need from me, and wait for my answers before building.

About me and my search:
- I am looking for [kind of roles, level, the titles you would search for].
- I live in [city]; I will consider [remote / hybrid / on-site within N minutes]; travel up to [X%].
- Hard no: [industries, companies, role shapes, anything that is an automatic pass].
- What makes a role a 10 for me: [three or four sentences].
- My job alerts arrive in Gmail under the label [label name], from [LinkedIn, Indeed, ...].
- I [do / do not] use Notion. [If yes: I am happy for the board to write a Network and an
  Opportunities database there.]
- I want these tabs: [Inbox, Shortlist, In Process, Passed, and optionally Startups, Network,
  To-dos, Map].

What I want from you, in this order, checking with me at each step:
1. A vault folder for my data (jobs/, meta/, network/) and a config.json pointing at it, with my
   rubric written into jobs/rubric.md from docs/rubric-template.md and my answers above.
2. A Supabase project: apply supabase/migrations, seed board_owners with my email, and tell me
   exactly what to click to create my user and get the keys. Skip the edge functions unless I use Notion.
3. The page deployed somewhere I can open on my phone, signed in as me, empty.
4. The collect step: a scheduled routine (a cron job, a GitHub Action, or a Claude Code routine)
   that reads my alert label every morning and appends new postings to jobs/inbox.csv, following
   docs/routines.md. Run it once by hand and show me the rows.
5. One deep pass by hand on the rows that cleared the floor, following docs/deep-pass.md, then
   py engine/build.py so the cards appear on my page. Walk me through giving my first verdicts.
6. The morning loop scheduled: ingest_db.py, the deep pass, build.py, and a short report to me
   (email, Slack, Discord, whatever I use).

Rules: keep the single-writer rule in docs/schema.md (one writer per generated file); never commit
config.json or web/config.js; do not change the page's layout unless I ask; and when you are
unsure which of two readings I mean, ask rather than guess.
```

## What to adapt, and what to leave alone

**Adapt**

- `jobs/rubric.md` (your vault): the whole point. Start from `docs/rubric-template.md`. Expect to rewrite it every couple of weeks from your own verdicts; `engine/calibrate.py` and the calibration routine in `docs/routines.md` do that synthesis for you.
- The alert sources and the canonical-URL rules in `engine/common.py` if your boards are not LinkedIn, Indeed, Glassdoor, Built In or employer ATS pages.
- The role types (`ROLE_TYPES` in `engine/render_dashboard.py`) and the three Shortlist columns in `web/index.html`: the demo's kinds are one person's search.
- The city on the Map and the office geocoding (`engine/office.py`): the demo is Boston.
- The Startups tab's source (`engine/startups.py`): it reads one city's public startup list. Leave the tab out if you do not have one.

**Leave alone**

- The single-writer rule and `build.py` as the only writer of `jobs.json`. Every drift problem in the first month came from a second writer.
- The timestamp rule in `ingest_db.py`: the page's row overlays the record only when it is newer, which is what makes the morning fold idempotent.
- The deep-pass brief's shape: a session reads the posting, writes facts and gates, and scores last. Scoring before reading was the original mistake.
- Row-level security in the migrations. The page uses a publishable key; the owner allowlist and RLS are what keep a stranger who finds the URL from seeing anything.

## If you do not want the automation

The page alone is useful. Skip steps 4 and 6 of the prompt, keep `jobs/inbox.csv` by hand (one row per posting you want read), and run the deep pass and `build.py` yourself whenever you have a batch. The board, the verdicts, the pipeline and the detail pages all work the same way.

## If you want only the demo

`web/` runs on `web/demo/data.json` with no database at all (`web/demo.js` stands in for the Supabase client). `demo/make_demo.py` shows every shape the page expects; replace the invented companies and roles with your own and you have a static board that needs nothing but a folder to host it. You lose sign-in, realtime and persistence, which is fine for a snapshot and wrong for a daily tool.
