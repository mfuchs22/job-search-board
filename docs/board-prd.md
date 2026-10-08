# Job Search Board: product requirements

v2, 2026-09-04, after the owner's walkthrough (answers recorded in section 10). The board is the one screen the job search runs from. It replaces the claude.ai artifact and its export-and-paste loop with a hosted page, a database, and a morning refresh that needs nobody in the loop.

## 1. Who and why

One user. Phone first thing in the morning for a quick scan (new postings, summary stats, the occasional verdict while waiting somewhere); laptop later for the deeper work (most verdicts, pipeline moves, reading a role). Jobs to be done:

1. **Clear the inbox, daily.** New roles that cleared the screen arrive overnight. For each: read enough to decide, give a verdict (Pursue, Maybe, Pass), say whether the score felt right (calibration), leave a note that explains the call, press Enter, next card. Every click saves instantly.
2. **Run the pipeline, daily.** Pursue roles move through stages (shortlist, researching, outreach, applied, interviewing, offer, closed; renamed 2026-09-15 so a yes lands on the shortlist and closed roles leave the columns for Screened out) with a next step and a date. Maybe roles are parked, visible, flippable.
3. **Open one role and read everything, periodically,** mostly for roles already liked: posting bullets and qualifications, the company and whether it is growing, who I know there, why it scored and what the mismatch is, the AI-fit read (Phase 3), the process log.
4. **Never have to check freshness.** The page states its own freshness so plainly that "is this today's batch?" is answered before the question forms.

Future, not this build: call prep and outreach writing.

## 2. Rules carried over (2026-09-03), all kept

- **Nothing reaches the inbox without the deep pass.** A card appears only after the posting has been read: role bullets, qualifications, company blurb, growth read, why and mismatch, deep score. Title-level radar rows never render as cards; they are the "waiting" count in the freshness banner.
- **The current rubric gates every newcomer.** Hard exclusions and the company blocklist first, then points.
- **Full cards, always.** A reviewed card keeps everything it had; the verdict is added, never swapped in for the content.
- **One card design, status on every card.** The owner's favourite of the four.

New in v2: **the review floor is 8.** 7s are not hidden; they live in a Borderline section with the same card and the same controls. 6 and below never appear.

## 3. Navigation and screens

**Navigation:** a section list on the left, on desktop and phone alike (a collapsible rail on phone). Choosing a section gives it the rest of the screen. Sections: Inbox, Board, Borderline, Screened out, and (when Phase 3 lands) Profile gaps. The summary strip and the freshness banner sit above whichever section is open.

### Freshness banner (top of every section)
A state, not a footer line: green "Fresh: postings through {data_asof}, built {time}"; amber "Radar delivered {radar_last}, {n} waiting for the deep pass"; red "Board is {n} days old". Always visible, never something to go and check.

### Summary strip
Four tiles: **New** (arrived in the latest delivery, not yet reviewed), **Reviewed** (has a verdict), **Pursue** (everything past the screen), **Screened out** (every Pass and exclusion). Pursue carries sub-filters Networked (known connection), Applied, Interviewed. Below the tiles, the breakdowns the owner likes: role type, work model, score distribution (placement to be settled on the canvas; the content stays).

### Inbox (default)
Cards grouped by arrival day, newest day first, score order inside each day, worked day by day. A **New** chip on cards from the latest delivery. Verdict controls on the card. Enter in the note field saves and moves focus to the next card. Empty state: "Nothing to review. Radar last delivered {date}."

### Board
Pursue roles by stage: columns on desktop, stacked sections on phone. Each card shows its next step and date; a next step older than 7 days shows its date in the warning colour. Maybe as its own parked section with inline verdict controls so a Maybe flips to Pursue or Pass in one click. Flagged roles (⚑, "excited about this one") sort first inside their stage.

### Borderline
The 7s, same card and controls as the inbox, grouped by day. A verdict here moves the role onto the Board or into Screened out like any other.

### Screened out
Pass and Excluded as collapsed lists with counts and reasons (the rubric's training data and the audit trail). Read-only on the page; reopening a Pass is a session task.

### Job detail (one route per role)
Header: title, company (link to the posting), location and work model, comp and travel when known, score with the deep marker, flag, verdict and stage controls, note.
Sections in order: What the role is (bullets); What they ask for (qualifications); Company (blurb, growth: headcount, trend, revenue, local office, confidence); Who I know (first-degree, second-degree with the "via", affinity-only); Why it scored (rubric math, why, mismatch); AI fit (Phase 3; until built, a single line "not yet assessed"); Process log (from the job file when one exists); Outreach plan (Phase 3 placeholder).
Roles without a job file show what the engine has; no empty boxes.

## 4. Card anatomy

Title; company; location and work model; score with deep or title marker; status pill (To review, Borderline, Pursue + stage, Maybe, Pass, Excluded); New chip; flag; connection indicator (known path or none); one-line why; one-line mismatch; verdict buttons; calibration (Too high, About right, Too low); note; for Pursue: stage select, outcome when closed, next step and date.

## 5. States the design must include

Loading; signed out (email and password, one sign-in per device that persists; Add to Home Screen on the phone); the three freshness states; empty inbox; a card mid-save and saved (visible tick); save failed (message, nothing lost on screen); a Pass in the collapsed list; a role with no known connection; a role with no job file; a Pursue with an overdue next step; a Borderline card; a flagged card.

## 6. Interactions

- Verdict, calibration, flag, stage, outcome: save on click.
- Note and next step: save on Enter and on leaving the field, with a short debounce while typing. Shift+Enter inserts a newline. In the inbox, Enter also advances to the next card.
- Two devices stay in step without reload (realtime); a phone tab that slept catches up when it wakes.
- Sign out exists but is out of the way.
- Phone first: inbox cards and their controls work one-handed; the detail page reads top to bottom; nothing scrolls horizontally.

## 7. Non-goals (confirmed)

No budget or application-document management. No editing of posting text or company facts on the page. No rubric editing on the page (corrections go to the rubric's feedback log through a session). No other users.

## 8. Visual direction

Reference: **Linear** as a feel (dense, quiet, keyboard-friendly, strong typography, subtle borders, colour used only for state), executed as an original design. Light and dark themes, both first-class. Two directions on the canvas: a dense list (rows that carry the full card) and a card layout; the owner picks and edits.

## 9. Data contract (Supabase)

- `jobs`: one row per live record (deep-scored 7 or higher, or carrying a verdict, or excluded); `payload` is the full card plus the rendered job file. Engine-only writer.
- `board_meta`: `summary` (tile counts, breakdown inputs, `data_asof`, `built_at`, `radar_last`, `waiting_deep_pass`, `review_floor` 8, `board_floor` 7), `companies` (blurb, url, growth), `paths` (who I know per company). Engine-only writer.
- `verdicts` (v, cal, note, flag, ts) and `stages` (stage, outcome, next, ts): page-written, one row per role, last writer wins; the engine folds rows newer than the record's stored timestamp back into the canonical record each morning.
- The page shows the record's stored verdict, flag, and stage as the baseline and overlays a row only when it is newer.

## 10. Walkthrough record (2026-09-04)

Prompts and the owner's answers, kept as the trail behind v2.

1. Where opened most: phone first for a quick scan (new postings, stats, the occasional verdict), laptop for the deeper work.
2. Frequency: daily inbox and pipeline; periodic detail reads for liked roles; freshness should be obvious without checking.
3. No fifth job yet; call prep and outreach are future work.
4. All four rules kept; one card design with status on every card called out as liked.
5. Floor 8, 7s in a Borderline section.
6. Inbox by arrival day, score order inside each.
7. Desktop board: columns by stage. 8. Phone board: stacked sections. Both with a left-hand section list.
9. Maybe cards keep inline verdict controls. 10. Reopening a Pass is a session task.
11. Detail order accepted; AI fit matters and becomes a real section when built.
12. Tiles: New, Reviewed, Pursue (with Networked, Applied, Interviewed filters), Screened out.
13. Freshness as a state banner accepted. 14. Card contents accepted.
15. Flag kept, meaning "excited about this one", independent of verdict and stage.
16. Password login once per device, Add to Home Screen. 17. Enter advances to the next card.
18. Overdue after 7 days, colored date. 19. Non-goals confirmed.
20. Linear as the reference; dark mode wanted. 21. Keep the summary cards, role-type and work-model breakdowns.

## 11. Direction chosen (2026-09-04, from the canvas)

Direction A, the dense list, in the light theme only (the dark version was "hard on my eyes"). Phone: the summary tiles shrink to a compact one-line strip; everything else as drawn. Canvas: https://claude.ai/code/artifact/cfe4eb3e-f55a-44ff-a427-8519284fe184 (page 1 is the chosen set; page 2 keeps the unchosen sketches).

## 12. To-dos tab (2026-09-22)

Built from the design canvas "Job Search To-dos" (fifteen working prototypes; the owner picked the split pane, the do-now three and the day-by-day agenda, and the build is round-2 option B, "Focus over the pane", with the phone stacking of option D).

- One agenda over three homes, never a list of its own: a Pursue role's next step (Notion Opportunities, `fb().next` and `nextDate`), a person's next touch (Notion Network, the same due rule as the Network tab's Do now), and the career tasks (Notion Tasks, Area career and not Complete, mirrored into `tasks` by `notion_sync.py` and `push_board.py`). Each source has its own chip colour.
- Groups: Overdue, Today, each of the next five days, Next week, Later and undated, No next step yet (Pursue roles without a step). Each folds.
- Right side, sticky: Do now (the first three overdue or due today, Done and Later, a Next up line) above the selected item's pane (title, who and what, when, notes, Done, Do today, Tomorrow, Next week, Open, "Also for", and where the item lives). Under 901px the page stacks Do now first and a tapped row opens in place.
- Done: a role's step is cleared (opportunity-write) and the pane asks for the following step; a person gets the Network done form (log the touch, set the next); a task is set Complete (task-write). Snoozes set the role's next step date, the person's next date, or the task's Plan day, never its Due.
- Rail count: items overdue or due today. Routes `#todos` and `#todos/<role|person|task>:<id>`.
- Nothing writes on click (2026-09-22, after a mistaken Done vanished at once). Every action is staged in the browser (localStorage, per item): a Done strikes the row through where it sits and drops it from Do now, a date moves the row to its new group, a new step renames it; each staged row has Undo. A bar at the top says N changes pending with Sync and Discard all. Sync sends the changes in order through the same three paths, keeps a failed one staged with its reason, and repaints from what Notion returned.
- The date buttons everywhere are Done, Today, Tomorrow, Next week, Later. Later means no date: a role keeps its step and loses its date, a person keeps the next touch and loses its date, a task loses both Plan day and Due (task-write's update accepts `due: null` for this and never sets Due).
- Consulting is not job search (2026-09-22, two consulting clients): the tasks mirror skips Project "Consulting" and the tab skips contacts whose status is Working together (Network keeps them).

## 13. Startups tab (2026-09-23)

the owner's ask, the same day the Boston startups research pass finished: see every company we now hold data on, much as MGMT Boston shows them, with a review and screening process for which are interesting and worth diligence, mapped where they sit in Boston, in the shape and style of the job board, viewed separately for now. Later the three tracks of the search (established businesses, consulting firms, the startup scene) may merge into one Companies view with roles tagged to their company; the tab is kept separate until the screen has run once.

- Universe: MGMT Boston's Big Board (343 companies), read from MGMT's own public database every Monday by Personal-OS `Tools/mgmt_watch.py`, exported as `research/boston-startups/mgmt-board.json`; `engine/startups.py` joins it with the research tables (`companies.md`), the board rows, first-degree connections and vault cards, geocodes the office through the shared cache, computes a deterministic screen pre-score (0 to 10, math on the card, tiers Look closer / Watch / Skip) and pushes `startups`.
- Shape: the Inbox split. List rows carry the screen score, name, stage, tag, HQ, headcount, latest round, and chips for the status, a posted seat, a first-degree path and board rows. Filters: status, pre-score band, stage, MGMT tag, seat posted, path in, researched, plus a search over name, one-liner, description and sector; kept in the browser.
- Inbox model (2026-09-23, after the first vetting session): every company is in exactly one of four statuses, To vet (no call yet), Interesting, Watch, Pass, and the status chips, the row chips and the pane all use those four words. The tab opens on To vet; a call moves the company out of the inbox and the split advances to the next row. The engine's pre-score tiers are a second, separate filter named High (9+), Mid (5 to 8), Low, never Watch, because the first cut named the tier filter Screen with a Watch chip beside the owner's Watch call and the two read as one thing. The pane: MGMT's record and links, what they do and why it fits from the research row, open roles on the archetype, path in, board rows with links, the office on a small map, the screen math, the vault links, and the call.
- The call: Interesting (worth diligence or a founder conversation), Watch (parked, the Monday post tracks it), Pass. Flag and a note. Saved on click to `startup_verdicts`; a call in the split advances to the next row. The engine never reads the calls back; the page overlays them.
- Map: `#startups/map`, every company with an address (336 of 343 on day one), pins coloured by the call, a side list that flies to a pin, a shared pin opens a chooser.
- On the Map tab (2026-09-23 night; the owner: "the page on the job board is the map page so it should be the map page", then "five different variations... on this page", then the call). Five renderings (Dots, Rings, Small, Named, Heat) and five dot styles were built as switches on the live page and he chose: dots only, every dot the role pins' size ("I don't think you need to size them based on some sort of random metric"), colour by his call and nothing else, two colours distinct from the roles' indigo and amber: Interesting green, Watch magenta; To vet grey; Pass never drawn. The filter area is two columns side by side, Roles on the left and Startups on the right ("left to right makes more sense"), each header a show/hide toggle. The startup chips are the tab's criteria but the Map's own state, after a shared state let a tap on the Map filter his review list. A company whose address is a city only (most of MGMT's records) is listed under the pins, not drawn on the centroid. A separate mockup page was rejected first: variations of an existing page belong on that page.
- Process: `Personal-OS/Projects/job-search/research/boston-startups/screen.md`.

