"""Org charts: a company's people, as its own website lists them, sorted into seniority tiers and departments.

    py engine/org_chart.py pep                fetch the team pages, write data/org/<slug>.json, print the chart
    py engine/org_chart.py pep --bios         also read each person's bio page (year joined, committees, one line)
    py engine/org_chart.py pep --show         print the chart from the saved file, flags included, no fetch
    py engine/org_chart.py push               push every saved chart, flagged against the vault, to board_meta org_charts
    py engine/org_chart.py list               the companies this knows how to read, and every saved chart with its status
    py engine/org_chart.py probe <url>        can this team page be read? static names and titles, filters, pager, JS shell
    py engine/org_chart.py import <roster.json> --company "<board company_key>" --slug <vault slug> --source <url>
                                              a roster extracted by the /org-chart skill from a site with no coded extractor
    py engine/org_chart.py preview <slug>     the draft page (tier list and team grid, flagged) in the vault at research/<slug>/org-chart.html
    py engine/org_chart.py approve <slug>     the owner's go: the chart may reach the board at the next push

Draft gate (2026-09-24): a chart saves as `status: draft` and `push` sends only approved charts, so nothing new reaches
the board until the owner has seen the preview and said so. A re-fetch keeps an approval already given.

Works for boutiques only, most likely: a firm that publishes its whole team with titles (most private equity, search
and advisory boutiques do; large companies publish a leadership page at most). Add a company by writing an extractor
that returns [{name, title, url, departments, offices}] and a SITES entry (below).

The roster file (data/org/<slug>.json) holds only what the company's own site says, with the source URLs and the
fetch date, so it can live in this repo. Who in it matters to the search is personal and never lands here: `push`
reads the vault at push time (research/<slug>/people.md, people/*.md, network/contacts.json, network/people.json)
and sends the flags to the board's Supabase only. push_board.py calls push_all after every build so the flags follow
the vault. Single writer of board_meta `org_charts`: this file.
"""
import argparse
import html
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import REPO  # noqa: E402

ORG_DIR = REPO / "data" / "org"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128 Safari/537.36"
PAUSE = 0.4  # seconds between requests: a small site, read politely

# ---------- seniority ----------

# Top to bottom. `lane` tiers render as their own rows: heads above the ladder, advisors below it.
TIERS = [
    ("chair", "Founder and Chairman"),
    ("heads", "C-suite and functional heads"),
    ("smd", "Senior Managing Director, Partner, Vice Chairman"),
    ("md", "Managing Director"),
    ("principal", "Director, Principal, SVP"),
    ("vp", "Vice President"),
    ("sr_assoc", "Senior Associate"),
    ("assoc", "Associate"),
    ("analyst", "Analyst"),
    ("staff", "Staff and support"),
    ("advisors", "Operating partners and senior advisors"),
]
TIER_RANK = {k: i for i, (k, _) in enumerate(TIERS)}

HEAD = re.compile(r"\b(chief\b|general counsel|head of|c[efiotm]o\b|cco\b|chro\b|treasurer)", re.I)
LADDER = [  # first match wins, so the longer phrase goes first
    ("chair", r"\b(founder|chairman|chairwoman|chair)\b(?!.*\bvice\b)"),
    ("advisors", r"\b(operating partner|senior advisor|advisor|adviser|executive in residence|operating executive)\b"),
    ("smd", r"\b(senior managing director|vice chairman|vice chair|managing partner|senior partner|general partner|partner)\b"),
    ("md", r"\bmanaging director\b|\bmd\b"),
    ("principal", r"\b(senior vice president|svp|principal|executive director|director)\b"),
    ("vp", r"\b(vice president|vp)\b"),
    ("sr_assoc", r"\bsenior associate\b"),
    ("assoc", r"\bassociate\b"),
    ("analyst", r"\banalyst\b"),
]


def tier_of(title):
    """(tier, is_head) from a title. A head (CIO, CTO, GC, CFO, Head of X) keeps its ladder tier too, so the page can
    show Dominguez as the CIO lane and still know he is a Senior Managing Director."""
    t = title or ""
    ladder = next((k for k, rx in LADDER if re.search(rx, t, re.I)), "staff")
    # "Chief of Staff" and "Associate General Counsel" are not heads
    head = bool(HEAD.search(t)) and not re.search(r"chief of staff|associate general counsel|deputy|assistant", t, re.I)
    if ladder == "chair" and re.search(r"vice chair", t, re.I):
        ladder = "smd"
    return ladder, head


# Department order when a person sits in several filters: the functional one wins over the umbrella ones.
UMBRELLA = ("Leadership", "Founder", "Senior Advisors")


def primary_department(depts):
    specific = [d for d in depts if d not in UMBRELLA]
    return (specific or list(depts) or ["Unlisted"])[0]


# ---------- fetching ----------

def get(url, tries=3):
    for i in range(tries):
        try:
            with urlopen(Request(url, headers={"User-Agent": UA, "Accept": "text/html"}), timeout=40) as r:
                return r.read().decode("utf-8", "replace")
        except HTTPError as e:
            if e.code == 404:
                return ""
            err = e
        except (URLError, TimeoutError) as e:
            err = e
        time.sleep(2 * (i + 1))
    raise SystemExit(f"could not fetch {url}: {err}")


def text(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


# ---------- extractors ----------

def drupal_options(page, name):
    """The option values of a Drupal views exposed-filter <select name=...> (the first one on the page)."""
    m = re.search(rf'<select[^>]*name="{name}"[^>]*>(.*?)</select>', page, re.S)
    vals = re.findall(r'<option[^>]*value="([^"]*)"', m.group(1)) if m else []
    return [html.unescape(v) for v in vals if v and v.lower() != "all"]


def drupal_cards(page):
    """Team-member teasers: <article about="/people/<slug>"> with the name in node__title and the title field."""
    out = []
    for m in re.finditer(r'<article[^>]*about="(/people/[a-z0-9-]+)"[^>]*>(.*?)</article>', page, re.S):
        path, body = m.group(1), m.group(2)
        name = text((re.search(r'node__title[^>]*>(.*?)</h\d>', body, re.S) or [None, ""])[1])
        if not name:
            name = text((re.search(r'visually-hidden[^>]*>(.*?)</span>\s*</span>', body, re.S) or [None, ""])[1])
        title = text((re.search(r'field--name-field-job-title[^>]*>(.*?)</div>', body, re.S) or [None, ""])[1])
        if not name:  # tolerate a card with no name markup: the slug is the name
            name = path.rsplit("/", 1)[-1].replace("-", " ").title()
        out.append({"path": path, "name": name, "title": title})
    return out


def drupal_sweep(base, params, seen_pages=40):
    """Every card behind one filter, page by page, until a page adds nobody."""
    found = {}
    for n in range(seen_pages):
        q = dict(params)
        if n:
            q["page"] = n
        page = get(f"{base}?{urlencode(q)}" if q else base)
        new = [c for c in drupal_cards(page) if c["path"] not in found]
        for c in new:
            found[c["path"]] = c
        time.sleep(PAUSE)
        if not new:
            break
    return found


def drupal_bio(url):
    page = get(url)
    time.sleep(PAUSE)
    if not page:
        return {}

    def field(name):
        m = re.search(rf'field--name-field-{name}\b.*?(?=<div class="field field--name|<div id="block-|</article>)', page, re.S)
        return [text(x) for x in re.findall(r'class="field__item"[^>]*>(.*?)</div>', m.group(0), re.S)] if m else []

    joined = field("year-joined")
    teaser = text((re.search(r'field--name-field-teaser-text[^>]*>(.*?)</div>', page, re.S) or [None, ""])[1])
    titles = text((re.search(r'class="node__job-titles"[^>]*>(.*?)</div>', page, re.S) or [None, ""])[1])
    return {k: v for k, v in {
        "joined": joined[0] if joined else "",
        "committees": field("committees"),
        "bio_offices": field("location"),
        "summary": teaser[:400],
        "bio_title": titles,
    }.items() if v}


def extract_pep(site, bios=False):
    """Example Partners: a Drupal view at /people with Team and Location filters and a pager. The unfiltered
    sweep is the roster; one sweep per Team value gives departments, one per Location value gives offices."""
    base = site["urls"][0]
    first = get(base)
    teams, offices = drupal_options(first, "team"), drupal_options(first, "location")
    roster = drupal_sweep(base, {})
    depts, locs = {}, {}
    for t in teams:
        for path in drupal_sweep(base, {"team": t}):
            depts.setdefault(path, []).append(t)
    for o in offices:
        for path in drupal_sweep(base, {"location": o}):
            locs.setdefault(path, []).append(o)
    for path in set(depts) | set(locs):  # someone reachable only through a filter still counts
        roster.setdefault(path, {"path": path, "name": path.rsplit("/", 1)[-1].replace("-", " ").title(), "title": ""})
    people = []
    for path, c in roster.items():
        url = urljoin(base, path)
        p = {"name": c["name"], "title": c["title"], "url": url,
             "departments": depts.get(path, []), "offices": locs.get(path, [])}
        if bios:
            b = drupal_bio(url)
            if len(b.get("bio_title", "")) > len(p["title"]):  # the listing can carry only the first of two titles
                p["title"] = b["bio_title"]
            b.pop("bio_title", None)
            if b.get("bio_offices") and not p["offices"]:
                p["offices"] = b["bio_offices"]
            b.pop("bio_offices", None)
            p.update(b)
        people.append(p)
    return people, {"departments": teams, "offices": offices}


SITES = {
    "pep": {
        "key": "Example Partners",  # the board's company_key, so the page finds the chart
        "slug": "example-partners",  # the vault's research/<slug>/ folder and the file name here
        "urls": ["https://www.provequity.com/people"],
        "extract": extract_pep,
    },
}


def site_for(arg, saved_ok=False):
    """A coded site, or (saved_ok) a chart saved by `import`, which has no extractor and can only be shown, previewed,
    approved and pushed. Re-running an import is how an imported chart refreshes."""
    a = arg.lower()
    for k, s in SITES.items():
        if a in (k, s["slug"], s["key"].lower()):
            return k, s
    if saved_ok:
        for f in sorted(ORG_DIR.glob("*.json")):
            ch = json.loads(f.read_text(encoding="utf-8"))
            if a in (ch["slug"], ch["company"].lower()):
                return ch["slug"], {"key": ch["company"], "slug": ch["slug"], "urls": ch["sources"], "extract": None}
    raise SystemExit(f"no extractor or saved chart for {arg!r}; coded: {', '.join(SITES)}")


def saved_sites():
    """Every chart in data/org/, as a site dict, coded or imported."""
    out = []
    for f in sorted(ORG_DIR.glob("*.json")):
        ch = json.loads(f.read_text(encoding="utf-8"))
        out.append({"key": ch["company"], "slug": ch["slug"], "urls": ch["sources"]})
    return out


# ---------- the chart ----------

def build_chart(site, people, filters):
    for p in people:
        p["tier"], p["head"] = tier_of(p["title"])
        p["department"] = primary_department(p["departments"])
        p["office"] = (p["offices"] or [""])[0]
    people.sort(key=lambda p: (TIER_RANK[p["tier"]], p["department"], p["name"].split()[-1], p["name"]))
    prev = load_chart(site) or {}
    return {
        "company": site["key"],
        "slug": site["slug"],
        "sources": site["urls"],
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": prev.get("status", "draft"),  # a refresh keeps an approval already given
        "approved_at": prev.get("approved_at"),
        "filters": filters,
        "tiers": [{"key": k, "label": l} for k, l in TIERS],
        "count": len(people),
        "people": people,
    }


def import_roster(path, company, slug, sources):
    """A roster the /org-chart skill extracted: a JSON list of {name, title, url?, departments?, offices?, joined?,
    summary?}. Checked here so a bad extraction fails loudly instead of landing as a thin chart."""
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(rows, dict):
        rows = rows.get("people") or []
    people, seen = [], set()
    for r in rows:
        name = text(r.get("name", ""))
        if len(name.split()) < 2 or name.lower() in seen:
            continue
        seen.add(name.lower())
        p = {"name": name, "title": text(r.get("title", "")), "url": r.get("url") or "",
             "departments": [text(d) for d in r.get("departments") or [] if text(d)],
             "offices": [text(o) for o in r.get("offices") or [] if text(o)]}
        for k in ("joined", "summary"):
            if r.get(k):
                p[k] = text(str(r[k]))
        people.append(p)
    if len(people) < 5:
        raise SystemExit(f"{path}: {len(people)} usable people; not a roster worth charting. Nothing written")
    untitled = sum(1 for p in people if not p["title"])
    if untitled > len(people) / 2:
        raise SystemExit(f"{path}: {untitled} of {len(people)} have no title, so no tiers can be inferred. Nothing written")
    site = {"key": company, "slug": slug, "urls": sources}
    filters = {"departments": sorted({d for p in people for d in p["departments"]}),
               "offices": sorted({o for p in people for o in p["offices"]})}
    return site, build_chart(site, people, filters)


def out_path(site):
    return ORG_DIR / f"{site['slug']}.json"


def load_chart(site):
    f = out_path(site)
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


# ---------- flags from the vault (never written to the repo) ----------

NICK = {"mike": "michael", "mick": "michael", "bob": "robert", "rob": "robert", "bill": "william", "will": "william",
        "jim": "james", "jimmy": "james", "tom": "thomas", "dave": "david", "dan": "daniel", "chris": "christopher",
        "matt": "matthew", "kate": "katherine", "katie": "katherine", "liz": "elizabeth", "beth": "elizabeth",
        "jon": "jonathan", "nick": "nicholas", "rick": "richard", "rich": "richard", "steve": "stephen",
        "tony": "anthony", "andy": "andrew", "drew": "andrew", "alex": "alexander", "sam": "samuel", "ben": "benjamin",
        "joe": "joseph", "greg": "gregory", "jeff": "jeffrey", "pat": "patrick", "kenny": "kenneth", "ken": "kenneth"}


def name_key(name):
    """(first, last) normalised: parentheses and initials dropped, nicknames folded."""
    n = re.sub(r"\(.*?\)", " ", html.unescape(name or "")).lower()
    n = re.sub(r"\b(jr|sr|ii|iii|iv)\b\.?", " ", n)
    toks = [t for t in re.findall(r"[a-z][a-z'\-]*", n) if len(t) > 1]
    if not toks:
        return None
    first, last = toks[0], toks[-1]
    return NICK.get(first, first), last


def same_person(a, b):
    ka, kb = name_key(a), name_key(b)
    if not ka or not kb or ka[1] != kb[1]:
        return False
    return ka[0] == kb[0] or ka[0].startswith(kb[0]) or kb[0].startswith(ka[0])


def vault_marks(cfg, site):
    """[(name, kind, line, ref)] for one company, read-only from the vault. kinds: process (the research table's
    'Role in the process'), profiled (a profile in research people.md), vault (a people/*.md page), network
    (a Notion Network contact), linkedin (a first-degree connection)."""
    vault = Path(cfg["vault"])
    marks = []
    rp = vault / "research" / site["slug"] / "people.md"
    ref = f"research/{site['slug']}/people"
    if rp.exists():
        md = rp.read_text(encoding="utf-8")
        head = None
        for line in md.splitlines():
            if not line.startswith("|"):
                head = None
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if cells[0].lower() == "name":
                head = [c.lower() for c in cells]
            elif head and "role in the process" in head and not set(cells[0]) <= set("-: "):
                row = dict(zip(head, cells))
                for nm in re.split(r",\s*| and ", row.get("name", "")):
                    if nm.strip():
                        marks.append((nm.strip(), "process", row.get("role in the process", ""), ref))
        for m in re.finditer(r"^###\s+(.+)$", md, re.M):
            for nm in re.split(r",\s*| and ", re.sub(r"\(.*?\)", "", m.group(1))):
                if len(nm.split()) >= 2:
                    marks.append((nm.strip(), "profiled", "", ref))
    key_rx = re.compile(re.escape(site["key"]) + "|" + re.escape(site["slug"]), re.I)
    for f in sorted((vault / "people").glob("*.md")):
        t = f.read_text(encoding="utf-8")
        comp = re.search(r"^\*\*Company:\*\*(.*)$", t, re.M)
        if not comp or not key_rx.search(comp.group(1)):
            continue
        nm = (re.search(r"^#\s+(.+)$", t, re.M) or [None, f.stem.replace("-", " ")])[1]
        st = (re.search(r"^\*\*Status:\*\*\s*(.*)$", t, re.M) or [None, ""])[1]
        role = (re.search(r"\((.*)\)", st) or [None, st])[1]
        marks.append((nm, "vault", role.strip(), f"people/{f.stem}"))
    try:
        contacts = json.loads((vault / "network" / "contacts.json").read_text(encoding="utf-8")).get("people") or []
    except (OSError, ValueError):
        contacts = []
    for c in contacts:
        if key_rx.search(c.get("company") or ""):
            line = " · ".join(x for x in (c.get("status"), c.get("how")) if x)
            marks.append((c.get("name") or "", "network", line, "Notion Network"))
    try:
        first = (json.loads((vault / "network" / "people.json").read_text(encoding="utf-8")).get(site["key"]) or {}).get("first") or []
    except (OSError, ValueError, AttributeError):
        first = []
    for c in first:
        marks.append((c.get("name") or "", "linkedin", f"1st-degree LinkedIn since {c.get('since')}" if c.get("since") else "1st-degree LinkedIn", "network/people.json"))
    return marks


KIND_ORDER = ("process", "vault", "network", "linkedin", "profiled")


def flag_chart(chart, marks):
    """The chart plus a `flag` on each person the vault or the network knows: {kinds, line, refs}. The line is the
    research table's role in the process when there is one, else the people page's status, else the network's."""
    matched = set()
    for p in chart["people"]:
        hits = [m for m in marks if same_person(p["name"], m[0])]
        if not hits:
            continue
        matched.update(m[0] for m in hits)
        hits.sort(key=lambda m: KIND_ORDER.index(m[1]))
        kinds = sorted({m[1] for m in hits}, key=KIND_ORDER.index)
        line = next((m[2] for m in hits if m[2]), "")
        p["flag"] = {"kinds": kinds, "line": line, "refs": sorted({m[3] for m in hits})}
    chart["flagged"] = sum(1 for p in chart["people"] if p.get("flag"))
    # people the vault names who are not on the site: worth knowing (left, or never listed)
    chart["not_on_site"] = sorted({m[0] for m in marks if m[1] in ("process", "vault", "network", "linkedin")
                                   and m[0] not in matched and not any(same_person(m[0], p["name"]) for p in chart["people"])})
    return chart


def push_all(cfg):
    """Every saved chart, flagged, into board_meta `org_charts` keyed by company_key. Returns a one-line report."""
    import supabase as sb
    charts, held = {}, []
    for site in saved_sites():
        ch = load_chart(site)
        if not ch:
            continue
        if ch.get("status") != "approved":  # the draft gate: the owner has not seen and passed this chart
            held.append(site["slug"])
            continue
        charts[site["key"]] = flag_chart(ch, vault_marks(cfg, site))
    tail = f"; held as drafts: {', '.join(held)}" if held else ""
    if not charts:
        return "org charts: none approved" + tail
    built = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    sb.upsert("board_meta", [{"key": "org_charts", "payload": charts, "updated_at": built}], cfg=cfg)
    return "org charts: " + ", ".join(f"{k} {c['count']} people, {c['flagged']} flagged" for k, c in charts.items()) + tail


def approve(site):
    ch = load_chart(site)
    if not ch:
        raise SystemExit(f"no saved chart for {site['slug']}")
    ch["status"], ch["approved_at"] = "approved", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out_path(site).write_text(json.dumps(ch, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return f"{site['slug']} approved; it reaches the board at the next push (py engine/org_chart.py push, or the next build)"


PREVIEW = Path(__file__).resolve().parent / "org_preview.html"


def preview(cfg, site, out=None):
    """The draft page: the chart flagged against the vault, in the board's two layouts (tier list, team grid), written into the vault (it carries the
    flags, so never into this repo). The /org-chart skill publishes it as a private page for the owner to review."""
    ch = load_chart(site)
    if not ch:
        raise SystemExit(f"no saved chart for {site['slug']}")
    ch = flag_chart(ch, vault_marks(cfg, site)) if cfg else ch
    data = json.dumps(ch, ensure_ascii=False).replace("</", "<\\/")
    page = (PREVIEW.read_text(encoding="utf-8").replace("__DATA__", data)
            .replace("__TITLE__", html.escape(f"{ch['company']} Org Chart"))
            .replace("__COMPANY__", html.escape(ch["company"])))
    out = Path(out) if out else Path(cfg["vault"]) / "research" / site["slug"] / "org-chart.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    return out, ch


# ---------- probe: can this team page be read? ----------

TITLE_WORDS = re.compile(r"\b(partner|managing director|principal|vice president|associate|analyst|director|chief|head of|"
                         r"counsel|advisor|operating partner|founder|chairman|president|manager|officer|controller|"
                         r"engineer|assistant|senior)\b", re.I)


def probe(url):
    """Facts for the skill's feasibility call, not the call itself: what the raw HTML holds before any JavaScript."""
    page = get(url)
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", page, flags=re.S | re.I)
    visible = text(body)
    links = set(re.findall(r'href="([^"#?]*/(?:people|team|our-team|professionals|bio|bios|leadership)/[^"#?]+)"', page, re.I))
    heads = [text(h) for h in re.findall(r"<h[2-5][^>]*>(.*?)</h[2-5]>", page, re.S | re.I)]
    namey = [h for h in heads if 2 <= len(h.split()) <= 4 and all(w[:1].isupper() for w in h.split())]
    selects = re.findall(r'<select[^>]*name="([^"]+)"', page, re.I)
    facts = {
        "url": url,
        "bytes": len(page),
        "visible_chars": len(visible),
        "scripts": len(re.findall(r"<script", page, re.I)),
        "person_links": len(links),
        "name_like_headings": len(namey),
        "title_words": len(TITLE_WORDS.findall(visible)),
        "filters": selects,
        "pager": bool(re.search(r"[?&]page=\d|rel=\"next\"|class=\"[^\"]*pager", page, re.I)),
        "load_more": bool(re.search(r"load more|show more|view all", visible, re.I)),
        "next_data": "__NEXT_DATA__" in page,
        "json_ld_person": '"@type":"Person"' in page.replace(" ", ""),
        "platform": next((p for p, rx in (("drupal", r"drupal"), ("wordpress", r"wp-content|wp-json"), ("squarespace", r"squarespace"),
                                           ("webflow", r"webflow"), ("wix", r"wix\.com"), ("hubspot", r"hs-scripts|hubspot"))
                          if re.search(rx, page, re.I)), "unknown"),
        "sample_names": namey[:8],
        "sample_links": sorted(links)[:5],
    }
    facts["js_shell"] = facts["visible_chars"] < 1500 and facts["scripts"] > 5
    return facts


# ---------- CLI ----------

def show(chart):
    label = dict(TIERS)
    print(f"{chart['company']}: {chart['count']} people, fetched {chart['fetched_at']} from {', '.join(chart['sources'])}")
    rows = {}
    for p in chart["people"]:
        rows.setdefault("heads" if p["head"] else p["tier"], {}).setdefault(p["department"], []).append(p)
    for k, _ in TIERS:
        if k not in rows:
            continue
        print(f"\n{label[k]} ({sum(len(v) for v in rows[k].values())})")
        for d, ps in sorted(rows[k].items()):
            names = ", ".join(p["name"] + (" *" if p.get("flag") else "") for p in ps)
            print(f"  {d}: {names}")
    fl = [p for p in chart["people"] if p.get("flag")]
    if fl:
        print(f"\nFlagged ({len(fl)}):")
        for p in fl:
            print(f"  {p['name']} ({p['title']}; {', '.join(p['flag']['kinds'])}): {p['flag']['line']}")
    if chart.get("not_on_site"):
        print(f"\nIn the vault or network but not on the site: {', '.join(chart['not_on_site'])}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("command", help="a SITES key (pep) or saved slug, or push, list, probe, import, preview, approve")
    ap.add_argument("target", nargs="?", help="probe: the URL; import: the roster file; preview and approve: the slug")
    ap.add_argument("--bios", action="store_true", help="read each bio page too (year joined, committees, one line)")
    ap.add_argument("--show", action="store_true", help="print the saved chart with flags; no fetch")
    ap.add_argument("--company", help="import: the board's company_key, verbatim")
    ap.add_argument("--slug", help="import: the vault slug (research/<slug>/)")
    ap.add_argument("--source", action="append", default=[], help="import: the team page URL (repeatable)")
    ap.add_argument("--out", help="preview: write here instead of the vault")
    a = ap.parse_args()
    try:
        from common import load_config
        cfg = load_config()
    except SystemExit:
        cfg = None
    c = a.command
    if c == "list":
        for k, s in SITES.items():
            print(f"coded {k}: {s['key']} ({', '.join(s['urls'])})")
        for s in saved_sites():
            ch = load_chart(s)
            print(f"saved {s['slug']}: {ch['count']} people, {ch.get('status', 'draft')}, read {ch['fetched_at'][:10]}")
        return
    if c == "probe":
        if not a.target:
            raise SystemExit("probe needs a URL")
        print(json.dumps(probe(a.target), indent=1, ensure_ascii=False))
        return
    if c == "push":
        if not cfg:
            raise SystemExit("config.json missing: push needs the vault and Supabase")
        print(push_all(cfg))
        return
    if c == "import":
        if not (a.target and a.company and a.slug and a.source):
            raise SystemExit("import needs <roster.json> --company --slug --source")
        site, chart = import_roster(a.target, a.company, a.slug, a.source)
        ORG_DIR.mkdir(parents=True, exist_ok=True)
        out_path(site).write_text(json.dumps(chart, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {out_path(site).relative_to(REPO)} ({chart['status']})")
    elif c in ("preview", "approve"):
        if not a.target:
            raise SystemExit(f"{c} needs a slug")
        _, site = site_for(a.target, saved_ok=True)
        if c == "approve":
            print(approve(site))
            return
        if not cfg and not a.out:
            raise SystemExit("config.json missing: preview needs the vault (or --out)")
        out, ch = preview(cfg, site, a.out)
        print(f"wrote {out}: {ch['count']} people, {ch.get('flagged', 0)} flagged, status {ch.get('status', 'draft')}")
        return
    else:
        k, site = site_for(c, saved_ok=a.show)
        if a.show:
            chart = load_chart(site)
            if not chart:
                raise SystemExit(f"no saved chart at {out_path(site)}; run without --show first")
        else:
            people, filters = site["extract"](site, bios=a.bios)
            if not people:
                raise SystemExit(f"{site['key']}: the extractor found nobody; the site may have changed. Nothing written")
            chart = build_chart(site, people, filters)
            ORG_DIR.mkdir(parents=True, exist_ok=True)
            out_path(site).write_text(json.dumps(chart, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"wrote {out_path(site).relative_to(REPO)} ({chart['status']})")
    if cfg:
        chart = flag_chart(chart, vault_marks(cfg, site))
    show(chart)


if __name__ == "__main__":
    main()
