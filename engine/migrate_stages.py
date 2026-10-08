"""One-off (2026-09-15): move Pursue stages onto the new ladder.

    shortlist -> researching -> outreach -> applied -> interviewing -> offer -> closed
    (closed carries an outcome: no_response, rejected, withdrew, accepted)

Every Pursue at researching moves to shortlist (none was actually being researched), Example Partners moves to
applied (the recruiter submitted the application), ghosted becomes no_response, and a record that is not a Pursue
loses any stray stage. jobs.json and the Supabase `stages` rows move together, stamped with one new ts, so
ingest_db.py never sees an old stage name and treats the migrated rows as already folded.

Run ingest_db.py first, so a stage move made on the board since the last refresh is folded before this rewrites it.

    py engine/ingest_db.py
    py engine/migrate_stages.py --dry-run
    py engine/migrate_stages.py            then py engine/build.py
"""
import sys
from datetime import datetime, timezone

from common import load_config, paths, load_jobs, save_jobs, by_id, STAGES, OUTCOMES, LEGACY_OUTCOME
import supabase as sb

RENAME = {"researching": "shortlist"}
MOVES = {"50ab1a0303": ("applied", "Recruiter submitted the application; interviews to be scheduled")}


def now_z():
    d = datetime.now(timezone.utc)
    return d.strftime("%Y-%m-%dT%H:%M:%S.") + f"{d.microsecond // 1000:03d}Z"


def target(j):
    """(stage, outcome, next_step) the record should carry after the migration."""
    st, oc, nx = j.get("stage"), j.get("outcome"), j.get("next_step")
    if j.get("verdict") != "pursue":
        return None, None, nx
    if j["id"] in MOVES:
        st, nx = MOVES[j["id"]]
    st = RENAME.get(st, st) or "shortlist"
    oc = LEGACY_OUTCOME.get(oc, oc) if st == "closed" else None
    assert st in STAGES and (oc is None or oc in OUTCOMES), (j["id"], st, oc)
    return st, oc, nx


def main():
    dry = "--dry-run" in sys.argv
    cfg = load_config()
    p = paths(cfg)
    data = load_jobs(p)
    idx = by_id(data)
    ts = now_z()
    remote = {r["id"]: r for r in sb.select("stages", {"select": "*"}, cfg=cfg)}

    rows = {}
    n_local = 0
    for j in data["jobs"]:
        before = (j.get("stage"), j.get("outcome"), j.get("next_step"))
        after = target(j)
        if after == before:
            continue
        n_local += 1
        why = "cleared, not a Pursue" if j.get("verdict") != "pursue" else f"{before[0]} -> {after[0]}"
        print(f"  {j['id']} {why}{' / ' + after[1] if after[1] else ''}  {j['company']}: {j['title']}")
        if dry:
            continue
        if after[0] != before[0] and j["id"] in MOVES:
            j["stage_date"] = j["next_step_date"] = ts[:10]
        j["stage"], j["outcome"], j["next_step"] = after
        if j.get("verdict") == "pursue" or j["id"] in remote:
            rows[j["id"]] = {"id": j["id"], "stage": after[0], "outcome": after[1], "next": after[2] or "", "ts": ts,
                             "title": j["title"], "company": j["company"]}
            j["stage_ts"] = ts

    # Supabase rows still carrying an old name whose record did not change locally (already migrated, or unknown ids).
    for rid, r in remote.items():
        if rid in rows:
            continue
        st = RENAME.get(r.get("stage"), r.get("stage"))
        oc = LEGACY_OUTCOME.get(r.get("outcome"), r.get("outcome"))
        if (st, oc) == (r.get("stage"), r.get("outcome")):
            continue
        print(f"  supabase row {rid}: {r.get('stage')} -> {st}")
        rows[rid] = {"id": rid, "stage": st, "outcome": oc, "next": r.get("next") or "", "ts": ts,
                     "title": r.get("title"), "company": r.get("company")}
        if rid in idx and not dry:
            idx[rid]["stage_ts"] = ts

    print(f"{n_local} records to change; {len(rows) if not dry else 'n/a (dry run)'} supabase rows to write; "
          f"{len(remote)} rows in supabase now")
    if dry:
        print("dry run: nothing written")
        return
    if rows:
        sb.upsert("stages", list(rows.values()), cfg=cfg)
    save_jobs(p, data)
    print("saved jobs.json and supabase stages; run py engine/build.py next")


if __name__ == "__main__":
    main()
