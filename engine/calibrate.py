"""Calibration inputs: the deterministic half of the rubric feedback loop (vault jobs/calibration.md).

The weekly rubric-calibration routine (Personal-OS Tools/rubric-calibration-prompt.md) runs this first, then does
the reasoning (clustering the owner's notes into candidate rules) on what it prints. Nothing here changes a record
or the rubric.

    py engine/calibrate.py                      window since the newest file in <vault>/jobs/calibration/
    py engine/calibrate.py --since 2026-09-14   explicit window start (verdicts after that date)
    py engine/calibrate.py --test "<regex>" [--fields qualifications,mismatch]
                                                backtest a candidate rule against EVERY verdict: hits, passes,
                                                and the Pursues it would have cut (the false kills)
    py engine/calibrate.py --json out.json      also write the window's verdict rows for the model to read

Prints: the tier table (Pursue rate by score tier, window and all time), the window's verdicts with the owner's
notes, and the routine-written rubric-gap lines from the feedback log since the window start.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_config, load_jobs, paths  # noqa: E402

TIERS = (("11+", 11, 99), ("9-10", 9, 10), ("8", 8, 8), ("7", 7, 7), ("<7", -99, 6))
DEFAULT_FIELDS = "qualifications,mismatch,travel,work_model,location,title,why"


def when(j):
    return (str(j.get("verdict_ts") or "")[:10]) or str(j.get("verdict_date") or "")


def tier(score):
    s = score or 0
    return next(name for name, lo, hi in TIERS if lo <= s <= hi)


def tier_table(rows):
    out = []
    for name, _, _ in TIERS:
        n = [j for j in rows if tier(j.get("score")) == name]
        p = sum(1 for j in n if j.get("verdict") == "pursue")
        if n:
            out.append(f"| {name} | {len(n)} | {p} | {100 * p // len(n)} percent |")
    return ["| Score | Verdicts | Pursue | Pursue rate |", "|---|---|---|---|"] + out


def window_start(p, since):
    if since:
        return since
    files = sorted(f.stem for f in (p.jobs_dir / "calibration").glob("????-??-??.md"))
    return files[-1] if files else "2026-09-01"


def feedback_gap_lines(p, start):
    if not p.feedback_log.exists():
        return []
    pat = re.compile(r"rubric|interpretation|rule", re.I)
    out = []
    for line in p.feedback_log.read_text(encoding="utf-8").splitlines():
        if line.startswith("- ") and line[2:12] > start and "source: routine" in line and pat.search(line):
            out.append(line[:400])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since")
    ap.add_argument("--test", help="regex to backtest against every verdict")
    ap.add_argument("--fields", default=DEFAULT_FIELDS)
    ap.add_argument("--json")
    a = ap.parse_args()
    p = paths(load_config())
    jobs = load_jobs(p)["jobs"]
    verdicts = [j for j in jobs if j.get("verdict")]
    start = window_start(p, a.since)
    window = sorted((j for j in verdicts if when(j) > start), key=when)

    if a.test:
        rx = re.compile(a.test, re.I)
        fields = [f.strip() for f in a.fields.split(",")]
        hits = [j for j in verdicts if rx.search(" ".join(str(j.get(f) or "") for f in fields))]
        kills = [j for j in hits if j["verdict"] == "pursue"]
        print(f"Backtest /{a.test}/ over {fields}: {len(hits)} hits, {len(hits) - len(kills)} passes or maybes, "
              f"{len(kills)} PURSUES (false kills if this were a gate)")
        for j in hits:
            print(f"  {j['verdict']:<6} {j.get('score')!s:>3} {j['company'][:26]:<26} {(j.get('title') or '')[:48]}")
        return

    print(f"Window: verdicts after {start} ({len(window)} of {len(verdicts)} all time)\n")
    print("## Pursue rate by tier, window\n" + "\n".join(tier_table(window)) + "\n")
    print("## Pursue rate by tier, all time\n" + "\n".join(tier_table(verdicts)) + "\n")
    print("## Verdicts in the window (date, verdict, calibration mark, score, company, title | work model | note)")
    for j in window:
        note = " ".join((j.get("note") or "").split())
        print(f"- {when(j)} {j['verdict']:<6} {str(j.get('calibration') or '-'):<11} {j.get('score')!s:>3} "
              f"{j['company'][:26]} | {(j.get('title') or '')[:50]} | {str(j.get('work_model') or '')[:30]} | {note[:300]}")
    gaps = feedback_gap_lines(p, start)
    print(f"\n## Rubric gaps the routines logged since {start} ({len(gaps)})")
    for g in gaps:
        print(g)
    if a.json:
        keep = ("id", "verdict", "verdict_date", "verdict_ts", "calibration", "score", "company", "title", "location",
                "work_model", "travel", "qualifications", "mismatch", "note", "flag", "stage", "excluded")
        rows = [{k: j.get(k) for k in keep} | {"math": (j.get("card") or {}).get("math")} for j in window]
        Path(a.json).write_text(json.dumps(rows, indent=1), encoding="utf-8")
        print(f"\nWrote {len(rows)} rows to {a.json}")


if __name__ == "__main__":
    main()
