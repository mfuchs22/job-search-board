# Conversation-led roles

A firm heard about the owner, usually through a recruiter or a contact, and wants to talk. There is no job description and no posting. Creating the Opportunity is the Pursue: there is no second decision and the board does not ask for one.

## How one gets into the engine

The 04:30 refresh (`py engine/build.py` on the mini) does this. Nothing is run by hand.

1. `data/conversations.json` in this repo is ingested. Each row becomes a Pursue if that Notion page is not already a record. Battery Global Advisors is the first row.
2. The build writes that record's Job ID onto the Notion page. It does not change stage, lane, or the next step.
3. `notion_sync.pull` keeps a page with **no Job ID, no posting, and a stage** on `untitled` in `network/opportunities.json`. Those pages are not rows in the opportunities mirror, because that table is keyed on Job ID. The same build mints a Pursue from each one the seed does not already cover, writes the Job ID, and pulls again so the mirror joins.

A future conversation needs no pull request. In Notion, create an Opportunities page, set the stage, leave Job ID and Posting empty. The next refresh tracks it. The seed file is how a role carries a precise person, channel, and reason (those are what the id is hashed from). A page with no seed row uses the page title, the company, Human Path People, and the next step.

`py engine/add_role.py --conversation` still works. It is the fallback, and it implies Pursue. `--verdict pass` is refused.

## Record

| Field | Value |
|---|---|
| `kind` | `conversation`, kept after a JD arrives |
| `verdict` | `pursue`. Tracking it is the decision |
| `stage` | the stage on the page or in the seed (BGA is `interviewing`) |
| `priority` | `high` |
| `score` | null, `score_kind` `conversation`, until a deep pass |
| `intake` | person, channel, reason, summary, `notion_page` |
| `id` | sha1 of `https://conversation.local/<company>/<person>/<date>/<reason>` |

The board shows the call as Pursue and does not offer Pursue, Pass, or back to review.

## What keeps running, and what does not

Skipped until a JD is scored: posting checks, the deep-pass newcomer queue, tailored resume and cover (`skip_materials`). Diligence, the campaign, call prep, mail, human path, and follow-up dates still run.

## Upgrade

```
py engine/add_role.py --upgrade --company "..." --title "..." --url https://...
```

The id stays. The score stays null until `apply_deep_pass.py` reads the JD.
