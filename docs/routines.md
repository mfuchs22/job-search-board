# Routines

Everything that runs on a schedule, in the order of a morning. Times are the owner's (US Eastern). "Deterministic" means a plain script with no model inside it; "model" means a Claude Code session following a written brief; "human" means the owner on the page. The split is deliberate: plumbing is cheap and should never wait on a model, and a model should never be the only writer of a file a script also writes.

| When | Name | Runs | Kind | Owns (the only files it writes) |
|---|---|---|---|---|
| 03:15 nightly | `posting-check` | `py engine/posting_check.py` | deterministic, with a model pass only for pages the rules cannot read | `posting` on each record, `jobs/posting-log.jsonl` |
| 04:00 daily | `job-alerts-sweep` (the radar) | a cloud Claude Code routine | model, but phase 1 is plumbing | `jobs/inbox.csv`, the seen-URL state, a heartbeat file |
| 04:30 daily | `job-board-refresh` | a local Claude Code routine | model | `jobs/jobs.json` through the engine, the views, job files, one Discord post |
| every 2 min | `board-sync` | `py engine/sync_worker.py` | deterministic | `sync_requests` rows; runs ingest and build on request |
| Mondays 05:30 | `rubric-calibration` | a local Claude Code routine | model | `jobs/calibration/<date>.md`, a Discord post; applies nothing |
| Mondays | `startups` | `py engine/startups.py` after the city list is refreshed | deterministic | the `startups` table and `startups_summary` |
| on demand | deep pass | a session following `deep-pass.md` | model | `out-*.json`, folded by `apply_deep_pass.py` |

## The radar (collect)

Reads the Gmail label the alerts land in, newer than the last sweep. For every posting in every new message: title, company, location, canonical URL (strip tracking parameters; LinkedIn by job id, Indeed by `jk`, Glassdoor by `jl`, Built In and Wellfound by path), the board it came from, and the alert's name. Non-posting mail (confirmations, marketing, "picked for you") is skipped. Dedupe against the seen set and the CSV, append the survivors with today's date and status `new`, update the state.

Then a provisional score: apply the rubric's gates (hard exclusions, company blocklist) first, then the points, from the title, company and location alone, since that is all the email carries. Write `score` and `why` into the row. Never fetch the posting page; that is the deep pass's job.

Every run appends one heartbeat line (date, mail count, rows appended, rows at the floor or above, ok / quiet / failed). The refresh reads it to tell a quiet morning from a dead one.

Guardrails: read the label only; the CSV is append-only; no browsing; blank fields stay blank. Phase 1 is a Gmail trigger, a parser and an append; it needs no model and is the first thing to move to a plain scheduled script.

## The refresh (pursue)

1. Pull the vault; read the radar's heartbeat.
2. `py engine/ingest_db.py`: fold the page's verdicts and stage moves into `jobs.json` (newer timestamps only).
3. `py engine/build.py --no-push`: new rows become records, duplicates merge, the views regenerate.
4. Deep pass on the newcomers at the floor or above with no deep-pass date: up to three parallel agents, each following `deep-pass.md`, each reading the rubric itself; results folded with `apply_deep_pass.py`. Mondays add a web sweep of the employer careers pages the alerts never send.
5. `py engine/build.py`: build and push the board.
6. Commit the vault. Cascade any new Pursue into a job file and a follow-up line.
7. One report to the owner: new to review (score, title, company, why, mismatch), read and dropped below the floor, folded from the board, waiting, and the posting-liveness block. One post a morning, never zero: a quiet morning gets two plain lines.

Steps 1, 2, 3, 5 and 6 are scripts; step 4 and the cascade need a model; the report is templated from step 4's output.

## The posting check

For every board row that is not closed and not passed: is the ad still up? Each source has a reader (LinkedIn's guest page, Greenhouse, Lever, Ashby and Workable's public APIs, Workday, employer pages via JSON-LD) that returns `active`, `closed`, `removed`, `unreachable` or `unknown` with the evidence. A Pursue whose ad is gone is proposed to the owner on the Closed tab and in the morning report; any other row closes itself with outcome `posting_removed`. A new radar row matching a record closed that way is a repost and joins the record instead of minting a card.

## Rubric calibration

Weekly. Reads the week's verdicts and notes against the scores they corrected, backtests the rubric's rules as regexes over the window, and writes numbered proposals (tighten this gate, add this adder, drop this rule). Posts them; applies nothing. The owner answers "apply 2" or "skip 3" in the channel, and a session edits the rubric, bumps the version, and records the owner's words in the changelog. Every card shows the rubric version it was scored under.

## The Sync button

The page's Sync now button inserts a `sync_requests` row. The worker on the always-on machine picks it up within two minutes, runs ingest and build, writes the result sentence on the row, and the page's freshness banner shows it. It never runs the deep pass; newcomers wait for the morning.
