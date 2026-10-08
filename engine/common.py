"""Shared helpers for the job-search engine: config, paths, ids, normalization, jobs.json I/O.

Every script in engine/ starts with `cfg = load_config()` and reaches the vault through `paths(cfg)`.
Nothing here knows about the owner specifically; the vault path is the only personal thing, and it lives in
config.json (git-ignored).
"""
import hashlib
import json
import os
import shutil
import subprocess
import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

REPO = Path(__file__).resolve().parent.parent

VERDICTS = ("pursue", "maybe", "pass")
# Pursue ladder (the owner, 2026-09-15): a yes lands on the shortlist; closed roles leave the board for Screened out.
STAGES = ("shortlist", "researching", "outreach", "applied", "interviewing", "offer", "closed")
# posting_removed (2026-10-06): the ad was filled or taken down and the owner confirmed it on the board; not a pass by either side
OUTCOMES = ("no_response", "rejected", "withdrew", "accepted", "posting_removed")
LEGACY_OUTCOME = {"ghosted": "no_response"}
# stage -> the job-file Status value the vault's SPEC.md uses
STAGE_TO_STATUS = {
    "shortlist": "Shortlist",
    "researching": "Researching",
    "outreach": "Reached out",
    "applied": "Applied",
    "interviewing": "Interviewing",
    "offer": "Offer",
    "closed": "Closed",
}


_OP_CACHE = {}


def _resolve_op(value):
    """Strings of the form op://<vault>/<item>/<field> are 1Password references; read them through the CLI.

    config.json holds the reference, 1Password holds the secret (Decisions/log.md 2026-10-06). Plain values
    still work, so a machine whose config.json has the key pasted in (the mini) needs no change. Each
    reference is read once per process."""
    if isinstance(value, dict):
        return {k: _resolve_op(v) for k, v in value.items()}
    if not (isinstance(value, str) and value.startswith("op://")):
        return value
    if value not in _OP_CACHE:
        op = shutil.which("op") or os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Packages",
                                                   "AgileBits.1Password.CLI_Microsoft.Winget.Source_8wekyb3d8bbwe", "op.exe")
        try:
            r = subprocess.run([op, "read", "--no-newline", value], capture_output=True, text=True, stdin=subprocess.DEVNULL)
        except OSError as e:
            raise SystemExit(f"1Password CLI (op) not found while reading {value}: {e}")
        if r.returncode:
            raise SystemExit(f"1Password could not read {value}: {r.stderr.strip()}")
        _OP_CACHE[value] = r.stdout
    return _OP_CACHE[value]


def load_config():
    p = REPO / "config.json"
    if not p.exists():
        raise SystemExit("config.json missing: copy config.example.json to config.json and set the vault path")
    return _resolve_op(json.loads(p.read_text(encoding="utf-8")))


class Paths:
    def __init__(self, cfg):
        self.vault = Path(cfg["vault"])
        self.jobs_dir = self.vault / "jobs"
        self.jobs_json = self.jobs_dir / "jobs.json"
        self.companies_json = self.jobs_dir / "companies.json"
        self.geocache = self.jobs_dir / "geocache.json"
        self.inbox_csv = self.jobs_dir / "inbox.csv"
        self.leaderboard = self.jobs_dir / "leaderboard.md"
        self.pipeline = self.vault / "meta" / "pipeline.md"
        self.people_json = self.vault / "network" / "people.json"
        self.network = self.vault / "network"
        self.people_dir = self.vault / "people"
        self.companies_dir = self.vault / "companies"
        # The vault sits at Personal-OS/Projects/job-search; the radar's heartbeat and the feedback log live in
        # Personal-OS/Tools. A vault elsewhere (the sample one) simply has neither file.
        self.personal_os = self.vault.parents[1] if len(self.vault.parents) > 1 else self.vault
        self.radar_heartbeat = self.personal_os / "Tools" / "job-radar-heartbeat.md"
        self.feedback_log = self.personal_os / "Tools" / "feedback" / "job-radar.md"


def paths(cfg):
    return Paths(cfg)


# ---------- normalization ----------

_TRACKING = {"utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "refId", "trackingId",
             "trk", "originalSubdomain", "position", "pageNum", "from", "vjs", "tk", "advn", "adid", "src"}


def canonical_url(url):
    """Stable form of a posting URL: lowercase host, no tracking params, no trailing slash.
    LinkedIn -> linkedin.com/jobs/view/<id>; Indeed keeps only jk=; Glassdoor keeps only jl= (if present)."""
    if not url:
        return ""
    url = url.strip()
    parts = urlsplit(url)
    host = parts.netloc.lower().replace("www.", "")
    path = parts.path.rstrip("/")
    q = dict(parse_qsl(parts.query, keep_blank_values=False))
    if "linkedin.com" in host:
        m = re.search(r"/jobs/view/(\d+)", path)
        if m:
            return f"https://linkedin.com/jobs/view/{m.group(1)}"
        q = {}
    elif "indeed.com" in host:
        q = {"jk": q["jk"]} if "jk" in q else {}
        path = "/viewjob" if q else path
    elif "glassdoor.com" in host:
        q = {"jl": q["jl"]} if "jl" in q else {}
    else:
        q = {k: v for k, v in q.items() if k not in _TRACKING}
    query = urlencode(sorted(q.items()))
    return urlunsplit(("https", host, path, query, ""))


def job_id(url, title="", company=""):
    """First 10 hex of sha1 over the canonical URL; falls back to title|company when there is no URL."""
    key = canonical_url(url) or f"{norm(title)}|{norm(company)}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]


_STOP = {"inc", "llc", "ltd", "corp", "corporation", "group", "company", "co", "plc", "the", "lp", "llp", "holdings"}


def norm(s):
    """Same normalization network_ingest.py uses for employer strings: lowercase, strip punctuation and stopwords."""
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return " ".join(w for w in s.split() if w not in _STOP)


def slug(s):
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return s


# ---------- jobs.json ----------

RECORD_FIELDS = [
    "id", "aliases", "url", "title", "company", "company_key", "location", "source", "date_first_seen",
    "score", "score_kind", "why", "mismatch", "comp", "flag",
    "verdict", "verdict_date", "calibration", "note", "status_note", "rubric_version",
    "stage", "stage_date", "outcome", "next_step", "job_file", "excluded", "human_path",
]


def new_record(**kw):
    r = {k: None for k in RECORD_FIELDS}
    r["aliases"] = []
    r["flag"] = False
    r["excluded"] = None
    r.update(kw)
    return r


def load_jobs(p):
    if not p.jobs_json.exists():
        return {"asof": None, "jobs": []}
    return json.loads(p.jobs_json.read_text(encoding="utf-8"))


def save_jobs(p, data):
    data["jobs"].sort(key=lambda j: (-(j.get("score") or 0), j.get("date_first_seen") or "", j["id"]))
    p.jobs_json.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")


def by_id(data):
    return {j["id"]: j for j in data["jobs"]}


def find_by_url(data, url):
    cu = canonical_url(url)
    if not cu:
        return None
    for j in data["jobs"]:
        if canonical_url(j.get("url")) == cu or cu in [canonical_url(a) for a in j.get("aliases", [])]:
            return j
    return None


def norm_title(title):
    """Title without a trailing location/remote qualifier, e.g. 'AI Lead (Remote)' -> 'ai lead'."""
    t = re.sub(r"\s*[\(\-–]\s*(remote|hybrid|us based[^)]*|[a-z ]+, [a-z]{2})\)?\s*$", "", (title or "").strip(), flags=re.I)
    return norm(t)


def same_company(a, b):
    """Equal after normalization, one contains the other, or one's words are a subset of the other's
    ('large cap pe via saragossa' vs 'large cap pe firm via saragossa')."""
    a, b = norm(a), norm(b)
    if not (a and b):
        return False
    sa, sb = set(a.split()), set(b.split())
    if a == b or a in b or b in a or sa <= sb or sb <= sa:
        return True
    # Same first two words (one firm Advisory Group vs one firm US, 2026-10-07): the sweeps minted two cards
    # for one Consulting AI Director and the owner reviewed both. Only ever combined with a title match by the callers.
    wa, wb = a.split(), b.split()
    return len(wa) >= 2 and len(wb) >= 2 and wa[:2] == wb[:2]


def find_by_title_company(data, title, company):
    """Exact normalized match first, then a loose one (title minus qualifiers, company containment)."""
    t, c = norm(title), norm(company)
    for j in data["jobs"]:
        if norm(j.get("title")) == t and norm(j.get("company")) == c:
            return j
    tt = norm_title(title)
    for j in data["jobs"]:
        if norm_title(j.get("title")) == tt and same_company(j.get("company"), company):
            return j
    return None


def rubric_version(p):
    """The live rubric version, from the "Current version: vX.Y" line of <vault>/jobs/rubric.md. The deep pass
    stamps it on each record it scores so the card can say which rules produced the score (the owner, 2026-10-07)."""
    f = p.jobs_dir / "rubric.md"
    if not f.exists():
        return None
    m = re.search(r"Current version:\s*\**(v[\d.]+)", f.read_text(encoding="utf-8"))
    return m.group(1) if m else None


def sibling_map(jobs):
    """For each record, the other records at the same company that the owner already decided on (verdict or closed),
    so a near-twin posting says so on its card ("Didn't I already see this job?", 2026-09-28; four such pairs reached
    the board in three weeks, calibration 2026-10-07). Different titles stay separate records; this only links them."""
    out = {}
    decided = [j for j in jobs if j.get("verdict") or j.get("stage") == "closed"]
    for j in jobs:
        rows = []
        for o in decided:
            if o["id"] == j["id"] or not same_company(o.get("company"), j.get("company")):
                continue
            what = o.get("verdict") or "closed"
            when = str(o.get("verdict_ts") or o.get("verdict_date") or o.get("stage_date") or "")[:10]
            rows.append({"id": o["id"], "title": o.get("title"), "what": f"{what} {when}".strip()})
        if rows:
            out[j["id"]] = sorted(rows, key=lambda r: r["what"], reverse=True)[:4]
    return out


def merge_duplicates(data):
    """Same posting seen under several locations or boards (same title and company): keep the earliest record,
    fold the others in as aliases with a joined location list. Records that already carry a verdict or a job
    file are always the survivor. Returns the number of records folded."""
    by_title = {}
    for j in data["jobs"]:
        by_title.setdefault(norm_title(j.get("title")), []).append(j)
    groups = {}
    for t, js in by_title.items():
        if not t:
            continue
        clusters = []
        for j in js:
            for c in clusters:
                if same_company(c[0].get("company"), j.get("company")):
                    c.append(j)
                    break
            else:
                clusters.append([j])
        for i, c in enumerate(clusters):
            groups[(t, i)] = c
    folded = 0
    for key, js in groups.items():
        if len(js) < 2:
            continue
        # A Pursue is always the survivor (2026-10-07: the first run of the looser company match folded the owner's one firm
        # Pursue into the twin he had passed on because the Pass was seen first); then any verdict or job file; then age.
        rank = {"pursue": 0, "maybe": 1, "pass": 2}
        js.sort(key=lambda j: (rank.get(j.get("verdict"), 1 if j.get("job_file") else 3), j.get("date_first_seen") or "9999", j["id"]))
        keep, rest = js[0], js[1:]
        locs = [keep.get("location")] if keep.get("location") else []
        for r in rest:
            if r.get("url") and r["url"] != keep.get("url"):
                keep["aliases"].append(r["url"])
            keep["aliases"].extend(a for a in r.get("aliases", []) if a not in keep["aliases"])
            if r.get("location") and r["location"] not in locs:
                locs.append(r["location"])
            for k in ("score", "why", "comp", "location"):
                if keep.get(k) is None and r.get(k) is not None:
                    keep[k] = r[k]
            if keep.get("score_kind") is None and r.get("score_kind"):
                keep["score_kind"] = r["score_kind"]
            data["jobs"].remove(r)
            folded += 1
        if len(locs) > 1:
            keep["location"] = "; ".join(locs)
    return folded
