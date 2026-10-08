"""Pull Notion into the vault: people, opportunities, meetings and career tasks.

Notion is the home for people (Network, 2026-09-15), for a Pursue role's process state (Opportunities, 2026-09-17),
for meeting notes, and for every task (the only task list, 2026-09-06). This module reads all four and writes four
files the board's mirrors are pushed from:

    <vault>/network/contacts.json       {"asof", "people": [...]}      (network_notion.py owns the person shape)
    <vault>/network/opportunities.json  {"asof", "opps": [{"id", "page", "url", "stage", "outcome", "next",
                                         "next_date", "hp", "hp_people", "flag", "company", "company_name",
                                         "people": [ids], "meetings": [ids], "tasks": [ids], "edited"}]}
    <vault>/network/meetings.json       {"asof", "meetings": [{"id", "url", "name", "date", "type", "summary",
                                         "actions", "status", "people": [ids], "companies": [ids], "opps": [ids]}]}
    <vault>/network/tasks.json         {"asof", "tasks": [{"id", "url", "title", "status", "area", "priority", "due",
                                         "plan_day", "waiting", "project", "notes", "opps": [ids], "meetings": [ids],
                                         "edited"}]}   (Area career and not Complete: what the To-dos tab shows)

`id` on an opportunity is the board record id (Notion's "Job ID"), so the page joins a card to its Notion page.
Meeting transcripts are not pulled. build.py calls refresh() before the push; push_board.py mirrors the four files
into the Supabase `contacts`, `opportunities`, `meetings` and `tasks` tables. The board's edits go the other way
through the network-write, opportunity-write and task-write edge functions, which write Notion first.

    py engine/notion_sync.py          pull and write the four files
    py engine/notion_sync.py --show   print what the last pull holds, no network
"""
import json
import sys
from datetime import datetime, timezone
from urllib.error import URLError

import notion
import network_notion
from common import load_config, paths
from notion import plain, query_all

STAGE = {"Shortlist": "shortlist", "Researching": "researching", "Outreach": "outreach", "Applied": "applied",
         "Interviewing": "interviewing", "Offer": "offer", "Closed": "closed"}
OUTCOME = {"No response": "no_response", "Rejected": "rejected", "Withdrew": "withdrew", "Accepted": "accepted",
           "Posting removed": "posting_removed"}
HP = {"Warm active": "warm active", "Warm reachable": "warm reachable", "Cold": "cold", "Unchecked": None}


def opps_file(p):
    return p.network / "opportunities.json"


def meetings_file(p):
    return p.network / "meetings.json"


def tasks_file(p):
    return p.network / "tasks.json"


def opportunity(page, company_names):
    """One Opportunities page as the board reads it. Keep in step with normalize() in opportunity-write."""
    P = page.get("properties") or {}
    g = lambda k: plain(P.get(k))
    co = g("Company") or []
    return {"id": g("Job ID"), "page": page["id"], "url": page.get("url"),
            "stage": STAGE.get(g("Stage")), "outcome": OUTCOME.get(g("Outcome")),
            "next": g("Next Step"), "next_date": g("Next Step Date"),
            "hp": HP.get(g("Human Path")), "hp_people": g("Human Path People"), "flag": bool(g("Flag")),
            "company": co[0] if co else None, "company_name": company_names.get(co[0]) if co else None,
            "people": g("People") or [], "meetings": g("Meetings") or [], "tasks": g("Tasks") or [],
            "edited": page.get("last_edited_time")}


def meeting(page):
    P = page.get("properties") or {}
    g = lambda k: plain(P.get(k))
    return {"id": page["id"], "url": page.get("url"), "name": g("Name"), "date": g("Date"), "type": g("Type"),
            "summary": g("Summary"), "actions": g("Action Items"), "status": g("Follow-up Status"),
            "people": g("People") or [], "companies": g("Company") or [], "opps": g("Opportunities") or []}


def task(page):
    """One Tasks page as the board reads it. Keep in step with normalize() in task-write."""
    P = page.get("properties") or {}
    g = lambda k: plain(P.get(k))
    return {"id": page["id"], "url": page.get("url"), "title": g("Task"), "status": g("Status"), "area": g("Area"),
            "priority": g("Priority"), "due": g("Due"), "plan_day": g("Plan day"), "waiting": g("Waiting on"),
            "project": g("Project"), "notes": g("Notes"), "opps": g("Opportunities") or [],
            "meetings": g("Meeting") or [], "edited": page.get("last_edited_time")}


# Only the career tasks still open: the To-dos tab's third source (2026-09-22). Status, Area and Project are selects.
# Project "Consulting" stays out (the owner, 2026-09-22): two consulting clients are private consulting and skill
# development, not the job search; he retags those tasks in Notion himself.
TASK_FILTER = {"filter": {"and": [{"property": "Area", "select": {"equals": "career"}},
                                  {"property": "Status", "select": {"does_not_equal": "Complete"}},
                                  {"property": "Project", "select": {"does_not_equal": "Consulting"}}]}}


def pull(cfg, p):
    tok = notion.token(cfg)
    n = cfg["notion"]
    contacts = network_notion.pull(cfg, p)
    names = {pg["id"]: plain((pg.get("properties") or {}).get("Name"))
             for pg in query_all(tok, notion.source(cfg, "companies_data_source"))}
    opps = [opportunity(pg, names) for pg in query_all(tok, notion.source(cfg, "opportunities_data_source"))]
    opps = [o for o in opps if o["id"]]
    opps.sort(key=lambda o: (o["stage"] or "", o["company_name"] or ""))
    meets = [meeting(pg) for pg in query_all(tok, notion.source(cfg, "meetings_data_source"))]
    meets.sort(key=lambda m: m["date"] or "", reverse=True)
    tasks = [task(pg) for pg in query_all(tok, notion.source(cfg, "tasks_data_source"), TASK_FILTER)] \
        if n.get("tasks_data_source") else []
    tasks.sort(key=lambda t: (t["plan_day"] or t["due"] or "9999", t["title"] or ""))
    asof = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    write(opps_file(p), {"asof": asof, "opps": opps})
    write(meetings_file(p), {"asof": asof, "meetings": meets})
    write(tasks_file(p), {"asof": asof, "tasks": tasks})
    return contacts, {"asof": asof, "opps": opps}, {"asof": asof, "meetings": meets}, {"asof": asof, "tasks": tasks}


def write(f, data):
    f.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")


def load(f, key):
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"asof": None, key: []}


def load_all(p):
    return (network_notion.load(p), load(opps_file(p), "opps"), load(meetings_file(p), "meetings"),
            load(tasks_file(p), "tasks"))


def refresh(cfg, p):
    """Pull when Notion is reachable; otherwise keep the last files. Never breaks the build."""
    if not cfg.get("notion"):
        return load_all(p), "notion: no notion block in config.json, skipped"
    try:
        c, o, m, t = pull(cfg, p)
        return (c, o, m, t), (f"notion {len(c['people'])} people, {sum(len(x['touches']) for x in c['people'])} touches, "
                              f"{len(o['opps'])} opportunities, {len(m['meetings'])} meetings, {len(t['tasks'])} career tasks")
    except (SystemExit, URLError, OSError, ValueError, KeyError) as e:
        return load_all(p), f"notion: pull failed ({e}); kept the last files"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    cfg = load_config()
    p = paths(cfg)
    c, o, m, t = load_all(p) if "--show" in sys.argv else pull(cfg, p)
    print(f"asof {o['asof']}: {len(c['people'])} people, {len(o['opps'])} opportunities, {len(m['meetings'])} meetings, "
          f"{len(t['tasks'])} career tasks")
    for x in o["opps"]:
        print(f"  {(x['stage'] or '-'):<13} {x['company_name'] or '-':<28} {x['id']}"
              f"{'  people ' + str(len(x['people'])) if x['people'] else ''}"
              f"{'  meetings ' + str(len(x['meetings'])) if x['meetings'] else ''}"
              f"{'  ' + x['next'] if x['next'] else ''}")
    for x in m["meetings"]:
        print(f"  {x['date'] or '----------'}  {x['type'] or '-':<12} {x['name']}"
              f"{'  opps ' + str(len(x['opps'])) if x['opps'] else ''}")
    for x in t["tasks"]:
        print(f"  {x['plan_day'] or x['due'] or '----------'}  {x['priority'] or '-':<3} {x['title']}"
              f"{'  ' + x['project'] if x['project'] else ''}")


if __name__ == "__main__":
    main()
