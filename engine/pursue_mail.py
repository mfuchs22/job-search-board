"""What happened by email on the roles in play, recorded once: log.md, then stage, Ball and the follow-up date.

    py engine/pursue_mail.py targets [--out FILE]   the roles to search Gmail for, as JSON: every open Pursue that is Active
                                                    or Applied and later, with the people, the recruiter, the company and
                                                    the newest log.md row (search from that date on)
    py engine/pursue_mail.py record events.json [--dry-run]
                                                    fold what the model found into each role: a row per event in
                                                    opportunities/<slug>/log.md (an event already there is skipped), then
                                                    one Notion write per role from its newest event
    py engine/pursue_mail.py sweep [--dry-run]      roles waiting on them past the follow-up date: propose the nudge, and
                                                    after a nudge with no answer, propose No response (the owner decides)

The model's part (the pursue-followup routine's mail step, Personal-OS Tools/pursue-followup-prompt.md) is only reading
Gmail and writing events.json:

    [{"id": "<record id>", "date": "YYYY-MM-DD", "time": "2:29 PM", "type": "Sent" | "Email" | "Applied" | "Invite",
      "with": "the recruiter (the search firm)", "what": "one line", "link": "https://mail.google.com/...", "when": "YYYY-MM-DD"}]

Sent is the owner writing to someone about the role; Email is them writing to him; Applied is a portal's confirmation;
Invite is an interview being booked, found in Gmail or only on the calendar (2026-10-23: invites that never reach
the inbox, booked straight onto the calendar); `when` is the interview's own date, and the role's next step is dated
for it, so Today's three-day interview rule sees it. The rules here are the owner's (2026-10-20): a send hands the ball to them and sets a
follow-up at 5 business days (10 after an application); a reply hands it back to him and replaces the reminder; an
invite moves the role to Interviewing. A stage only ever moves forward here, and nothing here closes a role: No
response is proposed as the owner's next step, never set. Every event from them on an Active role, and every invite, goes
to Tools/pursue-followup/urgent.json for engine/today.py to ping once. Nothing here sends anything.
"""
import argparse
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path

from common import by_id, load_config, load_jobs, paths
from notion_sync import load as load_notion, opps_file
from pursue_followup import LATE, job_slug, set_next
from render_dashboard import log_rows

ORDER = ["shortlist", "researching", "outreach", "applied", "interviewing", "offer"]
TYPES = {"Sent", "Email", "Applied", "Invite"}
HEAD = ("# Log: {title}, {company}\n\nEvery email and everything sent, one row each, kept by Claude from Gmail. The board's "
        "timeline and Library read it. Sent rows list the files that went out.\n\n"
        "| Date | Time | Type | With | What | Link | Assets |\n|---|---|---|---|---|---|---|\n")


def biz(d, n):
    """n business days after date d."""
    while n:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def urgent_file(p):
    return p.personal_os / "Tools" / "pursue-followup" / "urgent.json"


def in_play(p):
    """(record, opportunity) for every open Pursue that is Active, or Applied and later whatever its lane."""
    idx = by_id(load_jobs(p))
    for o in (load_notion(opps_file(p), "opps") or {}).get("opps") or []:
        j = idx.get(o.get("id"))
        if not j or j.get("verdict") != "pursue" or o.get("stage") in (None, "closed"):
            continue
        if o.get("lane") == "active" or o["stage"] in LATE:
            yield j, o


def targets(p):
    contacts = {c["id"]: c for c in ((load_notion(p.network / "contacts.json", "people") or {}).get("people") or [])}
    out = []
    for j, o in in_play(p):
        rows = log_rows(p.vault, j["job_file"]) if j.get("job_file") else []
        co = j.get("company") or ""
        out.append({
            "id": j["id"], "company": co, "title": j.get("title"), "stage": o["stage"], "lane": o.get("lane"),
            "ball": o.get("ball"), "next": o.get("next"), "next_date": o.get("next_date"), "slug": job_slug(j),
            "recruiter": co.split(" via ", 1)[1].strip() if " via " in co else None,
            "employer": co.split(" via ", 1)[0].strip(),
            "people": [{"name": contacts[i].get("name"), "company": contacts[i].get("company"), "role": contacts[i].get("role")}
                       for i in o.get("people") or [] if i in contacts],
            "hp_people": o.get("hp_people"),
            "since": max([r["date"] for r in rows] or [j.get("verdict_date") or ""]),
        })
    return out


def cell(s):
    return " ".join(str(s or "").replace("|", "/").split())


def append_log(p, j, events, dry):
    """Add the events not already in log.md. Returns the ones added."""
    d = p.vault / "opportunities" / job_slug(j)
    f = d / "log.md"
    have = {(r["date"], r["type"].lower(), r["url"] or r["what"][:40]) for r in log_rows(p.vault, j["job_file"])} if f.exists() else set()
    new = [e for e in events if (e["date"], e["type"].lower(), e.get("link") or cell(e["what"])[:40]) not in have]
    if new and not dry:
        d.mkdir(parents=True, exist_ok=True)
        txt = f.read_text(encoding="utf-8") if f.exists() else HEAD.format(title=j.get("title"), company=j.get("company"))
        rows = "".join(f"| {e['date']} | {cell(e.get('time'))} | {e['type']} | {cell(e['with'])} | {cell(e['what'])} | "
                       f"{cell(e.get('link'))} | |\n" for e in new)
        f.write_text(txt.rstrip("\n") + "\n" + rows, encoding="utf-8")
    return new


def effect(e, stage):
    """The Notion write one event implies: (stage or None, ball, next, next_date)."""
    d = date.fromisoformat(e["date"])
    fwd = lambda s: s if ORDER.index(s) > ORDER.index(stage) else None
    who = e["with"].split("(")[0].strip()
    if e["type"] == "Invite":
        when = e.get("when") if re.match(r"\d{4}-\d{2}-\d{2}$", e.get("when") or "") else None
        if when:
            return fwd("interviewing"), "owner", f"Interview with {who} on {when}: prep", when
        return fwd("interviewing"), "owner", f"Confirm the interview with {who} and prep", e["date"]
    if e["type"] == "Email":
        return None, "owner", f"Reply to {who}", e["date"]
    if e["type"] == "Applied":
        return fwd("applied"), "them", "Follow up on the application", biz(d, 10).isoformat()
    late = ORDER.index(stage) >= ORDER.index("applied")
    return (None if late else fwd("outreach")), "them", f"Follow up with {who} if no reply", biz(d, 10 if late else 5).isoformat()


def record(cfg, events, dry):
    p = paths(cfg)
    play = {j["id"]: (j, o) for j, o in in_play(p)}
    by_role = {}
    for e in events:
        if e.get("type") not in TYPES or not re.match(r"\d{4}-\d{2}-\d{2}$", e.get("date", "")):
            raise SystemExit(f"bad event: {e}")
        if e["id"] in play:
            by_role.setdefault(e["id"], []).append(e)
    urgent = json.loads(urgent_file(p).read_text(encoding="utf-8")) if urgent_file(p).exists() else []
    seen = {u["key"] for u in urgent}
    out = []
    for jid, evs in by_role.items():
        j, o = play[jid]
        new = append_log(p, j, sorted(evs, key=lambda e: e["date"]), dry)
        if not new:
            continue
        last = max(new, key=lambda e: (e["date"], e["type"] in ("Email", "Invite")))
        stage, ball, nxt, when = effect(last, o["stage"])
        if not dry:
            set_next(cfg, jid, nxt, when, ball, stage)
        for e in new:
            key = f"{jid}|{e['date']}|{e['type']}|{e['with']}"
            if (e["type"] == "Invite" or (e["type"] == "Email" and o.get("lane") == "active")) and key not in seen:
                urgent.append({"key": key, "id": jid, "company": j.get("company"), "type": e["type"], "with": e["with"],
                               "what": e["what"], "date": e["date"], "pinged": None})
                seen.add(key)
        out.append({"id": jid, "company": j.get("company"), "added": len(new), "stage": stage, "ball": ball, "next": nxt, "date": when})
    if not dry and out:
        urgent_file(p).parent.mkdir(parents=True, exist_ok=True)
        urgent_file(p).write_text(json.dumps(urgent[-200:], indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def sweep(cfg, dry, today=None):
    """Waiting on them past the date: the first time, propose a nudge (the owner's move); when the last thing in the log
    is a nudge already past its date too, propose No response. Proposals only."""
    p = paths(cfg)
    today = today or date.today()
    out = []
    for j, o in in_play(p):
        if o.get("ball") != "them" or not o.get("next_date") or o["next_date"] > today.isoformat():
            continue
        sent = [r for r in log_rows(p.vault, j["job_file"]) if r["type"].lower() in ("sent", "applied")] if j.get("job_file") else []
        nudged = len(sent) >= 2 and re.search(r"nudge|follow", sent[-1]["what"], re.I)
        nxt = ("No response? Close it as No response, or try one more route" if nudged
               else f"Nudge: no reply since {sent[-1]['date'] if sent else o['next_date']}")
        if not dry:
            set_next(cfg, j["id"], nxt, today.isoformat(), "owner")
        out.append({"id": j["id"], "company": j.get("company"), "next": nxt})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["targets", "record", "sweep"])
    ap.add_argument("file", nargs="?", help="record: the events JSON")
    ap.add_argument("--out", help="targets: write here instead of printing")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    cfg = load_config()
    if a.cmd == "targets":
        t = json.dumps(targets(paths(cfg)), indent=1, ensure_ascii=False)
        if a.out:
            Path(a.out).write_text(t + "\n", encoding="utf-8")
            print(f"wrote {a.out}")
        else:
            print(t)
    elif a.cmd == "record":
        if not a.file:
            raise SystemExit("record needs the events JSON")
        res = record(cfg, json.loads(Path(a.file).read_text(encoding="utf-8")), a.dry_run)
        for r in res:
            print(f"{r['company']}: {r['added']} row(s); next '{r['next']}' {r['date']}, ball {r['ball']}"
                  + (f", stage {r['stage']}" if r["stage"] else ""))
        print(f"{len(res)} roles updated" + (" (dry run)" if a.dry_run else ""))
    else:
        res = sweep(cfg, a.dry_run)
        for r in res:
            print(f"{r['company']}: {r['next']}")
        print(f"{len(res)} proposals" + (" (dry run)" if a.dry_run else ""))


if __name__ == "__main__":
    main()
