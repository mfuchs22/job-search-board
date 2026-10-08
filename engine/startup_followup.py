"""What the Startups tab's calls still owe the vault. Deterministic, no model, no web.

    py engine/startup_followup.py                 write the queue to <vault>/../Tools/startup-followup/queue.json
    py engine/startup_followup.py --show          print it as a table and write nothing
    py engine/startup_followup.py --cap 3         mark at most 3 Interesting companies for a diligence pass this run

the owner's rule (2026-09-23): "anything that gets an Interesting or a Watch should get its own file written up
about it." Interesting earns a company card plus a `/diligence <company> quick` pass (research/<slug>/);
Watch earns the company card only. This script reads `startup_verdicts` and `startups` from Supabase, checks
what exists in the vault, and writes the queue the nightly `startup-followup` routine works from. The
routine (Personal-OS Tools/startup-followup-prompt.md) does the writing; this decides what is owed.

Nothing here is personal: the vault path comes from config.json.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from common import load_config, paths, slug
from supabase import select

WANTED = {"interesting", "watch"}


def owed(vault: Path, name: str, call: str):
    """Which files a company with this call still lacks. Cards and research folders are named by slug(name),
    the same rule startups.py uses for `vault_card`, so the tab links them once startups.py reruns."""
    s = slug(name)
    card = vault / "companies" / f"{s}.md"
    brief = vault / "research" / s / "brief.md"
    need = []
    if not card.exists():
        need.append("card")
    if call == "interesting" and not brief.exists():
        need.append("diligence")
    return s, need


def build(cfg, cap):
    p = paths(cfg)
    verdicts = {v["id"]: v for v in select("startup_verdicts", {"select": "id,v,note,flag,ts"})}
    cards = {r["id"]: r["payload"] for r in select("startups", {"select": "id,payload"})}
    rows = []
    for vid, v in verdicts.items():
        call = (v.get("v") or "").lower()
        if call not in WANTED:
            continue
        c = cards.get(vid)
        if not c:
            rows.append({"id": vid, "name": v.get("name") or vid, "call": call, "slug": None, "need": [],
                         "problem": "verdict has no startups row (company left MGMT's board?)"})
            continue
        s, need = owed(p.vault, c["name"], call)
        rows.append({
            "id": vid, "name": c["name"], "slug": s, "call": call, "need": need,
            "note": v.get("note") or "", "flag": bool(v.get("flag")), "called_at": v.get("ts"),
            "card": f"companies/{s}.md", "research": f"research/{s}/",
            "one_liner": c.get("one_liner"), "hq": c.get("hq"), "stage": c.get("stage"), "tag": c.get("tag"),
            "people": c.get("people"), "founded": c.get("founded"), "round_type": c.get("round_type"),
            "round_date": c.get("round_date"), "raised": c.get("raised"), "investors": c.get("investors") or [],
            "website": c.get("website"), "careers": c.get("careers"), "linkedin": c.get("linkedin"), "mgmt": c.get("mgmt"),
            "description": c.get("description"), "research_row": c.get("research"),
            "first_degree": c.get("first_degree") or [], "board_rows": c.get("board_rows") or [],
            "screen": c.get("screen"),
        })
    # Newest call first: what the owner just decided is what he is most likely to act on next.
    rows.sort(key=lambda r: r.get("called_at") or "", reverse=True)
    # Cap the diligence passes per run so one night never eats the subscription's usage window.
    n = 0
    for r in rows:
        if "diligence" in r["need"]:
            if n < cap:
                r["diligence_this_run"] = True
                n += 1
            else:
                r["diligence_this_run"] = False
                r["need"] = [x for x in r["need"] if x != "diligence"] + ["diligence (deferred)"]
    todo = [r for r in rows if r["need"] or r.get("problem")]
    return {
        "built": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cap": cap,
        "calls": {k: sum(1 for r in rows if r["call"] == k) for k in sorted(WANTED)},
        "owed": len(todo),
        "cards_to_write": sum(1 for r in todo if "card" in r["need"]),
        "diligence_this_run": n,
        "diligence_deferred": sum(1 for r in todo if "diligence (deferred)" in r["need"]),
        "rows": todo,
        "done": [{"id": r["id"], "name": r["name"], "call": r["call"]} for r in rows if not r["need"] and not r.get("problem")],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--show", action="store_true", help="print the queue, write nothing")
    ap.add_argument("--cap", type=int, default=3, help="max Interesting companies to mark for a diligence pass (default 3)")
    ap.add_argument("--out", help="where to write queue.json (default <vault>/../Tools/startup-followup/queue.json)")
    a = ap.parse_args()
    cfg = load_config()
    q = build(cfg, a.cap)
    if a.show:
        print(f"calls: {q['calls']}   owed: {q['owed']}   cards to write: {q['cards_to_write']}   "
              f"diligence this run: {q['diligence_this_run']} (deferred {q['diligence_deferred']})")
        for r in q["rows"]:
            print(f"  {r['call']:<11} {r['name']:<24} {', '.join(r['need']) or r.get('problem')}")
        if q["done"]:
            print(f"  already written up: {', '.join(d['name'] for d in q['done'])}")
        return
    out = Path(a.out) if a.out else paths(cfg).vault.parent.parent / "Tools" / "startup-followup" / "queue.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(q, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out}: {q['owed']} owed ({q['cards_to_write']} cards, {q['diligence_this_run']} diligence now, "
          f"{q['diligence_deferred']} deferred)")


if __name__ == "__main__":
    main()
