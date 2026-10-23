"""One-page briefs for the items at the top of Today. Deterministic, no model, no web.

    py engine/briefs.py owed [--cap 15] [--out FILE]   the items that need a brief tonight, nearest first, as JSON
                                                      (the nightly pursue-followup routine writes each one)
    py engine/briefs.py show                          every brief on file, whether it still matches its item

the owner, 2026-10-23, on the Today cards: "When you click in, it should give you all the information you need to do the
thing... a one-page, detailed review of the action step and what to do next. That should be part of an overnight
run." The routine writes one brief per item in the vault's `briefs/<kind>-<id>.md` (shape: docs/brief.md); the board
shows its question and options A to C on the Today card and the whole page behind "Open brief". push_board.py pushes
them as board_meta `briefs`, keyed like the page's items (role:<job id>, person:<contact id>, plan:<job id>).

A brief belongs to one version of its item: `**For:**` holds the item's next step (or "plan vN"), and the page shows a
brief only while that still matches, so a stale brief never sits behind a changed card. A brief is owed when the item
can reach the top of Today (the same pools viewToday ranks: interviews within three days, plans to answer, a booked
call or a new intro, a move on a role in play or a touch due within a week, so the draft is ready before the
day; the owner, 2026-10-23: "every item should have a draft") and its file is missing, stale, or older than a week.
"""
import argparse
import json
import re
from datetime import date, timedelta

import network_notion
from common import by_id, load_config, load_jobs, paths
from notion_sync import load as load_notion, opps_file
from pursue_followup import CAP, EARLY, job_slug, plan_state
from render_dashboard import _keyvals, _linkify, _md, _sections, _wikilink, options, plan_record

AHEAD = 7     # days ahead: a move or touch due this week gets its brief and draft before the day (the owner, 2026-10-23)
MAX_AGE = 7   # days a brief stays good when its item has not changed
ACTS = ("brief", "done", "later", "snooze:N", "next:<step>|<days>", "sent", "applied", "promote", "bench", "pause",
        "close", "noresp", "slotquiet", "gone")  # what a Today button may do; anything else opens the brief


def brief_dir(p):
    return p.vault / "briefs"


def brief_file(p, key):
    return brief_dir(p) / (key.replace(":", "-") + ".md")


def _draft(sec):
    """The ## Draft section: its key-value lines (channel, to, gmail draft link) and the fenced text, for the copy
    and Claude buttons."""
    lines = sec.get("draft", [])
    kv = _keyvals(lines)
    m = re.search(r"```[a-z]*\n(.*?)\n```", "\n".join(lines), re.S)
    return {"channel": kv.get("channel", ""), "to": kv.get("to", ""), "subject": kv.get("subject", ""), "gmail": kv.get("gmail draft", ""),
            "text": m.group(1).strip() if m else ""} if lines else None


def _body_html(txt):
    """The brief's sections as HTML, without the header lines (the card shows those) and without ## Draft (the page
    shows it with its copy and Claude buttons)."""
    body = "\n## " + txt.split("\n## ", 1)[1] if "\n## " in txt else ""
    body = re.sub(r"\n## Draft\s*\n.*?(?=\n## |\Z)", "", body, flags=re.S | re.I)
    body = re.sub(r"\[\[([^\]]+)\]\]", _wikilink, body)
    return _linkify(_md.markdown(body, extensions=["tables"])) if _md else ""


def read(p, key):
    """One brief as the board needs it, or None."""
    f = brief_file(p, key)
    if not f.exists():
        return None
    txt = f.read_text(encoding="utf-8")
    sec = _sections(txt)
    kv = _keyvals(txt.split("\n## ", 1)[0].splitlines())
    title = re.search(r"^#\s+(.+)$", txt, re.M)
    rel = f.relative_to(p.vault).with_suffix("").as_posix()
    return {"key": key, "title": title.group(1).strip() if title else key, "for": kv.get("for", ""),
            "date": kv.get("date", ""), "kind": kv.get("kind", ""), "question": kv.get("question", ""),
            "action": kv.get("action", ""), "options": options(kv), "draft": _draft(sec),
            "html": _body_html(txt), "file": rel}


def load(p):
    """Every brief on file, keyed by item key, for board_meta `briefs`."""
    out = {}
    for f in sorted(brief_dir(p).glob("*.md")) if brief_dir(p).exists() else []:
        kind, _, rest = f.stem.partition("-")
        b = read(p, f"{kind}:{rest}")
        if b:
            out[b["key"]] = b
    return out


def _person_text(c):
    """The person's next touch as the page writes it (todoItems), so `**For:**` can match it."""
    t, a = c.get("next_type") or "", c.get("next_action") or "next touch"
    return (f"{t}: " if t and not a.lower().startswith(t.lower()) else "") + a


def candidates(p, today):
    """Every item that can reach the top of Today, in the page's rank order: [{key, for, kind, who, what, score}]."""
    idx = by_id(load_jobs(p))
    iso, k3, k1 = today.isoformat(), (today + timedelta(days=3)).isoformat(), (today + timedelta(days=1)).isoformat()
    k7 = (today + timedelta(days=AHEAD)).isoformat()
    iv, plans, moves, ppl_top, ppl_due, bench, gone = [], [], [], [], [], [], []
    active = 0
    for o in (load_notion(opps_file(p), "opps") or {}).get("opps") or []:
        j = idx.get(o.get("id"))
        if not j or j.get("verdict") != "pursue" or o.get("stage") in (None, "closed"):
            continue
        row = {"who": j["company"], "title": j.get("title", ""), "score": j.get("score") or 0, "job_file": j.get("job_file", "")}
        if o.get("lane") == "active" and o["stage"] in EARLY and job_slug(j):
            has, answered, _ = plan_state(p.vault, job_slug(j))
            plan = plan_record(p.vault, j["job_file"]) if has else None
            if has and not answered and plan and plan.get("status") == "proposed":
                plans.append({**row, "key": f"plan:{j['id']}", "for": f"plan v{plan['version']}", "kind": "plan",
                              "what": plan.get("decision") or plan.get("route", "")})
                continue
        active += o.get("lane") == "active" and o["stage"] in EARLY
        ps = j.get("posting") or {}
        if ps.get("state") in ("closed", "removed") and not ps.get("kept"):
            gone.append({**row, "key": f"role:{j['id']}", "for": o.get("next") or "", "kind": "move", "what": "posting gone: close or keep"})
            continue  # the page asks this before anything else about the role
        if o.get("lane") == "bench":
            bench.append({**row, "key": f"role:{j['id']}", "for": o.get("next") or "", "kind": "move", "what": "promote from the Bench"})
        in_play = o.get("lane") == "active" or o["stage"] not in EARLY
        nd, nxt = o.get("next_date") or "", o.get("next") or ""
        if o["stage"] == "interviewing" and nd and nd <= k3:
            iv.append({**row, "key": f"role:{j['id']}", "for": nxt, "kind": "interview", "what": nxt})
        elif in_play and o.get("ball") != "them" and nxt and nd and nd <= k7:
            moves.append({**row, "key": f"role:{j['id']}", "for": nxt, "kind": "move", "what": nxt})
    for c in network_notion.load(p).get("people") or []:
        nd = (c.get("next_date") or "")[:10]
        if not nd or c.get("status") == "Working together":
            continue  # undated touches never reach Today, and consulting stays on People
        row = {"key": f"person:{c['id']}", "for": _person_text(c), "who": c.get("name") or "", "title": c.get("company") or "",
               "what": _person_text(c), "score": 0, "high": c.get("priority") == "High", "date": nd}
        booked = re.match(r"^(call|meeting|event)$", c.get("next_type") or "", re.I) and iso <= nd <= k1
        intro = c.get("how") == "Warm intro" and c.get("status") != "Dormant" and nd <= iso
        if booked or intro:
            ppl_top.append({**row, "kind": "call" if booked else "intro"})
        elif nd <= k7:
            ppl_due.append({**row, "kind": "touch"})
    by_fit = lambda l: sorted(l, key=lambda r: -r["score"])
    ppl_due.sort(key=lambda r: (not r["high"], r["date"]))  # the page's order: High priority first, then oldest
    slot = by_fit(bench)[:1] if active < CAP else []  # the page offers the best Bench role an open slot
    return iv + by_fit(plans) + ppl_top + by_fit(moves) + gone + slot + ppl_due


def owed(p, today, cap):
    out = []
    for c in candidates(p, today):
        b = read(p, c["key"])
        stale = not b or b["for"] != c["for"] or not b["date"] or b["date"] < (today - timedelta(days=MAX_AGE)).isoformat()
        if stale:
            out.append({**c, "file": brief_file(p, c["key"]).relative_to(p.vault).as_posix(),
                        "reason": "missing" if not b else "item changed" if b["for"] != c["for"] else "older than a week"})
    return out[:cap]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["owed", "show"])
    ap.add_argument("--cap", type=int, default=15)
    ap.add_argument("--out")
    a = ap.parse_args()
    p = paths(load_config())
    today = date.today()
    if a.cmd == "owed":
        rows = owed(p, today, a.cap)
        txt = json.dumps(rows, indent=2, ensure_ascii=False)
        if a.out:
            open(a.out, "w", encoding="utf-8").write(txt + "\n")
        print(txt if not a.out else f"{len(rows)} briefs owed -> {a.out}")
        return
    cur = {c["key"]: c for c in candidates(p, today)}
    for k, b in load(p).items():
        c = cur.get(k)
        state = "current" if c and c["for"] == b["for"] else "item changed" if c else "not on Today"
        print(f"{k:50} {b['date']:10} {state:12} {b['title']}")


if __name__ == "__main__":
    main()
