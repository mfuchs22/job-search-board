"""Fold deep-pass results into jobs.json and companies.json.

    py engine/apply_deep_pass.py <out1.json> [<out2.json> ...]

Each input is a JSON array of objects in the shape defined by the deep-pass brief (id, fetched, location,
work_model, comp, travel, office, bullets, qualifications, company_about, company_url, growth, role_type, excluded,
score, math, why, mismatch). A record's score becomes authoritative (score_kind = deep); an excluded record
leaves the board with its reason. The office's coordinates are added by build.py (engine/office.py). Run build.py
afterwards.
"""
import json
import sys
from datetime import date

from common import load_config, paths, load_jobs, save_jobs, by_id, canonical_url, rubric_version
from office import merge as merge_office


def main():
    files = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not files:
        raise SystemExit("usage: py engine/apply_deep_pass.py out1.json [out2.json ...]")
    cfg = load_config()
    p = paths(cfg)
    version = rubric_version(p)
    data = load_jobs(p)
    idx = by_id(data)
    companies = json.loads(p.companies_json.read_text(encoding="utf-8")) if p.companies_json.exists() else {"asof": None, "companies": {}}
    today = date.today().isoformat()
    n = exc = 0
    for f in files:
        for r in json.loads(open(f, encoding="utf-8").read()):
            j = idx.get(r.get("id"))
            if not j:
                print(f"  unknown id {r.get('id')} ({r.get('title')} @ {r.get('company')}); skipped")
                continue
            n += 1
            if r.get("url") and canonical_url(r["url"]) != canonical_url(j.get("url") or ""):
                if j.get("url") and j["url"] not in j.setdefault("aliases", []):
                    j["aliases"].append(j["url"])
                j["url"] = canonical_url(r["url"])
            if r.get("company") and r["company"].strip() and r["company"].strip() != j.get("company"):
                j["company_as_posted"] = j.get("company")
                j["company"] = r["company"].strip()
                j["company_key"] = r["company"].strip()
            if r.get("location"):
                j["location"] = r["location"]
            if isinstance(r.get("office"), dict):
                merge_office(j, r["office"])
            for k in ("work_model", "comp", "travel", "qualifications", "role_type", "why", "mismatch"):
                if r.get(k) is not None:
                    j[k] = r[k]
            j["card"] = {"math": r.get("math"), "job": r.get("bullets") or [], "note": (f"travel {r['travel']}" if r.get("travel") else None)}
            j["fetched"] = bool(r.get("fetched"))
            j["deep_pass_date"] = today
            j["rubric_version"] = version
            if r.get("excluded"):
                j["excluded"] = r["excluded"]
                j["status_note"] = r["excluded"]
                j["score"] = None
                j["score_kind"] = "deep"
                exc += 1
            else:
                j["excluded"] = None
                if r.get("score") is not None:
                    j["score"] = int(r["score"])
                j["score_kind"] = "deep"
            c = companies["companies"].setdefault(j["company"], {"url": None, "about": []})
            if r.get("company_url"):
                c["url"] = r["company_url"]
            if r.get("company_about"):
                c["about"] = r["company_about"]
            if r.get("growth"):
                c["growth"] = r["growth"]
    companies["asof"] = today
    save_jobs(p, data)
    p.companies_json.write_text(json.dumps(companies, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"applied {n} deep-pass results ({exc} excluded); run build.py next")


if __name__ == "__main__":
    main()
