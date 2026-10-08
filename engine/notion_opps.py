"""Opportunities in Notion: one page per Pursue role, linked to Companies, Network people, Meeting Notes and Tasks.

Notion is the record for a Pursue role's process state from 2026-09-16: stage, outcome, next step, human path, and
the links. The page's "Job ID" is the board record id (the join key). This module creates and fills those pages from
jobs.json (run `py engine/ingest_db.py` first so verdicts and stages are current).

    py engine/notion_opps.py backfill --dry-run     what would be created or updated, and the meeting links it suggests
    py engine/notion_opps.py backfill               create or update one page per Pursue; link Company and People
    py engine/notion_opps.py backfill --meetings    also write the suggested meeting links (after checking the dry run)
    py engine/notion_opps.py fill [--dry-run]       write each page's body: the role, what they ask for, the score
                                                    and the warm path, the same read the board shows

Idempotent: a role that already has a page (matched on Job ID) is updated, never duplicated. People come from each
Network page's "Job board roles" ids; a company is matched on its normalized name and created in Companies when
missing ("X via Recruiter" links to the recruiter). Meeting suggestions are meetings whose Company is the role's company, or whose People include a person
linked to the role.
"""
import argparse
import sys
from datetime import date

import notion
from common import OUTCOMES, STAGES, load_config, load_jobs, norm, paths, same_company
from notion import plain, prop, query_all

STAGE_NAME = {s: s.capitalize() for s in STAGES}
OUTCOME_NAME = {o: o.replace("_", " ").capitalize() for o in OUTCOMES}
HP_NAME = {"warm active": "Warm active", "warm reachable": "Warm reachable", "cold": "Cold"}


def job_ids(text):
    return [x for x in str(text or "").replace(";", ",").replace(" ", ",").split(",")
            if len(x) == 10 and all(c in "0123456789abcdef" for c in x)]


def fields(cfg, j):
    """The page properties a Pursue record fills. Links are added separately."""
    hp = j.get("human_path") or {}
    board = (cfg.get("notion") or {}).get("board_url", "").rstrip("/")
    return {
        "Name": prop("title", f"{j.get('title')} · {j.get('company')}"),
        "Job ID": prop("rich_text", j["id"]),
        "Stage": prop("select", STAGE_NAME.get(j.get("stage") or "shortlist")),
        "Outcome": prop("select", OUTCOME_NAME.get(j.get("outcome")) if j.get("stage") == "closed" else None),
        "Next Step": prop("rich_text", j.get("next_step")),
        "Next Step Date": prop("date", j.get("next_step_date")),
        "Human Path": prop("select", HP_NAME.get(hp.get("verdict"), "Unchecked")),
        "Human Path People": prop("rich_text", hp.get("people")),
        "Score": prop("number", j.get("score")),
        "Location": prop("rich_text", j.get("location")),
        "Posting": prop("url", j.get("url")),
        "Board": prop("url", f"{board}/#job/{j['id']}" if board else None),
        "Flag": prop("checkbox", j.get("flag")),
        "Pursued On": prop("date", j.get("verdict_date")),
    }


def company_name(j):
    """The company a role links to. A recruiter's placeholder ("Large-cap PE via Saragossa") links to the recruiter
    until the actual firm is known."""
    name = j.get("company") or ""
    return name.split(" via ", 1)[1].strip() if " via " in name else name


def company_page(companies, name):
    """The Companies page for a posting's company: exact normalized name first, then a loose match."""
    exact = [c for c in companies if norm(c["name"]) == norm(name)]
    if exact:
        return exact[0]
    loose = [c for c in companies if same_company(c["name"], name)]
    return loose[0] if len(loose) == 1 else None


def load_world(cfg, tok):
    n = cfg["notion"]
    opps = {plain(pg["properties"].get("Job ID")): pg for pg in query_all(tok, n["opportunities_data_source"])}
    companies = [{"id": pg["id"], "name": plain(pg["properties"].get("Name")) or ""}
                 for pg in query_all(tok, n["companies_data_source"])]
    people = [{"id": pg["id"], "name": plain(pg["properties"].get("Name")),
               "roles": job_ids(plain(pg["properties"].get("Job board roles")))}
              for pg in query_all(tok, n["network_data_source"])]
    meetings = [{"id": pg["id"], "name": plain(pg["properties"].get("Name")), "date": plain(pg["properties"].get("Date")),
                 "companies": plain(pg["properties"].get("Company")) or [],
                 "people": plain(pg["properties"].get("People")) or []}
                for pg in query_all(tok, n["meetings_data_source"])]
    return opps, companies, people, meetings


OWN_HEADING = "From the job board"


def blocks_for(j):
    """The page body: what the board shows about the role, under a heading this module owns."""
    card = j.get("card") or {}
    hp = j.get("human_path") or {}
    o = j.get("office") or {}
    para = lambda s: {"type": "paragraph", "paragraph": {"rich_text": notion.text(s)}}
    bullet = lambda s: {"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": notion.text(s)}}
    head = lambda s: {"type": "heading_3", "heading_3": {"rich_text": notion.text(s)}}
    out = [head(OWN_HEADING)]
    facts = [x for x in [f"Score {j.get('score')} ({'deep pass' if j.get('score_kind') == 'deep' else 'title only'})",
                         j.get("location") and f"Posting location: {j['location']}",
                         j.get("work_model") and f"Work model: {j['work_model']}",
                         j.get("comp") and f"Comp: {j['comp']}",
                         j.get("travel") and f"Travel: {j['travel']}",
                         (o.get("label") or o.get("address")) and f"Office: {o.get('label') or o.get('address')}",
                         j.get("source") and j["source"] != "hand" and f"Source: {j['source']}",
                         j.get("date_first_seen") and f"First seen {j['date_first_seen']}"] if x]
    out += [bullet(f) for f in facts]
    if card.get("job"):
        out.append(head("What the role is"))
        out += [bullet(b) for b in card["job"]]
    if j.get("qualifications"):
        out.append(head("What they ask for"))
        out += [bullet(q) for q in j["qualifications"]]
    if j.get("why") or card.get("math") or j.get("mismatch"):
        out.append(head("Why it scored"))
        if card.get("math"):
            out.append({"type": "code", "code": {"language": "plain text", "rich_text": notion.text(card["math"])}})
        for x in (j.get("why"), j.get("mismatch")):
            if x:
                out.append(para(x))
    if hp.get("verdict") or hp.get("people"):
        out.append(head("Human path"))
        line = hp.get("verdict") or "unchecked"
        if hp.get("qualifier"):
            line += f" ({hp['qualifier']})"
        if hp.get("checked"):
            line += f", checked {hp['checked']}"
        out.append(para(line))
        if hp.get("people"):
            out.append(para(hp["people"]))
    if j.get("note") or j.get("status_note"):
        out.append(head("My notes"))
        for x in (j.get("note"), j.get("status_note")):
            if x:
                out.append(para(x))
    if j.get("url"):
        out.append({"type": "paragraph", "paragraph": {"rich_text": [
            {"type": "text", "text": {"content": "The posting", "link": {"url": j["url"]}}}]}})
    return out


def block_text(blocks):
    """The plain text of a block list, from either shape: what we are about to write, or what Notion holds."""
    out = []
    for b in blocks:
        t = b.get("type") or ""
        rt = (b.get(t) or {}).get("rich_text") or []
        out.append(t + ":" + "".join(x.get("plain_text") or ((x.get("text") or {}).get("content") or "") for x in rt))
    return "\n".join(out)


def own_blocks(tok, page_id):
    """Our heading and everything after it: what a previous run wrote, safe to replace."""
    kids = notion.children(tok, page_id)
    for i, b in enumerate(kids):
        t = b.get("type") or ""
        if t.startswith("heading"):
            text = "".join(x.get("plain_text", "") for x in (b.get(t) or {}).get("rich_text") or [])
            if text.strip() == OWN_HEADING:
                return kids[i:]
    return []


def fill(a):
    """Write each Pursue page's body from its record. Blocks above our heading, the owner's own, are never touched."""
    cfg = load_config()
    p = paths(cfg)
    tok = notion.token(cfg)
    pursue = {j["id"]: j for j in load_jobs(p)["jobs"] if j.get("verdict") == "pursue"}
    pages = query_all(tok, notion.source(cfg, "opportunities_data_source"))
    done = same = 0
    for pg in pages:
        jid = plain(pg["properties"].get("Job ID"))
        j = pursue.get(jid)
        if not j:
            continue
        blocks = blocks_for(j)
        mine = own_blocks(tok, pg["id"])
        if block_text(mine) == block_text(blocks):   # nothing changed: leave Notion alone (the build runs this daily)
            same += 1
            continue
        print(f"fill  {plain(pg['properties'].get('Name'))}: {len(blocks)} blocks")
        if a.dry_run:
            continue
        for b in mine:
            notion.call(tok, f"/blocks/{b['id']}", method="DELETE")
        for i in range(0, len(blocks), 100):
            notion.call(tok, f"/blocks/{pg['id']}/children", {"children": blocks[i:i + 100]}, "PATCH")
        done += 1
    print(f"\n{'would fill' if a.dry_run else 'filled'} {done} pages, {same} already current")


def backfill(a):
    cfg = load_config()
    p = paths(cfg)
    tok = notion.token(cfg)
    n = cfg["notion"]
    pursue = [j for j in load_jobs(p)["jobs"] if j.get("verdict") == "pursue"]
    opps, companies, people, meetings = load_world(cfg, tok)
    names = {x["id"]: x["name"] for x in people}
    print(f"{len(pursue)} Pursue roles; {len(opps)} Opportunities pages exist; "
          f"{len(companies)} companies, {len(people)} people, {len(meetings)} meetings in Notion\n")

    made = updated = linked_m = 0
    for j in sorted(pursue, key=lambda j: (j.get("company") or "").lower()):
        props = fields(cfg, j)
        co = company_page(companies, company_name(j))
        who = [x["id"] for x in people if j["id"] in x["roles"]]
        mt = [m for m in meetings if (co and co["id"] in m["companies"]) or set(who) & set(m["people"])]
        page = opps.get(j["id"])
        verb = "update" if page else "create"
        print(f"{verb:6} {j['id']}  {j.get('title')} · {j.get('company')}  [{STAGE_NAME.get(j.get('stage') or 'shortlist')}]")
        print(f"         company: {co['name'] if co else 'NEW ' + company_name(j)}"
              f"{'   people: ' + ', '.join(names[i] or '?' for i in who) if who else ''}")
        for m in mt:
            print(f"         meeting? {m['date'] or '----------'}  {m['name']}")
        if a.dry_run:
            continue
        if not co:
            res = notion.call(tok, "/pages", {"parent": {"data_source_id": n["companies_data_source"]}, "properties": {
                "Name": prop("title", company_name(j)), "Date Added": prop("date", date.today().isoformat())}}, "POST")
            co = {"id": res["id"], "name": company_name(j)}
            companies.append(co)
        rel = lambda k, ids: list(dict.fromkeys((plain(page["properties"].get(k)) if page else []) + ids))
        props["Company"] = prop("relation", rel("Company", [co["id"]]))
        props["People"] = prop("relation", rel("People", who))
        if a.meetings:
            props["Meetings"] = prop("relation", rel("Meetings", [m["id"] for m in mt]))
            linked_m += len(mt)
        if page:
            notion.call(tok, f"/pages/{page['id']}", {"properties": props}, "PATCH")
            updated += 1
        else:
            res = notion.call(tok, "/pages", {"parent": {"data_source_id": n["opportunities_data_source"]},
                                              "icon": {"type": "emoji", "emoji": "🎯"}, "properties": props}, "POST")
            opps[j["id"]] = res
            made += 1
    if not a.dry_run:
        print(f"\ncreated {made}, updated {updated}" + (f", {linked_m} meeting links" if a.meetings else ""))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backfill")
    b.add_argument("--dry-run", action="store_true")
    b.add_argument("--meetings", action="store_true", help="write the suggested meeting links too")
    f = sub.add_parser("fill")
    f.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if a.cmd == "backfill":
        backfill(a)
    elif a.cmd == "fill":
        fill(a)


if __name__ == "__main__":
    main()
