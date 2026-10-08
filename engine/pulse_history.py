"""Pulse history: one snapshot a day of the numbers the Overview trends (the owner, 2026-09-24: "what is the trend in to-do").

    py engine/pulse_history.py        take today's snapshot from the local Notion mirrors and jobs.json, print the series

Kept in the vault at network/pulse-history.json {"days": {date: {...}}} and pushed to board_meta `pulse_history` by
push_board.py at every push; the day's last push wins. Counts: open career tasks, overdue, due in the next 7 days;
people with a touch due this week, overdue touches, touches logged in the last 7 days; roles on the Shortlist and In
Process. Nothing earlier exists (Notion keeps no history), so the series starts on the first push. Single writer.
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

LIVE = ("applied", "interviewing", "offer")


def history_file(p):
    return Path(p.vault) / "network" / "pulse-history.json"


def snapshot(data, contacts, opps, tasks, today=None):
    t = today or date.today()
    iso, week, last7 = t.isoformat(), (t + timedelta(days=7)).isoformat(), (t - timedelta(days=7)).isoformat()
    open_t = [x for x in (tasks or {}).get("tasks") or [] if x.get("status") != "Complete" and (x.get("area") in (None, "", "career")) and x.get("project") != "Consulting"]
    due = lambda x: (x.get("plan_day") or x.get("due") or "")[:10]
    people = (contacts or {}).get("people") or []
    stage = {o["id"]: o.get("stage") for o in (opps or {}).get("opps") or []}
    pursued = [j for j in data.get("jobs") or [] if (j.get("verdict") or "").lower() == "pursue"]
    st = lambda j: stage.get(j["id"]) or j.get("stage") or "shortlist"
    return {
        "tasks_open": len(open_t),
        "tasks_overdue": sum(1 for x in open_t if due(x) and due(x) < iso),
        "tasks_week": sum(1 for x in open_t if due(x) and iso <= due(x) <= week),
        "people_due_week": sum(1 for c in people if (c.get("next_date") or "")[:10] and iso <= c["next_date"][:10] <= week),
        "people_overdue": sum(1 for c in people if (c.get("next_date") or "")[:10] and c["next_date"][:10] < iso and c.get("status") != "Dormant"),
        "touches_7d": sum(1 for c in people for x in c.get("touches") or [] if (x.get("date") or "")[:10] >= last7),
        "shortlist": sum(1 for j in pursued if st(j) not in LIVE and st(j) != "closed"),
        "in_process": sum(1 for j in pursued if st(j) in LIVE),
    }


def update(p, data, contacts, opps, tasks, today=None):
    f = history_file(p)
    try:
        h = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        h = {"days": {}}
    d = (today or date.today()).isoformat()
    h["days"][d] = snapshot(data, contacts, opps, tasks, today)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(h, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return h


def main():
    from common import load_config, paths, load_jobs
    from notion_sync import load_all
    cfg = load_config(); p = paths(cfg)
    contacts, opps, _, tasks = load_all(p)
    h = update(p, load_jobs(p), contacts, opps, tasks)
    for d, s in sorted(h["days"].items()):
        print(d, s)


if __name__ == "__main__":
    main()
