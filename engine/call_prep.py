"""Conversations booked with people, and which still owe a prep brief.

    py engine/call_prep.py owed [--days 3]      the Network people with a Call or Meeting as their next touch in the next
                                                N days (today included) and no prep brief yet, as JSON
    py engine/call_prep.py note <contact id> <text> [--dry-run]
                                                append one line to the person's Notes in Notion (the brief's link)

the owner, 2026-10-21: "You book a call, and there should be background diligence on the person, on the company, the
opportunity, and everything you can find to prep you for that interaction." Deciding what is owed is deterministic and
lives here; the brief is the /call-prep skill (Personal-OS .claude/skills/call-prep), run by the nightly pursue-followup
routine for each row, or by the owner. A brief is <vault>/meetings/YYYY-MM-DD-<person-slug>-prep.md, dated for the call, so
the /debrief record lands beside it. Reads the last Notion pull (network/contacts.json); run network_notion.py first for
a fresh one. Nothing here contacts anyone.
"""
import argparse
import json
import re
import sys
from datetime import date, timedelta

import notion
from common import load_config, paths
from network_notion import contacts_file

TYPES = {"call", "meeting"}


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")


def owed(p, days, today=None):
    today = today or date.today()
    last = (today + timedelta(days=days - 1)).isoformat()
    people = (json.loads(contacts_file(p).read_text(encoding="utf-8")) if contacts_file(p).exists() else {}).get("people") or []
    out = []
    for c in people:
        d = c.get("next_date") or ""
        if (c.get("next_type") or "").lower() not in TYPES or not (today.isoformat() <= d <= last):
            continue
        s = slug(c.get("name"))
        brief = p.vault / "meetings" / f"{d}-{s}-prep.md"
        if brief.exists():
            continue
        out.append({"id": c["id"], "name": c.get("name"), "company": c.get("company"), "role": c.get("role"),
                    "date": d, "type": c.get("next_type"), "action": c.get("next_action"), "how": c.get("how"),
                    "hook": c.get("hook"), "roles": c.get("roles") or [], "person_file": f"people/{s}.md",
                    "brief": brief.relative_to(p.vault).as_posix()})
    return sorted(out, key=lambda r: r["date"])


def note(cfg, cid, text, dry):
    tok = notion.token(cfg)
    page = notion.call(tok, f"/pages/{cid}")
    cur = notion.plain(page["properties"].get("Notes")) or ""
    if text in cur:
        return "already noted"
    new = (cur + "\n" if cur else "") + text
    if dry:
        return f"would set Notes to: {new[-200:]}"
    notion.call(tok, f"/pages/{cid}", {"properties": {"Notes": notion.prop("rich_text", new[-2000:])}}, "PATCH")
    return "noted"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("owed")
    o.add_argument("--days", type=int, default=3)
    n = sub.add_parser("note")
    n.add_argument("id")
    n.add_argument("text")
    n.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    cfg = load_config()
    if a.cmd == "owed":
        json.dump(owed(paths(cfg), a.days), sys.stdout, indent=1)
        print()
    else:
        print(note(cfg, a.id, a.text, a.dry_run))


if __name__ == "__main__":
    main()
