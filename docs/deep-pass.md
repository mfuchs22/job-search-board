# Deep pass brief

The deep pass is the step that turns a radar row (title, company, location, a provisional title-level score) into a card the owner can decide on. Nothing renders on the board without it. It needs a model reading the posting and the company, and it needs a machine that can fetch posting pages (the cloud radar cannot), so it runs in a local Claude Code session: the morning refresh routine, or any session on request.

## Who gets a deep pass

Records in `jobs.json` with `score_kind == "title"`, `score >= min_score`, no `deep_pass_date`, not `excluded`, no `verdict`. `build.py` ingests inbox.csv first, so run it (with `--no-push`) before selecting.

## Inputs

- The vault rubric (`<vault>/jobs/rubric.md`): the live version's order of operations (hard exclusions, company gate, points), every owner adjustment, and the feedback log. Read it fresh every run; it changes after most review sessions.
- `<vault>/jobs/companies.json`: reuse an existing company entry (about, url, growth) rather than researching twice.
- The record: `id`, `url`, `aliases`, `title`, `company`, `location`, `why` (the radar's one-liner).

## Steps, per record

1. **Fetch the posting** at `url` (fall back to each alias). Liveness is not this pass's call (2026-10-06): "filled", "expired" or "no longer accepting" text alone never makes a posting closed when the page carries a `datePosted` inside 30 days or a working apply link (BCG X carried both, feedback 2026-10-06, line 114); record what the page said in `mismatch` and leave the state to the nightly `engine/posting_check.py`, which writes `posting` on the record. Lever (`jobs.lever.co`) and Glassdoor return 403 to plain fetches: read those through the browser pane (Claude in Chrome) as the standard fallback, not as a last resort. If the page still cannot be read, set `fetched: false`, keep the title-level score, and still fill what the title and company allow; say so in `mismatch`. When a recruiter-board listing (Swooped, RemoteHunter, and the like) hides the employer and the posting reveals it, name the real employer in the first bullet and in `mismatch` so the duplicate is visible; the record's company name stays as posted (a corrected-company field is on the review list).
2. **Read the role.** 4 to 7 `bullets` on what the role actually does (verbs, scope, who it reports to, team size if stated). `qualifications`: the hard asks in one line each (years, degrees, certs, domain), with unmeetable ones marked.
3. **Read the company.** `company_about`: 2 to 3 short sentences (what it sells, to whom, scale). `company_url`. `growth`: `employees {count, as_of, source}`, `headcount_trend {read: growing|flat|shrinking|unknown, detail, source}`, `revenue {latest, growth, source}`, `local_office {detail, source}`, `read` (one line), `confidence` (high|medium|low). Web sources only (filings, press, third-party trackers); no LinkedIn browsing.
4. **Confirm the facts the gates need**: `location` (city, state; every location the posting lists), `work_model` (remote|hybrid|onsite plus days if stated), `travel` (percentage or phrase if stated), `comp` (range if stated).
   `office`: the one office this role is hired into, not every office the company has: `{address, label, precision, source}`. If the posting names a site, give that site's street address, sourced from the company's locations or contact page. If the posting names only a city and the company has exactly one office in that metro, give that office's street address. If the company has several offices there and the posting does not say which, give `"City, ST"` with `precision: "city"` and name the candidates in `label`. A remote role is `{"precision": "remote"}`. When nothing can be found, `{"precision": "unknown"}`. `precision` is `street`, `city`, `remote` or `unknown`. No coordinates: `engine/office.py` geocodes on the next build.
5. **Apply the rubric in order.** Hard exclusions and company blocklist first: if one fires, set `excluded` to the reason text and stop scoring. Then the company gate, then points. Write `math` as the visible arithmetic (`base 7; agentic +2; growing +1; enablement-as-training -1 = 9`), `score` as the integer, `why` (one line, the strongest reason it fits) and `mismatch` (one line, the strongest reason it does not; when the posting requires a domain, stack, credential, years of formal product management or experience leading product managers the owner does not have, `mismatch` starts with `stretch: <the ask, verbatim>`, rubric v3.3, no points). `apply_deep_pass.py` stamps `rubric_version` from the rubric's "Current version" line, and the card shows it next to the score. A judgment the rubric does not cover (a requirement not on the unmeetable list, a travel ask between the flag and the gate) is made, written into `math` as `interpretation: <rule>`, and logged to `Tools/feedback/job-radar.md` as a proposal; it never becomes practice by repetition. The weekly `rubric-calibration` routine reads those lines (vault `jobs/calibration.md`, 2026-10-07).
6. **Type the role**: `role_type` from `transformation-owner`, `internal-platform-pm`, `fde-embedded`, `ai-product-pm`, `governance-risk`, `enablement-adoption`, `consulting-advisory`, `program-project`, `other`.

## Corrections the pass may return

- `url`: when the record's url is a search link rather than a posting (an Indeed row whose alert id could not be recovered), or when a recruiter-board link resolves to the employer's own posting. `apply_deep_pass.py` moves the old url into `aliases` and sets the new one; the record id does not change.
- `company`: when a recruiter board (Swooped, RemoteHunter, and the like) hid the employer and the posting names it. `apply_deep_pass.py` keeps the posted name in `company_as_posted`, sets `company` and `company_key` to the real employer, and the next build folds duplicates that now share a title and company.

## Output

One JSON array per agent, one object per record, saved as `out-<date>-<n>.json` in the engine repo root (git-ignored is not needed; the files are transient and deleted after apply):

```json
[{
  "id": "…", "fetched": true,
  "location": "Andover, MA", "work_model": "hybrid, 3 days", "comp": "$180-220K", "travel": null,
  "office": {"address": "…, Andover, MA 01810", "label": "Andover HQ", "precision": "street", "source": "https://…/locations"},
  "bullets": ["…"], "qualifications": ["…"],
  "company_about": ["…", "…"], "company_url": "https://…",
  "growth": {"employees": {"count": "…", "as_of": "…", "source": "…"},
             "headcount_trend": {"read": "growing", "detail": "…", "source": "…"},
             "revenue": {"latest": "…", "growth": "…", "source": "…"},
             "local_office": {"detail": "…", "source": "…"},
             "read": "…", "confidence": "medium"},
  "role_type": "transformation-owner",
  "excluded": null,
  "score": 8, "math": "base 7; … = 8", "why": "…", "mismatch": "…"
}]
```

Then `py engine/apply_deep_pass.py out-<date>-*.json` and `py engine/build.py`. The build pushes the board; the new cards appear with the New chip.

## Parallelism

Up to three agents, each with a disjoint slice of the records and this brief verbatim. Each agent reads the rubric itself. Company research for a company already in `companies.json` is reused, not repeated.
