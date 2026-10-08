"""Posting check: is the ad still up? Nightly lint of the board.

One `posting` object per jobs.json record, owned by this script and nothing else:

    {"state": "closed", "since": "2026-10-04", "checked": "2026-10-07", "checks": 3, "streak": 2,
     "method": "linkedin-guest", "http": 200, "evidence": "No longer accepting applications",
     "url_checked": "https://www.linkedin.com/jobs/view/4466245131", "last_active": "2026-09-30",
     "frozen": false}

States: active (the page answers and shows no closed marker), closed (up, but not taking applications), removed
(404/410 or a redirect to the board's listings root), unreachable (bot wall, rate limit, or no checkable URL),
unknown (the rules conflicted, the BCG shape: "filled" text next to a fresh datePosted; the model or the owner decides).
`stale` is a report bucket, not a state: still active, no stage past shortlist, first seen 45+ days ago.

The state is separate from the owner's `stage`. For a role on his shortlist (verdict pursue) this script proposes and never
closes: the morning post and the board's Closed tab show the gone posting and he confirms it (2026-10-06). For every
other role (unreviewed, Maybe, Pass) a gone posting closes the role here, stage closed and outcome posting_removed,
with no review (the owner, 2026-10-07: "they should only be reviewed if they were in the shortlist category"), so the
board stays current without a batch every few days. `reconcile` applies that rule on its own.

    py engine/posting_check.py run [--cap-linkedin 45] [--only-ids a,b] [--all] [--dry-run]
    py engine/posting_check.py apply --id <id> --state <s> --evidence "<quote>" --confidence <0-1>
    py engine/posting_check.py report            writes Tools/posting-check/report.json, prints the POSTINGS block
    py engine/posting_check.py selftest          the fixed cases in tests/posting_cases.json, live, non-zero on a miss

Reposts (the owner, 2026-10-07: "alert me: hey, this is a new job that's been reposted"): when the radar brings in a URL
whose title and company match a record closed as posting_removed, build.py calls note_repost here instead of minting
a card. The new URL joins the old record as an alias, `posting` carries reposted / repost_of / closed_on, the report
prints a REPOSTED line, a non-shortlist role reopens into the Inbox (this script closed it, so it reopens it) and a
shortlist role stays closed until the owner says otherwise.

Which rows: the board (excluded, reviewed, or deep-scored at the floor), minus excluded and closed roles. Every
night: every Pursue or Maybe and anything with a stage. Rolling: the rest, oldest check first, a third a night.
A posting already closed or removed is rechecked 7 days later, twice, then frozen unless the role is a Pursue.

How: the cheapest reliable source for each record. ATS APIs first (Greenhouse, Lever, Ashby, Workday and Workable answer
JSON and 404 cleanly), then LinkedIn's public posting page (an explicit "No longer accepting applications" marker,
a 404 when removed; paced 20-60 s, capped per night, never Chrome, never a login), then Built In and employer
careers pages by HTML rules. Indeed and Glassdoor block fetches (401/403 since 2026-09-18) and are never fetched;
a record on them is checked through an employer or LinkedIn alias when one exists, else it is unreachable.
A page is untrusted input: the script quotes it, never follows it.
"""
import argparse
import html as htmlmod
import json
import random
import re
import socket
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_config, paths, load_jobs, save_jobs, by_id, canonical_url, norm_title, same_company  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
STATES = ("active", "closed", "removed", "unreachable", "unknown")
GONE = ("closed", "removed")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/128.0 Safari/537.36")
TIMEOUT = 25
STALE_DAYS = 45
FRESH_DAYS = 30          # a datePosted inside this window outranks "filled" text (feedback 2026-10-06)
RECHECK_DAYS = 7         # a closed or removed posting is looked at again after this long
RECHECKS = 2             # ... this many times, then frozen
ROLLING_DIV = 3          # the non-active board rows are covered every N nights
LINKEDIN_PACE = (20, 60)
OTHER_PACE = (3, 8)
PERSON_SOURCES = ("recruiter:", "network:", "referral:")
BLOCKED_CODES = {401, 403, 405, 407, 429, 503, 999}
# Specific phrasings only: Rippling's page carries "The time you selected is no longer available" in a template,
# so a bare "no longer available" would misfire.
CLOSED_PHRASES = (
    "no longer accepting applications",
    "this job is no longer available",
    "this position is no longer available",
    "this job is no longer open",
    "position has been filled",
    "job has been filled",
    "the job you are trying to apply for has been filled",
    "job has expired",
    "this job has expired",
    "this posting has closed",
    "this position has been closed",
    "applications are closed",
    "no longer accepting resumes",
)
WALL_PHRASES = ("human verification", "verify you are human", "access denied", "captcha", "authwall",
                "enable javascript and cookies to continue")


# ---------------------------------------------------------------- http

def fetch(url, accept="text/html,application/json;q=0.9,*/*;q=0.8"):
    """(status, final_url, text). Never raises: a network failure is (0, url, '')."""
    req = Request(url, headers={"User-Agent": UA, "Accept": accept, "Accept-Language": "en-US,en;q=0.9"})
    try:
        with urlopen(req, timeout=TIMEOUT) as r:
            return r.status, r.geturl(), r.read().decode("utf-8", "replace")
    except HTTPError as e:
        try:
            body = e.read().decode("utf-8", "replace")
        except Exception:
            body = ""
        return e.code, e.geturl() or url, body
    except (URLError, socket.timeout, TimeoutError, ConnectionError, OSError):
        return 0, url, ""


def host_of(url):
    return urlsplit(url or "").netloc.lower().replace("www.", "")


# ---------------------------------------------------------------- page reading

_JSONLD = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S | re.I)


def jsonld_posting(body):
    """The JobPosting object in a page's JSON-LD, or None."""
    for m in _JSONLD.finditer(body or ""):
        try:
            obj = json.loads(htmlmod.unescape(m.group(1)).strip())
        except Exception:
            continue
        for o in (obj if isinstance(obj, list) else [obj]):
            if isinstance(o, dict):
                if o.get("@type") == "JobPosting":
                    return o
                for g in o.get("@graph") or []:
                    if isinstance(g, dict) and g.get("@type") == "JobPosting":
                        return g
    # BCG's Phenom page inlines the object without a type attribute on the script; Built In writes datePosted before @type
    if re.search(r'"@type"\s*:\s*"JobPosting"', body or ""):
        m = re.search(r'"datePosted"\s*:\s*"([^"]+)"', body)
        if m:
            out = {"@type": "JobPosting", "datePosted": m.group(1)}
            v = re.search(r'"validThrough"\s*:\s*"([^"]+)"', body)
            if v:
                out["validThrough"] = v.group(1)
            return out
    return None


def ago_to_date(text, today):
    """LinkedIn's 'posted 3 weeks ago' as an approximate ISO date (None when the text is not a span)."""
    m = re.search(r"(\d+)\s+(minute|hour|day|week|month|year)s?\s+ago", text or "")
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    days = {"minute": 0, "hour": 0, "day": 1, "week": 7, "month": 30, "year": 365}[unit] * n
    return (today - timedelta(days=days)).isoformat()


def parse_day(s):
    if not s:
        return None
    m = re.match(r"(\d{4}-\d{2}-\d{2})", str(s))
    try:
        return date.fromisoformat(m.group(1)) if m else None
    except ValueError:
        return None


def page_text(body, cap=15000):
    """The page as plain text for the model pass: no scripts, no tags, whitespace collapsed, capped."""
    t = re.sub(r"<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", body or "", flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = htmlmod.unescape(t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:cap]


def title_match(title, text):
    """Most of the role title's real words appear on the page."""
    words = [w for w in re.findall(r"[a-z0-9]+", (title or "").lower()) if len(w) > 3]
    if not words:
        return True
    return sum(1 for w in words if w in text) >= max(1, round(len(words) * 0.6))


def signals(status, final_url, body, url, today, title=None):
    """What a generic careers page says about itself. Pure; the decision is in classify_html."""
    text = page_text(body, cap=400000).lower()
    found = [p for p in CLOSED_PHRASES if p in text]
    ld = jsonld_posting(body) or {}
    posted = parse_day(ld.get("datePosted"))
    through = parse_day(ld.get("validThrough"))
    apply_link = bool(re.search(r"(apply now|apply for this job|apply to this job|applyurl|apply-button|\"apply\")",
                                (body or "").lower()))
    fin = urlsplit(final_url or url)
    start = urlsplit(url)
    redirected_root = (fin.netloc.replace("www.", "") == start.netloc.replace("www.", "")
                       and fin.path.rstrip("/") != start.path.rstrip("/")
                       and (fin.path.count("/") <= 2 or "error=" in (fin.query or "") or "error=" in fin.path))
    walled = any(w in text for w in WALL_PHRASES) and len(text) < 4000
    return {"http": status, "final_url": final_url, "phrases": found, "date_posted": posted.isoformat() if posted else None,
            "valid_through": through.isoformat() if through else None,
            "fresh": bool(posted and (today - posted).days <= FRESH_DAYS),
            "expired": bool(through and through < today),
            "apply_link": apply_link, "title_match": title_match(title, text), "redirected_root": redirected_root,
            "walled": walled, "size": len(body or "")}


def classify_html(sig):
    """(state or 'ambiguous', evidence) from a generic careers page."""
    h = sig["http"]
    if h == 0:
        return "unreachable", "no response"
    if h in (404, 410):
        return "removed", f"HTTP {h}"
    if sig["redirected_root"]:
        return "removed", f"redirected to {sig['final_url']}"
    if h in BLOCKED_CODES or sig["walled"]:
        return "unreachable", f"HTTP {h}" + (" (bot wall)" if sig["walled"] else "")
    if h >= 400:
        return "unreachable", f"HTTP {h}"
    if sig["phrases"]:
        quote = sig["phrases"][0]
        if sig["fresh"] or sig["apply_link"]:
            why = f'"{quote}" but datePosted {sig["date_posted"]}' if sig["fresh"] else f'"{quote}" but an apply link is present'
            return "ambiguous", why
        return "closed", f'"{quote}"'
    if sig["expired"] and not sig["date_posted"]:
        return "ambiguous", f"validThrough {sig['valid_through']} has passed"
    if sig["date_posted"]:
        return "active", f"datePosted {sig['date_posted']}"
    if sig["apply_link"] and sig["title_match"]:
        return "active", "title and apply link on the page"
    if sig["apply_link"]:
        return "ambiguous", "apply link present but the title is not on the page"
    return "ambiguous", "no posting markers found"


# ---------------------------------------------------------------- checkers: (state, method, http, evidence, extra)

_CACHE = {}


def check_linkedin(url, today, title=None):
    m = re.search(r"/jobs/view/(?:[^/]*-)?(\d+)", url)
    if not m:
        return "unknown", "linkedin-guest", None, "no job id in URL", {}
    jid = m.group(1)
    status, final, body = fetch(f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{jid}")
    extra = {"url_checked": f"https://www.linkedin.com/jobs/view/{jid}"}
    if status == 404:
        return "removed", "linkedin-guest", 404, "HTTP 404", extra
    if status in BLOCKED_CODES or "authwall" in (final or "") or "/login" in (final or "") or status == 0:
        return "unreachable", "linkedin-guest", status, f"HTTP {status} (blocked)", {**extra, "blocked": True}
    if status != 200:
        return "unreachable", "linkedin-guest", status, f"HTTP {status}", extra
    if "closed-job__flavor--closed" in body or "no longer accepting applications" in body.lower():
        return "closed", "linkedin-guest", 200, "No longer accepting applications", extra
    ago = re.search(r'posted-time-ago__text[^>]*>\s*([^<]+?)\s*<', body)
    if ago:
        extra["posted"] = ago_to_date(ago.group(1), today)
        extra["posted_approx"] = True
    if "num-applicants__caption" in body or "topcard__" in body:
        n = re.search(r"(\d[\d,]*)\s+applicants", body)
        return "active", "linkedin-guest", 200, f"{n.group(1)} applicants" if n else "posting page up", extra
    return "unknown", "linkedin-guest", 200, "page answered without the usual markers", extra


def check_greenhouse(url, today, title=None):
    m = re.search(r"greenhouse\.io/([^/]+)/jobs/(\d+)", url)
    if not m:
        return "unknown", "greenhouse-api", None, "unrecognised Greenhouse URL", {}
    slug, jid = m.groups()
    status, _, body = fetch(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{jid}", accept="application/json")
    if status == 200:
        upd = re.search(r'"updated_at"\s*:\s*"([^"]+)"', body)
        pub = re.search(r'"first_published"\s*:\s*"([^"]+)"', body)
        return "active", "greenhouse-api", 200, f"on the board (updated {upd.group(1)[:10]})" if upd else "on the board", \
            {"posted": pub.group(1)[:10]} if pub else {}
    if status == 404:
        key = ("gh", slug)
        if key not in _CACHE:
            _CACHE[key] = fetch(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=false",
                                accept="application/json")[0]
        if _CACHE[key] == 200:
            return "removed", "greenhouse-api", 404, "not on the company's Greenhouse board", {}
        return "unreachable", "greenhouse-api", 404, f"board {slug} not found", {}
    return "unreachable", "greenhouse-api", status, f"HTTP {status}", {}


def check_lever(url, today, title=None):
    m = re.search(r"lever\.co/([^/]+)/([0-9a-f-]{36})", url)
    if not m:
        return "unknown", "lever-api", None, "unrecognised Lever URL", {}
    co, pid = m.groups()
    status, _, _ = fetch(f"https://api.lever.co/v0/postings/{co}/{pid}", accept="application/json")
    if status == 200:
        return "active", "lever-api", 200, "posting on Lever", {}
    if status == 404:
        return "removed", "lever-api", 404, "not on the company's Lever board", {}
    return "unreachable", "lever-api", status, f"HTTP {status}", {}


def check_ashby(url, today, title=None):
    m = re.search(r"ashbyhq\.com/([^/?#]+)/([0-9a-f-]{36})", url)
    if not m:
        return "unknown", "ashby-api", None, "unrecognised Ashby URL", {}
    slug, pid = m.groups()
    key = ("ashby", slug)
    if key not in _CACHE:
        status, _, body = fetch(f"https://api.ashbyhq.com/posting-api/job-board/{slug}", accept="application/json")
        ids, pub = None, {}
        if status == 200:
            try:
                for jb in json.loads(body).get("jobs", []):
                    pub[jb.get("id")] = (jb.get("publishedAt") or "")[:10] or None
                ids = set(pub)
            except Exception:
                ids = set(re.findall(r'"id"\s*:\s*"([0-9a-f-]{36})"', body))
        _CACHE[key] = (status, ids, pub)
    status, ids, pub = _CACHE[key]
    if status != 200:
        return "unreachable", "ashby-api", status, f"HTTP {status}", {}
    if pid in ids:
        return "active", "ashby-api", 200, "on the company's Ashby board", {"posted": pub.get(pid)} if pub.get(pid) else {}
    return "removed", "ashby-api", 200, "not on the company's Ashby board", {}


def check_workday(url, today, title=None):
    m = re.match(r"https?://([^.]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([^/]+)/job/(.+)$", url)
    if not m:
        return "unknown", "workday-cxs", None, "unrecognised Workday URL", {}
    tenant, wd, site, rest = m.groups()
    rest = rest.split("?")[0]
    status, _, body = fetch(f"https://{tenant}.{wd}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/job/{rest}",
                            accept="application/json")
    if status == 200 and "jobPostingInfo" in body:
        sd = re.search(r'"startDate"\s*:\s*"(\d{4}-\d{2}-\d{2})', body)
        return "active", "workday-cxs", 200, "posting in Workday", {"posted": sd.group(1)} if sd else {}
    if status == 404:
        code = re.search(r'"errorCode"\s*:\s*"([^"]+)"', body)
        return "removed", "workday-cxs", 404, f"Workday {code.group(1) if code else '404'}", {}
    return "unreachable", "workday-cxs", status, f"HTTP {status}", {}


def check_workable(url, today, title=None):
    """apply.workable.com/<account>/j/<code>: the public job API answers 200 with the published date while the ad is up and
    404 "Job not found" once it is gone (Board of Innovation, 2026-10-07). The HTML page is a JavaScript shell."""
    m = re.search(r"apply\.workable\.com/([^/]+)/j/([A-Za-z0-9]+)", url)
    if not m:
        return "unknown", "workable-api", None, "unrecognised Workable URL (needs the account in the path)", {}
    acct, code = m.groups()
    status, _, body = fetch(f"https://apply.workable.com/api/v2/accounts/{acct}/jobs/{code}", accept="application/json")
    if status == 200:
        pub = re.search(r'"published"\s*:\s*"(\d{4}-\d{2}-\d{2})', body)
        return "active", "workable-api", 200, "posting on Workable", {"posted": pub.group(1)} if pub else {}
    if status == 404:
        return "removed", "workable-api", 404, "not on the company's Workable board", {}
    return "unreachable", "workable-api", status, f"HTTP {status}", {}


def check_builtin(url, today, title=None):
    status, final, body = fetch(url)
    if status in (404, 410):
        return "removed", "builtin-html", status, f"HTTP {status}", {}
    if status != 200:
        return "unreachable", "builtin-html", status, f"HTTP {status}", {}
    sig = signals(status, final, body, url, today, title)
    if sig["redirected_root"]:
        return "removed", "builtin-html", 200, f"redirected to {final}", {}
    if sig["phrases"]:
        return "closed", "builtin-html", 200, f'"{sig["phrases"][0]}"', {}
    # Built In stamps validThrough about 25 days after datePosted by default and keeps showing Apply Now past it,
    # so the date is a note, not a verdict.
    ev = f"datePosted {sig['date_posted']}" if sig["date_posted"] else "apply link present"
    return "active", "builtin-html", 200, ev, {"valid_through": sig["valid_through"], "posted": sig["date_posted"]}


def check_html(url, today, title=None):
    status, final, body = fetch(url)
    sig = signals(status, final, body, url, today, title)
    state, ev = classify_html(sig)
    extra = {"signals": sig, "posted": sig["date_posted"]}
    if state == "ambiguous":
        extra["page_text"] = page_text(body)
    return state, "html", status, ev, extra


CHECKERS = (
    (re.compile(r"greenhouse\.io$"), check_greenhouse, 0),
    (re.compile(r"lever\.co$"), check_lever, 0),
    (re.compile(r"ashbyhq\.com$"), check_ashby, 0),
    (re.compile(r"myworkdayjobs\.com$"), check_workday, 0),
    (re.compile(r"^apply\.workable\.com$"), check_workable, 0),
    (re.compile(r"^linkedin\.com$"), check_linkedin, 2),
    (re.compile(r"^builtin(boston)?\.com$"), check_builtin, 1),
)
NEVER = re.compile(r"(^|\.)(indeed\.com|glassdoor\.com|hand\.local)$")


def checker_for(url):
    """(fn, rank) for a URL; rank orders candidates (0 = an API, 1 = plain HTML, 2 = LinkedIn, paced)."""
    h = host_of(url)
    if not h or NEVER.search(h) or "/jobs/needs-url/" in url:
        return None, 9
    for pat, fn, rank in CHECKERS:
        if pat.search(h):
            return fn, rank
    return check_html, 1


def candidates(rec):
    """The record's URLs worth fetching, best first."""
    out = []
    for u in [rec.get("url") or ""] + list(rec.get("aliases") or []):
        if not isinstance(u, str) or not u.startswith("http"):
            continue
        fn, rank = checker_for(u)
        if fn:
            out.append((rank, u, fn))
    out.sort(key=lambda t: t[0])
    return out


# ---------------------------------------------------------------- selection

def board_rows(data, cfg):
    """The rows worth checking: on the board, not closed, and not Passed (the owner, 2026-10-07: a passed role is never
    looked at again)."""
    floor = int(cfg.get("min_score", 7))
    return [j for j in data["jobs"]
            if not j.get("excluded") and j.get("stage") != "closed" and j.get("verdict") != "pass"
            and (j.get("verdict") or ((j.get("score") or 0) >= floor and j.get("score_kind") == "deep"))]


def due(rec, today):
    """Is a board row due tonight? Active-set rows always; a closed/removed posting after RECHECK_DAYS, unless frozen."""
    p = rec.get("posting") or {}
    if p.get("state") in GONE:
        if p.get("frozen") and rec.get("verdict") != "pursue":
            return False
        last = parse_day(p.get("checked"))
        return not last or (today - last).days >= RECHECK_DAYS
    return True


def select(data, cfg, today, all_rows=False, only_ids=None):
    rows = board_rows(data, cfg)
    if only_ids:
        want = set(only_ids)
        return [j for j in data["jobs"] if j["id"] in want]
    if all_rows:
        return [j for j in rows if due(j, today)]
    nightly = [j for j in rows if (j.get("verdict") in ("pursue", "maybe") or j.get("stage")) and due(j, today)]
    rest = [j for j in rows if j not in nightly and due(j, today)]
    rest.sort(key=lambda j: ((j.get("posting") or {}).get("checked") or "", j["id"]))
    share = -(-len(rest) // ROLLING_DIV)
    return nightly + rest[:share]


# ---------------------------------------------------------------- one record

def check_record(rec, today, linkedin_budget):
    """Fetch every link the record has (LinkedIn, a board, the company page) and keep each answer.

    Returns (result dict with `sources`, linkedin_used, blocked). The record's state is derived: any live source makes
    it active (an expired LinkedIn listing does not close a role the employer still shows); a conflicting page makes
    it ambiguous (queued for the model); every checkable source gone makes it closed or removed; nothing readable
    makes it unreachable. A person-sourced role whose only link is a hand-typed company URL that 404s is
    unreachable, not gone (the owner, 2026-10-06: Example Co came through the search firm on LinkedIn; the firm's site never had it).
    """
    cands = candidates(rec)
    person = (rec.get("source") or "").startswith(PERSON_SOURCES)
    if not cands:
        why = "no posting URL" if host_of(rec.get("url") or "") == "hand.local" or not rec.get("url") \
            else "only Indeed/Glassdoor links, which block fetches; no employer or LinkedIn alias"
        if person:
            why += f"; the role came through a person ({rec.get('source')}), add the posting link if there is one"
        return {"state": "unreachable", "method": "none", "http": None, "evidence": why, "url_checked": None,
                "sources": []}, 0, False
    sources, used, blocked, li_done, page = [], 0, False, 0, None
    for rank, url, fn in cands:
        if fn is check_linkedin:
            # One LinkedIn id per record is enough; a second alias is tried only when the first was not live.
            if li_done >= 2 or (li_done == 1 and any(x["kind"] == "linkedin-guest" and x["state"] == "active" for x in sources)):
                continue
            if linkedin_budget - used <= 0:
                sources.append({"url": url, "kind": "linkedin-guest", "state": "skipped", "http": None,
                                "evidence": "LinkedIn cap reached tonight"})
                continue
        state, method, http, ev, extra = fn(url, today, rec.get("title"))
        if fn is check_linkedin:
            used += 1
            li_done += 1
        blocked = blocked or bool(extra.get("blocked"))
        row = {"url": extra.get("url_checked", url), "kind": method, "state": state, "http": http, "evidence": ev}
        if extra.get("posted"):
            row["posted"] = extra["posted"]
            if extra.get("posted_approx"):
                row["posted_approx"] = True
        if state == "ambiguous" and page is None:
            page = extra.get("page_text") or ""
            row["conflict"] = {k: extra.get("signals", {}).get(k) for k in ("phrases", "date_posted", "valid_through", "apply_link", "http")}
        if state == "removed" and person and fn is check_html and rank == 1:
            row["hand_typed"] = True
        sources.append(row)
        if state == "active" and method != "linkedin-guest":
            break   # the employer or its ATS shows the role: that settles it, no need to spend a LinkedIn fetch
    checked = [x for x in sources if x["state"] != "skipped"]
    states = [x["state"] for x in checked]
    out = {"method": "multi" if len(checked) > 1 else (checked[0]["kind"] if checked else "none"), "sources": sources,
           "url_checked": (checked[0]["url"] if checked else cands[0][1])}
    dated = [x for x in checked if x.get("posted")]
    exact = [x for x in dated if not x.get("posted_approx")]
    if exact or dated:
        best = min(exact or dated, key=lambda x: x["posted"])
        out["posted"], out["posted_approx"] = best["posted"], bool(best.get("posted_approx"))
    def pick(st):
        for x in checked:
            if x["state"] == st and x["kind"] != "linkedin-guest":
                return x
        return next(x for x in checked if x["state"] == st)
    if "active" in states:
        x = pick("active")
        out.update(state="active", http=x["http"], evidence=f"{x['evidence']} ({x['kind']})", url_checked=x["url"])
    elif "ambiguous" in states:
        x = pick("ambiguous")
        out.update(state="ambiguous", http=x["http"], evidence=x["evidence"], url_checked=x["url"], page_text=page or "",
                   signals={"conflict": x.get("conflict")})
    elif any(st in GONE for st in states):
        gone = [x for x in checked if x["state"] in GONE]
        if all(x.get("hand_typed") for x in gone):
            x = gone[0]
            out.update(state="unreachable", http=x["http"], evidence=f"company page {x['evidence']}; the role came through a person ({rec.get('source')}), add the posting link if there is one")
        else:
            real = [x for x in gone if not x.get("hand_typed")]
            x = next((x for x in real if x["state"] == "closed"), real[0])
            out.update(state=x["state"], http=x["http"], evidence=f"{x['evidence']} ({x['kind']})", url_checked=x["url"])
    elif not checked:
        out.update(state="skipped", http=None, evidence="LinkedIn cap reached tonight")
    else:
        x = checked[0]
        out.update(state="unreachable", http=x["http"], evidence="; ".join(f"{y['kind']}: {y['evidence']}" for y in checked))
    return out, used, blocked


def merge_posting(prev, res, today, model=False):
    prev = prev or {}
    state = "unknown" if res["state"] == "ambiguous" else res["state"]
    same = prev.get("state") == state
    streak = (prev.get("streak") or 0) + 1 if same else 1
    p = {
        "state": state,
        "since": prev.get("since") if same and prev.get("since") else today.isoformat(),
        "checked": today.isoformat(),
        "checks": (prev.get("checks") or 0) + 1,
        "streak": streak,
        "method": "model" if model else res["method"],
        "http": res.get("http"),
        "evidence": res.get("evidence"),
        "url_checked": res.get("url_checked") or prev.get("url_checked"),
        "last_active": today.isoformat() if state == "active" else prev.get("last_active"),
        "frozen": state in GONE and streak >= 1 + RECHECKS,
    }
    if prev.get("kept") and state in GONE:
        p["kept"] = prev["kept"]
    for k in ("reposted", "repost_of", "closed_on"):
        if prev.get(k):
            p[k] = prev[k]
    if res.get("valid_through"):
        p["valid_through"] = res["valid_through"]
    # posted: an exact date beats an approximate LinkedIn span, and the earliest exact date ever seen is kept, because
    # some careers platforms (BCG's Phenom) bump datePosted every day
    newp, newa = res.get("posted"), bool(res.get("posted_approx"))
    oldp, olda = prev.get("posted"), bool(prev.get("posted_approx"))
    if newp and (not oldp or (olda and not newa) or (olda == newa and newp < oldp)):
        p["posted"], p["posted_approx"] = newp, newa
    elif oldp:
        p["posted"], p["posted_approx"] = oldp, olda
    if res.get("sources") is not None:
        p["sources"] = [{k: v for k, v in x.items() if k != "conflict"} for x in res["sources"]]
    elif prev.get("sources"):
        p["sources"] = prev["sources"]
    if state == "unknown" and res.get("signals", {}).get("conflict"):
        p["conflict"] = res["signals"]["conflict"]
    return p


# ---------------------------------------------------------------- files

def tools_dir(p):
    d = p.personal_os / "Tools" / "posting-check"
    (d / "pages").mkdir(parents=True, exist_ok=True)
    return d


def log_line(p, row):
    f = p.jobs_dir / "posting-log.jsonl"
    with f.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def is_stale(rec, today):
    p = rec.get("posting") or {}
    if p.get("state") not in ("active", None) or rec.get("verdict") == "pass":
        return False
    if rec.get("stage") not in (None, "shortlist"):
        return False
    seen = parse_day(rec.get("date_first_seen"))
    return bool(seen and (today - seen).days >= STALE_DAYS)


def brief(rec):
    return f"{rec.get('score') if rec.get('score') is not None else '-'} · {rec.get('title')} · {rec.get('company')}"


def auto_close(data, cfg, today):
    """Close every non-Pursue board row whose posting is gone (the owner, 2026-10-07). Returns the rows closed."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    done = []
    for j in board_rows(data, cfg):
        if j.get("verdict") == "pursue" or (j.get("posting") or {}).get("state") not in GONE:
            continue
        j["stage"], j["outcome"] = "closed", "posting_removed"
        j["stage_date"], j["stage_ts"] = today.isoformat(), now
        done.append(j)
    return done


def find_repost(data, title, company):
    """The record a new inbox row is a repost of: same normalized title and company, closed because its posting went
    away (outcome posting_removed). A role the owner closed himself (rejected, withdrew, no response) is not a repost match;
    a new ad there is a new card. None when there is no such record."""
    tt = norm_title(title)
    if not tt:
        return None
    hits = [j for j in data["jobs"] if j.get("outcome") == "posting_removed" and j.get("stage") == "closed"
            and norm_title(j.get("title")) == tt and same_company(j.get("company"), company)]
    hits.sort(key=lambda j: (0 if j.get("verdict") == "pursue" else 1, -(j.get("score") or 0)))
    return hits[0] if hits else None


def note_repost(rec, url, today):
    """A gone posting is back under a new id. The URL joins the record as an alias; posting reads active again (method
    repost, verified by the next nightly check) with the dates the report and the board show; a non-shortlist role
    reopens into the Inbox, a shortlist role stays closed for the owner to reopen (2026-10-07)."""
    cu = canonical_url(url)
    known = [canonical_url(rec.get("url"))] + [canonical_url(a) for a in rec.get("aliases") or []]
    if cu and cu not in known:
        rec.setdefault("aliases", []).append(cu)
    prev = rec.get("posting") or {}
    p = {k: v for k, v in prev.items() if k not in ("kept", "conflict")}
    p.update(state="active", since=today.isoformat(), streak=0, method="repost", http=None,
             evidence=f"reposted as {cu}", url_checked=cu, frozen=False,
             reposted=today.isoformat(), repost_of=rec.get("url"), closed_on=rec.get("stage_date") or prev.get("since"))
    rec["posting"] = p
    if rec.get("verdict") != "pursue":
        rec["stage"], rec["stage_date"], rec["outcome"] = None, None, None
        rec["stage_ts"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")   # an older stages row must not re-close it
    return rec


# ---------------------------------------------------------------- commands

def cmd_run(args):
    cfg = load_config()
    p = paths(cfg)
    data = load_jobs(p)
    today = date.today()
    only = [s.strip() for s in args.only_ids.split(",") if s.strip()] if args.only_ids else None
    rows = select(data, cfg, today, all_rows=args.all, only_ids=only)
    # APIs and plain pages first; LinkedIn last so a block there costs nothing else.
    rows.sort(key=lambda j: (candidates(j)[0][0] if candidates(j) else 9, j["id"]))
    budget = args.cap_linkedin
    counts = {s: 0 for s in STATES}
    queue, blocked_note, skipped = [], None, 0
    tdir = tools_dir(p)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for i, rec in enumerate(rows):
        res, used, blocked = check_record(rec, today, budget)
        budget -= used
        if blocked and budget > 0:
            blocked_note = f"LinkedIn answered {res['http']} at row {i + 1}; the rest of its rows were left unreachable"
            budget = 0
        state = "unknown" if res["state"] == "ambiguous" else res["state"]
        print(f"{rec['id']} {state:11} {res['method']:15} {res['evidence']}  [{brief(rec)}]")
        if state == "skipped":
            skipped += 1
            continue
        counts[state] += 1
        if not args.dry_run:
            rec["posting"] = merge_posting(rec.get("posting"), res, today)
            log_line(p, {"ts": now, "id": rec["id"], "state": state, "method": res["method"], "http": res.get("http"),
                         "url": res.get("url_checked"), "evidence": res.get("evidence")})
            if res["state"] == "ambiguous" and rec.get("verdict") == "pursue":
                (tdir / "pages" / f"{rec['id']}.txt").write_text(res.get("page_text") or "", encoding="utf-8")
                queue.append({"id": rec["id"], "title": rec.get("title"), "company": rec.get("company"),
                              "url": res.get("url_checked"), "page": f"Tools/posting-check/pages/{rec['id']}.txt",
                              "why": res["evidence"], "signals": rec["posting"].get("conflict")})
        if res["method"] != "none" and i + 1 < len(rows):
            lo, hi = LINKEDIN_PACE if res["method"] == "linkedin-guest" else OTHER_PACE
            time.sleep(random.uniform(lo, hi))
    closed_off = auto_close(data, cfg, today) if not args.dry_run else []
    for j in closed_off:
        log_line(p, {"ts": now, "id": j["id"], "state": "auto_closed", "method": "rule", "http": None,
                     "url": (j.get("posting") or {}).get("url_checked"), "evidence": "not on the shortlist; posting gone"})
    if not args.dry_run:
        save_jobs(p, data)
        (tdir / "queue.json").write_text(json.dumps({"asof": today.isoformat(), "rows": queue}, ensure_ascii=False, indent=1) + "\n",
                                         encoding="utf-8", newline="\n")
    stale = sum(1 for j in board_rows(data, cfg) if is_stale(j, today))
    summary = (f"checked {len(rows)}, active {counts['active']}, closed {counts['closed']}, removed {counts['removed']}, "
               f"unreachable {counts['unreachable']}, unknown {counts['unknown']}, stale {stale}")
    if skipped:
        summary += f"; {skipped} LinkedIn rows skipped at the cap"
    if closed_off:
        summary += f"; {len(closed_off)} non-shortlist roles closed off the board (posting gone)"
    if blocked_note:
        summary += f". {blocked_note}"
    if args.dry_run:
        summary += " (dry run, nothing written)"
    print(summary)


def cmd_apply(args):
    cfg = load_config()
    p = paths(cfg)
    data = load_jobs(p)
    rec = by_id(data).get(args.id)
    if not rec:
        raise SystemExit(f"no record {args.id}")
    if args.state not in ("active", "closed", "removed", "unknown"):
        raise SystemExit("state must be active, closed, removed or unknown")
    today = date.today()
    conf = float(args.confidence)
    state = args.state if conf >= 0.7 else "unknown"
    ev = args.evidence.strip()
    if state != args.state:
        ev = f"model unsure ({conf:.2f}): {ev}"
    prev = rec.get("posting") or {}
    res = {"state": state, "method": "model", "http": prev.get("http"), "evidence": ev, "url_checked": prev.get("url_checked")}
    # The model's call replaces tonight's script result rather than stacking a second check on it.
    base = dict(prev)
    if base.get("checked") == today.isoformat():
        base["checks"] = max((base.get("checks") or 1) - 1, 0)
        base["streak"] = max((base.get("streak") or 1) - 1, 0)
        if base.get("since") == today.isoformat():
            base["state"] = None
    rec["posting"] = merge_posting(base, res, today, model=True)
    rec["posting"].pop("conflict", None)
    save_jobs(p, data)
    log_line(p, {"ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "id": rec["id"], "state": state,
                 "method": "model", "http": prev.get("http"), "url": prev.get("url_checked"), "evidence": ev,
                 "confidence": conf})
    print(f"{rec['id']} {state} ({conf:.2f}) {ev}  [{brief(rec)}]")


def report_block(data, cfg, today, last_asof):
    rows = board_rows(data, cfg)
    # Only shortlist roles are listed for the owner (2026-10-07); the rest were closed by the rule and are counted.
    gone = [j for j in rows if (j.get("posting") or {}).get("state") in GONE and j.get("verdict") == "pursue"
            and not (j.get("posting") or {}).get("kept")]
    new_gone = [j for j in gone if not last_asof or (j["posting"].get("since") or "") > last_asof]
    unknown = [j for j in rows if (j.get("posting") or {}).get("state") == "unknown" and j.get("verdict") == "pursue"]
    auto = [j for j in data["jobs"] if j.get("outcome") == "posting_removed" and j.get("verdict") != "pursue"
            and (not last_asof or (j.get("stage_date") or "") > last_asof)]
    unreach = [j for j in rows if (j.get("posting") or {}).get("state") == "unreachable"]
    stale = sorted((j for j in rows if is_stale(j, today)), key=lambda j: j.get("date_first_seen") or "")
    checked = [j for j in rows if (j.get("posting") or {}).get("checked") == today.isoformat()]

    def when(j):
        s = j["posting"].get("since") or ""
        return datetime.strptime(s, "%Y-%m-%d").strftime("%b %d").replace(" 0", " ") if s else ""

    reposted = sorted((j for j in data["jobs"] if (j.get("posting") or {}).get("reposted")
                       and (not last_asof or j["posting"]["reposted"] > last_asof)), key=lambda j: -(j.get("score") or 0))

    def day(s):
        return datetime.strptime(s, "%Y-%m-%d").strftime("%b %d").replace(" 0", " ") if s else "?"

    lines = [f"POSTINGS: {len(checked)} checked last night."]
    for j in reposted:
        p = j["posting"]
        where = ("on your shortlist, closed; say the word to reopen it" if j.get("verdict") == "pursue"
                 else "back in the Inbox with a Reposted chip")
        lines.append(f"REPOSTED: {j.get('company')} reposted {j.get('title')}, closed {day(p.get('closed_on'))}, "
                     f"back {day(p.get('reposted'))}; {where}. {p.get('url_checked')}")
    if auto:
        lines.append(f"Closed off the board, not on your shortlist: {len(auto)}.")
    if new_gone:
        lines.append(f"Shortlist postings gone since the last post ({len(new_gone)}), confirm on the Closed tab:")
        for j in sorted(new_gone, key=lambda j: -(j.get("score") or 0)):
            tag = "Pursue, " if j.get("verdict") == "pursue" else "Maybe, " if j.get("verdict") == "maybe" else ""
            lines.append(f"- {brief(j)} · posting {j['posting']['state']} {when(j)} ({tag}{j['posting'].get('evidence')})")
    else:
        lines.append("Shortlist postings gone since the last post: none.")
    if unknown:
        lines.append(f"Needs a look ({len(unknown)}):")
        for j in sorted(unknown, key=lambda j: -(j.get("score") or 0)):
            lines.append(f"- {brief(j)} · {j['posting'].get('evidence')}")
    if unreach:
        only = sum(1 for j in unreach if (j["posting"].get("evidence") or "").startswith("only Indeed"))
        li = sum(1 for j in unreach if j["posting"].get("method") == "linkedin-guest")
        parts = [f"{only} with only Indeed or Glassdoor links" if only else "", f"{li} LinkedIn blocked" if li else "",
                 f"{len(unreach) - only - li} bot-walled elsewhere" if len(unreach) - only - li > 0 else ""]
        lines.append(f"Unverifiable: {len(unreach)} (" + "; ".join(x for x in parts if x) + ").")
    if stale:
        top = "; ".join(f"{brief(j)} ({j.get('date_first_seen')})" for j in stale[:3])
        lines.append(f"STALE (still posted, no move, {STALE_DAYS}+ days): {len(stale)}. Oldest: {top}.")
    payload = {"asof": today.isoformat(), "checked": len(checked), "gone": [j["id"] for j in gone], "auto_closed": [j["id"] for j in auto],
               "reposted": [j["id"] for j in reposted],
               "new_gone": [j["id"] for j in new_gone], "unknown": [j["id"] for j in unknown],
               "unreachable": [j["id"] for j in unreach], "stale": [j["id"] for j in stale], "text": "\n".join(lines)}
    return payload


def cmd_report(args):
    cfg = load_config()
    p = paths(cfg)
    data = load_jobs(p)
    today = date.today()
    tdir = tools_dir(p)
    f = tdir / "report.json"
    last = None
    if f.exists():
        try:
            last = json.loads(f.read_text(encoding="utf-8")).get("asof")
        except Exception:
            last = None
    if last == today.isoformat():
        # a rerun the same morning keeps the "since the last post" window from the previous day's report
        try:
            last = json.loads(f.read_text(encoding="utf-8")).get("previous_asof")
        except Exception:
            last = None
    payload = report_block(data, cfg, today, last)
    payload["previous_asof"] = last
    if not args.print_only:
        f.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(payload["text"])


def cmd_reconcile(args):
    cfg = load_config()
    p = paths(cfg)
    data = load_jobs(p)
    today = date.today()
    done = auto_close(data, cfg, today)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for j in done:
        log_line(p, {"ts": now, "id": j["id"], "state": "auto_closed", "method": "rule", "http": None,
                     "url": (j.get("posting") or {}).get("url_checked"), "evidence": "not on the shortlist; posting gone"})
        print(f"closed {brief(j)}")
    if done:
        save_jobs(p, data)
    print(f"{len(done)} non-shortlist roles closed off the board")


def cmd_keep(args):
    """the owner keeps a shortlist role whose ad is gone (Example Co, 2026-10-07): posting.kept records the date, the board and
    the report stop flagging it, and the weekly recheck still runs so a repost shows up."""
    cfg = load_config()
    p = paths(cfg)
    data = load_jobs(p)
    rec = by_id(data).get(args.id)
    if not rec:
        raise SystemExit(f"no record {args.id}")
    rec.setdefault("posting", {})["kept"] = date.today().isoformat()
    save_jobs(p, data)
    print(f"kept {brief(rec)}")


def cmd_selftest(args):
    cases = json.loads((REPO / "tests" / "posting_cases.json").read_text(encoding="utf-8"))
    today = date.today()
    bad = 0
    for c in cases:
        if "repost" in c:       # offline: does the ingest path see a repost here?
            hit = find_repost({"jobs": [c["repost"]["closed"]]}, c["repost"]["title"], c["repost"]["company"])
            state, ev = ("reposted", f"matches {hit['id']}") if hit else ("new", "no closed posting_removed match")
            url = ""
        elif "record" in c:     # live, every link the record carries, as the nightly run reads it
            res, _, _ = check_record(c["record"], today, 5)
            state, ev = ("unknown" if res["state"] == "ambiguous" else res["state"]), res["evidence"]
            url = " ".join([c["record"].get("url") or ""] + list(c["record"].get("aliases") or []))
        else:
            url = c["url"]
            fn, _ = checker_for(url)
            if not fn:
                state, ev = "unreachable", "never fetched"
            else:
                state, _, _, ev, _ = fn(url, today, c.get("title"))
                state = "unknown" if state == "ambiguous" else state
        ok = state == c["expect"]
        bad += not ok
        print(f"{'ok  ' if ok else 'MISS'} {c['name']}: {state} ({ev}); expected {c['expect']}")
        if url:
            time.sleep(random.uniform(*(LINKEDIN_PACE if "linkedin" in url else OTHER_PACE)) if args.pace else 1)
    print(f"{len(cases) - bad}/{len(cases)} cases agree")
    sys.exit(1 if bad else 0)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="check tonight's rows and write the posting field")
    r.add_argument("--cap-linkedin", type=int, default=45)
    r.add_argument("--only-ids", help="comma-separated record ids, regardless of schedule")
    r.add_argument("--all", action="store_true", help="every due board row, not the rolling share")
    r.add_argument("--dry-run", action="store_true", help="fetch and print, write nothing")
    r.set_defaults(fn=cmd_run)
    a = sub.add_parser("apply", help="the model pass's write path for one queued record")
    a.add_argument("--id", required=True)
    a.add_argument("--state", required=True)
    a.add_argument("--evidence", required=True)
    a.add_argument("--confidence", required=True)
    a.set_defaults(fn=cmd_apply)
    rp = sub.add_parser("report", help="write report.json and print the POSTINGS block")
    rp.add_argument("--print-only", action="store_true", help="print without moving the since-last-post window")
    rp.set_defaults(fn=cmd_report)
    kp = sub.add_parser("keep", help="the owner keeps a shortlist role whose ad is gone: stop flagging it")
    kp.add_argument("--id", required=True)
    kp.set_defaults(fn=cmd_keep)
    rc = sub.add_parser("reconcile", help="close every non-shortlist board row whose posting is gone (run does this too)")
    rc.set_defaults(fn=cmd_reconcile)
    st = sub.add_parser("selftest", help="the fixed cases in tests/posting_cases.json, live")
    st.add_argument("--pace", action="store_true", help="use the nightly pacing between cases")
    st.set_defaults(fn=cmd_selftest)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
