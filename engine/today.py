"""The Today page in a sentence, and the few things worth a ping. Deterministic, no model.

    py engine/today.py line             one line for the 04:30 #job-search post: interviews, plans to answer, moves due,
                                        waiting on them, the Active count, and the link to Today
    py engine/today.py urgent [--mark]  the pings not yet sent, one line each: an interview booked or within 48 hours,
                                        a reply from someone on an Active role, a move of the owner's due within 48 hours.
                                        --mark records them as sent (Tools/pursue-followup/pinged.json) so each pings once

the owner, 2026-10-20 (decision 8 of the agreed workflow): one Today line in the morning post, and pings only for a booked
interview, a reply from an Active contact, or something due within 48 hours. The counts follow the page's own rules
(web/index.html viewToday) from the same data: jobs.json, the last Notion pull and the plan in campaign.md.
"""
import argparse
import json
from datetime import date, datetime, timedelta, timezone

from common import by_id, load_config, load_jobs, paths
from notion_sync import load as load_notion, opps_file
from pursue_followup import CAP, EARLY, plan_state, job_slug
from pursue_mail import urgent_file

BOARD = "https://<your-board-host>/#today"


def pinged_file(p):
    return p.personal_os / "Tools" / "pursue-followup" / "pinged.json"


def state(p, today):
    idx = by_id(load_jobs(p))
    rows = []
    for o in (load_notion(opps_file(p), "opps") or {}).get("opps") or []:
        j = idx.get(o.get("id"))
        if j and j.get("verdict") == "pursue" and o.get("stage") not in (None, "closed"):
            rows.append((j, o))
    soon = (today + timedelta(days=2)).isoformat()
    iv = [(j, o) for j, o in rows if o["stage"] == "interviewing" and o.get("next_date") and o["next_date"] <= (today + timedelta(days=3)).isoformat()]
    live = [(j, o) for j, o in rows if o.get("lane") not in ("bench", "paused")]
    plans = []
    for j, o in live:
        s = job_slug(j)
        if o.get("lane") == "active" and o["stage"] in EARLY and s:
            has, answered, _ = plan_state(p.vault, s)
            if has and not answered:
                plans.append(j)
    mine = [(j, o) for j, o in live if o.get("ball") != "them" and o.get("next") and o.get("next_date") and o["next_date"] <= today.isoformat()]
    theirs = [(j, o) for j, o in live if o.get("ball") == "them"]
    due48 = [(j, o) for j, o in live if o.get("ball") != "them" and o.get("next_date") and today.isoformat() <= o["next_date"] <= soon]
    active = sum(1 for _, o in rows if o.get("lane") == "active" and o["stage"] in EARLY)
    return {"iv": iv, "plans": plans, "mine": mine, "theirs": theirs, "due48": due48, "active": active}


def day(iso, today):
    d = date.fromisoformat(iso[:10])
    return "today" if d == today else "tomorrow" if d == today + timedelta(days=1) else d.strftime("%a")


def line(p, today):
    s = state(p, today)
    parts = []
    if s["iv"]:
        parts.append(f"{len(s['iv'])} interview{'s' if len(s['iv']) > 1 else ''} ("
                     + ", ".join(f"{j['company'].split(' via ')[0]} {day(o['next_date'], today)}" for j, o in s["iv"]) + ")")
    parts.append(f"{len(s['plans'])} plan{'' if len(s['plans']) == 1 else 's'} to answer")
    parts.append(f"{len(s['mine'])} move{'' if len(s['mine']) == 1 else 's'} due")
    parts.append(f"{len(s['theirs'])} waiting on them")
    return f"Today: {', '.join(parts)}. Active {s['active']}/{CAP}. {BOARD}"


def urgent(p, today, mark):
    s = state(p, today)
    sent = json.loads(pinged_file(p).read_text(encoding="utf-8")) if pinged_file(p).exists() else {}
    out = []
    for u in (json.loads(urgent_file(p).read_text(encoding="utf-8")) if urgent_file(p).exists() else []):
        what = "Interview booked" if u["type"] == "Invite" else "Reply"
        out.append((f"mail|{u['key']}", f"{what}: {u['with']} on {u['company']}: {u['what']}"))
    for j, o in s["iv"]:
        if o["next_date"] <= (today + timedelta(days=2)).isoformat():
            out.append((f"iv|{j['id']}|{o['next_date']}", f"Interview {day(o['next_date'], today)}: {j['company']}, {o.get('next') or j['title']}"))
    for j, o in s["due48"]:
        out.append((f"due|{j['id']}|{o['next_date']}|{o.get('next')}", f"Due {day(o['next_date'], today)}: {j['company']}, {o['next']}"))
    new = [(k, t) for k, t in out if k not in sent]
    if mark and new:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        sent.update({k: now for k, _ in new})
        pinged_file(p).parent.mkdir(parents=True, exist_ok=True)
        pinged_file(p).write_text(json.dumps(sent, indent=1) + "\n", encoding="utf-8")
    return [t for _, t in new]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["line", "urgent"])
    ap.add_argument("--mark", action="store_true", help="urgent: record the printed pings as sent")
    a = ap.parse_args()
    p = paths(load_config())
    today = date.today()
    if a.cmd == "line":
        print(line(p, today))
    else:
        for t in urgent(p, today, a.mark):
            print(t)


if __name__ == "__main__":
    main()
