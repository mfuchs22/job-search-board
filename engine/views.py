"""The owner's views: a cleaned-up paragraph for each verdict note, shown on the board in place of the raw note.

Notes are typed or dictated freehand on the page. A model (the morning refresh session, or any Claude session) rewrites
each one into a tight first-person paragraph that keeps every point; the board shows that paragraph while the raw note
is unchanged, and falls back to the raw note the moment it is edited, until the next pass rewrites it.

    py engine/views.py pending [--out FILE]   notes with no current view, as JSON [{kind, id, name, note}]
    py engine/views.py apply FILE             merge [{kind, id, view}] into the vault's meta/views.json and push
    py engine/views.py push                   push meta/views.json to board_meta `views`

meta/views.json: {"jobs": {id: {"src": note, "view": text}}, "startups": {id: {...}}}. A view is current when its
src equals the note now on the board (both stripped). Single writer of board_meta `views`: this file.
"""
import json
import sys
from datetime import datetime, timezone

from common import load_config, paths, load_jobs
import supabase as sb


def _file(p):
    return p.vault / "meta" / "views.json"


def load(p):
    f = _file(p)
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"jobs": {}, "startups": {}}


def current_notes(cfg, p):
    """Every note as the board shows it: a job's newest of jobs.json and its `verdicts` row; a startup's `startup_verdicts` row."""
    data = load_jobs(p)
    recs = data["jobs"] if isinstance(data, dict) else data
    jobs = {j["id"]: {"name": f'{j.get("title", "")} @ {j.get("company", "")}', "note": j.get("note") or "", "ts": j.get("verdict_ts") or ""} for j in recs}
    for r in sb.select("verdicts", {"select": "id,note,ts,title,company"}, cfg=cfg):
        ts = sb.iso_z(r.get("ts"))
        cur = jobs.get(r["id"])
        if cur is None:
            jobs[r["id"]] = {"name": f'{r.get("title") or ""} @ {r.get("company") or ""}', "note": r.get("note") or "", "ts": ts}
        elif ts > cur["ts"]:
            cur["note"], cur["ts"] = r.get("note") or "", ts
    starts = {r["id"]: {"name": r.get("name") or r["id"], "note": r.get("note") or ""}
              for r in sb.select("startup_verdicts", {"select": "id,note,name"}, cfg=cfg)}
    return {"jobs": jobs, "startups": starts}


def pending(cfg, p):
    v = load(p)
    out = []
    for kind, notes in current_notes(cfg, p).items():
        for i, n in notes.items():
            note = n["note"].strip()
            if note and (v.get(kind, {}).get(i, {}).get("src", "").strip() != note):
                out.append({"kind": kind, "id": i, "name": n["name"], "note": note})
    return out


def push(cfg, p):
    v = load(p)
    sb.upsert("board_meta", [{"key": "views", "payload": v, "updated_at": datetime.now(timezone.utc).isoformat()}], cfg=cfg)
    return f"views pushed: {len(v.get('jobs', {}))} jobs, {len(v.get('startups', {}))} startups"


def apply(cfg, p, rows):
    """rows: [{kind, id, view}]; the src recorded is the note as it stands now, so a note edited since is not marked current."""
    v = load(p)
    notes = current_notes(cfg, p)
    n = 0
    for r in rows:
        src = notes.get(r["kind"], {}).get(r["id"], {}).get("note", "").strip()
        if not src or not r.get("view", "").strip():
            continue
        v.setdefault(r["kind"], {})[r["id"]] = {"src": src, "view": r["view"].strip()}
        n += 1
    f = _file(p)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(v, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return f"{n} views applied; " + push(cfg, p)


def main():
    cfg = load_config()
    p = paths(cfg)
    cmd = sys.argv[1] if len(sys.argv) > 1 else "pending"
    if cmd == "pending":
        out = json.dumps(pending(cfg, p), indent=1, ensure_ascii=False)
        if "--out" in sys.argv:
            path = sys.argv[sys.argv.index("--out") + 1]
            open(path, "w", encoding="utf-8").write(out)
            print(f"{len(json.loads(out))} pending -> {path}")
        else:
            sys.stdout.reconfigure(encoding="utf-8")
            print(out)
    elif cmd == "apply":
        print(apply(cfg, p, json.loads(open(sys.argv[2], encoding="utf-8").read())))
    elif cmd == "push":
        print(push(cfg, p))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
