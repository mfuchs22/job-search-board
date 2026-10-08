"""Build the board payload from jobs.json, companies.json, people.json, and the job markdown files.

Called by push_board.py (and so by build.py). Returns the four things the page reads from Supabase:
jobs (one record per live posting, with the rendered job markdown as `doc`), companies, paths, summary.
Nothing is written here; push_board.py upserts the result.
"""
import csv
import json
import re
import socket
from datetime import datetime, timezone

try:
    import markdown as _md
except ImportError:  # pragma: no cover
    _md = None

from common import STAGES, OUTCOMES, sibling_map

ROLE_TYPES = {
    "transformation-owner": "Transformation owner",
    "internal-platform-pm": "Internal AI platform PM",
    "fde-embedded": "Forward-deployed / embedded",
    "ai-product-pm": "AI product PM",
    "governance-risk": "Governance / risk",
    "enablement-adoption": "Enablement / adoption",
    "consulting-advisory": "Consulting / advisory",
    "program-project": "Program / project",
    "other": "Other",
}


def _wikilink(m):
    target = m.group(1).split("|")[0]
    name = target.split("/")[-1].replace("-", " ")
    return name.title() if "/" in target else name


# Bare URLs in the job markdown (the **Job posting:** header line, sources in the notes) are plain
# text after markdown conversion, so the posting could only be reached from the company name in the
# meta line. Linkify them in the rendered HTML rather than in the source: entities are already
# correct for both an href and a text node there, and splitting on tags keeps us out of existing
# anchors and attributes.
_BARE_URL = re.compile(r"https?://[^\s<>\"']+")
_TAGS = re.compile(r"(<a\b[^>]*>.*?</a>|<[^>]+>)", re.S)


def _linkify(html):
    def one(m):
        url = m.group(0)
        trail = ""
        # A URL at the end of a sentence swallows the punctuation, and a URL in parentheses swallows
        # the closing paren. Semicolons stay: markdown leaves &amp; in the query string.
        while url and (url[-1] in ".,:!?" or (url[-1] == ")" and url.count(")") > url.count("("))):
            trail = url[-1] + trail
            url = url[:-1]
        if not url:
            return m.group(0)
        return f'<a href="{url}" target="_blank" rel="noopener">{url}</a>{trail}'

    return "".join(
        part if part.startswith("<") else _BARE_URL.sub(one, part)
        for part in _TAGS.split(html)
    )


def render_job_md(vault, job_file):
    f = vault / (job_file + ".md")
    if not f.exists():
        return ""
    txt = f.read_text(encoding="utf-8")
    txt = re.sub(r"^# .+\n", "", txt, count=1)
    txt = re.sub(r"\[\[([^\]]+)\]\]", _wikilink, txt)
    if _md:
        return _linkify(_md.markdown(txt, extensions=["tables"]))
    return _linkify("".join(f"<p>{para}</p>" for para in txt.split("\n\n")))


# ---------- the in-process view (Applied and later): campaign.md, stakeholders, the README timeline ----------
# Claude writes Projects/job-search/opportunities/<slug>/campaign.md after each prep pack and debrief (interview-prep
# stages 2 and 5); the page shows it read-only on the Campaign view (the owner, 2026-09-24).

def _plain(s):
    """Markdown inline to plain text: wikilinks to their last segment, links to their text, bold and code dropped."""
    s = re.sub(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", lambda m: m.group(2) or m.group(1).rsplit("/", 1)[-1].replace("-", " "), s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1", s)
    return re.sub(r"\*\*|`", "", s).strip()


def _sections(txt):
    out, cur = {}, None
    for line in txt.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            cur = m.group(1).strip().lower()
            out[cur] = []
        elif cur is not None:
            out[cur].append(line)
    return out


def _items(lines):
    return [_plain(m.group(1)) for l in lines for m in [re.match(r"^\s*(?:\d+\.|[-*])\s+(.+)$", l)] if m]


def _keyvals(lines):
    return {m.group(1).strip().lower(): _plain(m.group(2)) for l in lines
            for m in [re.match(r"^\*\*([^*:]+):\*\*\s*(.*)$", l.strip())] if m}


def _table(lines):
    rows = [[c.strip() for c in l.strip().strip("|").split("|")] for l in lines if l.strip().startswith("|")]
    rows = [r for r in rows if not all(set(c) <= set("-: ") for c in r)]
    if len(rows) < 2:
        return []
    head = [h.lower() for h in rows[0]]
    return [dict(zip(head, r)) for r in rows[1:]]


def opp_dir(vault, job_file):
    """The opportunity folder for a job file: opportunities/<slug>, the job file's own slug (they match by convention)."""
    d = vault / "opportunities" / job_file.rsplit("/", 1)[-1]
    return d if d.is_dir() else None


def _ball(s):
    """'Them: the recruiter schedules round two (since 2026-09-24)' as {side, text, since}; whose move it is."""
    m = re.match(r"^\s*(you|them)\s*[:,—-]\s*(.*?)\s*(?:\(since (\d{4}-\d{2}-\d{2})\))?\s*$", s or "", re.I)
    return {"side": m.group(1).lower(), "text": m.group(2), "since": m.group(3) or ""} if m else None


def campaign_record(vault, job_file):
    """campaign.md parsed, plus the stakeholders.md rows for the people in Next conversation. None without the file."""
    d = opp_dir(vault, job_file)
    f = d / "campaign.md" if d else None
    if not f or not f.exists():
        return None
    txt = f.read_text(encoding="utf-8")
    head = _keyvals(txt.split("\n## ", 1)[0].splitlines())
    sec = _sections(txt)
    nxt = _keyvals(sec.get("next conversation", []))
    who = [w.strip() for w in re.split(r";", nxt.get("who", "")) if w.strip()]
    stake = []
    sf = d / "roadmap" / "stakeholders.md"
    if sf.exists() and who:
        rows = _table(sf.read_text(encoding="utf-8").splitlines())
        for w in who:
            last = w.split()[-1].lower()
            r = next((r for r in rows if last in (r.get("name") or "").lower()), None)
            stake.append({"name": w, "role": _plain(r.get("role", "")) if r else "",
                          "hear": _plain(r.get("what they need to hear", "")) if r else "",
                          "fear": _plain(r.get("what they fear", "")) if r else ""})
    pages = []
    rd = d / "README.md"
    if rd.exists():  # the prep pages linked from the README's table ("**The package (page):** [cards](url)")
        for m in re.finditer(r"\*\*([^*]+?)\s*\(page\):\*\*\s*\[([^\]]+)\]\((https?://[^)]+)\)", rd.read_text(encoding="utf-8")):
            pages.append({"label": f"{m.group(1).strip()}: {m.group(2)}", "url": m.group(3)})
    return {"updated": head.get("updated", ""), "stale": head.get("stale", ""),
            "next": {"who": who, "when": nxt.get("when", ""), "format": nxt.get("format", ""), "before": nxt.get("before it", "")},
            "ball": _ball(nxt.get("ball", "")),
            "people": stake, "get_across": _items(sec.get("get across", [])), "ask": _items(sec.get("ask", [])),
            "avoid": _items(sec.get("avoid", [])), "settled": _items(sec.get("settled", [])),
            "open": _items(sec.get("open", [])), "fix": _items(sec.get("fix from last time", [])), "pages": pages}


def timeline_rows(vault, job_file):
    """The opportunity README's ## Timeline table as [{date, what}], newest first."""
    d = opp_dir(vault, job_file)
    rd = d / "README.md" if d else None
    if not rd or not rd.exists():
        return []
    rows = _table(_sections(rd.read_text(encoding="utf-8")).get("timeline", []))
    out = [{"date": r.get("date", ""), "what": _plain(r.get("what", ""))} for r in rows if re.match(r"\d{4}-\d{2}-\d{2}", r.get("date", ""))]
    return sorted(out, key=lambda r: r["date"], reverse=True)


def _repo_url(vault, f):
    """A vault file's page on GitHub (the private Personal-OS repo), so the board can link it; opens only for the owner."""
    root = next((d for d in [vault, *vault.parents] if (d / ".git").exists()), None)
    if not root:
        return ""
    from urllib.parse import quote
    return "https://github.com/<you>/<your-vault>/blob/master/" + quote(f.relative_to(root).as_posix())


def _title(f):
    try:
        m = re.search(r"^#\s+(.+)$", f.read_text(encoding="utf-8"), re.M)
    except (OSError, UnicodeDecodeError):
        m = None
    return _plain(m.group(1)) if m else f.stem.replace("-", " ")


_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")
_GROUP = {"application": "Application", "prep": "Prep", "roadmap": "Roadmap"}


def asset_list(vault, job_file, with_sent=True):
    """Every asset the process produced for one opportunity, for the live-opportunities tab: the opportunity folder
    (application, prep, roadmap, campaign), the company's research folder, the meetings and raw notes the README
    links, and the published pages it links. [{group, label, date, kind, url}], vault files linked on GitHub."""
    d = opp_dir(vault, job_file)
    if not d:
        return []
    out, seen = [], set()

    def add(group, f=None, label=None, url=None, date=""):
        key = url or str(f)
        if key in seen:
            return
        seen.add(key)
        kind = "page" if url else ("pdf" if f.suffix.lower() == ".pdf" else "doc")
        date = date or ((_DATE.search(f.name) or [None, ""])[1] if f else "")
        if not label and f is not None:
            v = re.search(r"-(v\d+)$", f.stem)
            if re.search(r"resume", f.stem, re.I):  # every resume version carries the same heading, so name it by file
                label = f"Resume {v.group(1) if v else '(current)'}, {'PDF' if f.suffix.lower() == '.pdf' else 'text'}"
            elif f.stem.startswith("cover-letter"):
                label = f"Cover note {v.group(1) if v else '(current)'}"
            else:
                label = _title(f) if f.suffix == ".md" else f.name
            label = re.sub(r"^\d{4}-\d{2}-\d{2}\s*[—–:-]\s*", "", label)
        out.append({"group": group, "label": label, "date": date,
                    "path": f.relative_to(vault).as_posix() if f is not None else "",
                    "kind": kind, "url": url or _repo_url(vault, f)})

    for f in sorted(d.rglob("*")):
        if f.is_file() and f.suffix.lower() in (".md", ".pdf") and f.name != "README.md":
            sub = f.relative_to(d).parts[0] if len(f.relative_to(d).parts) > 1 else ""
            add(_GROUP.get(sub, "Campaign" if f.name == "campaign.md" else "Opportunity"), f)
    rd = d / "README.md"
    txt = rd.read_text(encoding="utf-8") if rd.exists() else ""
    if rd.exists():
        add("Opportunity", rd, label="Opportunity README (the front door)")
    job = vault / (job_file + ".md")
    if job.exists():
        add("Opportunity", job, label="Role record (process log, prep notes)")
        co = re.search(r"^\*\*Company:\*\*\s*\[\[companies/([^\]|]+)", job.read_text(encoding="utf-8"), re.M)
        rs = vault / "research" / co.group(1) if co else None
        if rs and rs.is_dir():
            for f in sorted(rs.glob("*.md")):
                add("Research", f)
    for m in re.finditer(r"\[\[((?:meetings|raw/conversations)/[^\]|]+)\]\]", txt):
        f = vault / (m.group(1) + ".md")
        if f.exists():
            add("Meetings" if m.group(1).startswith("meetings/") else "Raw notes", f)
    for m in re.finditer(r"\*\*([^*]+?)\s*\(page\):\*\*\s*\[([^\]]+)\]\((https?://[^)]+)\)", txt):
        add("Pages", label=f"{m.group(1).strip()}: {m.group(2)}", url=m.group(3))
    for m in re.finditer(r"([A-Z][^.;:\[\]()*]{3,40}):\s*(https://claude\.ai/artifact/\w+)", txt):
        add("Pages", label=m.group(1).strip(), url=m.group(2))
    if with_sent:  # what went out, and when, from the Sent rows of log.md
        sent = {}
        for r in log_rows(vault, job_file):
            if r["type"].lower() == "sent":
                for a in r["assets"]:
                    sent.setdefault(a["path"], f"{r['date']} to {r['with']}")
        for a in out:
            if a.get("path") in sent:
                a["sent"] = sent[a["path"]]
    return out


def _wikifile(vault, target):
    f = vault / target
    return f if f.suffix and f.exists() else vault / (target + ".md")


def log_rows(vault, job_file):
    """opportunities/<slug>/log.md: the emails and the things sent, one row each (Claude keeps it from Gmail and
    the owner's updates). [{date, time, type, with, what, url, assets: [{label, url}]}], oldest first as written; each Sent
    row's assets are the files that went out."""
    d = opp_dir(vault, job_file)
    f = d / "log.md" if d else None
    if not f or not f.exists():
        return []
    by_path = {a["path"]: a for a in asset_list(vault, job_file, with_sent=False) if a.get("path")}
    out = []
    for r in _table(f.read_text(encoding="utf-8").splitlines()):
        if not _DATE.match(r.get("date", "")):
            continue
        assets = []
        for m in re.finditer(r"\[\[([^\]|]+)\]\]", r.get("assets", "")):
            wf = _wikifile(vault, m.group(1))
            rel = wf.relative_to(vault).as_posix() if wf.exists() else ""
            a = by_path.get(rel)
            assets.append({"label": a["label"] if a else wf.stem.replace("-", " "), "url": a["url"] if a else _repo_url(vault, wf) if wf.exists() else "", "path": rel})
        url = (re.search(r"https?://\S+", r.get("link", "")) or [None])[0] if r.get("link") else ""
        out.append({"date": r["date"], "time": r.get("time", ""), "type": _plain(r.get("type", "")) or "Email",
                    "with": _plain(r.get("with", "")), "what": _plain(r.get("what", "")), "url": url or "", "assets": assets})
    return out


def meeting_rows(vault, job_file):
    """The vault meeting records the README links, as dated timeline rows with a link to the record."""
    return [{"date": a["date"], "kind": "Meeting", "what": a["label"], "url": a["url"]}
            for a in asset_list(vault, job_file) if a["group"] == "Meetings" and a["date"]]


FIELDS = ("id", "url", "title", "company", "company_key", "location", "work_model", "comp", "travel", "score",
          "score_kind", "why", "mismatch", "flag", "verdict", "verdict_date", "verdict_ts", "calibration", "note",
          "status_note", "stage", "stage_date", "stage_ts", "outcome", "next_step", "next_step_date", "job_file",
          "date_first_seen", "source", "role_type", "qualifications", "excluded", "deep_pass_date", "rubric_version", "human_path", "office",
          "posting")


def page_record(j, docs, extras=None):
    r = {k: j.get(k) for k in FIELDS}
    card = j.get("card") or {}
    r["math"] = card.get("math")
    r["bullets"] = card.get("job") or []
    r["alert"] = card.get("note")
    r["doc"] = docs.get(j["id"], "")
    r.update((extras or {}).get(j["id"], {}))  # campaign and timeline, for the in-process view
    return r


def radar_last(p):
    """Newest date_first_seen in inbox.csv: the radar's last delivery, which may be ahead of the board."""
    if not p.inbox_csv.exists():
        return ""
    with p.inbox_csv.open(encoding="utf-8", newline="") as f:
        return max((row.get("date_first_seen") or "" for row in csv.DictReader(f)), default="")


_HEARTBEAT = re.compile(r"^- (\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}) UTC \| mail: (\d+) \| rows: (\d+) \| 7\+: (\d+) \| (ok|quiet|failed)(?::\s*(.*))?$")


def radar_pulse(p):
    """The radar's newest heartbeat line (Personal-OS Tools/job-radar-heartbeat.md), parsed: when it ran, what it
    found, and whether it ended ok, quiet, or failed. None when the file is missing (a vault outside Personal-OS)."""
    hb = getattr(p, "radar_heartbeat", None)
    if not hb or not hb.exists():
        return None
    best = None
    for line in hb.read_text(encoding="utf-8").splitlines():
        m = _HEARTBEAT.match(line.strip())
        if m and (best is None or (m.group(1), m.group(2)) >= (best.group(1), best.group(2))):
            best = m
    if not best:
        return None
    d, t, mail, rows, above, status, note = best.groups()
    return {"at": f"{d}T{t}:00+00:00", "date": d, "status": status, "mail": int(mail), "rows": int(rows),
            "above_floor": int(above), "note": (note or "").strip()[:300]}


def board_health(p, extra=None):
    """What the page's banner needs to say whether the board is current: which host built it, the radar's last
    pulse, the inbox's newest row, and how the Notion pull and page fills went (passed in by build.py; a push
    without a build says so)."""
    h = {"host": socket.gethostname().split(".")[0], "radar": radar_pulse(p), "inbox_newest": radar_last(p),
         "notion": {"ok": None, "detail": "not pulled in this push"}, "pages": {"ok": None, "detail": ""}}
    h.update(extra or {})
    return h


def board_payload(cfg, p, data, health=None):
    min_score = int(cfg.get("min_score", 7))
    companies = json.loads(p.companies_json.read_text(encoding="utf-8"))["companies"] if p.companies_json.exists() else {}
    people = json.loads(p.people_json.read_text(encoding="utf-8")) if p.people_json.exists() else {}

    all_jobs = data["jobs"]
    # Live = on the board: excluded (collapsed list), reviewed, or at/above the floor with the deep pass done.
    # Title-level radar rows at 7+ never render as cards (rule 1, 2026-09-03); they are the waiting_deep_pass count.
    live = [j for j in all_jobs if j.get("excluded") or j.get("verdict")
            or ((j.get("score") or 0) >= min_score and j.get("score_kind") == "deep")]
    docs = {j["id"]: render_job_md(p.vault, j["job_file"]) for j in live if j.get("job_file")}
    extras = {j["id"]: {"campaign": campaign_record(p.vault, j["job_file"]), "timeline": timeline_rows(p.vault, j["job_file"]),
                        "assets": asset_list(p.vault, j["job_file"]), "meetings_vault": meeting_rows(p.vault, j["job_file"]),
                        "log": log_rows(p.vault, j["job_file"])}
              for j in live if j.get("job_file")}
    jobs = [page_record(j, docs, extras) for j in live]
    sibs = sibling_map(live)
    for r in jobs:
        r["siblings"] = sibs.get(r["id"], [])
    page_companies = {j["company"] for j in live} | {j.get("company_key") for j in live if j.get("company_key")}
    companies = {k: v for k, v in companies.items() if k in page_companies}
    people = {k: v for k, v in people.items() if k in page_companies}

    unscored = sum(1 for j in all_jobs if j.get("score") is None and not j.get("excluded") and not j.get("verdict"))
    below = sum(1 for j in all_jobs if j.get("score") is not None and j["score"] < min_score and not j.get("verdict") and not j.get("excluded"))
    waiting = sum(1 for j in all_jobs if j.get("score_kind") == "title" and (j.get("score") or 0) >= min_score
                  and not j.get("excluded") and not j.get("verdict") and not j.get("deep_pass_date"))
    summary = {
        "title": cfg.get("dashboard_title", "Job Board"),
        "min_score": min_score,
        "board_floor": min_score,
        "review_floor": int(cfg.get("review_floor", 8)),
        "stages": list(STAGES),
        "outcomes": list(OUTCOMES),
        "role_types": ROLE_TYPES,
        "asof": data.get("asof") or "",
        "data_asof": max((j.get("date_first_seen") or "" for j in live if not j.get("excluded")), default=""),
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "radar_last": radar_last(p),
        "waiting_deep_pass": waiting,
        # posting liveness (engine/posting_check.py, nightly): the ad is down but the role is not closed, and the
        # pages the rules could not read. Counts over the live rows; the Closed tab lists them.
        "postings_gone": sum(1 for j in live if (j.get("posting") or {}).get("state") in ("closed", "removed") and j.get("stage") != "closed"),
        "postings_unknown": sum(1 for j in live if (j.get("posting") or {}).get("state") == "unknown"),
        # the Closed tab's two groups (the owner, 2026-10-07): Pursues he was engaged with, and Pursues whose ad went away
        "closed_engaged": sum(1 for j in live if j.get("verdict") == "pursue" and j.get("stage") == "closed" and j.get("outcome") != "posting_removed"),
        "closed_gone": sum(1 for j in live if j.get("verdict") == "pursue" and j.get("stage") == "closed" and j.get("outcome") == "posting_removed"),
        "reposted": sum(1 for j in live if (j.get("posting") or {}).get("reposted")),
        "tracked": len(all_jobs),
        "unscored": unscored,
        "below_floor": below,
        "excluded": sum(1 for j in all_jobs if j.get("excluded")),
        "sources": sorted({(j.get("source") or "").split(":")[0] for j in all_jobs if j.get("source")}),
        "first_seen": min((j.get("date_first_seen") or "9999" for j in all_jobs), default=""),
        "health": board_health(p, health),
    }
    return jobs, companies, people, summary
