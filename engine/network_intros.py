"""Introductions by email, recorded once as people in the Notion Network.

    py engine/network_intros.py record intros.json [--dry-run]

the owner, 2026-10-21: a contact emailing to connect him with someone (a friend introducing a former colleague) is often
the best lead he has, and it should land on the board's People tab without his saying so.
The model's part (the pursue-followup routine's mail step, Personal-OS Tools/pursue-followup-prompt.md) is only
reading Gmail and judging which emails are introductions; it writes intros.json:

    [{"name": "Rhea Kapoor", "email": "rhea@example.com", "company": "Lattice Health", "role": "VP Operations",
      "introducer": "Sam Delgado", "date": "YYYY-MM-DD", "context": "one line: why they should talk",
      "link": "https://mail.google.com/...", "replied": false}]

`replied` is whether the owner has already answered on the thread. Everything else here is deterministic: a person already
in the Network (same name, by a live Notion query) is left alone; a new one is created with How Connected = Warm intro,
the intro as the Hook and the first touch, and the next touch set: reply and book a time (today), or, when the owner has
replied, book the conversation once they answer (5 business days out, status Waiting on them). The board's People tab
lists a Warm intro with no call or meeting logged under Intros to act on. Nothing here sends anything.
"""
import argparse
import json
from datetime import date, timedelta
from pathlib import Path

import notion
from common import load_config


def biz(d, n):
    """n business days after date d."""
    while n:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def value(kind, v):
    """A property value in the shape its Notion type wants (Status may be a status or a select property)."""
    if kind == "status":
        return {"status": {"name": v} if v else None}
    return notion.prop(kind, v)


def existing(tok, ds, name):
    flt = {"filter": {"property": "Name", "title": {"equals": name}}}
    return notion.query_all(tok, ds, flt)


def page_for(i, today):
    """The Network fields for one intro."""
    when = date.fromisoformat(i["date"])
    hook = f"Intro from {i['introducer']} (email, {when.strftime('%b')} {when.day})"
    if i.get("context"):
        hook += f": {i['context']}"
    replied = bool(i.get("replied"))
    notes = " · ".join(x for x in [i.get("email"), i.get("link")] if x)
    return {
        "Name": i["name"].strip(), "Company": i.get("company") or "", "Role": i.get("role") or "",
        "How Connected": "Warm intro", "Track": "Relationship", "Status": "Waiting on them" if replied else "Not contacted", "Hook": hook,
        "Last Touch Type": "Email", "Last Touch Date": i["date"], "Last Touch Note": f"{i['introducer']}'s intro email",
        "Next Touch Type": "Email",
        "Next Action": "Book the conversation once they answer" if replied else "Reply to the intro and book a time",
        "Next Action Date": (biz(today, 5) if replied else today).isoformat(), "Notes": notes,
    }, f"{i['date']} · Email · Intro from {i['introducer']}" + (f": {i['context']}" if i.get("context") else "")


def record(cfg, intros, dry, today=None):
    today = today or date.today()
    tok, ds = notion.token(cfg), notion.source(cfg, "network_data_source")
    schema = {k: v["type"] for k, v in (notion.call(tok, f"/data_sources/{ds}").get("properties") or {}).items()}
    out = []
    for i in intros:
        if not (i.get("name") and i.get("introducer") and i.get("date")):
            out.append(f"skipped (needs name, introducer and date): {json.dumps(i)[:120]}")
            continue
        if existing(tok, ds, i["name"].strip()):
            out.append(f"{i['name']}: already in the Network, left alone")
            continue
        fields, line = page_for(i, today)
        props = {k: value(schema[k], v or None) for k, v in fields.items() if k in schema and (v or k == "Name")}
        if dry:
            out.append(f"{i['name']}: would add (intro from {i['introducer']}), next: {fields['Next Action']} {fields['Next Action Date']}")
            continue
        page = notion.call(tok, "/pages", {"parent": {"type": "data_source_id", "data_source_id": ds}, "properties": props}, "POST")
        notion.call(tok, f"/blocks/{page['id']}/children", {"children": [
            {"type": "heading_3", "heading_3": {"rich_text": notion.text("Touch log")}},
            {"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": notion.text(line)}}]}, "PATCH")
        out.append(f"{i['name']}: added (intro from {i['introducer']}), next: {fields['Next Action']} {fields['Next Action Date']}")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("record")
    r.add_argument("file")
    r.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    intros = json.loads(Path(a.file).read_text(encoding="utf-8"))
    lines = record(load_config(), intros, a.dry_run)
    print("\n".join(lines) or "no intros")
    print(f"intros: {sum(' added' in l or 'would add' in l for l in lines)} added, {sum('already' in l for l in lines)} known")


if __name__ == "__main__":
    main()
