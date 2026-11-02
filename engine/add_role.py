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

Conversation-led (no posting, no JD): --conversation. Required with it: --person, --channel, --reason and --summary
(the call notes stand in for the JD). The record is unscored (`score_kind` conversation, no rubric number) and high
priority. --notion-page links an existing Opportunities page so the next `notion_opps.py backfill` writes the Job ID
onto that page instead of creating one. --score and --deep-pass are refused here: a rubric score arrives later.

Upgrade in place: --upgrade --update, with a real --title or a posting --url (and --deep-pass when the JD has been
read). The id, stage and intake history stay. See engine/conversation.py.

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
from common import (load_config, paths, load_jobs, save_jobs, new_record, canonical_url, job_id, slug, norm,  # noqa: E402
                    find_by_url, find_by_title_company, VERDICTS, STAGES, OUTCOMES)
from conversation import make_record, mark_scored, notion_id, upgrade as upgrade_record  # noqa: E402
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
    ap.add_argument("--title", help="required except --conversation, which defaults to 'Role (title TBD)'")
    ap.add_argument("--company", required=True)
    ap.add_argument("--source", help="hand | recruiter:<firm-slug> | network:<person-slug> | referral:<person-slug>; required on create")
    ap.add_argument("--conversation", action="store_true",
                    help="no posting and no JD: a firm wants to talk. Unscored, high priority")
    ap.add_argument("--person", help="with --conversation: who brought it (the person, not the firm slug)")
    ap.add_argument("--channel", help="with --conversation: how it arrived (phone, recruiter bulletin, intro)")
    ap.add_argument("--reason", help="with --conversation: one line, e.g. 'BGA CIO asked to meet'")
    ap.add_argument("--summary", help="with --conversation: the call notes, standing in for the JD")
    ap.add_argument("--notion-page", help="existing Opportunities page URL or id; backfill links it instead of creating one")
    ap.add_argument("--upgrade", action="store_true",
                    help="with --update: a title or posting arrived. Same id. Pass --deep-pass to score it")
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
    if a.upgrade:
        a.update = True
    if a.conversation and (a.score is not None or a.deep_pass) and not a.upgrade:
        raise SystemExit("a conversation-led role is unscored until a JD is read; add it without --score/--deep-pass, "
                         "then --upgrade --deep-pass when the title or posting arrives")
    if a.conversation and not a.upgrade:
        # Asking for the role to be tracked is the Pursue. There is no second decision and no Pass.
        if a.verdict not in (None, "pursue"):
            raise SystemExit("a conversation-led role is a Pursue; it is not a Pass or a Maybe")
        a.verdict = "pursue"
    if not a.upgrade and not a.title and not a.conversation:
        raise SystemExit("--title is required (or pass --conversation, which mints 'Role (title TBD)')")
    if not a.update and not a.source:
        raise SystemExit("--source is required when adding a role")

    cfg = load_config()
    p = paths(cfg)
    data = load_jobs(p)
    today = date.today().isoformat()
    source = parse_source(a.source) if a.source else None

    def conversations_at(company):
        return [j for j in data["jobs"] if j.get("kind") == "conversation" and norm(j.get("company")) == norm(company)]

    fresh = None
    if a.upgrade or (a.conversation and a.update):
        # A new title or posting URL belongs to this record, so it is not how we find it.
        conv = conversations_at(a.company)
        if len(conv) == 1:
            existing = conv[0]
        elif len(conv) > 1:
            raise SystemExit(f"{len(conv)} conversation-led roles at {a.company}; upgrade or update needs a single open conversation there")
        elif a.upgrade:
            raise SystemExit(f"no conversation-led role to upgrade at {a.company}")
        else:
            existing = None
    else:
        if a.conversation:
            try:
                fresh = make_record(company=a.company, source=source, person=a.person, channel=a.channel,
                                    reason=a.reason, summary=a.summary, when=a.date_first_seen, title=a.title,
                                    contact=a.contact, notion_page=a.notion_page)
            except ValueError as e:
                raise SystemExit(str(e))
            url = fresh["url"]
        else:
            url = canonical_url(a.url) if a.url else mint_url(a.title, a.company, a.company_url)
        existing = find_by_url(data, url) or (find_by_title_company(data, a.title, a.company) if a.title else None)
        if existing and not a.update:
            raise SystemExit(f"already on the board: {existing['id']} {existing['title']} @ {existing['company']} "
                             f"(verdict {existing.get('verdict')}, stage {existing.get('stage')}); pass --update to change it")
    if a.conversation and a.update and not a.upgrade and not existing:
        raise SystemExit(f"no conversation-led role to update at {a.company}")

    if a.upgrade:
        try:
            j = upgrade_record(existing, today=today, title=a.title, url=a.url)
        except ValueError as e:
            raise SystemExit(str(e))
    elif fresh and not existing:
        j = fresh
    elif existing and a.conversation and not a.upgrade:
        j = existing
        intake = j.setdefault("intake", {})
        for key, val in (("person", a.person), ("channel", a.channel), ("reason", a.reason), ("summary", a.summary)):
            if val:
                intake[key] = val.strip()
        if a.summary and j.get("score_kind") == "conversation":
            j.setdefault("card", {})["job"] = [a.summary.strip()]
        if a.reason and j.get("score_kind") == "conversation":
            j["why"] = a.reason.strip()
    else:
        j = existing or new_record(id=job_id(url), url=url, title=a.title.strip(), company=a.company.strip(),
                                   company_key=a.company.strip(), date_first_seen=a.date_first_seen)
    if a.notion_page:
        page = notion_id(a.notion_page)
        if not page:
            raise SystemExit(f"not a Notion page id or URL: {a.notion_page}")
        if j.get("kind") == "conversation":
            j.setdefault("intake", {})["notion_page"] = page
        else:
            j["notion_page"] = page
    if source:
        j["source"] = source
    if a.contact:
        j["contact"] = slug(a.contact)
    for k, v in (("location", a.location), ("work_model", a.work_model), ("comp", a.comp), ("travel", a.travel),
                 ("note", a.note), ("next_step", a.next_step), ("next_step_date", a.next_step_date)):
        if v:
            j[k] = v

    # job file: the front door markdown, or, for a conversation, the opportunity folder of the same slug
    # (opportunities/<slug>/ even when jobs/<slug>.md is not written yet).
    title_for_file = a.title or j.get("title") or ""
    candidates = [a.job_file] if a.job_file else [f"jobs/{slug(a.company)}-{slug(title_for_file)}"]
    if j.get("kind") == "conversation" and not a.job_file:
        candidates.append(f"jobs/{slug(a.company)}")
    linked = False
    for job_file in candidates:
        if not job_file:
            continue
        folder = p.vault / "opportunities" / job_file.rsplit("/", 1)[-1]
        if (p.vault / (job_file + ".md")).exists() or folder.is_dir():
            j["job_file"] = job_file
            linked = True
            break
    if a.job_file and not linked:
        print(f"  note: {a.job_file}.md is not in the vault yet; job_file left unset until it exists")
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
        mark_scored(j, today)

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
