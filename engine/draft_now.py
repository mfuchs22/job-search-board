"""Draft on the spot when the owner answers a plan on the board (2026-10-23). No model here: this starts one.

    py engine/draft_now.py            fold any new plan answers and, if one wants drafts, start Claude on it now
    py engine/draft_now.py --status   print the run in flight, or the last one

the owner, 2026-10-23: "if it says 'Claude is drafting,' Claude should be drafting in the moment. It shouldn't be waiting
for an overnight batch... real-time triggers: when status A changes, action B occurs." Before this, an answer on a
Today plan card waited for the 01:30 pursue-followup routine. Now the board-sync service on the mini (sync_worker.py,
every two minutes) calls kick() first: it folds the unfolded plan_inputs rows into campaign.md (the same fold the
nightly queue runs), and for each answered role still Active and not closed it starts a headless `claude -p` on the
pursue-followup playbook for those roles alone: the drafts his answer calls for, the role's brief, the commit, and a
board push. The run itself sets the role's next step to "Review drafts" with the ball on the owner, which clears the
card's "Waiting on Claude" on the board. One run at a time; a run older than RUN_MINUTES no longer blocks the next.
Nothing is sent: the playbook's guardrails hold (Gmail drafts only).
"""
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_config, load_jobs, by_id, paths  # noqa: E402
import supabase as sb  # noqa: E402
from pursue_followup import fold_inputs, job_slug, set_next  # noqa: E402

RUN_MINUTES = 45
ET = ZoneInfo("America/New_York")


def state_file(p):
    """Machine-local and git-ignored, so the mini's unclaimed-files commit never sweeps it into Personal-OS."""
    return Path(__file__).resolve().parents[1] / ".draft-now" / "drafting.json"


def busy(p):
    """The run in flight, or None. A pid that is gone, or a run past RUN_MINUTES, no longer counts."""
    f = state_file(p)
    if not f.exists():
        return None
    s = json.loads(f.read_text(encoding="utf-8"))
    if s.get("finished"):
        return None
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(s["started"])).total_seconds() / 60
    try:
        os.kill(int(s["pid"]), 0)
    except (OSError, ValueError, KeyError):
        return None
    return s if age < RUN_MINUTES else None


def claude_bin(cfg):
    return cfg.get("claude") or shutil.which("claude") or str(Path.home() / ".local" / "bin" / "claude")


def prompt(rows, today):
    names = "; ".join(f"{r['company']}, {r['title']} (job id {r['id']}, folder opportunities/{r['slug']})" for r in rows)
    return (
        "Read Tools/pursue-followup-prompt.md. the owner just answered the plan for these roles on the board, and the drafts "
        f"are owed now, not tonight: {names}. Do step 1 (sync). Then, for these roles only and nothing else: step 3 (read), "
        "the drafts item of step 4 (his answer is under ## the owner's input in campaign.md; follow it, not the plan; if his "
        "answer picked a route that needs no drafts, say so and set the next step that route calls for), step 4b for "
        "these roles' briefs only (run `py engine/briefs.py owed --out briefs-owed.json` and work only the rows whose "
        "key ends in one of these job ids), and step 5. Skip introductions, call prep, mail, warm paths, diligence and "
        "every other row. Then step 8's commit, with the message "
        f"\"Pursue drafts on answer {today}: {', '.join(r['company'] for r in rows)}\", and then in the job-search-agent "
        "folder run `py engine/push_board.py` so the drafts and briefs reach the board. Nothing is ever sent. Your "
        "working directory is Personal-OS; the prompt was written on Windows, so read any C:\\Users\\matth\\ path as "
        "your home folder with forward slashes. `py` works here."
    )


def kick(cfg, p):
    """Fold new plan answers; start one drafting run if any answered role wants drafts. Returns a line, or None."""
    if busy(p):
        return None
    if not sb.select("plan_inputs", {"select": "id", "folded_at": "is.null", "limit": "1"}, cfg=cfg):
        return None
    subprocess.run(["git", "pull", "--rebase", "--autostash", "origin", "master"], cwd=str(p.personal_os),
                   capture_output=True, text=True, timeout=300)
    idx = by_id(load_jobs(p))
    ids = sorted(set(fold_inputs(cfg, p, idx, False)))
    if not ids:
        return None
    opps = {r["id"]: r.get("payload") or {} for r in
            sb.select("opportunities", {"select": "id,payload", "id": f"in.({','.join(ids)})"}, cfg=cfg)}
    rows = []
    for i in ids:
        o, j = opps.get(i, {}), idx.get(i)
        if not j or o.get("stage") == "closed" or (o.get("lane") or "active") != "active":
            continue  # benched, paused or closed by the answer itself: nothing to draft
        rows.append({"id": i, "company": j.get("company") or "", "title": j.get("title") or "", "slug": job_slug(j)})
    if not rows:
        return f"folded {len(ids)} plan answers; none wants drafts"
    now = datetime.now(timezone.utc)
    today = now.astimezone(ET).date().isoformat()
    clock = now.astimezone(ET).strftime("%I:%M %p").lstrip("0")
    for r in rows:
        set_next(cfg, r["id"], f"Claude is drafting from your plan answer (started {clock})", today, "claude")
    f = state_file(p)
    f.parent.mkdir(parents=True, exist_ok=True)
    logs = Path.home() / "Library" / "Logs" / "fleet"
    log = (logs if logs.exists() else f.parent) / "draft-now.log"
    with open(log, "a", encoding="utf-8") as out:
        out.write(f"\n=== {now.isoformat(timespec='seconds')} {', '.join(r['id'] for r in rows)}\n")
        out.flush()
        proc = subprocess.Popen([claude_bin(cfg), "-p", prompt(rows, today), "--permission-mode", "auto",
                                 "--permission-prompts", "none"], cwd=str(p.personal_os), stdout=out,
                                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    f.write_text(json.dumps({"pid": proc.pid, "jobs": [r["id"] for r in rows], "started": now.isoformat(timespec="seconds"),
                             "log": str(log)}, indent=1) + "\n", encoding="utf-8")
    return f"drafting now for {', '.join(r['company'] for r in rows)} (pid {proc.pid})"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    cfg = load_config()
    p = paths(cfg)
    if "--status" in sys.argv:
        f = state_file(p)
        s = json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
        print("no run yet" if not s else f"{'running' if busy(p) else 'not running'}: {', '.join(s['jobs'])}, "
                                         f"started {s['started']}, log {s['log']}")
        return
    print(kick(cfg, p) or "nothing to draft")


if __name__ == "__main__":
    main()
