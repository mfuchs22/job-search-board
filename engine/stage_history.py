"""Stage history: when each pursued role entered each stage, so the board can show age on every card and the Overview
can show movement from the Shortlist into In Process (the owner, 2026-09-24).

    py engine/stage_history.py        update from the current jobs.json and the Notion Opportunities mirror, print it

Kept in the vault at network/stage-history.json {"asof", "roles": {job id: [{"stage", "date", "source"}]}} and pushed
to board_meta `stage_history` by push_board.py at every push. The board has never kept history (Notion holds only the
current stage), so it starts here: a role seen for the first time is seeded with its Pursue date on the Shortlist and,
if it is further along, its current stage on its stage_date; after that a changed stage is appended with the date of
the push that saw it (the daily build plus every board sync, so a move is dated to the day). Single writer: this file.
"""
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def history_file(p):
    return Path(p.vault) / "network" / "stage-history.json"


def load(p):
    f = history_file(p)
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"asof": "", "roles": {}}


def current_stages(data, opps):
    """{job id: (stage, stage_date, pursued_date)} for every pursued role; the Notion Opportunity wins over jobs.json."""
    by_opp = {o["id"]: o for o in (opps or {}).get("opps") or []}
    out = {}
    for j in data.get("jobs") or []:
        o = by_opp.get(j["id"])
        if (j.get("verdict") or "").lower() != "pursue" and not o:
            continue
        stage = (o or {}).get("stage") or j.get("stage") or "shortlist"
        out[j["id"]] = (stage, j.get("stage_date") or "", j.get("verdict_date") or j.get("date_first_seen") or "")
    return out


def repair_seed_bounce(ev, stage_date):
    """Collapse the seed artifact found 2026-10-07: a role seeded as shortlist and researching on the same day (the
    pre-2026-09-15 mapping put a yes at researching) and then logged as moving back to shortlist on a later push, which
    made the card read one day in Shortlist. The role never left the shortlist; its record's stage_date says so."""
    if (len(ev) == 3 and ev[0]["source"] == "seed" and ev[1]["source"] == "seed" and ev[0]["date"] == ev[1]["date"]
            and ev[2]["source"] == "push" and ev[2]["stage"] == ev[0]["stage"] and (stage_date or "") <= ev[0]["date"]):
        del ev[1:]


def update(p, data, opps, today=None):
    today = today or date.today().isoformat()
    h = load(p)
    roles = h.setdefault("roles", {})
    moved = 0
    for jid, (stage, stage_date, pursued) in current_stages(data, opps).items():
        ev = roles.get(jid)
        if not ev:
            ev = roles[jid] = [{"stage": "shortlist", "date": pursued or today, "source": "seed"}]
            if stage != "shortlist":
                ev.append({"stage": stage, "date": stage_date or today, "source": "seed"})
        elif ev[-1]["stage"] != stage:
            ev.append({"stage": stage, "date": today, "source": "push"})
            moved += 1
        repair_seed_bounce(ev, stage_date)
    h["asof"] = today
    f = history_file(p)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(h, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return h, moved


def main():
    from common import load_config, paths, load_jobs
    from notion_sync import load_all
    cfg = load_config(); p = paths(cfg)
    _, opps, _, _ = load_all(p)
    h, moved = update(p, load_jobs(p), opps)
    for jid, ev in sorted(h["roles"].items(), key=lambda kv: kv[1][-1]["date"], reverse=True)[:15]:
        print(jid, " > ".join(f"{e['stage']} {e['date']}" for e in ev))
    print(f"{len(h['roles'])} roles, {moved} moved this run")


if __name__ == "__main__":
    main()
