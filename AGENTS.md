# AGENTS.md

The public showcase of a job-search board: the board page running in demo mode on invented data, plus a scrubbed copy of the engine, the Supabase schema and functions, and the docs. Live demo: https://demo.mattfuchs.dev/job-board/ (and GitHub Pages from this repo). This repo is public; everything in it must stay free of real people, firms and personal details.

## Where the code comes from

Most of this repo is generated. The owner's private engine repo (`job-search-agent`) runs `py tools/publish_public.py [--ship]`, which overwrites `engine/`, `web/` (except `config.js`, `README.md` and `demo/`), `docs/`, `supabase/`, `config.example.json` and `requirements.txt` here with a name-scrubbed copy. With `--ship` it then runs `demo/screenshots.py`, does `git add -A`, commits "Sync from the engine: ...", pulls and pushes straight to `master`, and redeploys the demos hub.

So:

- **Don't edit the generated folders here.** A change to `engine/`, `docs/`, `supabase/` or `web/index.html` etc. is lost on the next sync. Make it in the engine repo.
- **Owned by this repo** (the sync never touches them): `README.md`, `BUILD-WITH-AI.md`, `AGENTS.md`, `CLAUDE.md`, `LICENSE`, `.gitignore`, `.github/workflows/pages.yml`, `demo/`, `screenshots/`, `web/config.js`, `web/README.md`, `web/demo/data.json`.
- The scrub check only scans the generated folders. Anything you write in the owned files gets no check: never put a real company, person, machine name or private path in them.
- The sync's `git add -A` commits whatever is in the owner's local main checkout of this repo. Leave uncommitted work there only on purpose.

## Layout

| Path | What |
|---|---|
| `web/` | The board page: `index.html` (vanilla JS, no build step), `startups.js`, `calendar.js`, `demo.js` (stands in for supabase-js), `config.js` (demo config, committed on purpose), `demo/data.json` (the invented dataset) |
| `demo/make_demo.py` | Writes `web/demo/data.json`. Dates are relative; `demo.js` shifts them to today on load |
| `demo/screenshots.py` | Renders every tab at desktop and phone sizes into `screenshots/`; fails if the page throws |
| `engine/` | Python scripts (collect, score, build, push to Supabase, Notion sync). Generated; not runnable here without a real `config.json` and vault |
| `supabase/` | Migrations and edge functions. Generated; nothing here is deployed from this repo |
| `docs/` | Schema, PRD, deep pass, routines, cloud setup. Generated |
| `BUILD-WITH-AI.md` | The brief a reader hands to a coding agent to build their own board |

## Run and test locally

```
py -m http.server 8742 --directory web        # then open http://localhost:8742
py demo/make_demo.py                           # rebuild web/demo/data.json
py -m pip install playwright && py -m playwright install chromium   # once
py demo/screenshots.py                         # re-render screenshots/*.png, fails on a page error
```

No test suite or CI checks beyond the Pages deploy. `requirements.txt` is the engine's (`markdown`).

## Deploy

- `.github/workflows/pages.yml` publishes `web/` to GitHub Pages on every push to `master` (or by hand). No secrets.
- The demos hub (demo.mattfuchs.dev) is deployed by the engine repo's `publish_public.py --ship`, not from here. Don't deploy it by hand.

## Env vars and secrets

None in this repo. `config.example.json` and `web/config.example.js` are templates for a reader's own deployment; real `config.json` is git-ignored. Never commit a real Supabase URL or key, a Notion token, or a real `web/config.js`.

## Open work

- No open branches besides `master` (the one remote branch, `claude/project-thread-ey40vw`, was merged as PR #1).

## Conventions

- Default branch `master`. Sync commits from the engine push to `master` directly; hand changes go on a `claude/...` branch with a PR to `master` for the owner to review.
- Commit subjects are plain sentences ("Public README refresh, fresh screenshots, demo banner fix"). `Sync from the engine:` is reserved for the publish script.
- Demo data stays invented. A new tab or field in the page needs matching rows in `demo/make_demo.py`, or the demo shows it empty.
