# Schema

## `jobs/jobs.json` (in the vault)

```json
{"asof": "2026-09-03", "jobs": [ <record>, ... ]}
```

One record per posting. Written only by `engine/build.py`, `engine/apply_deep_pass.py`, and `engine/ingest_db.py`.

| Field | Meaning |
|---|---|
| `id` | first 10 hex of sha1 over the canonical URL; stable for the life of the record |
| `aliases` | other canonical URLs folded into this record (same posting, another location or board) |
| `url`, `title`, `company`, `company_key`, `location`, `comp` | the posting; `company_key` is the join key into `people.json` and `companies.json` |
| `source` | `board:alert_name` from the radar, `baseline-<date>` from a deep pass, or `hand` |
| `date_first_seen` | ISO date the posting entered the funnel |
| `score`, `score_kind` | rubric score; `deep` (posting read) or `title` (radar, provisional) |
| `why`, `mismatch` | one line each from the scorer |
| `card` | deep-pass extras for the page: `math` (rubric arithmetic), `job` (bullets), `note` (alert chip) |
| `work_model`, `travel`, `qualifications`, `role_type`, `deep_pass_date`, `fetched` | deep-pass facts (see `docs/deep-pass.md`) |
| `flag` | owner's ⚑, never displaced by score |
| `verdict`, `verdict_date`, `verdict_ts` | `pursue`, `maybe`, `pass`, or null; date for the views, ISO timestamp for idempotence against the board database |
| `calibration`, `note` | "Too high / About right / Too low" and the owner's free text |
| `status_note` | the short reason shown in the leaderboard Status column and the passed list |
| `stage`, `stage_date`, `stage_ts`, `outcome` | Pursue only: `shortlist`, `researching`, `outreach`, `applied`, `interviewing`, `offer`, `closed`; outcome `no_response`, `rejected`, `withdrew`, `accepted`, `posting_removed` when closed (legacy `ghosted` reads as `no_response`). `posting_removed` is the owner's "Confirm removal" on the board's Closed tab (2026-10-06): the ad was filled or taken down, nobody passed. A Pursue closes through Notion as usual after the owner confirms; a non-Pursue role whose posting is gone is closed by `engine/posting_check.py` itself with no review (2026-10-07), so `stage: closed` can sit on a Pass or unreviewed record for that one outcome |
| `next_step`, `next_step_date` | the pipeline's Next Step cell |
| `job_file`, `company_file` | vault-relative paths without `.md` (`jobs/whoop-senior-pm-ai`, `companies/whoop`) |
| `excluded` | reason text when a hard exclusion removed the role from the board; kept, never deleted |
| `office` | the office the role is hired into, `{address, label, precision, source, lat, lng, geocoded, fallback}`: `precision` is `street`, `city`, `remote` or `unknown`; the deep pass (or `engine/office.py set`) gives the first four, `engine/office.py` adds the coordinates (OpenStreetMap Nominatim, cached in `jobs/geocache.json`); `fallback` is true when a street address resolved only to its city |
| `human_path` | the warm-path gate, `{verdict, qualifier, people, checked, ref, attached}`: verdict `warm active`, `warm reachable`, or `cold`; `people` the names and routes; `checked` ISO date; `attached` true/false once an application went out with or without a person. Written by `engine/human_path.py` and mirrored as the `**Human path:**` line on the role's front door (`jobs/<slug>.md`, and `opportunities/<slug>/README.md` when it exists) |
| `posting` | is the ad still up, `{state, since, checked, checks, streak, method, http, evidence, url_checked, last_active, frozen}`: state `active`, `closed` (the page says it is not taking applications), `removed` (404/410 or a redirect to the listings root), `unreachable` (bot wall, rate limit, or only Indeed/Glassdoor links), `unknown` (the rules conflicted, e.g. "filled" text next to a fresh datePosted; the model or the owner decides). `posted` is the ad's own posted date where a source gives one (JSON-LD datePosted, Greenhouse first_published, Ashby publishedAt, Workday startDate; LinkedIn's "posted N weeks ago" is kept as approximate, `posted_approx`); `kept` is the date the owner chose to keep a shortlist role whose ad is gone (`posting_check.py keep --id`), which stops the flag but not the recheck; `since` is the first date the current state was seen; `frozen` stops rechecking a closed or removed posting after two confirmations unless the role is a Pursue. `reposted`, `repost_of` and `closed_on` mark a repost (2026-10-07): the radar brought in a new URL with the same title and company as a record closed `posting_removed`, so `build.py` folded it in as an alias through `posting_check.note_repost` instead of minting a card (state active, method `repost` until the next nightly check verifies it); a non-Pursue role reopens into the Inbox (stage cleared), a Pursue stays closed until the owner reopens it; the morning POSTINGS block prints a REPOSTED line. Written only by `engine/posting_check.py` (the nightly `posting-check` routine); separate from `stage`, which stays the owner's. Passed roles are never checked (2026-10-07). Trace in `jobs/posting-log.jsonl` |
| `legacy_rank` | rank on the 2026-08-31 baseline review page (historical) |

Stage to the vault's job-file `Status:` value: shortlist = Shortlist, researching = Researching, outreach = Reached out, applied = Applied, interviewing = Interviewing, offer = Offer, closed = Closed (2026-09-15; before that a yes landed at researching and applied and interviewing both read In process).

## `jobs/companies.json`

```json
{"asof": "2026-09-03", "companies": {"<company_key>": {"url": "...", "about": ["..."], "growth": {...}}}}
```

`growth` carries `employees {count, as_of, source}`, `headcount_trend {read, detail, source}`, `revenue {latest, growth, source}`, `local_office {detail, source}`, `read`, `confidence`.

## `network/people.json`

Per `company_key`: `first` (connections: `id`, `name`, `title`, `url`, `since`, `tags`, `vault`), `second` (leads with a `via`), `affinity_only`, `vault` (person-file paths). Built by `engine/network_ingest.py`.

## Board database (Supabase, `supabase/migrations/`)

| Table | Writer | Row |
|---|---|---|
| `jobs` | engine (`push_board.py`) | `id`, `company_key`, `payload` (the page record: the fields above plus `math`, `bullets`, `alert`, `doc` = the job markdown rendered to HTML, `campaign` = the vault's `opportunities/<slug>/campaign.md` parsed plus the `roadmap/stakeholders.md` rows for the people in the next conversation, or null, `timeline` = the opportunity README's Timeline table newest first, `assets` = every asset for the opportunity with `sent` where log.md records it, `meetings_vault` = the README-linked meeting records, `log` = opportunities/<slug>/log.md rows), `updated_at` |
| `board_meta` | engine | `key` in `summary`, `companies`, `paths`; `payload`. Also `stage_history` (`stage_history.py`, called by `push_board.py`): `{asof, roles: {job id: [{stage, date, source}]}}`. Also `org_charts` (`org_chart.py`, called by `push_board.py`): `{company_key: chart}`, approved charts only (`status: approved` in the file; drafts are held), each chart the saved `data/org/<slug>.json` plus a `flag` {kinds, line, refs} on each person the vault or network knows, `flagged` and `not_on_site` |
| `verdicts` | the page (owner) | `id`, `v` ("Pursue" / "Maybe" / "Pass" / ""), `cal`, `note`, `ts`, `title`, `company` |
| `stages` | the page (owner) | `id`, `stage`, `outcome`, `next`, `ts`, `title`, `company` |
| `board_owners` | seeded once by hand | `email`; read only by the `is_board_owner()` definer function |
| `startups` | engine (`startups.py`) | `id` (MGMT slug), `name`, `payload` (the company card: MGMT's record, `office`, `research` row, `board_rows`, `first_degree`, `vault_card`, `screen` {score, tier, math}, `seat_posted`), `updated_at`; `board_meta` key `startups_summary` carries the counts |
| `startup_verdicts` | the page (owner) | `id`, `v` ("Interesting" / "Watch" / "Pass" / ""), `note`, `flag`, `ts`, `name`; last writer wins, the page overlays a row only when its `ts` is newer |

`summary` carries the tile counts plus `data_asof` (newest `date_first_seen` on the board), `built_at`, `radar_last` (newest `date_first_seen` in `inbox.csv`), `waiting_deep_pass`, `min_score`, `stages`, `outcomes`, `role_types`, `title`.

Access: row-level security on every table. The signed-in owner (email in `board_owners`) may select all four tables and insert or update `verdicts` and `stages`; nobody may delete through the API; the `anon` role has no grants at all. The engine uses the project's secret key, which bypasses RLS. Realtime is published on all four tables so an open page follows a build and a second device.

The page writes a whole row on every change (last writer wins). `ingest_db.py` applies a row only when its `ts` is newer than the record's stored `verdict_ts` / `stage_ts`, after normalising PostgREST's `+00:00` suffix to the page's `Z` form (`supabase.iso_z`), which makes re-reading the database a no-op. The page treats the record's stored verdict and stage as the baseline and overlays a row only when its `ts` is newer.

## `jobs/inbox.csv` (radar output)

`date_first_seen,board,alert_name,title,company,location,url,status,score,why`. Append-only. `score` and `why` were added 2026-09-03; older rows leave them blank and the record keeps whatever score a session assigned.
