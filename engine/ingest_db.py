"""Fold the owner's verdicts and stage moves from Supabase back into jobs.json.

The page (web/) writes one row per posting into `verdicts` (v, cal, note, ts) and `stages` (stage, outcome, next, ts).

    py engine/ingest_db.py            merge rows newer than the record's stored timestamp; report what changed
    py engine/ingest_db.py --dry-run  report only

A Pursue's stage, outcome and next step are mirrored from the last Notion Opportunities pull (network/opportunities.json,
refreshed by build.py) the same way, since 2026-10-07: that is where the board writes them.

Idempotent: a row whose ts is not newer than the record's verdict_ts / stage_ts is skipped. Run build.py afterwards
to regenerate the views; the session then cascades new Pursues into job files, follow-ups, and people pages.
"""
import sys

from common import load_config, paths, load_jobs, save_jobs, by_id, VERDICTS, STAGES, OUTCOMES, LEGACY_OUTCOME
from notion_sync import load as load_notion, opps_file
import supabase as sb


def rows(table, cfg):
    """Rows keyed by id, ts normalized to the page's ISO-Z form so string comparison with jobs.json is exact."""
    out = {}
    for r in sb.select(table, {"select": "*", "order": "ts.asc"}, cfg=cfg):
        r = dict(r)
        r["ts"] = sb.iso_z(r.get("ts"))
        out[r["id"]] = r
    return out


def main():
    dry = "--dry-run" in sys.argv
    cfg = load_config()
    p = paths(cfg)
    data = load_jobs(p)
    idx = by_id(data)
    changes = []

    for jid, d in rows("verdicts", cfg).items():
        j = idx.get(jid)
        if not j:
            print(f"  verdict for unknown id {jid} ({d.get('title', '?')} @ {d.get('company', '?')}); ignored")
            continue
        ts = d.get("ts") or ""
        if ts and ts <= (j.get("verdict_ts") or ""):
            continue
        v = (d.get("v") or "").lower() or None
        if v and v not in VERDICTS:
            print(f"  bad verdict '{v}' for {jid}; ignored")
            continue
        before = (j.get("verdict"), j.get("calibration"), j.get("note"), bool(j.get("flag")))
        j["verdict"] = v
        j["flag"] = bool(d.get("flag"))
        j["calibration"] = d.get("cal") or None
        j["note"] = (d.get("note") or "").strip() or None
        j["verdict_ts"] = ts
        if v and (before[0] != v):
            j["verdict_date"] = ts[:10] if ts else j.get("verdict_date")
            if v == "pursue" and j.get("stage") in (None, "closed"):
                j["stage"], j["stage_date"] = "shortlist", j["verdict_date"]
            if v == "pursue" and j.get("excluded"):
                # the owner's override from the board's "Move to Shortlist" (2026-09-25): the rubric's reason is kept, the flag is lifted
                j["excluded_overridden"], j["excluded"] = j["excluded"], None
            if v != "pursue":
                j["stage"], j["outcome"] = None, None
            if v == "pass" and j.get("note") and not j.get("status_note"):
                j["status_note"] = j["note"][:120]
        if not v and before[0]:
            # "Back to review" on the board (2026-09-25): the role returns to the inbox, off the ladder
            j["stage"], j["outcome"] = None, None
        if before != (j.get("verdict"), j.get("calibration"), j.get("note"), bool(j.get("flag"))):
            changes.append(f"verdict {jid}: {before[0]} -> {v}{' flagged' if j.get('flag') else ''} ({j['title']} @ {j['company']})")

    for jid, d in rows("stages", cfg).items():
        j = idx.get(jid)
        if not j:
            print(f"  stage for unknown id {jid}; ignored")
            continue
        ts = d.get("ts") or ""
        if ts and ts <= (j.get("stage_ts") or ""):
            continue
        st = d.get("stage") or None
        if st and st not in STAGES:
            print(f"  bad stage '{st}' for {jid}; ignored")
            continue
        oc = LEGACY_OUTCOME.get(d.get("outcome"), d.get("outcome")) or None
        if oc and oc not in OUTCOMES:
            oc = None
        before = (j.get("stage"), j.get("outcome"), j.get("next_step"))
        if st and st != j.get("stage"):
            j["stage_date"] = ts[:10] if ts else j.get("stage_date")
        j["stage"] = st or j.get("stage")
        j["outcome"] = oc if (j.get("stage") == "closed") else None
        j["next_step"] = (d.get("next") or "").strip() or None
        if j.get("next_step"):
            j["next_step_date"] = ts[:10] if ts else j.get("next_step_date")
        j["stage_ts"] = ts
        if before != (j.get("stage"), j.get("outcome"), j.get("next_step")):
            changes.append(f"stage {jid}: {before[0]} -> {j['stage']}{' / ' + j['outcome'] if j.get('outcome') else ''}; next: {j.get('next_step') or '-'} ({j['title']})")

    # A Pursue's stage lives in Notion Opportunities (2026-09-17); the board writes it there through opportunity-write and
    # reads it from the mirror, so a close the owner confirms on the page (Confirm removal, 2026-10-07) never reached jobs.json,
    # and the POSTINGS block kept asking him to confirm it. Mirror the last Notion pull (build.py refreshes it every run)
    # into the record, newest edit wins, same guard as the stages table.
    opps = load_notion(opps_file(p), "opps")
    for o in (opps or {}).get("opps") or []:
        j = idx.get(o.get("id"))
        if not j or j.get("verdict") != "pursue":
            continue
        ts = sb.iso_z(o.get("edited")) or ""
        if ts and ts <= (j.get("stage_ts") or ""):
            continue
        st = o.get("stage") if o.get("stage") in STAGES else None
        oc = o.get("outcome") if o.get("outcome") in OUTCOMES else None
        before = (j.get("stage"), j.get("outcome"), j.get("next_step"))
        if st and st != j.get("stage"):
            j["stage"], j["stage_date"] = st, (ts[:10] if ts else j.get("stage_date"))
        j["outcome"] = oc if j.get("stage") == "closed" else None
        nxt = (o.get("next") or "").strip() or None
        if nxt != j.get("next_step"):
            j["next_step"] = nxt
            if nxt:
                j["next_step_date"] = o.get("next_date") or (ts[:10] if ts else j.get("next_step_date"))
        j["stage_ts"] = ts
        if before != (j.get("stage"), j.get("outcome"), j.get("next_step")):
            changes.append(f"notion stage {o['id']}: {before[0]} -> {j['stage']}{' / ' + j['outcome'] if j.get('outcome') else ''}; next: {j.get('next_step') or '-'} ({j['title']})")

    for c in changes:
        print(c)
    if not changes:
        print("nothing new in Supabase verdicts/stages or the Notion pull")
    elif dry:
        print(f"dry run: {len(changes)} changes not saved")
    else:
        save_jobs(p, data)
        print(f"saved {len(changes)} changes to {p.jobs_json}; run build.py next")


if __name__ == "__main__":
    main()
