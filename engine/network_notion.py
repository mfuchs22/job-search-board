"""Networking contacts from Notion into the vault and the board.

The owner's Notion Network database is the home for contacts (2026-09-15): who, how connected, status, next touch
and its date. This module reads it through a Notion integration and writes <vault>/network/contacts.json:

    {"asof": "2026-09-15T09:30:00Z",
     "people": [{"id", "url", "name", "company", "role", "how", "status", "priority", "hook",
                 "last_type", "last_date", "last_note", "next_type", "next_action", "next_date",
                 "linkedin", "notes", "last_met", "roles": ["<10-hex job id>", ...], "edited",
                 "touches": [{"date", "type", "note"}, ...]}]}

Status is where the relationship stands (Not contacted, Waiting on them, In conversation, Working together, Champion,
Dormant); a touch is one contact, typed Email, Message, Call, Meeting, Event, Intro ask, Thank-you, Share or Check-in.
Each person carries their last touch (type, date, note), their next touch (type, what, date) and a Hook (why now).
The page body holds the touch log: a "Touch log" heading and one bulleted line per touch, "YYYY-MM-DD · Type · note".
The board's Done appends a line (network-write); `touches` is that log, newest first.

Networking tasks are not pulled (the owner, 2026-09-15: redundant with each person's next touch).

`roles` comes from the Network property "Job board roles" (job ids, comma-separated): a person can be the next step on
a specific role; the page also links people to roles by company name. build.py calls refresh() before the push, and
push_board.py mirrors people into the Supabase `contacts` table. The board's edits go the other way through the
network-write edge function (supabase/functions/network-write), which writes Notion first.

config.json:
    "notion": {"token_file": "~/.notion_integration_token", "network_data_source": "<id>"}

    py engine/network_notion.py          pull and write contacts.json
    py engine/network_notion.py --show   print what the last pull holds, no network
"""
import json
import re
import sys
from datetime import datetime, timezone
from urllib.error import URLError

import notion
from common import load_config, paths
from notion import call, plain, query_all

TOUCH = re.compile(r"^(\d{4}-\d{2}-\d{2})\s+·\s+(.+?)(?:\s+·\s+(.*))?$", re.S)


def contacts_file(p):
    return p.network / "contacts.json"


def settings(cfg):
    return notion.token(cfg), notion.source(cfg, "network_data_source")


def parse_touch(text):
    """One touch-log line. Keep in step with TOUCH in supabase/functions/network-write."""
    m = TOUCH.match(text.strip())
    return {"date": m.group(1), "type": m.group(2).strip(), "note": (m.group(3) or "").strip()} if m else None


def touches(token, page_id):
    """The touch log in a Network page body, newest first."""
    out = []
    for b in notion.children(token, page_id):
        if b.get("type") in ("bulleted_list_item", "paragraph"):
            t = parse_touch("".join(x.get("plain_text", "") for x in (b.get(b["type"]) or {}).get("rich_text") or []))
            if t:
                out.append(t)
    return sorted(out, key=lambda t: t["date"], reverse=True)


def person(page):
    """Keep in step with normalize() in supabase/functions/network-write."""
    P = page.get("properties") or {}
    g = lambda k: plain(P.get(k))
    roles = [x for x in str(g("Job board roles") or "").replace(";", ",").replace(" ", ",").split(",")
             if len(x) == 10 and all(c in "0123456789abcdef" for c in x)]
    return {"id": page["id"], "url": page.get("url"), "name": g("Name"), "company": g("Company"), "role": g("Role"),
            "how": g("How Connected"), "status": g("Status"), "priority": g("Priority"), "hook": g("Hook"),
            "last_type": g("Last Touch Type"), "last_date": g("Last Touch Date"), "last_note": g("Last Touch Note"),
            "next_type": g("Next Touch Type"), "next_action": g("Next Action"), "next_date": g("Next Action Date"),
            "linkedin": g("LinkedIn"), "notes": g("Notes"), "last_met": g("Last met"),
            "roles": roles, "edited": page.get("last_edited_time")}


def pull(cfg, p):
    token, network_ds = settings(cfg)
    people = [person(pg) for pg in query_all(token, network_ds)]
    for x in people:
        x["touches"] = touches(token, x["id"])
    people.sort(key=lambda x: (x["next_date"] or "9999", (x["name"] or "").lower()))
    out = {"asof": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "people": people}
    contacts_file(p).write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    return out


def load(p):
    f = contacts_file(p)
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"asof": None, "people": []}


def refresh(cfg, p):
    """Pull when Notion is reachable; otherwise keep the last file. Never breaks the build."""
    if not cfg.get("notion"):
        return load(p), "contacts: no notion block in config.json, skipped"
    try:
        out = pull(cfg, p)
        return out, f"contacts {len(out['people'])} people, {sum(len(x['touches']) for x in out['people'])} touches logged"
    except (SystemExit, URLError, OSError, ValueError, KeyError) as e:
        return load(p), f"contacts: notion pull failed ({e}); kept the last file"


def main():
    cfg = load_config()
    p = paths(cfg)
    data = load(p) if "--show" in sys.argv else pull(cfg, p)
    print(f"asof {data['asof']}: {len(data['people'])} people")
    for x in data["people"]:
        print(f"  {x['next_date'] or '----------'}  {x['status'] or '-':<12} {x['name']} ({x['company'] or '-'})"
              f"{' roles ' + ','.join(x['roles']) if x['roles'] else ''}: {x['next_action'] or ''}"
              f"{' [' + str(len(x.get('touches') or [])) + ' touches]' if x.get('touches') else ''}")


if __name__ == "__main__":
    main()
