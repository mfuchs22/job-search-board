"""What each open Pursue still owes before the owner's next decision. Deterministic, no model, no web.

    py engine/pursue_followup.py                write the queue to <Personal-OS>/Tools/pursue-followup/queue.json
    py engine/pursue_followup.py --show         print it as a table and write nothing
    py engine/pursue_followup.py --cap 3        mark at most 3 diligence passes for this run (default 3)
    py engine/pursue_followup.py --lanes        first give every open Pursue without a Lane one, in Notion: Active while
                                                fewer than 8 count, else Bench (Applied and later are Active, uncounted)
    py engine/pursue_followup.py --fold         only fold the owner's plan answers from the board into campaign.md
    py engine/pursue_followup.py --set <id> [--next "..."] [--date YYYY-MM-DD] [--ball owner|claude|them]
                                                write one role's Next Step, its date and Ball to Notion (the routine's
                                                only Notion write; the board's mirror follows at the next build)

The agreed post-Pursue workflow (2026-10-20, the Job Board App project's workflow/agreed-spec.md): every new Pursue
gets quick research on its own (a warm-path check and a `/diligence <company> quick` pass), Bench included; an Active
role also gets its opportunity folder and a short plan in campaign.md, and the plan goes to the owner as one card before
anything personal is drafted. the owner's answer to that card (route plus notes, saved under `## the owner's input`) makes the
drafts owed. This script decides what is owed from the vault and the last Notion pull (network/opportunities.json,
refreshed by every build); the nightly `pursue-followup` routine (Personal-OS Tools/pursue-followup-prompt.md) does
the work. Nothing here sends anything, and nothing here decides a verdict; a stage moves only from --set --stage, which
the interactive /interview-prep skill uses when a round is booked.

the owner's answer to a plan card on the board's Today page lands in Supabase `plan_inputs`; every run that writes the
queue first folds the unfolded rows into the role's campaign.md under `## the owner's input` (one dated line each, never
rewriting a line) and stamps the row `folded_at`. That fold is the only writer of the section besides the owner himself.

Notion writes here: Lane with --lanes (the cap is arithmetic, so it belongs in a script), and one role's Next Step,
date and Ball with --set, so the routine needs the engine's token rather than a connector.
"""
import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import notion
from common import load_config, paths, load_jobs, by_id
from notion_sync import load as load_notion, opps_file
from render_dashboard import log_rows, meeting_rows, plan_record
from notion_sync import meetings_file

CAP = 8                                         # the owner, 2026-10-20: Active is capped at 8
EARLY = {"shortlist", "researching", "outreach"}  # the stages that count toward the cap
LATE = {"applied", "interviewing", "offer"}       # Active, never counted


def job_slug(j):
    return (j.get("job_file") or "").rsplit("/", 1)[-1]


def company_slug(vault, j):
    """The research folder's slug: the job file's **Company:** wikilink, the same rule render_dashboard.asset_list uses."""
    f = vault / ((j.get("job_file") or "") + ".md")
    if not j.get("job_file") or not f.exists():
        return None
    m = re.search(r"^\*\*Company:\*\*\s*\[\[companies/([^\]|]+)", f.read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else None


def plan_state(vault, slug):
    """(has a plan, the owner has answered this version of it, drafts exist) from opportunities/<slug>/campaign.md and the
    folders beside it. An answer counts when it names this version ("plan v2") or, written by hand, is dated on or
    after the plan."""
    d = vault / "opportunities" / slug
    plan = plan_record(vault, f"jobs/{slug}") if (d / "campaign.md").exists() else None
    if not plan:
        return False, False, False
    tag = f"(plan v{plan['version']})"
    answered = any(tag in l or ("(plan v" not in l and l[:10] >= (plan["date"] or "0")) for l in plan["input"])
    drafts = ((d / "application").is_dir() and any((d / "application").glob("*.md"))) or (d / "outreach").is_dir()
    return True, answered, drafts


def add_input(f, line):
    """Append one line to campaign.md's ## the owner's input, creating the section at the end when it is missing."""
    txt = f.read_text(encoding="utf-8")
    m = re.search(r"^##\s+the owner's input\s*$", txt, re.M | re.I)
    if not m:
        f.write_text(txt.rstrip("\n") + f"\n\n## the owner's input\n\n{line}\n", encoding="utf-8")
        return
    nxt = re.search(r"^##\s", txt[m.end():], re.M)
    end = m.end() + (nxt.start() if nxt else len(txt) - m.end())
    body = txt[m.end():end].rstrip("\n")
    rest = txt[end:]
    f.write_text(txt[:m.end()] + (body + "\n" if body.strip() else "\n\n") + line + "\n" + ("\n" + rest if rest else ""),
                 encoding="utf-8")


def fold_inputs(cfg, p, idx, dry):
    """the owner's plan answers from the board (Supabase plan_inputs, folded_at null) into campaign.md. Returns the ids."""
    if not (cfg.get("supabase") or {}).get("url"):
        return []
    import supabase
    rows = supabase.select("plan_inputs", {"select": "*", "folded_at": "is.null", "order": "ts.asc"}, cfg=cfg)
    done = []
    for r in rows:
        j = idx.get(r["job_id"])
        s = job_slug(j) if j else ""
        f = p.vault / "opportunities" / s / "campaign.md" if s else None
        if not f or not f.exists():
            continue  # the plan's file is gone or not pulled yet; the row waits for the next run
        what = "Approved" if r.get("approve") else "Changed"
        if r.get("choice"):
            opt = next((o for o in (plan_record(p.vault, j["job_file"]) or {}).get("options", []) if o["letter"] == r["choice"]), None)
            what = f"Chose {r['choice']}" + (f" ({opt['label']})" if opt else "")
        note = " ".join((r.get("note") or "").split())
        line = f"- {r['ts'][:10]} (plan v{r.get('version') or 1}): {what}." + (f" {note}" if note else "")
        if not dry:
            add_input(f, line)
            supabase.request("PATCH", "plan_inputs", params={"id": f"eq.{r['id']}"},
                             body={"folded_at": datetime.now(timezone.utc).isoformat()}, prefer="return=minimal", cfg=cfg)
        done.append(r["job_id"])
    return done


def assign_lanes(cfg, opps, jobs_idx, dry):
    """Every open Pursue without a Lane gets one, in score order. Returns [(id, lane)] written."""
    open_ = [o for o in opps if o.get("stage") and o["stage"] != "closed" and jobs_idx.get(o["id"], {}).get("verdict") == "pursue"]
    active = sum(1 for o in open_ if o.get("lane") == "active" and o["stage"] in EARLY)
    todo = sorted((o for o in open_ if not o.get("lane")),
                  key=lambda o: -(jobs_idx[o["id"]].get("score") or 0))
    out = []
    for o in todo:
        if o["stage"] in LATE:
            lane = "active"
        elif active < CAP:
            lane, active = "active", active + 1
        else:
            lane = "bench"
        out.append((o["id"], lane))
        o["lane"] = lane
    if out and not dry:
        tok = notion.token(cfg)
        for jid, lane in out:
            page = next(o["page"] for o in opps if o["id"] == jid)
            notion.call(tok, f"/pages/{page}", {"properties": {"Lane": notion.prop("select", lane.title())}}, "PATCH")
    return out


def set_next(cfg, jid, nxt=None, date=None, ball=None, stage=None):
    """One role's Next Step, Next Step Date and Ball (and, for engine/pursue_mail.py only, a forward Stage), written to
    its Opportunities page (found by Job ID)."""
    tok = notion.token(cfg)
    res = notion.call(tok, f"/data_sources/{notion.source(cfg, 'opportunities_data_source')}/query",
                      {"page_size": 1, "filter": {"property": "Job ID", "rich_text": {"equals": jid}}}, "POST")
    page = (res.get("results") or [None])[0]
    if not page:
        raise SystemExit(f"no Notion opportunity for {jid}")
    props = {}
    if nxt is not None:
        props["Next Step"] = notion.prop("rich_text", nxt)
    if date is not None:
        if date and not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
            raise SystemExit(f"--date wants YYYY-MM-DD, got {date}")
        props["Next Step Date"] = notion.prop("date", date or None)
    if ball is not None:
        if ball and ball not in ("owner", "claude", "them"):
            raise SystemExit(f"--ball is owner, claude or them, got {ball}")
        props["Ball"] = notion.prop("select", ball.title() if ball else None)
    if stage is not None:
        props["Stage"] = notion.prop("select", stage.title())
    if not props:
        raise SystemExit("--set needs at least one of --next, --date, --ball")
    notion.call(tok, f"/pages/{page['id']}", {"properties": props}, "PATCH")
    return sorted(props)


def build(cfg, cap, lanes=False, dry=False):
    p = paths(cfg)
    data = load_jobs(p)
    idx = by_id(data)
    opps = (load_notion(opps_file(p), "opps") or {}).get("opps") or []
    folded = fold_inputs(cfg, p, idx, dry)
    set_lanes = assign_lanes(cfg, opps, idx, dry) if lanes else []
    today = datetime.now().date().isoformat()
    week_ago = (datetime.now().date() - timedelta(days=7)).isoformat()
    notes = (load_notion(meetings_file(p), "meetings") or {}).get("meetings") or []
    rows = []
    for o in opps:
        j = idx.get(o["id"])
        if not j or j.get("verdict") != "pursue" or o.get("stage") in (None, "closed") or o.get("lane") == "paused":
            continue
        lane = o.get("lane") or "unset"
        s, co = job_slug(j), company_slug(p.vault, j)
        need = []
        if not s:
            need.append("job file (the morning cascade writes it)")
        hp = j.get("human_path") or {}
        if not (hp.get("verdict") if isinstance(hp, dict) else hp) and o.get("hp") in (None, "unchecked"):
            need.append("warm path")
        if co is None or not (p.vault / "research" / co / "brief.md").exists():
            need.append("diligence")
        if lane == "active" and o["stage"] in EARLY and s:
            if not (p.vault / "opportunities" / s / "README.md").exists():
                need.append("folder")
            plan, answered, drafts = plan_state(p.vault, s)
            if not plan:
                need.append("plan")
            elif answered and not drafts:
                need.append("drafts")
        if s and o["stage"] not in EARLY:
            # An interview booked (an Invite row the mail step logged, dated from yesterday on) with no prep file written
            # since: the /interview-prep skill is owed. A Notion meeting note for the role from the last week with no
            # meeting record in the vault on that date: /debrief is owed (the owner, 2026-10-20, Phase 4).
            inv = [r["date"] for r in log_rows(p.vault, j["job_file"]) if r["type"].lower() == "invite" and r["date"] >= week_ago]
            prep = p.vault / "opportunities" / s / "prep"
            made = [f.name[:10] for f in prep.glob("*.md")] if prep.is_dir() else []
            if inv and not any(m >= max(inv) for m in made):
                need.append("interview prep")
            have = {m["date"] for m in meeting_rows(p.vault, j["job_file"])}
            if any(o.get("page") in (m.get("opps") or []) and (m.get("date") or "")[:10] >= week_ago
                   and (m.get("date") or "")[:10] <= today and (m.get("date") or "")[:10] not in have for m in notes):
                need.append("debrief")
        rows.append({
            "id": j["id"], "company": j.get("company"), "title": j.get("title"), "score": j.get("score"),
            "lane": lane, "stage": o["stage"], "ball": o.get("ball"), "slug": s, "company_slug": co,
            "page": o.get("page"), "url": j.get("url"), "job_file": j.get("job_file"),
            "human_path": hp or o.get("hp"), "hp_people": o.get("hp_people"),
            "next": o.get("next"), "next_date": o.get("next_date"), "note": j.get("note") or "",
            "verdict_date": j.get("verdict_date"), "need": need,
        })
    # Active first (it is where the owner's next decisions come from), then the newest Pursue: what he just chose is what
    # he most expects to see move.
    rows.sort(key=lambda r: (r["lane"] != "active", -(int((r["verdict_date"] or "0").replace("-", "") or 0))))
    n = 0
    for r in rows:  # cap the diligence passes so one night never eats the subscription's usage window
        if "diligence" in r["need"]:
            if n < cap:
                n += 1
            else:
                r["need"] = [x for x in r["need"] if x != "diligence"] + ["diligence (deferred)"]
    todo = [r for r in rows if r["need"]]
    return {
        "built": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cap": cap,
        "active": sum(1 for r in rows if r["lane"] == "active" and r["stage"] in EARLY),
        "bench": sum(1 for r in rows if r["lane"] == "bench"),
        "lanes_set": [{"id": i, "lane": l} for i, l in set_lanes],
        "answers_folded": folded,
        "owed": len(todo),
        "diligence_this_run": n,
        "rows": todo,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--show", action="store_true", help="print the queue, write nothing (Notion included)")
    ap.add_argument("--cap", type=int, default=3, help="max diligence passes marked this run (default 3)")
    ap.add_argument("--lanes", action="store_true", help="give open Pursues without a Lane one, in Notion")
    ap.add_argument("--fold", action="store_true", help="only fold the board's plan answers into campaign.md")
    ap.add_argument("--set", metavar="ID", help="write one role's Next Step, date and Ball to Notion")
    ap.add_argument("--next", help="with --set: the Next Step text")
    ap.add_argument("--date", help="with --set: the Next Step Date, YYYY-MM-DD (empty clears it)")
    ap.add_argument("--ball", help="with --set: owner, claude or them (empty clears it)")
    ap.add_argument("--stage", choices=["outreach", "applied", "interviewing", "offer"],
                    help="with --set, from an interactive session only (the /interview-prep skill): move the stage")
    ap.add_argument("--out", help="where to write queue.json (default <Personal-OS>/Tools/pursue-followup/queue.json)")
    a = ap.parse_args()
    cfg = load_config()
    if a.set:
        print(f"{a.set}: wrote {', '.join(set_next(cfg, a.set, a.next, a.date, a.ball, a.stage))}")
        return
    if a.fold:
        p = paths(cfg)
        print(f"folded {len(fold_inputs(cfg, p, by_id(load_jobs(p)), False))} plan answers")
        return
    q = build(cfg, a.cap, lanes=a.lanes, dry=a.show)
    if a.show:
        print(f"active {q['active']}/{CAP}   bench {q['bench']}   owed: {q['owed']}   diligence this run: {q['diligence_this_run']}")
        for i in q["answers_folded"]:
            print(f"  would fold an answer for {i}")
        for l in q["lanes_set"]:
            print(f"  would set lane {l['lane']:<6} {l['id']}")
        for r in q["rows"]:
            print(f"  {r['lane']:<6} {r['stage']:<12} {(r['company'] or '')[:26]:<26} {', '.join(r['need'])}")
        return
    out = Path(a.out) if a.out else paths(cfg).personal_os / "Tools" / "pursue-followup" / "queue.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(q, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out}: active {q['active']}/{CAP}, bench {q['bench']}, {q['owed']} owed, "
          f"{q['diligence_this_run']} diligence this run, {len(q['lanes_set'])} lanes set, "
          f"{len(q['answers_folded'])} answers folded")


if __name__ == "__main__":
    main()
