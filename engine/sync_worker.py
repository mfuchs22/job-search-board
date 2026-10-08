"""Run one board sync requested from the page's Sync button.

    py engine/sync_worker.py            # take the oldest pending request, run it, exit (launchd runs this every 2 min)
    py engine/sync_worker.py --loop     # the same, forever, two minutes apart (a Windows logon task)
    py engine/sync_worker.py --status   # print the last five requests

The page inserts a `sync_requests` row (status requested, an optional note). This worker, on the always-on host,
claims it (requested -> running, atomically, so two hosts never both take it), then does the deterministic part of
the morning refresh: pull the vault, fold the board's verdicts (ingest_db.py), build and push (build.py), log the
note as a feedback line, commit the vault, post one line to #job-search, and write the outcome on the row
(done or failed, with a plain sentence the banner shows). The deep pass on newcomers still belongs to the morning
routine; a sync only reports how many wait for it.

Single-writer rule: this is the only writer of sync_requests rows past `requested`.
"""
import re
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_config, load_jobs, paths  # noqa: E402
import supabase as sb  # noqa: E402

ENGINE = Path(__file__).resolve().parent
HOST = socket.gethostname().split(".")[0]
STALE_MINUTES = 30      # a `running` row older than this was abandoned (the host died mid-run)
ET = ZoneInfo("America/New_York")
CLOCK = "%#I:%M %p" if sys.platform == "win32" else "%-I:%M %p"


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def et(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(ET).strftime(CLOCK)


def run(argv, cwd, timeout=900):
    r = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=timeout)
    out = (r.stdout or "").strip()
    if r.stderr and r.stderr.strip():
        out = (out + "\n" + r.stderr.strip()).strip()
    return r.returncode, out


def patch(cfg, rid, body, where=None):
    params = {"id": f"eq.{rid}", **(where or {})}
    return sb.request("PATCH", "sync_requests", params=params, body=body, prefer="return=representation", cfg=cfg) or []


def touch_last_run():
    """The fleet's liveness file: a 2-minute job quiet for 25 minutes has died."""
    try:
        state = Path.home() / ".local" / "state" / "board-sync"
        state.mkdir(parents=True, exist_ok=True)
        (state / "last-run").write_text(now_iso(), encoding="utf-8")
    except OSError:
        pass


def claim(cfg):
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=STALE_MINUTES)).isoformat(timespec="seconds")
    for s in sb.select("sync_requests", {"select": "id,host,started_at", "status": "eq.running",
                                         "started_at": f"lt.{cutoff}"}, cfg=cfg):
        patch(cfg, s["id"], {"status": "failed", "finished_at": now_iso(),
                             "result": f"{s.get('host') or 'A machine'} took this sync at {et(s['started_at'])} "
                                       f"and never finished; try again"})
    pending = sb.select("sync_requests", {"select": "*", "status": "eq.requested", "order": "requested_at.asc",
                                          "limit": "1"}, cfg=cfg)
    if not pending:
        return None
    got = patch(cfg, pending[0]["id"], {"status": "running", "host": HOST, "started_at": now_iso()},
                where={"status": "eq.requested"})
    return got[0] if got else None   # empty: another host claimed it first


def waiting_deep_pass(cfg, p):
    data = load_jobs(p)
    floor = int(cfg.get("min_score", 7))
    return sum(1 for j in data["jobs"] if j.get("score_kind") == "title" and (j.get("score") or 0) >= floor
               and not j.get("excluded") and not j.get("verdict") and not j.get("deep_pass_date"))


def log_note(p, req, context):
    """The note becomes a line in the feedback log, the same file the routines and sessions write."""
    note = " ".join((req.get("note") or "").split())
    if not note or not p.feedback_log.exists():
        return False
    when = datetime.now(ET)
    line = (f"- {when:%Y-%m-%d} | source: the owner | routine: job-board-refresh (Sync button on the board) | "
            f"what: \"{note}\" | context: sync requested from the board at {when:%H:%M} ET; {context} | change: none yet\n")
    with p.feedback_log.open("a", encoding="utf-8", newline="\n") as f:
        f.write(line)
    return True


def commit_vault(p, message, extra_paths=()):
    """Commit what the build wrote (tracked files only, under jobs/ and meta/) plus the feedback log. Never
    touches anything else in the vault, matching the morning routine's rule."""
    root = p.personal_os
    rel = lambda x: str(Path(x).resolve().relative_to(root.resolve())).replace("\\", "/")
    run(["git", "add", "-u", "--", rel(p.jobs_dir), rel(p.vault / "meta")], root, 120)
    for x in extra_paths:
        run(["git", "add", "--", rel(x)], root, 60)
    code, out = run(["git", "diff", "--cached", "--quiet"], root, 60)
    if code == 0:
        return "nothing to commit"
    code, out = run(["git", "commit", "-q", "-m", message], root, 120)
    if code:
        return f"commit failed: {out[-200:]}"
    code, out = run(["git", "push", "-q", "origin", "master"], root, 300)
    return "committed and pushed" if code == 0 else f"committed; push failed: {out[-200:]}"


def post_discord(p, text):
    script = p.personal_os / "Tools" / "discord_post.py"
    if not script.exists():
        return
    try:
        run([sys.executable, str(script), "job-search", text], p.personal_os, 60)
    except (OSError, subprocess.TimeoutExpired):
        pass


def do_sync(cfg, p, req):
    root = p.personal_os
    code, out = run(["git", "pull", "--rebase", "--autostash", "origin", "master"], root, 300)
    if code or "safe in the stash" in out:
        raise RuntimeError(f"the vault would not pull cleanly on {HOST}: {out[-240:]}")

    code, out = run([sys.executable, str(ENGINE / "ingest_db.py")], ENGINE.parent, 600)
    if code:
        raise RuntimeError(f"folding the verdicts failed on {HOST}: {out[-240:]}")
    m = re.search(r"saved (\d+) changes", out)
    folded = int(m.group(1)) if m else 0
    folded_lines = [l for l in out.splitlines() if l.startswith(("verdict ", "stage "))]

    code, out = run([sys.executable, str(ENGINE / "build.py")], ENGINE.parent, 1500)
    if code:
        raise RuntimeError(f"the build failed on {HOST}: {out[-240:]}")
    build_msg = out.splitlines()[-1] if out else ""
    m = re.search(r"\+(\d+) from inbox", build_msg)
    new_rows = int(m.group(1)) if m else 0
    notion_bad = "pull failed" in build_msg
    waiting = waiting_deep_pass(cfg, p)

    parts = [f"{folded} verdict{'s' if folded != 1 else ''} folded, board rebuilt on {HOST}"]
    if new_rows:
        parts.append(f"{new_rows} new radar row{'s' if new_rows != 1 else ''} taken in")
    if notion_bad:
        parts.append("Notion was not reachable, so people and opportunities are from the last good pull")
    if waiting:
        parts.append(f"{waiting} new posting{'s' if waiting != 1 else ''} wait for the morning read")
    summary = "; ".join(parts)

    noted = log_note(p, req, summary)
    if noted:
        summary += "; note logged"
    when = datetime.now(ET)
    git_msg = commit_vault(p, f"Job board sync {when:%Y-%m-%d %H:%M} ET: {folded} verdicts folded, {new_rows} new rows",
                           extra_paths=[p.feedback_log] if noted else ())
    if git_msg.startswith(("commit failed", "committed; push failed")):
        summary += f" ({git_msg})"

    lines = [f"Board synced from the page at {when.strftime(CLOCK)} ET: {summary}."]
    lines += [f"  {l}" for l in folded_lines[:12]]
    if noted:
        lines.append(f"  Note logged to the feedback file: \"{' '.join(req['note'].split())[:300]}\"")
    post_discord(p, "\n".join(lines))
    return summary


def once(cfg, p):
    touch_last_run()
    req = claim(cfg)
    if not req:
        return False
    print(f"sync request {req['id']} from {req.get('requested_by') or '?'} at {req['requested_at']}: running on {HOST}")
    try:
        result = do_sync(cfg, p, req)
        patch(cfg, req["id"], {"status": "done", "finished_at": now_iso(), "result": result[:1000]})
        print(f"done: {result}")
    except (RuntimeError, OSError, SystemExit, subprocess.TimeoutExpired, ValueError, KeyError) as e:
        msg = f"{e}"[:1000] or f"failed on {HOST} without a message"
        patch(cfg, req["id"], {"status": "failed", "finished_at": now_iso(), "result": msg})
        print(f"failed: {msg}")
        post_discord(p, f"Board sync from the page failed on {HOST}: {msg}")
    return True


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    cfg = load_config()
    p = paths(cfg)
    if "--status" in sys.argv:
        for r in sb.select("sync_requests", {"select": "*", "order": "requested_at.desc", "limit": "5"}, cfg=cfg):
            print(f"{r['requested_at']}  {r['status']:<9} {r.get('host') or '-':<12} {r.get('result') or ''}"
                  f"{'  note: ' + r['note'] if r.get('note') else ''}")
        return
    if "--loop" in sys.argv:
        while True:
            once(cfg, p)
            time.sleep(120)
    once(cfg, p)


if __name__ == "__main__":
    main()
