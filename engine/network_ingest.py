"""Connection layer ingest: LinkedIn Connections export -> who do I know at each target company.

Usage:  py engine/network_ingest.py [--raw PATH]

Reads   Projects/job-search/network/raw/Connections.csv (or the newest LinkedIn export
        in ~/Downloads, which it copies into raw/ first)
        Projects/job-search/jobs/leaderboard.md and jobs/baseline-2026-08-31.md (company keys)
        Projects/job-search/network/aliases.md, tags.md, leads.md (hand-maintained tables)
        Projects/job-search/people/*.md and Knowledge/People/*.md (LinkedIn URLs already in the vault)
        Knowledge/Reference/duxbury-yacht-club/DYC-2026-Member-Directory.csv (affinity proposals)
        Projects/job-search/network/connections-email.csv (connections learned from LinkedIn's "accepted your
        invitation" emails between exports; appended by the Monday mgmt-watch routine, same columns plus `source`;
        a row whose id the export already carries is dropped, so the export always wins on title and employer)
Writes  Projects/job-search/network/connections.csv (email column dropped)
        Projects/job-search/network/people.json (per company key)
        Projects/job-search/network/report.md (the human-readable pass)

Stdlib only. Idempotent: same inputs give byte-identical outputs.
Fuzzy employer matches are proposals in report.md, never applied automatically.
"""
import argparse
import csv
import difflib
import io
import json
import re
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path

from common import load_config  # noqa: E402  (engine config: vault path, DYC directory)

_CFG = load_config()
ROOT = Path(_CFG.get("personal_os", "."))
JS = Path(_CFG["vault"])
NET = JS / "network"
RAW_DIR = NET / "raw"
RAW = RAW_DIR / "Connections.csv"
DYC = Path(_CFG["dyc_directory"]) if _CFG.get("dyc_directory") else None
PEOPLE_DIRS = [JS / "people", ROOT / "Knowledge" / "People"]
BOARDS = [JS / "jobs" / "leaderboard.md", JS / "jobs" / "baseline-2026-08-31.md"]

FUZZY_MIN = 0.88
STOP = {"inc", "llc", "ltd", "corp", "corporation", "group", "company", "co", "plc", "the", "lp", "llp", "holdings"}


# ---------- helpers ----------

def norm(s):
    s = s.lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    words = [w for w in s.split() if w not in STOP]
    return " ".join(words)


def slug_from_url(url):
    m = re.search(r"linkedin\.com/in/([^/?#]+)", url or "")
    return m.group(1).strip().lower() if m else ""


def parse_date(s):
    s = (s or "").strip()
    for fmt in ("%d %b %Y", "%b %d, %Y", "%Y-%m-%d", "%d-%b-%y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return s


def read_md_table(path):
    """Rows of the first pipe table in a markdown file, as dicts keyed by header cell."""
    if not path.exists():
        return []
    rows, header = [], None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            if header is not None and rows:
                break
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if header is None:
            header = [c.lower() for c in cells]
            continue
        if all(re.fullmatch(r":?-+:?", c) for c in cells):
            continue
        if len(cells) < len(header):
            cells += [""] * (len(header) - len(cells))
        rows.append(dict(zip(header, cells)))
    return rows


# ---------- inputs ----------

def locate_raw(explicit):
    if explicit:
        src = Path(explicit)
        if src.suffix.lower() == ".zip":
            return extract_zip(src)
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, RAW)
        return RAW
    if RAW.exists():
        return RAW
    downloads = Path.home() / "Downloads"
    candidates = sorted(
        list(downloads.glob("Connections*.csv")) + list(downloads.glob("*LinkedInDataExport*.zip")),
        key=lambda p: p.stat().st_mtime, reverse=True)
    for src in candidates:
        if src.suffix.lower() == ".zip":
            with zipfile.ZipFile(src) as z:
                if not any(n.lower().endswith("connections.csv") for n in z.namelist()):
                    continue  # LinkedIn's first installment ships without Connections.csv
            print(f"using {src}")
            return extract_zip(src)
        print(f"using {src}")
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, RAW)
        return RAW
    sys.exit("No Connections.csv in network/raw/ or Downloads (the first-installment zip has none; "
             "wait for the full archive email). See network/linkedin-pass.md.")


def extract_zip(zpath):
    with zipfile.ZipFile(zpath) as z:
        name = next((n for n in z.namelist() if n.lower().endswith("connections.csv")), None)
        if not name:
            sys.exit(f"{zpath} has no Connections.csv")
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        RAW.write_bytes(z.read(name))
    return RAW


def read_connections(path):
    text = path.read_text(encoding="utf-8-sig")
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if l.startswith("First Name")), None)
    if start is None:
        sys.exit("Header row 'First Name,...' not found in the export")
    reader = csv.DictReader(io.StringIO("\n".join(lines[start:])))
    out = []
    for r in reader:
        first = (r.get("First Name") or "").strip()
        last = (r.get("Last Name") or "").strip()
        url = (r.get("URL") or "").strip()
        if not (first or last):
            continue
        sid = slug_from_url(url) or re.sub(r"[^a-z0-9]+", "-", f"{first} {last}".lower()).strip("-")
        out.append({
            "id": sid, "first": first, "last": last, "url": url,
            "company_raw": (r.get("Company") or "").strip(),
            "position": (r.get("Position") or "").strip(),
            "connected_on": parse_date(r.get("Connected On")),
        })
    out.sort(key=lambda c: (c["last"].lower(), c["first"].lower(), c["id"]))
    return out


EMAIL_CSV = NET / "connections-email.csv"


def merge_email_connections(conns):
    """Add connections learned from LinkedIn's acceptance emails since the last export (connections-email.csv).
    The export is the truth for anyone it carries; an email row only fills the gap until the next export."""
    if not EMAIL_CSV.exists():
        return conns
    have = {c["id"] for c in conns} | {c["url"].rstrip("/").lower() for c in conns if c.get("url")}
    added = 0
    with EMAIL_CSV.open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            url = (r.get("url") or "").strip()
            sid = (r.get("id") or "").strip() or slug_from_url(url) or re.sub(r"[^a-z0-9]+", "-", f"{r.get('first','')} {r.get('last','')}".lower()).strip("-")
            if not sid or sid in have or url.rstrip("/").lower() in have:
                continue
            conns.append({"id": sid, "first": (r.get("first") or "").strip(), "last": (r.get("last") or "").strip(), "url": url,
                          "company_raw": (r.get("company_raw") or "").strip(), "position": (r.get("position") or "").strip(),
                          "connected_on": (r.get("connected_on") or "").strip()})
            have.add(sid); added += 1
    if added:
        print(f"merged {added} connection(s) from {EMAIL_CSV.name} (not yet in the export)")
    conns.sort(key=lambda c: (c["last"].lower(), c["first"].lower(), c["id"]))
    return conns


def board_companies(aliases):
    """Company keys in board order (leaderboard first, then baseline extras).
    A board spelling that aliases.md maps elsewhere collapses into its target key."""
    keys = []
    for path in BOARDS:
        for row in read_md_table(path):
            c = row.get("company", "").strip()
            if not c:
                continue
            for k in (aliases.get(norm(c)) or [c]):
                if k not in keys:
                    keys.append(k)
    return keys


def load_aliases():
    out = {}
    for r in read_md_table(NET / "aliases.md"):
        src = r.get("linkedin_company", "").strip()
        keys = [k.strip() for k in r.get("company_key", "").split(";") if k.strip()]
        if src:
            out[norm(src)] = keys  # empty list = deliberate non-match, never proposed
    return out


def load_tags():
    out = {}
    for r in read_md_table(NET / "tags.md"):
        i, t = r.get("id", "").strip().lower(), r.get("tag", "").strip()
        if i and t:
            out.setdefault(i, {})[t] = r.get("source", "").strip()
    return out


def load_leads():
    return [r for r in read_md_table(NET / "leads.md") if r.get("company_key", "").strip()]


def vault_links():
    """slug -> vault-relative path of a person file that carries that LinkedIn URL."""
    out = {}
    for d in PEOPLE_DIRS:
        if not d.exists():
            continue
        for f in sorted(d.glob("*.md")):
            for m in re.finditer(r"linkedin\.com/in/([^/\s)\]]+)", f.read_text(encoding="utf-8")):
                out.setdefault(m.group(1).strip().lower(), str(f.relative_to(ROOT)).replace("\\", "/"))
    return out


def dyc_names():
    """(first, last) lowercase pairs for members and partners in the DYC directory."""
    names = {}
    if not DYC or not DYC.exists():
        return names
    with DYC.open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            ln, fn = (r.get("LastName") or "").strip(), (r.get("FirstName") or "").strip()
            if fn and ln:
                names[(fn.lower(), ln.lower())] = f"member since {r.get('YearJoined','').strip() or '?'}"
            p = (r.get("Partner") or "").strip()
            if "," in p:
                pl, pf = [x.strip() for x in p.split(",", 1)]
                if pf and pl:
                    names.setdefault((pf.lower(), pl.lower()), f"partner of {fn} {ln}")
    return names


# ---------- matching ----------

def match_company(company_raw, keys_by_norm, aliases):
    n = norm(company_raw)
    if not n:
        return [], None
    if n in keys_by_norm:
        return [keys_by_norm[n]], None
    if n in aliases:
        return aliases[n], None
    # proposal only: fuzzy or whole-word containment
    best, best_ratio = None, 0.0
    for kn, key in keys_by_norm.items():
        ratio = difflib.SequenceMatcher(None, n, kn).ratio()
        if ratio > best_ratio:
            best, best_ratio = key, ratio
        if len(kn) >= 4 and (re.search(rf"\b{re.escape(kn)}\b", n) or re.search(rf"\b{re.escape(n)}\b", kn)):
            return [], (key, max(ratio, 0.90), "contains")
    if best and best_ratio >= FUZZY_MIN:
        return [], (best, best_ratio, "fuzzy")
    return [], None


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", help="path to Connections.csv or a LinkedIn export zip")
    args = ap.parse_args()

    try:
        conns = read_connections(locate_raw(args.raw))
    except SystemExit as e:
        # No export on this machine (the mini keeps no raw/ folder): the current connections.csv is the base,
        # so the Monday routine can still fold in the acceptance-email rows and refresh people.json.
        cur = NET / "connections.csv"
        if not cur.exists():
            raise
        print(f"no raw export here ({str(e).split('.')[0]}); using the current connections.csv as the base")
        with cur.open(encoding="utf-8-sig", newline="") as fh:
            conns = [{"id": r["id"], "first": r["first"], "last": r["last"], "url": r["url"], "company_raw": r["company_raw"],
                      "position": r["position"], "connected_on": r["connected_on"]} for r in csv.DictReader(fh)]
    conns = merge_email_connections(conns)
    aliases = load_aliases()
    keys = board_companies(aliases)
    keys_by_norm = {norm(k): k for k in keys}
    tags = load_tags()
    leads = load_leads()
    vault = vault_links()
    dyc = dyc_names()

    unresolved = {}   # company_raw -> (key, ratio, how, count)
    for c in conns:
        matched, proposal = match_company(c["company_raw"], keys_by_norm, aliases)
        c["company_key"] = ";".join(matched)
        if proposal:
            key, ratio, how = proposal
            u = unresolved.setdefault(c["company_raw"], [key, ratio, how, 0])
            u[3] += 1
        # taggers
        t = tags.setdefault(c["id"], {})
        blob = f"{c['company_raw']} {c['position']}".lower()
        if "prior employer" in blob and "prior-employer-alumni" not in t:
            t["prior-employer-alumni"] = "position-text"
        c["tags"] = sorted(t)
        c["vault"] = vault.get(c["id"], "")

    # DYC proposals (only for people not already tagged dyc)
    dyc_props = []
    for c in conns:
        note = dyc.get((c["first"].lower(), c["last"].lower()))
        if note and "dyc" not in c["tags"]:
            dyc_props.append((c, note))

    # connections.csv
    NET.mkdir(parents=True, exist_ok=True)
    with (NET / "connections.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["id", "first", "last", "url", "company_raw", "position", "connected_on", "company_key"])
        for c in conns:
            w.writerow([c["id"], c["first"], c["last"], c["url"], c["company_raw"], c["position"], c["connected_on"], c["company_key"]])

    # people.json
    people = {}
    for k in keys:
        people[k] = {"first": [], "second": [], "affinity_only": [], "vault": []}
    for c in conns:
        for k in [x for x in c["company_key"].split(";") if x]:
            people[k]["first"].append({
                "id": c["id"], "name": f"{c['first']} {c['last']}".strip(), "title": c["position"],
                "url": c["url"], "since": c["connected_on"][:4], "tags": c["tags"], "vault": c["vault"],
            })
    for l in leads:
        k = l["company_key"]
        if k not in people:
            people[k] = {"first": [], "second": [], "affinity_only": [], "vault": []}
        entry = {f: l.get(f, "") for f in ("name", "title", "affinity", "degree", "via", "source", "date")}
        (people[k]["second"] if l.get("via") else people[k]["affinity_only"]).append(entry)
    for k, v in people.items():
        v["first"].sort(key=lambda p: (p["name"].lower(), p["id"]))
        v["second"].sort(key=lambda p: p["name"].lower())
        v["affinity_only"].sort(key=lambda p: p["name"].lower())
        v["vault"] = sorted({p["vault"] for p in v["first"] if p["vault"]})
    (NET / "people.json").write_text(json.dumps(people, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    # report.md
    matched_n = sum(1 for c in conns if c["company_key"])
    lines = ["# Who do I know: connection report", "",
             f"Generated by `Tools/network_ingest.py`. {len(conns)} connections in the export, "
             f"{matched_n} at a board company, {len(keys)} board companies, "
             f"{sum(1 for k in keys if people[k]['first'] or people[k]['second'] or people[k]['affinity_only'])} with a known path.",
             "", "Board order follows `jobs/leaderboard.md` then the baseline extras. Tags come from `tags.md`; "
             "the sections at the bottom are proposals for the owner to accept into `aliases.md` and `tags.md`.", ""]
    lines.append("## Companies with a path")
    lines.append("")
    none = []
    for k in keys:
        v = people[k]
        if not (v["first"] or v["second"] or v["affinity_only"]):
            none.append(k)
            continue
        lines.append(f"### {k}")
        for p in v["first"]:
            tag = f" [{', '.join(p['tags'])}]" if p["tags"] else ""
            vlt = f" ({p['vault']})" if p["vault"] else ""
            since = f", connected {p['since']}" if p["since"] else ""
            lines.append(f"- 1st: [{p['name']}]({p['url']}), {p['title'] or 'title unknown'}{since}{tag}{vlt}")
        for p in v["second"]:
            lines.append(f"- 2nd: {p['name']}, {p['title']}, via {p['via']} ({p['affinity'] or 'no affinity'}, {p['source']} {p['date']})")
        for p in v["affinity_only"]:
            lines.append(f"- affinity: {p['name']}, {p['title']} ({p['affinity']}, {p['source']} {p['date']})")
        lines.append("")
    lines.append("## No known path")
    lines.append("")
    lines.append(", ".join(none) if none else "none")
    lines.append("")
    lines.append("## Unresolved employer matches (accept into aliases.md or ignore)")
    lines.append("")
    if unresolved:
        lines.append("| LinkedIn company | Connections | Candidate key | How | Ratio |")
        lines.append("|---|---|---|---|---|")
        for raw_name, (key, ratio, how, n) in sorted(unresolved.items(), key=lambda x: (-x[1][3], x[0].lower())):
            lines.append(f"| {raw_name} | {n} | {key} | {how} | {ratio:.2f} |")
    else:
        lines.append("none")
    lines.append("")
    lines.append("## DYC directory name matches (confirm into tags.md as `dyc`, source `dyc-directory`)")
    lines.append("")
    if dyc_props:
        lines.append("| id | Name | LinkedIn company | DYC note |")
        lines.append("|---|---|---|---|")
        for c, note in dyc_props:
            lines.append(f"| {c['id']} | {c['first']} {c['last']} | {c['company_raw']} | {note} |")
    else:
        lines.append("none")
    lines.append("")
    lines.append("## Top employers in the network (not necessarily on the board)")
    lines.append("")
    counts = {}
    for c in conns:
        if c["company_raw"]:
            counts[c["company_raw"]] = counts.get(c["company_raw"], 0) + 1
    top = sorted(counts.items(), key=lambda x: (-x[1], x[0].lower()))[:40]
    lines.append("| Employer | Connections | On board as |")
    lines.append("|---|---|---|")
    for name, n in top:
        keys_hit = ";".join(match_company(name, keys_by_norm, aliases)[0])
        lines.append(f"| {name} | {n} | {keys_hit} |")
    lines.append("")
    (NET / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"{len(conns)} connections, {matched_n} matched to board companies, "
          f"{len(unresolved)} unresolved employers, {len(dyc_props)} DYC proposals")
    print(f"wrote {NET / 'connections.csv'}, people.json, report.md")


if __name__ == "__main__":
    main()
