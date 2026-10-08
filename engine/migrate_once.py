"""One-off: seed jobs.json and companies.json from the vault's legacy files.

Sources (all read-only here): jobs/review-data.json (56 baseline cards + verdicts keyed by page rank),
jobs/inbox.csv (every posting the radar collected), jobs/leaderboard.md (hand/radar-maintained ranks and
statuses), meta/pipeline.md (next steps), jobs/*.md (job files: status, verdict, company link).

Run once: py engine/migrate_once.py [--force]. Refuses to overwrite an existing jobs.json without --force.
After this, build.py owns jobs.json, leaderboard.md, and pipeline.md; review-data.json is retired.
"""
import csv
import json
import re
import sys
from datetime import date

from common import (load_config, paths, new_record, save_jobs, canonical_url, job_id, norm,
                    find_by_url, find_by_title_company, merge_duplicates)

# rows removed from the leaderboard under hard exclusions, with the reason (from leaderboard.md header + rubric)
EXCLUDED = {
    ("Head of AI Product", "Fitch Solutions"): "NYC three days a week: any required on-site days outside Boston commuting range",
    ("Director, Services Ops AI Governance & AI-First Ways of Working", "Citi"): "NYC three days on site",
    ("US Commercial AI, Portfolio Lead", "Pfizer"): "company blocklist (sleepy pharma, shrinking)",
    ("AI Transformation Technology Enablement and Platform Leader", "BDO USA"): "M365 Copilot rollout role",
    ("Director, AI Adoption & Change Management", "phData"): "50% travel",
    ("Director, AI Enablement", "Scotiabank"): "Dallas, no remote option",
    ("Agentic Operations Consultant", "Salesforce"): "multi-week on-site POC consulting motion; Salesforce blocklisted",
    ("AI Business Solutions, Senior Director", "EY-Parthenon"): "client-delivery consulting with travel",
    ("AI Solution & Enablement Lead", "LG Energy Solution Vertech"): "about 90 minutes each way",
    ("Senior Program Manager, AI Partnerships and Enablement", "Boston Scientific"): "about 90 minutes each way, three days a week",
    ("Deployment Strategist", "Salesforce"): "Salesforce blocklisted",
    ("Forward Deployed AI Lead", "Caylent"): "50% travel; 8+ years software development and a vendor cert as hard requirements",
    ("AI Strategist", "Tenex"): "NYC five days on site",
}

STATUS_TO_STAGE = {"Researching": "researching", "Reached out": "outreach", "In process": "applied",
                   "Offer": "offer", "Closed": "closed"}


def parse_table_rows(text):
    rows = []
    for ln in text.splitlines():
        if ln.startswith("| ") and not ln.startswith("| Rank") and not ln.startswith("| Company |") and not ln.startswith("|--"):
            cells = [c.strip() for c in ln.strip().strip("|").split(" | ")]
            rows.append(cells)
    return rows


def main():
    force = "--force" in sys.argv
    cfg = load_config()
    p = paths(cfg)
    if p.jobs_json.exists() and not force:
        raise SystemExit(f"{p.jobs_json} exists; pass --force to rebuild it from the legacy files")

    rd = json.loads((p.jobs_dir / "review-data.json").read_text(encoding="utf-8"))
    data = {"asof": date.today().isoformat(), "jobs": []}

    # 1. inbox.csv: every posting the radar has collected
    with p.inbox_csv.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if find_by_url(data, row["url"]):
                continue
            data["jobs"].append(new_record(
                id=job_id(row["url"]), url=canonical_url(row["url"]), title=row["title"].strip(),
                company=row["company"].strip(), location=row["location"].strip() or None,
                source=f"{row['board']}:{row['alert_name']}", date_first_seen=row["date_first_seen"],
                score=(int(row["score"]) if row.get("score") else None),
                score_kind=("title" if row.get("score") else None), why=row.get("why") or None,
            ))
    n_inbox = len(data["jobs"])

    # 2. baseline cards + verdicts (deep scores, authoritative)
    fb = rd.get("feedback", {})
    for c in rd["jobs"]:
        j = find_by_url(data, c["url"]) or find_by_title_company(data, c["title"], c["company"])
        if not j:
            j = new_record(id=job_id(c["url"], c["title"], c["company"]), url=canonical_url(c["url"]),
                           date_first_seen=rd.get("baseline", "2026-08-31"), source="baseline-2026-08-31")
            data["jobs"].append(j)
        if canonical_url(c["url"]) and canonical_url(c["url"]) != j["url"]:
            j["aliases"].append(canonical_url(c["url"]))
        j.update(title=c["title"], company=c["company"], location=c.get("location") or j["location"],
                 comp=c.get("comp"), score=c["score"], score_kind="deep", why=c.get("why"),
                 mismatch=c.get("mismatch"), flag=bool(c.get("flag")))
        j["card"] = {"math": c.get("math"), "job": c.get("job", []), "note": c.get("note")}
        v = fb.get(str(c["rank"]))
        if v and v.get("v"):
            j["verdict"] = v["v"].lower()
            j["verdict_date"] = rd.get("feedback_asof", "2026-09-03")
            j["calibration"] = (v.get("cal") or None)
            j["note"] = (v.get("note") or "").strip() or None
        key = (c["title"], c["company"])
        if key in EXCLUDED:
            j["excluded"] = EXCLUDED[key]
    n_cards = len(rd["jobs"])

    # 3. leaderboard rows: ranks, flags, status notes, title-level scores for radar newcomers
    lb = p.leaderboard.read_text(encoding="utf-8")
    table = lb.split("## Closed")[0]
    n_lb = 0
    for cells in parse_table_rows(table):
        if len(cells) < 8 or not cells[0].isdigit():
            continue
        rank, title, company, score, flag, location, status, source = cells[:8]
        j = find_by_title_company(data, title, company)
        if not j:
            j = new_record(id=job_id("", title, company), title=title, company=company, source=source,
                           date_first_seen="2026-08-31")
            data["jobs"].append(j)
        n_lb += 1
        if j["score"] is None:
            j["score"] = int(score)
            j["score_kind"] = "title"
        if not j["location"]:
            j["location"] = location
        if "⚑" in flag:
            j["flag"] = True
        m = re.match(r"New via radar (\d{4}-\d{2}-\d{2})", status)
        if m:
            j["date_first_seen"] = j["date_first_seen"] or m.group(1)
            if not j["source"] or ":" not in (j["source"] or ""):
                j["source"] = j["source"] or source
        elif ":" in status and status.split(":")[0].split(" (")[0] in ("Pass", "Maybe", "Pursue"):
            j["status_note"] = status.split(":", 1)[1].strip()
        if not j["source"]:
            j["source"] = source
    # Babel Street closed during the scan, never ranked: keep the memory
    if not find_by_title_company(data, "Senior Director, Generative & Agentic AI", "Babel Street"):
        data["jobs"].append(new_record(id=job_id("", "Senior Director, Generative & Agentic AI", "Babel Street"),
                                       title="Senior Director, Generative & Agentic AI", company="Babel Street",
                                       source="baseline-2026-08-31", date_first_seen="2026-08-31",
                                       verdict="pass", verdict_date="2026-08-31",
                                       status_note="found closed during the baseline scan; never ranked",
                                       excluded="posting closed"))

    # 4. job files: job_file, company link, stage from Status
    n_files = 0
    for f in sorted(p.jobs_dir.glob("*.md")):
        if f.name in ("leaderboard.md", "rubric.md", "baseline-scan-handoff.md") or f.name.startswith(("baseline-", "company-growth")):
            continue
        txt = f.read_text(encoding="utf-8")
        h1 = re.search(r"^# (.+)$", txt, re.M)
        url = re.search(r"^\*\*(?:URL|Job posting):\*\*\s*(\S+)", txt, re.M)
        company = re.search(r"^\*\*Company:\*\*\s*\[\[companies/([^\]|]+)", txt, re.M)
        status = re.search(r"^\*\*Status:\*\*\s*(.+)$", txt, re.M)
        j = find_by_url(data, url.group(1)) if url else None
        if not j and h1:
            m = re.match(r"(.+?) @ (.+)$", h1.group(1))
            if m:
                j = find_by_title_company(data, m.group(1), m.group(2))
        if not j:
            print(f"  no record for job file {f.name}; left unlinked")
            continue
        n_files += 1
        j["job_file"] = f"jobs/{f.stem}"
        if company:
            j["company_file"] = f"companies/{company.group(1)}"
        if status:
            st = status.group(1).split(":")[0].strip().split("  ")[0]
            stage = STATUS_TO_STAGE.get(st)
            if j["verdict"] == "pursue" or (j["verdict"] is None and stage and stage != "closed"):
                j["stage"] = stage or "researching"
                j["stage_date"] = j["verdict_date"] or "2026-09-03"

    # 5. pipeline.md next steps
    n_pipe = 0
    for cells in parse_table_rows(p.pipeline.read_text(encoding="utf-8")):
        if len(cells) < 5:
            continue
        company, role, status, next_step, dt = cells[:5]
        m = re.search(r"\[\[jobs/([^\]|]+)\]\]", role)
        j = None
        if m:
            j = next((x for x in data["jobs"] if x.get("job_file") == f"jobs/{m.group(1)}"), None)
        elif "anthropic" in company.lower():
            j = new_record(id=job_id("", "Services Partner", "Anthropic"), title="Services Partner", company="Anthropic",
                           company_file="companies/anthropic", source="hand", date_first_seen="2026-07-02",
                           verdict="pursue", verdict_date="2026-07-02", stage="researching", stage_date="2026-07-02")
            data["jobs"].append(j)
        if j and next_step and next_step != "None":
            j["next_step"] = next_step
            j["next_step_date"] = dt
            n_pipe += 1

    # The Long Game exploration: a networking thread with a job file, not a posting; keep the pipeline memory
    if (p.jobs_dir / "the-long-game-exploration.md").exists() and not find_by_title_company(data, "Fractional AI Implementation", "The Long Game"):
        data["jobs"].append(new_record(id=job_id("", "Fractional AI Implementation", "The Long Game"),
                                       title="Fractional AI Implementation", company="The Long Game",
                                       company_file="companies/the-long-game", job_file="jobs/the-long-game-exploration",
                                       source="hand", date_first_seen="2026-06-18", verdict="pass", verdict_date="2026-06-30",
                                       status_note="Chrissie likely taking a full-time job", excluded="thread closed"))

    n_folded = merge_duplicates(data)

    # defaults: every Pursue has a stage
    for j in data["jobs"]:
        if j["verdict"] == "pursue" and not j["stage"]:
            j["stage"], j["stage_date"] = "researching", j["verdict_date"]
        j["company_key"] = j["company"]

    save_jobs(p, data)
    print(f"folded {n_folded} duplicate postings (same title and company, other locations or boards)")

    # 6. companies.json from the card payload
    companies = {}
    for k, v in rd.get("companies", {}).items():
        companies[k] = {"url": v.get("url"), "about": v.get("about", [])}
    for k, g in rd.get("growth", {}).items():
        companies.setdefault(k, {"url": None, "about": []})["growth"] = g
    p.companies_json.write_text(json.dumps({"asof": rd.get("growth_asof"), "companies": companies},
                                           ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")

    from collections import Counter
    vc = Counter(j["verdict"] for j in data["jobs"])
    print(f"jobs.json: {len(data['jobs'])} records ({n_inbox} from inbox.csv, {n_cards} baseline cards, "
          f"{n_lb} leaderboard rows, {n_files} job files linked, {n_pipe} next steps)")
    print(f"verdicts: {dict(vc)}; excluded: {sum(1 for j in data['jobs'] if j['excluded'])}; "
          f"score>=7 unreviewed: {sum(1 for j in data['jobs'] if (j['score'] or 0) >= 7 and not j['verdict'] and not j['excluded'])}")
    print(f"companies.json: {len(companies)} companies")


if __name__ == "__main__":
    main()
