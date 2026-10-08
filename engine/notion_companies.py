"""Company pages in Notion, filled from the board's company read.

Each Pursue role's Notion Opportunity links to a Companies page. This fills that page with what the board already
knows about the employer (companies.json, written by the deep pass): what they do, the website, the office the roles
hire into, headcount and its trend, the growth read and revenue. The scannable facts go in properties; the prose and
its sources go in the page body, under a heading this module owns.

    py engine/notion_companies.py fill --dry-run    what would change, page by page
    py engine/notion_companies.py fill              write the properties and the body section

Idempotent: properties are rewritten from companies.json every run, and the body section below "From the job board"
is replaced (blocks above it, the owner's own, are never touched). `Status`, `Category`, `Why Interesting` and `Notes`
belong to the owner; this module never writes them.
"""
import argparse
import json
import re
import sys

import notion
from common import load_config, norm, paths, same_company
from notion import plain, prop, query_all

OWN_HEADING = "From the job board"
TREND = {"growing": "Growing", "flat": "Flat", "shrinking": "Shrinking"}


def company_read(cos, name):
    """The companies.json entry for a Notion company page title, matched the way the rest of the engine matches."""
    for k, v in cos.items():
        if norm(k) == norm(name):
            return v
    loose = [v for k, v in cos.items() if same_company(k, name)]
    return loose[0] if len(loose) == 1 else None


GENERIC = {"hq", "office", "offices", "hybrid", "remote", "onsite", "site", "area", "primary", "not", "stated",
            "days", "week", "option", "preferred", "employer", "undisclosed", "and", "the", "for", "with", "per"}


def place(s):
    """The place words in an office label, so "Boston HQ (Fan Pier)" and "Vertex HQ, Boston Seaport" are one place."""
    return {w for w in re.findall(r"[a-z]{3,}", s.lower()) if w not in GENERIC}


def offices(jobs, name):
    """Where the linked roles actually sit: the office label or address, else the posting's location. Short and
    distinct — a company hiring into four cities gets the first three, not every posting's wording."""
    seen = []
    for j in jobs:
        co = j.get("company") or ""
        co = co.split(" via ", 1)[1] if " via " in co else co
        if not same_company(co, name) or j.get("verdict") != "pursue":
            continue
        o = j.get("office") or {}
        v = o.get("label") or o.get("address") or j.get("location") or ""
        v = re.sub(r"\s*\((?:also|plus)[^)]*\)?", "", v)   # drop "(also Chicago, LA, NYC…)": this is the hiring office
        v = re.split(r"[;,]?\s*(?:also|and)\b|;", v)[0].strip(" ,;")
        if v.count("(") > v.count(")"):                   # a label cut mid-parenthesis
            v = v[:v.rindex("(")].strip(" ,;")
        if v and not any(place(v) & place(x) for x in seen):
            seen.append(v)
    return seen[:3]


def props(read, where):
    g = (read.get("growth") or {}) if read else {}
    emp, trend, rev = g.get("employees") or {}, g.get("headcount_trend") or {}, g.get("revenue") or {}
    head = " · ".join(x for x in [emp.get("count"), emp.get("as_of")] if x)
    out = {
        "About": prop("rich_text", " ".join(read.get("about") or []) if read else None),
        "Website": prop("url", (read or {}).get("url")),
        "Location": prop("rich_text", "; ".join(where)),
        "Headcount": prop("rich_text", head),
        "Headcount Trend": prop("select", TREND.get((trend.get("read") or "").lower(), "Unknown")),
        "Growth Read": prop("rich_text", g.get("read") or trend.get("detail")),
        "Revenue": prop("rich_text", " · ".join(x for x in [rev.get("latest"), rev.get("growth")]
                                               if x and not x.lower().startswith("unknown")) or None),
    }
    return out


def body(read, where, roles):
    """The blocks under our heading: what they do, the numbers, the office, the open roles, and the sources."""
    g = (read.get("growth") or {}) if read else {}
    emp, trend, rev, loc = (g.get(k) or {} for k in ("employees", "headcount_trend", "revenue", "local_office"))
    para = lambda s: {"type": "paragraph", "paragraph": {"rich_text": notion.text(s)}}
    bullet = lambda s: {"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": notion.text(s)}}
    blocks = [{"type": "heading_3", "heading_3": {"rich_text": notion.text(OWN_HEADING)}}]
    for line in (read.get("about") or []) if read else []:
        blocks.append(para(line))
    facts = []
    if emp.get("count"):
        facts.append(f"Headcount: {emp['count']}" + (f" (as of {emp['as_of']})" if emp.get("as_of") else ""))
    if trend.get("detail"):
        facts.append(f"Trend: {trend.get('read') or 'unknown'} — {trend['detail']}")
    if rev.get("latest") and rev["latest"] != "unknown":
        facts.append(f"Revenue: {rev['latest']}" + (f"; growth {rev['growth']}" if rev.get("growth") not in (None, "unknown") else ""))
    if loc.get("detail"):
        facts.append(f"Local office: {loc['detail']}")
    if where:
        facts.append("Roles hire into: " + "; ".join(where))
    if g.get("read"):
        facts.append(f"Read: {g['read']}" + (f" (confidence {g['confidence']})" if g.get("confidence") else ""))
    blocks += [bullet(f) for f in facts]
    if roles:
        blocks.append(bullet("Open roles on the board: " + ", ".join(roles)))
    srcs = [s for s in [emp.get("source"), trend.get("source"), rev.get("source"), loc.get("source")] if s]
    for s in dict.fromkeys(srcs):
        link = s.startswith("http://") or s.startswith("https://")  # a source is sometimes a note, not a URL
        blocks.append({"type": "bulleted_list_item", "bulleted_list_item": {
            "rich_text": [{"type": "text", "text": {"content": s[:300], **({"link": {"url": s}} if link else {})}}]}})
    return blocks


def block_text(blocks):
    """The plain text of a block list, from either shape: what we are about to write, or what Notion holds."""
    out = []
    for b in blocks:
        t = b.get("type") or ""
        rt = (b.get(t) or {}).get("rich_text") or []
        out.append(t + ":" + "".join(x.get("plain_text") or ((x.get("text") or {}).get("content") or "") for x in rt))
    return "\n".join(out)


def prop_text(value):
    """A property value we are about to write, as plain text, so it can be compared with what Notion holds."""
    kind = next(iter(value))
    v = value[kind]
    if kind in ("title", "rich_text"):
        return "".join((x.get("text") or {}).get("content") or "" for x in v or []) or None
    if kind == "select":
        return (v or {}).get("name")
    if kind == "date":
        return (v or {}).get("start")
    return v


def props_current(page, want):
    """True when every property we write already holds that value."""
    have = page.get("properties") or {}
    return all(plain(have.get(name)) == prop_text(value) for name, value in want.items())


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
    cfg = load_config()
    p = paths(cfg)
    tok = notion.token(cfg)
    cos = json.loads(p.companies_json.read_text(encoding="utf-8"))["companies"]
    jobs = json.loads(p.jobs_json.read_text(encoding="utf-8"))["jobs"]
    opps = {pg["id"]: pg for pg in query_all(tok, notion.source(cfg, "opportunities_data_source"))}
    pages = query_all(tok, notion.source(cfg, "companies_data_source"))
    linked = {}   # company page id -> role titles
    for pg in opps.values():
        for cid in plain(pg["properties"].get("Company")) or []:
            linked.setdefault(cid, []).append(plain(pg["properties"].get("Name")) or "")

    filled = thin = same = 0
    for pg in sorted(pages, key=lambda x: (plain(x["properties"].get("Name")) or "").lower()):
        name = plain(pg["properties"].get("Name")) or ""
        if pg["id"] not in linked and not a.all:
            continue        # a company page from the owner's own diligence, not one of ours
        read = company_read(cos, name)
        where = offices(jobs, name)
        roles = [r.split(" · ")[0] for r in linked.get(pg["id"], [])]
        have = [k for k, v in props(read, where).items() if json.dumps(v) not in ('{"rich_text": []}', '{"url": null}')]
        print(f"{'fill  ' if read else 'thin  '}{name}: {', '.join(have) or 'nothing to add'}"
              f"{'  roles: ' + ', '.join(roles) if roles else ''}")
        if not read:
            thin += 1
            print(f"         no company read in companies.json{'  (location: ' + '; '.join(where) + ')' if where else ''}")
        if a.dry_run:
            continue
        want = body(read, where, roles)
        mine = own_blocks(tok, pg["id"])
        if block_text(mine) == block_text(want) and props_current(pg, props(read, where)):
            same += 1
            continue                                  # nothing changed: leave Notion alone (the build runs this daily)
        notion.call(tok, f"/pages/{pg['id']}", {"properties": props(read, where)}, "PATCH")
        for b in mine:
            notion.call(tok, f"/blocks/{b['id']}", method="DELETE")
        notion.call(tok, f"/blocks/{pg['id']}/children", {"children": want}, "PATCH")
        filled += 1
    print(f"\n{'would fill' if a.dry_run else 'filled'} {len(linked) if a.dry_run else filled} pages"
          f"{f', {same} already current' if same else ''}{f', {thin} with no company read yet' if thin else ''}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fill")
    f.add_argument("--dry-run", action="store_true")
    f.add_argument("--all", action="store_true", help="every Companies page, not only the ones an opportunity links to")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if a.cmd == "fill":
        fill(a)


if __name__ == "__main__":
    main()
