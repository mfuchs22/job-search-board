"""Startups: the Boston startup scene as its own screen on the board (the Startups tab, 2026-09-23).

    py engine/startups.py                 build the rows, geocode what is new, push `startups` and the summary
    py engine/startups.py --dry-run       build and report, push nothing (geocache still fills)
    py engine/startups.py --no-geocode    skip the geocoder (cache only)
    py engine/startups.py --show          print the tier counts and the top of the screen
    py engine/startups.py --unlabeled     list what lenses.json is missing: companies with no vertical and theme, and
                                          kept ones (Interesting or Watch) in no thesis or with no look-again trigger;
                                          the Monday mgmt-watch labels these before it pushes

Sources, all in the vault (config.json `vault`):
  research/boston-startups/mgmt-board.json   MGMT Boston's Big Board as data, exported by Personal-OS Tools/mgmt_watch.py
                                             every Monday (stage, sector tag, one-liner, HQ, street address, headcount,
                                             latest round, investors, open-role count, careers link)
  research/boston-startups/companies.md      the research tables: per company, what they do, why it fits, the open roles
                                             that match the archetype, the path in, and the board or vault link. Rows are
                                             matched to MGMT companies by name (aliases below cover the spellings)
  jobs/jobs.json                             board rows at the same company (title, score, verdict)
  network/people.json                        first-degree connections per company
  companies/<slug>.md                        whether a vault card exists
  research/boston-startups/lenses.json       Claude's sorting (2026-09-24): vertical (who buys) and theme (what it does)
                                             per company, the theses that group the kept ones, and each kept one's
                                             look-again trigger; theses ride on the summary as `theses`

Writes: Supabase `startups` (one row per company, payload = the card) and `board_meta` key `startups_summary`.
The page writes `startup_verdicts` (Interesting / Watch / Pass, flag, note); nothing here reads them, the page
overlays them. Coordinates come from engine/office.py's geocoder and its shared cache (jobs/geocache.json), so
an address is looked up once across jobs and startups.

Screen pre-score (v2, 2026-09-23, after the owner's first batch of 31 calls; 0 to 15, deterministic, the math is on the
card): a first sort so the list opens in a useful order. It is not the rubric and it is not a verdict; the owner's call on
the page is the screen. v1 leaned on "a seat is posted" and "already on the board", and neither predicted a call
(twenty of his 23 Passes had a seat posted); his three stated criteria all point at the company, so v2 does too:
funding velocity, investor quality, founder pedigree, then his sector lens, where the seat would sit, age, and small
credits for the AI tag, growth stage, team size, a written fit, a path in, a seat posted. Tiers: 9+ look, 5 to 8 watch.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

from common import load_config, paths, load_jobs, same_company, slug
from office import Geocoder, geo_query, city_of
import supabase as sb

BOSTON = {"boston", "cambridge", "somerville", "waltham", "watertown", "needham", "burlington", "lexington", "brookline",
          "newton", "woburn", "medford", "charlestown", "quincy", "dedham", "bedford", "wellesley", "canton", "beverly",
          "south deerfield", "framingham", "natick", "andover", "billerica", "wilmington", "marlborough", "westborough",
          "shrewsbury", "amesbury", "boston (seaport)", "boston, ma"}
ALIAS = {  # MGMT name -> the name the research tables use (lowercase, base before any parenthetical)
    "systalize": "systalyze", "markit social": "markit ai", "nethopper": "nethopper", "via science": "via", "tori": "tori",
    "ray": "ray", "clockwork": "clockwork", "ekos": "ekos", "tulip": "tulip interfaces", "cmt.ai": "cambridge mobile telematics",
    "merlin": "merlin labs", "commonwealth fusion": "commonwealth fusion systems", "basys": "basys.ai",
    "the boston agents company": "boston agents company", "fairmarkit": "fairmarkit", "daylit": "daylit", "laminar": "laminar",
    "all spice": "allspice.io", "flexcompute": "flexcompute", "subconscious": "subconscious", "openhands": "openhands",
    "consensus": "consensus", "quotient ai": "quotient ai", "eliza": "eliza", "protex ai": "protex ai",
}
TOP_TIER = ["sequoia", "andreessen", "a16z", "accel", "index ventures", "greylock", "benchmark", "lightspeed", "founders fund",
            "general catalyst", "khosla", "bessemer", "insight partners", "ivp", "thrive capital", "capitalg", "gv", "google ventures",
            "coatue", "spark capital", "crv", "battery ventures", "new enterprise associates", "nea", "union square ventures",
            "felicis", "flagship pioneering", "kleiner", "tiger global", "redpoint", "menlo ventures", "y combinator", "salesforce ventures",
            "nvidia", "nventures", "advent", "cppib", "temasek", "softbank", "goldman sachs", "morgan stanley", "amd ventures"]
BOSTON_TIER = ["pillar vc", "glasswing", "flybridge", "underscore", "hyperplane", "boston seed", "york ie", "e14", "link ventures",
               "accomplice", "founder collective", "nextview", "polaris", "volition", "openview", "mit", "the engine"]
OPERATORS = ["hubspot", "klaviyo", "drift", "toast", "wayfair", "draftkings", "amazon", "google", "meta", "facebook", "openai",
             "anthropic", "stripe", "datadog", "salesforce", "microsoft", "apple", "nvidia", "palantir", "tripadvisor", "carbon black",
             "rapid7", "desktop metal", "commonwealth fusion", "cursor", "databricks", "snowflake", "solidworks", "harvard", "mit"]
PEDIGREE = re.compile(r"\b(ex-|former |founded by|founders? (are|is|include)|spinout|spin-out|co-?founder|serial founder|repeat founder|professor)", re.I)
SECURITY = re.compile(r"\b(security|cyber|fraud|impersonation|phishing|threat|pentest|soc\b|siem|zero-trust|vulnerab|deepfake)", re.I)
MEDTECH = re.compile(r"\b(medical device|medtech|clinical|regulated medtech|prior auth|health plan|payer|payor|revenue cycle|dme\b|hme\b|clinic)", re.I)
NICHE = re.compile(r"\b(accounts payable|invoice|fundrais|nonprofit|philanthrop|loan-linked|gift agreement|earned wage|returns analytics|tire)", re.I)
HORIZONTAL = re.compile(r"\b(crm|sales platform|workflow|agents? for|agentic|enterprise ai|copilot|deployment platform|context layer|orchestrat|automation platform|ai-native (crm|platform|consulting))", re.I)
COMMUTE_MINUS = {"somerville", "waltham", "watertown", "burlington", "lexington", "woburn", "needham", "bedford", "medford", "brookline",
                 "newton", "wellesley", "framingham", "natick", "andover", "billerica", "wilmington", "marlborough", "westborough",
                 "shrewsbury", "south deerfield", "beverly", "amesbury", "canton", "dedham", "quincy"}
BUSINESS_ELSEWHERE = re.compile(r"business (roles|seats) (are |sit )?(nyc|new york|sf|san francisco|remote|elsewhere|in [a-z ]+)|(nyc|sf)[ -]only|are (sf|nyc)|is nyc|san mateo|mountain view", re.I)
SEAT = re.compile(r"forward deployed|chief of staff|strategy|implementation|solutions? (engineer|architect|consultant|delivery)|deployment|product manager|engagement manager|program manager|customer success|value consultant|automation strategist|delivery and success|operations (manager|lead)|head of|director", re.I)
NO_SEAT = re.compile(r"none on archetype|nothing on archetype|^0 open|^0 posted|^0 found|^none\b|no roles|not checked|none visible|none found|none;", re.I)


def base_name(s):
    return re.sub(r"\s*\(.*?\)\s*", " ", s or "").strip().lower()


def parse_research(md_path: Path):
    """Every 8-cell table row in companies.md, keyed by the base name, plus the left-out rows (2 cells)."""
    rows, left = {}, {}
    if not md_path.exists():
        return rows, left
    for line in md_path.read_text(encoding="utf-8").splitlines():
        t = line.strip()
        if not t.startswith("|") or t.startswith("|---") or t.startswith("| Company |"):
            continue
        cells = [c.strip() for c in t.strip("|").split("|")]  # empty cells stay as "" (a spaced split would collapse them)
        if len(cells) == 8:
            name = cells[0]
            rec = {"name": name, "stage_text": cells[1], "what": cells[2], "sector": cells[3], "fit": cells[4],
                   "roles": cells[5], "path": cells[6], "board": cells[7]}
            rows.setdefault(base_name(name), rec)
            for alt in re.findall(r"\((.*?)\)", name):  # "TORI (OpenCity)", "Daylit (fka Lendica)"
                for tok in re.split(r"\bfka\b|\bnow\b|also listed by MGMT as|,|;", alt):
                    tok = tok.strip().lower()
                    if 2 < len(tok) < 40 and tok not in ("boston roles only", "mgmt spells it systalize"):
                        rows.setdefault(tok, rec)
        elif len(cells) == 2 and cells[0].lower() not in ("company",):
            left.setdefault(base_name(cells[0]), cells[1])
    return rows, left


def find_research(name, rows, left):
    keys = [name.lower(), base_name(name), ALIAS.get(name.lower(), "")]
    for k in keys:
        if k and k in rows:
            return rows[k], None
    for k in keys:
        if k and k in left:
            return None, left[k]
    nk = re.sub(r"[^a-z0-9]", "", name.lower())
    for k, v in rows.items():
        if re.sub(r"[^a-z0-9]", "", k) == nk:
            return v, None
    return None, None


def board_rows(jobs, name):
    out = []
    for j in jobs:
        if j.get("company") and same_company(j["company"], name) and len(name) > 3:
            out.append({"id": j["id"], "title": j.get("title"), "score": j.get("score"), "verdict": j.get("verdict"),
                        "location": j.get("location"), "url": j.get("url")})
    return sorted(out, key=lambda r: -(r["score"] or 0))


def first_degree(people, name):
    for k, v in people.items():
        if same_company(k, name) and len(name) > 3:
            return [{"name": x.get("name"), "title": x.get("title")} for x in (v.get("first") or [])]
    return []


def months_since(iso):
    if not iso:
        return None
    try:
        d = date.fromisoformat(iso[:10])
    except ValueError:
        return None
    return (date.today().year - d.year) * 12 + date.today().month - d.month


def money(n):
    if not n:
        return ""
    n = float(n)
    return f"${n/1e9:.1f}B" if n >= 1e9 else f"${n/1e6:.0f}M"


def _has(text, names):
    t = (text or "").lower()
    return [n for n in names if n in t]


def screen(c, r, boston, seat, fd, onboard):
    """v2. Returns {score, tier, math}. `r` is the research row (or None), `c` MGMT's record with `facts`."""
    pts, why = 0, []
    f = c.get("facts") or {}
    research_text = " ".join((r or {}).get(k) or "" for k in ("stage_text", "what", "fit", "roles", "sector"))
    # the sector lens reads what the company does, never its job titles (a "Customer Success, Cyber" posting is not a security company)
    blurb = " ".join([c.get("one_liner") or "", c.get("primary_industry") or "", (r or {}).get("what") or "", (r or {}).get("sector") or ""])
    # 1. funding velocity (up to 4, stale -2)
    m = months_since(f.get("latest_round_date"))
    if m is not None and m <= 18:
        pts += 2; why.append("round in the last 18 months +2")
    elif m is not None and m > 36:
        pts -= 2; why.append(f"last round {m // 12} years ago -2")
    rounds = f.get("round_count") or 0
    founded = c.get("founded_year")
    if rounds >= 2 and (founded or 0) >= 2022:
        pts += 1; why.append("two rounds since 2022 +1")
    raised = f.get("total_raised_usd") or 0
    years = max(1, date.today().year - founded) if founded else None
    if years and raised / years >= 50e6:
        pts += 1; why.append(f"{money(raised)} over {years} years +1")
    # 2. investors (up to 2)
    inv = [i.get("name") or "" for i in (f.get("investors") or [])]
    inv_text = " ".join(inv + [(r or {}).get("stage_text") or ""])
    top = _has(inv_text, TOP_TIER)
    if top:
        pts += 2; why.append("top-tier investor (" + top[0] + ") +2")
    elif _has(inv_text, BOSTON_TIER):
        pts += 1; why.append("known Boston investor +1")
    # 3. founder pedigree (up to 2)
    if PEDIGREE.search(research_text) and _has(research_text, OPERATORS):
        pts += 2; why.append("founders from a known operator or an MIT/Harvard spinout +2")
    elif PEDIGREE.search(research_text):
        pts += 1; why.append("founder story on the row +1")
    # 4. the owner's sector lens
    if SECURITY.search(blurb):
        pts -= 2; why.append("security or fraud -2")
    elif MEDTECH.search(blurb):
        pts -= 1; why.append("medtech or clinical -1")
    elif NICHE.search(blurb):
        pts -= 1; why.append("narrow back-office niche -1")
    if HORIZONTAL.search(blurb) and not SECURITY.search(blurb):
        pts += 1; why.append("AI-native business software +1")
    # 5. where the seat sits
    hq = (c.get("hq_city") or "").lower()
    roles = (r or {}).get("roles") or ""
    if hq in COMMUTE_MINUS:
        pts -= 1; why.append(f"{c.get('hq_city')} commute -1")
    elif boston and not BUSINESS_ELSEWHERE.search(roles):
        pts += 1; why.append("Boston or Cambridge, business seats here +1")
    elif boston:
        why.append("Boston HQ but business seats elsewhere 0")
    # 6. age
    if founded and founded < 2016 and not (m is not None and m <= 18):
        pts -= 1; why.append(f"founded {founded}, no recent round -1")
    # 7. small credits
    if c.get("tag") == "AI":
        pts += 1; why.append("AI tag +1")
    if c.get("stage") == "growth":
        pts += 1; why.append("growth +1")
    n = f.get("employee_count_display") or c.get("employee_count")
    try:
        n = int(str(n).replace(",", "").split("-")[0].strip("+ ")) if n else None
    except ValueError:
        n = None
    if n and 15 <= n <= 400:
        pts += 1; why.append(f"{n} people +1")
    if r and r.get("fit"):
        pts += 1; why.append("fit written +1")
    if (r and r.get("path")) or fd:
        pts += 1; why.append("path in +1")
    if seat:
        pts += 1; why.append("seat posted +1")
    pts = max(0, min(pts, 15))
    tier = "look" if pts >= 9 else "watch" if pts >= 5 else "skip"
    return {"score": pts, "tier": tier, "math": "; ".join(why) or "nothing to go on", "version": 2}


def address_of(c):
    parts = [c.get("street_address"), c.get("hq_city"), " ".join(x for x in (c.get("state"), (c.get("postal_code") or "")[:5]) if x)]
    parts = [p.strip() for p in parts if p and p.strip()]
    if c.get("street_address"):
        return ", ".join(parts), "street"
    if c.get("hq_city"):
        return f"{c['hq_city']}, {c.get('state') or 'MA'}", "city"
    return "", "unknown"


def load_lenses(p):
    f = p.vault / "research" / "boston-startups" / "lenses.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


DILIGENCE_FILES = (("brief", "Brief"), ("dossier", "Dossier"), ("people", "People"), ("connections", "Connections"), ("sources", "Sources"))
# Section keys (2026-09-25, the Watchlist profile layouts): every /diligence file splits on its H2s into keyed sections,
# so the page can compose one profile from the pieces instead of pasting five documents. First keyword match wins.
SECTION_KEYS = {
    "dossier": [("gate", "gate read"), ("snapshot", "snapshot"), ("ownership", "ownership"), ("size", "size and trajectory"),
                ("what", "what they do"), ("portfolio", "portfolio"), ("failures", "failures"), ("operate", "how they operate"),
                ("hiring", "hiring"), ("culture", "culture"), ("news", "news timeline"), ("market", "market position"),
                ("signal", "signal in the last"), ("seat", "what this means"), ("questions", "open questions"), ("flags", "flags"),
                ("changelog", "change log")],
    "brief": [("five", "five lines"), ("sponsor", "seat and the sponsor"), ("say", "what to say"), ("ask", "what to ask"),
              ("avoid", "what to avoid"), ("unknown", "still does not know"), ("gate", "gate read"), ("paths", "paths in"), ("files", "files")],
    "people": [("who", "who matters"), ("profiles", "profiles"), ("org", "org shape"), ("trajectory", "trajectory"), ("alumni", "alumni"), ("gaps", "gaps")],
    "connections": [("summary", "summary"), ("first", "1st degree"), ("second", "2nd degree"), ("alumni", "alumni"), ("recruiter", "recruiter"),
                    ("sequence", "suggested sequence"), ("linkedin", "linkedin pass"), ("vault", "vault"), ("gaps", "gaps")],
}


def _md_html(txt):
    from render_dashboard import _md, _linkify
    txt = re.sub(r"\[\[([^\]]+)\]\]", lambda m: m.group(1).split("|")[-1].split("/")[-1].replace("-", " ") if "|" not in m.group(1) else m.group(1).split("|")[-1], txt)
    return _linkify(_md.markdown(txt, extensions=["tables"])) if _md else "<p>" + txt + "</p>"


def split_sections(kind, txt):
    """{key: {"t": heading, "html": ..., "items": [{"label", "html"}] for bulleted **Label:** lists}} plus "_order"."""
    parts = re.split(r"^## +(.+)$", txt, flags=re.M)
    out, order = {}, []
    for i in range(1, len(parts), 2):
        head, body = parts[i].strip(), parts[i + 1].strip()
        low = head.lower()
        key = next((k for k, kw in SECTION_KEYS.get(kind, []) if kw in low), re.sub(r"[^a-z0-9]+", "-", low).strip("-")[:30])
        if key in out:
            key = f"{key}-{i}"
        title = re.sub(r"^\d+[a-z]?\.\s*", "", re.sub(r"\s*\((?:quick pass|researched)[^)]*\)", "", head)).strip()
        sec = {"t": title, "html": _md_html(body)}
        items = re.findall(r"^- \*\*([^*]+?):?\*\*:?\s*(.+?)(?=^- \*\*|\Z)", body, flags=re.M | re.S)
        if len(items) >= 2:
            sec["items"] = [{"label": l.strip().rstrip(":"), "html": _md_html(b.strip())} for l, b in items]
        out[key] = sec
        order.append(key)
    out["_order"] = order
    return out


def profile_extras(p, c):
    """The Watchlist profile: the vault company card and any /diligence folder, split into keyed sections. Only for
    companies with a card or a research folder, so the payload of the other 300-odd stays small."""
    from render_dashboard import render_job_md
    out = {}
    card = f"companies/{slug(c['name'])}"
    if (p.vault / f"{card}.md").exists():
        out["card_html"] = render_job_md(p.vault, card)
    for sl in dict.fromkeys([slug(c["name"]), c["slug"]]):
        d = p.vault / "research" / sl
        if d.is_dir() and (d / "dossier.md").exists():
            secs = {k: split_sections(k, (d / f"{k}.md").read_text(encoding="utf-8")) for k, _ in DILIGENCE_FILES if (d / f"{k}.md").exists()}
            head = (d / "dossier.md").read_text(encoding="utf-8")[:600] + ((d / "brief.md").read_text(encoding="utf-8")[:600] if (d / "brief.md").exists() else "")
            m = re.search(r"(20\d\d-\d\d-\d\d)", head)
            out["diligence"] = {"folder": f"research/{sl}", "date": m.group(1) if m else None,
                                "mode": "quick" if re.search(r"quick", head, re.I) else "deep",
                                "files": [{"k": k, "l": l} for k, l in DILIGENCE_FILES if k in secs], "s": secs}
            if (d / "facts.json").exists():
                out["diligence"]["facts"] = json.loads((d / "facts.json").read_text(encoding="utf-8"))
            break
    return out


def build(cfg, p, geocode=True):
    research_dir = p.vault / "research" / "boston-startups"
    lenses = load_lenses(p); lab = lenses.get("companies") or {}; look = lenses.get("look_again") or {}
    board = json.loads((research_dir / "mgmt-board.json").read_text(encoding="utf-8"))
    rows, left = parse_research(research_dir / "companies.md")
    jobs = load_jobs(p)["jobs"]
    people = json.loads(p.people_json.read_text(encoding="utf-8")) if p.people_json.exists() else {}
    g = Geocoder(p, network=geocode)
    out, unmatched = [], []
    for c in board["companies"]:
        r, left_reason = find_research(c["name"], rows, left)
        if not r and not left_reason:
            unmatched.append(c["name"])
        f = c.get("facts") or {}
        addr, precision = address_of(c)
        office = {"address": addr, "precision": precision, "lat": None, "lng": None}
        if addr:
            q = geo_query(addr)
            hit = g.lookup(q)
            fallback = False
            if not hit and precision == "street" and g.missed(q):
                city = city_of(q) or f"{c.get('hq_city')}, MA"
                hit = g.lookup(city); fallback = True
            if hit:
                office.update(lat=hit["lat"], lng=hit["lng"], fallback=fallback)
        boston = (c.get("hq_city") or "").lower() in BOSTON and not c.get("is_boston_office_expansion")
        roles = (r or {}).get("roles") or ""
        seat = bool(r) and bool(SEAT.search(roles)) and not NO_SEAT.search(roles)
        fd = first_degree(people, c["name"])
        onb = board_rows(jobs, c["name"])
        vault = p.companies_dir / f"{slug(c['name'])}.md"
        out.append({
            "id": c["slug"], "name": c["name"], "stage": c.get("stage"), "tag": c.get("tag"), "sector": c.get("sector"),
            "one_liner": c.get("one_liner"), "description": c.get("apollo_description"), "industry": c.get("primary_industry"),
            "hq": c.get("hq_city"), "boston_hq": boston, "expansion": c.get("is_boston_office_expansion"), "expansion_origin": c.get("expansion_origin"),
            "office": office, "people": f.get("employee_count_display") or c.get("employee_count"), "people_source": f.get("employee_count_source"),
            "pct_local": c.get("pct_local_employees"), "workplace": f.get("workplace_model") or c.get("workplace_model"),
            "founded": c.get("founded_year"), "round_type": f.get("latest_round_type"), "round_date": f.get("latest_round_date"),
            "raised": f.get("total_raised_usd"), "round_count": f.get("round_count"), "investors": [i.get("name") for i in (f.get("investors") or []) if i.get("name")],
            "open_roles": f.get("open_roles"), "careers": f.get("careers_url") or c.get("careers_url"), "website": c.get("website_url"),
            "linkedin": c.get("linkedin_url"), "mgmt": c.get("mgmt_boston_url"), "logo": c.get("logo_url"), "lantern": c.get("lantern_youtube_url"),
            "customers": f.get("key_local_customers") or c.get("key_local_customers"),
            "research": r, "left_out": left_reason, "first_degree": fd, "board_rows": onb,
            "vault_card": f"companies/{slug(c['name'])}" if vault.exists() else None,
            "screen": screen(c, r, boston, seat, fd, bool(onb)), "seat_posted": seat,
            "vertical": (lab.get(c["slug"]) or {}).get("vertical"), "theme": (lab.get(c["slug"]) or {}).get("theme"),
            "look_again": look.get(c["slug"]),
            **profile_extras(p, c),
        })
    g.save()
    return out, unmatched, g.calls, board.get("asof")


def summary(rows, asof, built):
    by = lambda k: {v: sum(1 for r in rows if (r.get(k) or "") == v) for v in sorted({r.get(k) or "" for r in rows})}
    return {"asof": asof, "built_at": built, "count": len(rows), "by_stage": by("stage"), "by_tag": by("tag"),
            "by_tier": by_tier(rows), "pinned": sum(1 for r in rows if r["office"].get("lat") is not None),
            "researched": sum(1 for r in rows if r.get("research")), "seats": sum(1 for r in rows if r.get("seat_posted")),
            "first_degree": sum(1 for r in rows if r.get("first_degree")), "on_board": sum(1 for r in rows if r.get("board_rows"))}


def by_tier(rows):
    return {t: sum(1 for r in rows if r["screen"]["tier"] == t) for t in ("look", "watch", "skip")}


def unlabeled(p, cfg):
    lenses = load_lenses(p); lab = lenses.get("companies") or {}; look = lenses.get("look_again") or {}
    placed = {m for t in lenses.get("theses") or [] for m in t.get("members") or []}
    board = json.loads((p.vault / "research" / "boston-startups" / "mgmt-board.json").read_text(encoding="utf-8"))
    cos = {c["slug"]: c for c in board["companies"]}
    kept = {v["id"]: v["v"] for v in sb.select("startup_verdicts", {"select": "id,v"}, cfg=cfg) if v.get("v") in ("Interesting", "Watch")}
    new = [c for sl, c in cos.items() if sl not in lab]
    loose = [sl for sl in kept if sl in cos and (sl not in placed or sl not in look)]
    print(f"unlabeled: {len(new)} companies with no vertical and theme; {len(loose)} kept ones missing a thesis or a look-again trigger")
    for c in new:
        print(f"  label  {c['slug']} | {c['name']} | {c.get('tag') or ''} | {(c.get('one_liner') or c.get('apollo_description') or '')[:140]}")
    for sl in loose:
        miss = [w for w, ok in (("thesis", sl in placed), ("look_again", sl in look)) if not ok]
        print(f"  keep   {sl} | {cos[sl]['name']} | {kept[sl]} | needs {', '.join(miss)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-geocode", action="store_true")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--unlabeled", action="store_true")
    a = ap.parse_args()
    cfg = load_config(); p = paths(cfg)
    if a.unlabeled:
        return unlabeled(p, cfg)
    rows, unmatched, calls, asof = build(cfg, p, geocode=not a.no_geocode)
    built = datetime.now(timezone.utc).isoformat()
    s = summary(rows, asof, built)
    s["theses"] = load_lenses(p).get("theses") or []
    print(f"startups: {s['count']} companies (MGMT {asof}); researched {s['researched']}, seats posted {s['seats']}, "
          f"first-degree {s['first_degree']}, on board {s['on_board']}, pinned {s['pinned']}, geocoder calls {calls}; "
          f"tiers look {s['by_tier']['look']} / watch {s['by_tier']['watch']} / skip {s['by_tier']['skip']}")
    if unmatched:
        print(f"  {len(unmatched)} MGMT names with no research row: " + ", ".join(unmatched[:12]) + (" ..." if len(unmatched) > 12 else ""))
    if a.show:
        for r in sorted(rows, key=lambda r: -r["screen"]["score"])[:25]:
            print(f"  {r['screen']['score']:>2} {r['name']:<28} {r['stage']:<7} {r['tag'] or '':<11} {r['screen']['math']}")
    if a.dry_run:
        return
    sb.upsert("startups", [{"id": r["id"], "name": r["name"], "payload": r, "updated_at": built} for r in rows], cfg=cfg)
    stale = sb.delete_not_in("startups", [r["id"] for r in rows], cfg=cfg)
    sb.upsert("board_meta", [{"key": "startups_summary", "payload": s, "updated_at": built}], cfg=cfg)
    print(f"  pushed {len(rows)} rows" + (f", removed {len(stale)} stale" if stale else ""))


if __name__ == "__main__":
    main()
