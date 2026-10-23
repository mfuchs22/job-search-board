"""Who changed jobs: the monthly LinkedIn export compared with the last one, and a weekly read of the people who matter.

    py engine/contact_refresh.py diff [--dry-run]          compare network/connections.csv (fresh from the export,
                                                           network_ingest.py) with the snapshot of the last export;
                                                           record every company or title change, update the Notion
                                                           Network row of anyone who is in it, then move the snapshot
    py engine/contact_refresh.py targets [--cap 10] [--days 14]
                                                           the Network people to read on LinkedIn this week, as JSON
    py engine/contact_refresh.py record reads.json [--dry-run]
                                                           fold the week's reads into Notion and the change list
    py engine/contact_refresh.py show                      the changes of the last 30 days

the owner, 2026-10-23: contact details should refresh on a schedule. The rule set (agreed the same day):
- Everyone (~535 connections) once a month, from LinkedIn's own data export. No profile is opened; the export lists
  each connection's current company and title, so a job change shows as a difference between two exports. The first
  run only seeds the snapshot. Rows learned from acceptance emails (connections-email.csv) carry no prior and are skipped.
- The people who matter once a week: Network people tied to a role in play (Active, or Applied and later) through the
  Opportunity's people or "Job board roles", or whose Status is In conversation, Waiting on them, Champion or Working
  together. At most --cap a run, none read in the last --days, the longest unread first. The reading is the model's
  (Personal-OS Tools/contact-refresh-prompt.md, the owner's Chrome on the mini, paced, capped); it writes reads.json:

    [{"id": "<Notion contact id>", "company": "Acme", "role": "VP Operations", "linkedin": "https://...",
      "changed": true, "since": "Oct 2026", "draft": "Congrats on the move to Acme..."}]

  `changed` is the model's call that the role is new (a reworded title is not a change); a different employer counts
  whatever it says. `draft` is a short congratulations note for the owner to send himself. A page it could not read is
  {"id": ..., "unreadable": true} and only resets nothing.

What a change writes: the person's Notion Company and Role (the old values go into the change row, never lost), LinkedIn
when the row had none, and Profile checked. Every read person gets Profile checked. The change itself goes to
network/contact-changes.json, which push_board.py sends to the board (board_meta contact_changes) and Today shows as a
relationship prompt with the draft, ranked first when the person is on a role in play (their warm path moved). Nothing
here sends anything to anyone.
"""
import argparse
import csv
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import notion
from common import load_config, norm, paths
from network_notion import contacts_file
from notion_sync import load as load_notion, opps_file
from pursue_followup import EARLY

WARM = {"In conversation", "Waiting on them", "Champion", "Working together"}
KEEP_DAYS = 30
SNAP_COLS = ["id", "first", "last", "url", "company_raw", "position", "company_key"]


def snapshot_file(p):
    return p.network / "contact-snapshot.csv"


def changes_file(p):
    return p.network / "contact-changes.json"


def checks_file(p):
    return p.network / "contact-checks.json"


def read_json(f, empty):
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else empty


def write_json(f, data):
    f.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")


def read_csv(f):
    if not f.exists():
        return []
    with f.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def li_slug(url):
    u = (url or "").lower().split("?")[0].rstrip("/")
    return u.split("/in/")[-1] if "/in/" in u else ""


def same_employer(a, b):
    """Equal after normalization, or one inside the other ('Bain' and 'Bain & Company'). Stricter than
    common.same_company, whose first-two-words rule is for posting titles, not people."""
    a, b = norm(a), norm(b)
    if not (a and b):
        return a == b
    return a == b or f" {a} " in f" {b} " or f" {b} " in f" {a} "


def in_play(p):
    """Job id -> opportunity, for the Pursue roles in play (Active, or Applied and later; not closed)."""
    out = {}
    for o in load_notion(opps_file(p), "opps").get("opps") or []:
        if o.get("stage") in (None, "closed"):
            continue
        if o.get("lane") == "active" or o.get("stage") not in EARLY:
            out[o["id"]] = o
    return out


def people(p):
    return read_json(contacts_file(p), {}).get("people") or []


def roles_for(c, play):
    """The in-play job ids this person is tied to: Opportunity people, or the Network row's Job board roles."""
    ids = {jid for jid, o in play.items() if c["id"] in (o.get("people") or [])}
    return sorted(ids | {r for r in c.get("roles") or [] if r in play})


def record_changes(p, rows, today):
    """Append change rows, one per person and new position, and drop rows older than KEEP_DAYS."""
    data = read_json(changes_file(p), {"changes": []})
    have = {r["key"] for r in data["changes"]}
    new = [r for r in rows if r["key"] not in have]
    cut = (today - timedelta(days=KEEP_DAYS)).isoformat()
    data["changes"] = sorted([r for r in data["changes"] if r["date"] >= cut] + new, key=lambda r: (r["date"], r["key"]), reverse=True)
    data["asof"] = today.isoformat()
    return data, new


def change_row(today, source, name, linkedin, old_co, old_role, new_co, new_role, c=None, roles=(), company_key="", draft="", since=""):
    return {"key": f"{li_slug(linkedin) or norm(name).replace(' ', '-')}|{norm(new_co)}|{norm(new_role)}",
            "date": today.isoformat(), "source": source, "name": name, "linkedin": linkedin,
            "contact": (c or {}).get("id"), "old_company": old_co, "old_role": old_role,
            "new_company": new_co, "new_role": new_role, "since": since, "company_key": company_key,
            "roles": list(roles), "draft": draft}


def notion_fields(c, new_co, new_role, linkedin, today):
    """The Network properties a change or a read writes. Company and Role only when they moved."""
    f = {"Profile checked": ("date", today.isoformat())}
    if new_co and not same_employer(new_co, c.get("company")):
        f["Company"] = ("rich_text", new_co)
    if new_role and new_role != (c.get("role") or ""):
        f["Role"] = ("rich_text", new_role)
    if linkedin and not c.get("linkedin"):
        f["LinkedIn"] = ("url", linkedin)
    return f


def write_notion(tok, schema, cid, fields):
    props = {k: notion.prop(kind, v) for k, (kind, v) in fields.items() if k in schema}
    if props:
        notion.call(tok, f"/pages/{cid}", {"properties": props}, "PATCH")
    return sorted(props)


def notion_session(cfg):
    tok, ds = notion.token(cfg), notion.source(cfg, "network_data_source")
    return tok, set((notion.call(tok, f"/data_sources/{ds}").get("properties") or {}))


# ---------- diff: the monthly export ----------

def diff(cfg, p, dry, today=None):
    today = today or date.today()
    cur = [r for r in read_csv(p.network / "connections.csv")]
    snap = {r["id"]: r for r in read_csv(snapshot_file(p))}
    out = []
    if not snap:
        out.append(f"no snapshot yet: seeded from {len(cur)} connections, nothing compared")
        rows = []
    else:
        by_slug = {li_slug(c.get("linkedin")): c for c in people(p) if li_slug(c.get("linkedin"))}
        play = in_play(p)
        rows = []
        for r in cur:
            old = snap.get(r["id"])
            if not old:
                continue
            moved = not same_employer(r["company_raw"], old["company_raw"])
            retitled = (r["position"] or "").strip() != (old["position"] or "").strip()
            if not (moved or retitled) or not (r["company_raw"] or r["position"]):
                continue
            c = by_slug.get(li_slug(r["url"])) or by_slug.get(r["id"])
            name = f"{r['first']} {r['last']}".strip()
            rows.append((change_row(today, "export", name, r["url"], old["company_raw"], old["position"], r["company_raw"],
                                    r["position"], c, roles_for(c, play) if c else [], r.get("company_key") or ""), c))
    data, new = record_changes(p, [r for r, _ in rows], today)
    fresh = {r["key"] for r in new}
    tok = schema = None
    for r, c in rows:
        if r["key"] not in fresh:
            continue
        where = "not in the Network"
        if c:
            f = notion_fields(c, r["new_company"], r["new_role"], r["linkedin"], today)
            if dry:
                where = "would write " + ", ".join(sorted(f))
            else:
                if tok is None:
                    tok, schema = notion_session(cfg)
                where = "wrote " + ", ".join(write_notion(tok, schema, c["id"], f))
        out.append(f"{r['name']}: {r['old_role'] or '?'} at {r['old_company'] or '?'} -> {r['new_role'] or '?'} at {r['new_company'] or '?'} ({where})")
    if not dry:
        write_json(changes_file(p), data)
        with snapshot_file(p).open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=SNAP_COLS, extrasaction="ignore", lineterminator="\n")
            w.writeheader()
            w.writerows(cur)
    out.append(f"export diff: {len(new)} changes, {sum(1 for r, c in rows if c and r['key'] in fresh)} in the Network")
    return out


# ---------- targets and record: the weekly read ----------

def targets(p, cap, days, today=None):
    today = today or date.today()
    play = in_play(p)
    checked = read_json(checks_file(p), {})
    cut = (today - timedelta(days=days)).isoformat()
    out = []
    for c in people(p):
        roles = roles_for(c, play)
        if not c.get("linkedin") or not (roles or c.get("status") in WARM):
            continue
        last = checked.get(c["id"]) or ""
        if last > cut:
            continue
        out.append({"id": c["id"], "name": c.get("name"), "linkedin": c["linkedin"], "company": c.get("company"),
                    "role": c.get("role"), "status": c.get("status"), "roles": roles, "last_checked": last or None,
                    "read": c["linkedin"].split("?")[0].rstrip("/") + "/details/experience/"})
    out.sort(key=lambda r: (r["last_checked"] or "", not r["roles"], r["name"] or ""))
    return out[:cap]


def record(cfg, p, reads, dry, today=None):
    today = today or date.today()
    idx = {c["id"]: c for c in people(p)}
    play = in_play(p)
    checked = read_json(checks_file(p), {})
    rows, lines, writes = [], [], []
    for r in reads:
        c = idx.get(r.get("id"))
        if not c:
            lines.append(f"skipped (not in the last Notion pull): {json.dumps(r)[:120]}")
            continue
        if r.get("unreadable"):
            lines.append(f"{c['name']}: unreadable, left for next week")
            continue
        co, role = (r.get("company") or "").strip(), (r.get("role") or "").strip()
        moved = bool(co) and not same_employer(co, c.get("company"))
        if moved or r.get("changed"):
            rows.append(change_row(today, "profile", c["name"], r.get("linkedin") or c.get("linkedin"), c.get("company") or "",
                                   c.get("role") or "", co or c.get("company") or "", role or c.get("role") or "", c,
                                   roles_for(c, play), draft=(r.get("draft") or "").strip(), since=r.get("since") or ""))
            f = notion_fields(c, co, role, r.get("linkedin"), today)
            lines.append(f"{c['name']}: now {role or '?'} at {co or c.get('company') or '?'}")
        else:
            f = notion_fields(c, "", "", r.get("linkedin"), today)
            lines.append(f"{c['name']}: no change")
        writes.append((c["id"], f))
        checked[c["id"]] = today.isoformat()
    data, new = record_changes(p, rows, today)
    if dry:
        lines += [f"would write {cid[:8]}: {', '.join(sorted(f))}" for cid, f in writes]
    else:
        if writes:
            tok, schema = notion_session(cfg)
            for cid, f in writes:
                write_notion(tok, schema, cid, f)
        write_json(changes_file(p), data)
        write_json(checks_file(p), dict(sorted(checked.items())))
    lines.append(f"profiles: {len(writes)} read, {len(new)} changed")
    return lines


def show(p, today=None):
    today = today or date.today()
    rows = read_json(changes_file(p), {"changes": []})["changes"]
    cut = (today - timedelta(days=KEEP_DAYS)).isoformat()
    return [f"{r['date']} {r['source']:7} {r['name']}: {r['old_company'] or '?'} -> {r['new_role'] or '?'} at {r['new_company'] or '?'}"
            + (" (in the Network)" if r.get("contact") else "") + (f" [roles {', '.join(r['roles'])}]" if r.get("roles") else "")
            for r in rows if r["date"] >= cut] or ["no changes in the last 30 days"]


def board_payload(p):
    """board_meta contact_changes: the last KEEP_DAYS of changes, for Today (push_board.py)."""
    return read_json(changes_file(p), {"asof": None, "changes": []})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("diff")
    d.add_argument("--dry-run", action="store_true")
    t = sub.add_parser("targets")
    t.add_argument("--cap", type=int, default=10)
    t.add_argument("--days", type=int, default=14)
    r = sub.add_parser("record")
    r.add_argument("file")
    r.add_argument("--dry-run", action="store_true")
    sub.add_parser("show")
    a = ap.parse_args()
    cfg = load_config()
    p = paths(cfg)
    if a.cmd == "diff":
        print("\n".join(diff(cfg, p, a.dry_run)))
    elif a.cmd == "targets":
        json.dump(targets(p, a.cap, a.days), sys.stdout, indent=1, ensure_ascii=False)
        print()
    elif a.cmd == "record":
        print("\n".join(record(cfg, p, json.loads(Path(a.file).read_text(encoding="utf-8")), a.dry_run)))
    else:
        print("\n".join(show(p)))


if __name__ == "__main__":
    main()
