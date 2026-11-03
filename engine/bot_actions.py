"""Outreach done outside the board, folded into Notion so the board's line for that person resolves (2026-11-02).

the owner emailed Chrissie Gorman Francona through the Grok career-coach bot and expected it to land everywhere. Notion's
Network database is the home for people; the board's `contacts` table, the vault's contacts.json and Today all follow
it. So a send made anywhere becomes one Notion write here, the same write the board's Done makes through network-write:
the last touch, a "YYYY-MM-DD · Type · note" line in the page's Touch log, and the next touch cleared when the send
fulfilled one that was due (or set, when the row says what comes next). The rows wait in the Supabase `bot_actions`
table, written by the Grok bot (supabase/functions/bot-action) and by the nightly Gmail read (`record` below).

    py engine/bot_actions.py fold [--dry-run]       fold every `new` row: find the person, write Notion, mark the row
                                                    done, skipped (already in the touch log) or failed (no one matches)
    py engine/bot_actions.py people [--out FILE]    the Network people with an email address, and the day to search
                                                    Gmail from (their last touch), for the nightly mail step
    py engine/bot_actions.py record events.json [--source gmail] [--dry-run]
                                                    insert the mail step's finds as rows, then fold
                                                    [{"person": "<page id or email>", "type": "Email", "date": "YYYY-MM-DD",
                                                      "note": "one line", "ext_id": "<Gmail message id>"}]

A row names a person by Network page id, by an email address in their page, or by full name; nobody new is created.
Nothing here sends anything. board-sync and the nightly runs call `fold`; it is a step, not a loop.
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import notion
import supabase
from common import load_config

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
UUID = re.compile(r"^[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}$", re.I)
SENT_TYPES = {"Email", "Message", "Call", "Meeting", "Event", "Intro ask", "Thank-you", "Share", "Check-in"}


def norm_id(s):
    return str(s or "").replace("-", "").lower()


def gmail_key(addr):
    """Gmail ignores dots and +tags in the local part: chrissie.gorman@ and chrissiegorman@ are one inbox."""
    local, _, domain = addr.lower().partition("@")
    local = local.split("+")[0]
    if domain in ("gmail.com", "googlemail.com"):
        local, domain = local.replace(".", ""), "gmail.com"
    return f"{local}@{domain}"


def emails(c):
    return sorted({gmail_key(m) for m in EMAIL.findall(" ".join(str(c.get(k) or "") for k in ("notes", "hook", "email")))})


def match(people, who):
    """The one Network person a row names, or (None, why)."""
    who = str(who or "").strip()
    if not who:
        return None, "no person named"
    if UUID.match(who):
        hit = [c for c in people if norm_id(c.get("id")) == norm_id(who)]
    elif "@" in who:
        key = gmail_key(EMAIL.search(who).group(0)) if EMAIL.search(who) else who.lower()
        hit = [c for c in people if key in emails(c)]
    else:
        n = " ".join(who.lower().split())
        hit = [c for c in people if " ".join(str(c.get("name") or "").lower().split()) == n]
    if len(hit) == 1:
        return hit[0], ""
    return None, (f"two or more Network people match {who}" if hit else f"no Network person matches {who}")


def plan(c, row):
    """What to write for one row: (properties as plain fields, touch-log line) or (None, why it is skipped)."""
    date, kind = str(row.get("date") or "")[:10], row.get("type") or "Email"
    note = (row.get("note") or "").strip()
    if kind not in SENT_TYPES:
        return None, f"unknown touch type {kind}"
    for t in c.get("touches") or []:
        if t.get("date") == date and t.get("type") == kind:
            return None, f"already in the touch log ({date} · {kind})"
    fields = {}
    if not c.get("last_date") or c["last_date"] <= date:
        fields.update(last_type=kind, last_date=date, last_note=note or None)
    if row.get("next_type") or row.get("next_action") or row.get("next_date"):
        fields.update(next_type=row.get("next_type"), next_action=row.get("next_action"), next_date=row.get("next_date"))
    elif c.get("next_date") and c["next_date"] <= date:
        fields.update(next_type=None, next_action=None, next_date=None)  # this send was the touch that was due
    line = " · ".join(x for x in (date, kind, note) if x)
    return fields, line


PROPS = {"last_type": ("Last Touch Type", "select"), "last_date": ("Last Touch Date", "date"),
         "last_note": ("Last Touch Note", "rich_text"), "next_type": ("Next Touch Type", "select"),
         "next_action": ("Next Action", "rich_text"), "next_date": ("Next Action Date", "date")}


def write(tok, c, fields, line):
    """One Notion write, the shape network-write's done action makes: properties, then the touch-log line."""
    props = {PROPS[k][0]: notion.prop(PROPS[k][1], v) for k, v in fields.items()}
    if props:
        notion.call(tok, f"/pages/{c['id']}", {"properties": props}, "PATCH")
    kids = [] if c.get("touches") else [{"type": "heading_3", "heading_3": {"rich_text": notion.text("Touch log")}}]
    kids.append({"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": notion.text(line)}})
    notion.call(tok, f"/blocks/{c['id']}/children", {"children": kids}, "PATCH")


def people_now(cfg):
    """The Network as the board sees it: the contacts mirror (notion-hook keeps it within minutes of Notion)."""
    return [r["payload"] for r in supabase.select("contacts", {"select": "payload"}, cfg=cfg) if r.get("payload")]


def fold(cfg, dry=False, out=print):
    rows = supabase.select("bot_actions", {"select": "*", "status": "eq.new", "order": "created_at"}, cfg=cfg)
    if not rows:
        out("bot actions: nothing new")
        return []
    people, tok, done = people_now(cfg), None if dry else notion.token(cfg), []
    for row in rows:
        c, why = match(people, row.get("person"))
        if not c:
            status, result = "failed", why
        else:
            fields, line = plan(c, row)
            if fields is None:
                status, result = "skipped", line
            else:
                status, result = "done", f"{c.get('name')}: logged {line}" + ("; next touch cleared" if fields.get("next_date", 1) is None else "")
                if not dry:
                    write(tok, c, fields, line)
                    c.setdefault("touches", []).insert(0, {"date": row.get("date"), "type": row.get("type"), "note": row.get("note")})
        out(f"  #{row['id']} {row.get('source')}: {status}, {result}")
        done.append((row["id"], status, result))
        if not dry:
            supabase.request("PATCH", "bot_actions", {"id": f"eq.{row['id']}"},
                             {"status": status, "result": result, "folded_at": datetime.now(timezone.utc).isoformat()},
                             prefer="return=minimal", cfg=cfg)
    return done


def people_list(cfg):
    return [{"id": c["id"], "name": c.get("name"), "emails": emails(c), "since": c.get("last_date")}
            for c in people_now(cfg) if emails(c)]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fold")
    f.add_argument("--dry-run", action="store_true")
    pl = sub.add_parser("people")
    pl.add_argument("--out")
    r = sub.add_parser("record")
    r.add_argument("events")
    r.add_argument("--source", default="gmail")
    r.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    cfg = load_config()
    if a.cmd == "fold":
        fold(cfg, a.dry_run)
    elif a.cmd == "people":
        data = json.dumps(people_list(cfg), indent=1, ensure_ascii=False)
        Path(a.out).write_text(data, encoding="utf-8") if a.out else print(data)
    else:
        events = json.loads(Path(a.events).read_text(encoding="utf-8"))
        rows = [{"source": a.source, "ext_id": e.get("ext_id"), "person": e["person"], "type": e.get("type") or "Email",
                 "date": e["date"], "note": e.get("note")} for e in events if e.get("person") and e.get("date")]
        if a.dry_run:
            print(f"would record {len(rows)} rows")
        elif rows:
            supabase.request("POST", "bot_actions", {"on_conflict": "source,ext_id"}, rows,
                             prefer="resolution=ignore-duplicates,return=minimal", cfg=cfg)
        fold(cfg, a.dry_run)


if __name__ == "__main__":
    sys.exit(main())
