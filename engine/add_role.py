"""Add a role that did not come through the radar (a recruiter, a network lead, a referral) to jobs.json,
then rebuild the board.

Drop this file into engine/ and run it from the repo root, for example:

  py engine/add_role.py --title "AI Solutions Architect, Portfolio Operations" \
      --company "Example Partners" --source recruiter:search-firm \
      --contact example-recruiter --location "Example Partners, RI / Boston, MA (office TBD)" \
      --company-url https://www.provequity.com --verdict pursue --stage applied \
      --job-file jobs/example-partners-ai-solutions-architect-portfolio-ops \
      --deep-pass example.json

Sources: `recruiter:<firm-slug>`, `network:<person-slug>`, `referral:<person-slug>`, or `hand`. The pipeline view
already lists every record with a job file or the source `hand`, so a hand-added role shows there on the next build.

Identity: pass --url when a posting exists. When it does not, the script mints a path-form identity URL from the
company site (https://<company-host>/careers/<title-slug>) or, with no company site, https://hand.local/<company-slug>/
<title-slug>. canonical_url() keeps the path, so the id stays stable and merge_duplicates() cannot fold two hand roles
into one. A real posting found later goes in through apply_deep_pass.py's url correction (the minted one becomes an alias).

Deep pass: --deep-pass takes the same JSON object docs/deep-pass.md describes (bullets, qualifications, company_about,
company_url, growth, role_type, score, math, why, mismatch, work_model, comp, travel, location, office). Its fields are applied
exactly the way apply_deep_pass.py applies them, so the card renders with the New chip and a deep score, no title screen.
Without it the record lands unscored (score_kind None) and the next refresh's deep pass picks it up only if it has a url
the pass can fetch, so pass --score/--why/--mismatch at least.

--dry-run prints the record and writes nothing. --no-build skips build.py; --no-push is passed through to build.py.
"""
import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (load_config, paths, load_jobs, save_jobs, new_record, canonical_url, job_id, slug,  # noqa: E402
                    find_by_url, find_by_title_company, VERDICTS, STAGES, OUTCOMES)
from office import merge as merge_office  # noqa: E402

REPO = Path(__file__).resolve().parent.parent


def mint_url(title, company, company_url):
    if company_url:
        host = urlsplit(company_url if "://" in company_url else "https://" + company_url).netloc.lower().replace("www.", "")
        if host:
            return f"https://{host}/careers/{slug(title)}"
    return f"https://hand.local/{slug(company)}/{slug(title)}"


def parse_source(s):
    if s == "hand":
        return s
    kind, _, who = s.partition(":")
    if kind not in ("recruiter", "network", "referral") or not who:
        raise SystemExit("--source must be hand, recruiter:<firm-slug>, network:<person-slug>, or referral:<person-slug>")
    return f"{kind}:{slug(who)}"


def main():
    ap = argparse.ArgumentParser(description="Add a recruiter- or network-sourced role to jobs.json and rebuild the board.")
    ap.add_argument("--title", required=True)
    ap.add_argument("--company", required=True)
    ap.add_argument("--source", required=True, help="hand | recruiter:<firm-slug> | network:<person-slug> | referral:<person-slug>")
    ap.add_argument("--contact", help="people/ slug of the person who brought it (the recruiter, the referrer)")
    ap.add_argument("--url", help="the posting, when one exists")
    ap.add_argument("--company-url", help="company website; used to mint the identity url when there is no posting")
    ap.add_argument("--location")
    ap.add_argument("--work-model")
    ap.add_argument("--comp")
    ap.add_argument("--travel")
    ap.add_argument("--date-first-seen", default=date.today().isoformat())
    ap.add_argument("--verdict", choices=VERDICTS)
    ap.add_argument("--stage", choices=STAGES)
    ap.add_argument("--outcome", choices=OUTCOMES, help="only on a closed stage: how it ended")
    ap.add_argument("--next-step")
    ap.add_argument("--next-step-date")
    ap.add_argument("--note", help="the owner's words about the role, shown on the card")
    ap.add_argument("--job-file", help="vault-relative path without .md, e.g. jobs/acme-ai-lead; auto-detected from the title and company when omitted")
    ap.add_argument("--deep-pass", help="path to a JSON object in the docs/deep-pass.md output shape")
    ap.add_argument("--score", type=int)
    ap.add_argument("--why")
    ap.add_argument("--mismatch")
    ap.add_argument("--update", action="store_true", help="update the existing record for this role instead of refusing")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-build", action="store_true")
    ap.add_argument("--no-push", action="store_true")
    a = ap.parse_args()

    cfg = load_config()
    p = paths(cfg)
    data = load_jobs(p)
    today = date.today().isoformat()
    source = parse_source(a.source)

    url = canonical_url(a.url) if a.url else mint_url(a.title, a.company, a.company_url)
    existing = find_by_url(data, url) or find_by_title_company(data, a.title, a.company)
    if existing and not a.update:
        raise SystemExit(f"already on the board: {existing['id']} {existing['title']} @ {existing['company']} "
                         f"(verdict {existing.get('verdict')}, stage {existing.get('stage')}); pass --update to change it")

    j = existing or new_record(id=job_id(url), url=url, title=a.title.strip(), company=a.company.strip(),
                               company_key=a.company.strip(), date_first_seen=a.date_first_seen)
    j["source"] = source
    if a.contact:
        j["contact"] = slug(a.contact)
    for k, v in (("location", a.location), ("work_model", a.work_model), ("comp", a.comp), ("travel", a.travel),
                 ("note", a.note), ("next_step", a.next_step), ("next_step_date", a.next_step_date)):
        if v:
            j[k] = v

    # job file and company file: link when the vault has them
    job_file = a.job_file or f"jobs/{slug(a.company)}-{slug(a.title)}"
    if (p.vault / (job_file + ".md")).exists():
        j["job_file"] = job_file
    elif a.job_file:
        print(f"  note: {job_file}.md is not in the vault yet; job_file left unset until it exists")
    company_file = f"companies/{slug(a.company)}"
    if (p.vault / (company_file + ".md")).exists():
        j["company_file"] = company_file

    # deep pass, applied the way apply_deep_pass.py applies it
    dp = json.loads(Path(a.deep_pass).read_text(encoding="utf-8")) if a.deep_pass else {}
    if isinstance(dp, list):
        dp = dp[0] if dp else {}
    for k in ("location", "work_model", "comp", "travel", "qualifications", "role_type", "why", "mismatch"):
        if dp.get(k) is not None:
            j[k] = dp[k]
    if isinstance(dp.get("office"), dict):
        merge_office(j, dp["office"])
    if a.score is not None:
        dp["score"] = a.score
    if a.why:
        j["why"] = a.why
    if a.mismatch:
        j["mismatch"] = a.mismatch
    if dp or a.score is not None:
        j["card"] = {"math": dp.get("math"), "job": dp.get("bullets") or [], "note": (f"travel {dp['travel']}" if dp.get("travel") else None)}
        j["fetched"] = bool(dp.get("fetched", False))
        j["deep_pass_date"] = today
        j["excluded"] = dp.get("excluded") or None
        if j["excluded"]:
            j["status_note"], j["score"] = j["excluded"], None
        elif dp.get("score") is not None:
            j["score"] = int(dp["score"])
        j["score_kind"] = "deep"

    if a.verdict:
        j["verdict"], j["verdict_date"] = a.verdict, today
    if a.stage:
        j["stage"], j["stage_date"] = a.stage, today
    if a.outcome:
        j["outcome"] = a.outcome
    elif j.get("verdict") == "pursue" and not j.get("stage"):
        j["stage"], j["stage_date"] = "shortlist", today

    if a.dry_run:
        print(json.dumps(j, ensure_ascii=False, indent=1))
        print("dry run: nothing written")
        return

    if not existing:
        data["jobs"].append(j)
    save_jobs(p, data)

    companies = json.loads(p.companies_json.read_text(encoding="utf-8")) if p.companies_json.exists() else {"asof": None, "companies": {}}
    c = companies["companies"].setdefault(j["company"], {"url": None, "about": []})
    if dp.get("company_url") or a.company_url:
        c["url"] = dp.get("company_url") or a.company_url
    if dp.get("company_about"):
        c["about"] = dp["company_about"]
    if dp.get("growth"):
        c["growth"] = dp["growth"]
    companies["asof"] = today
    p.companies_json.write_text(json.dumps(companies, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")

    print(f"{'updated' if existing else 'added'} {j['id']} {j['title']} @ {j['company']} (source {source}, score {j.get('score')}, verdict {j.get('verdict')})")
    if a.no_build:
        print("build skipped; run py engine/build.py")
        return
    cmd = [sys.executable, str(REPO / "engine" / "build.py")] + (["--no-push"] if a.no_push else [])
    raise SystemExit(subprocess.call(cmd, cwd=str(REPO)))


if __name__ == "__main__":
    main()
