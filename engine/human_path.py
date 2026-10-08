"""Human path: the warm-path gate's answer for one role, kept on the record and on the role's front door.

The vault method (network/warm-path.md) walks the ladder before any application and records one line on the
role's front door:

    **Human path:** warm active | warm reachable | cold. <names and routes>. Checked YYYY-MM-DD (<ref>).

This module owns the `human_path` object on each jobs.json record and keeps it and that line in step:

    {"verdict": "warm reachable", "qualifier": null, "people": "Jim Gorman (...) can name ...",
     "checked": "2026-09-14", "ref": "network/warm-path-audit-2026-09-14.md", "attached": null}

`qualifier` is the optional parenthetical after the verdict ("weak"). `attached` is set once the application goes
out: whether a person was attached at that moment (the 70 percent ratio); on the line it is a trailing
"Applied with a person: yes." sentence.

    py engine/human_path.py backfill [--dry-run]    fold every front-door line into jobs.json (build.py does this each run)
    py engine/human_path.py set <id or job slug> --verdict "warm reachable" --people "..." [--qualifier weak]
                                [--checked YYYY-MM-DD] [--ref path] [--attached yes|no] [--dry-run] [--no-build] [--no-push]
    py engine/human_path.py show                    Pursue counts by verdict, and the Pursues with no line

Front doors: `jobs/<slug>.md` always (under ## Prep Notes), and `opportunities/<slug>/README.md` when that folder
exists. Fold rule (line -> record): a line whose Checked date is on or after the record's replaces the record's object
when they differ, so a line a session edits by hand still reaches the board; a missing line never clears the record.
"""
import argparse
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_config, paths, load_jobs, save_jobs, by_id  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
VERDICTS = ("warm active", "warm reachable", "cold")
KEYS = ("verdict", "qualifier", "people", "checked", "ref", "attached")

LINE_RE = re.compile(
    r"^\*\*Human path:\*\*[ \t]*(warm,? active|warm,? reachable|cold)(?:[ \t]*\(([^)\n]*)\))?\.[ \t]*(.*?)[ \t]*"
    r"Checked (\d{4}-\d{2}-\d{2})(?:[ \t]*\(([^)\n]*)\))?\.(?:[ \t]*Applied with a person: (yes|no)\.)?[ \t]*$",
    re.M)


def norm_verdict(v):
    v = " ".join((v or "").lower().replace(",", " ").replace("-", " ").replace("_", " ").split())
    return v if v in VERDICTS else None


def parse_line(text):
    m = LINE_RE.search(text or "")
    if not m:
        return None
    return {"verdict": norm_verdict(m[1]), "qualifier": m[2] or None, "people": m[3].strip() or None,
            "checked": m[4], "ref": m[5] or None, "attached": {"yes": True, "no": False}.get(m[6])}


def format_line(hp):
    out = [f"**Human path:** {hp['verdict']}" + (f" ({hp['qualifier']})" if hp.get("qualifier") else "") + "."]
    if hp.get("people"):
        ppl = hp["people"].strip()
        out.append(ppl if ppl.endswith(".") else ppl + ".")
    out.append(f"Checked {hp['checked']}" + (f" ({hp['ref']})" if hp.get("ref") else "") + ".")
    if hp.get("attached") is not None:
        out.append(f"Applied with a person: {'yes' if hp['attached'] else 'no'}.")
    return " ".join(out)


def doors(p, j):
    """(path, is_readme) for the role's front doors that exist, job file first so the README wins a tie."""
    if not j.get("job_file"):
        return []
    slug = j["job_file"].split("/", 1)[-1]
    cands = [(p.vault / (j["job_file"] + ".md"), False), (p.vault / "opportunities" / slug / "README.md", True)]
    return [(f, r) for f, r in cands if f.exists()]


def read_doors(p, j):
    best = None
    for f, _ in doors(p, j):
        hp = parse_line(f.read_text(encoding="utf-8"))
        if hp and (best is None or hp["checked"] >= best["checked"]):
            best = hp
    return best


def same(a, b):
    return all((a or {}).get(k) == (b or {}).get(k) for k in KEYS)


def fold_all(p, data):
    """Front-door lines into records. Returns the records whose human_path changed."""
    changed = []
    for j in data["jobs"]:
        hp = read_doors(p, j)
        if not hp:
            continue
        cur = j.get("human_path")
        if cur and (hp["checked"] < (cur.get("checked") or "") or same(cur, hp)):
            continue
        j["human_path"] = hp
        changed.append(j)
    return changed


def write_door(f, line, is_readme):
    txt = f.read_text(encoding="utf-8")
    if LINE_RE.search(txt):
        new = LINE_RE.sub(lambda m: line, txt, count=1)
    elif is_readme:
        m = re.search(r"^\*\*Status", txt, re.M)
        if not m:
            return False
        new = txt[:m.start()] + line + "\n\n" + txt[m.start():]
    else:
        m = re.search(r"^## Prep Notes[ \t]*\n", txt, re.M)
        if m:
            new = txt[:m.end()] + "\n" + line + "\n" + txt[m.end():]
        else:
            m = re.search(r"^## Process Log", txt, re.M)
            block = "## Prep Notes\n\n" + line + "\n\n"
            new = txt[:m.start()] + block + txt[m.start():] if m else txt.rstrip("\n") + "\n\n" + block.rstrip("\n") + "\n"
    if new != txt:
        f.write_text(new, encoding="utf-8", newline="\n")
        return True
    return False


def resolve(data, key):
    j = by_id(data).get(key)
    if j:
        return j
    s = key.replace("\\", "/").removesuffix(".md").split("/")[-1]
    hits = [j for j in data["jobs"] if (j.get("job_file") or "").split("/")[-1] == s]
    if len(hits) != 1:
        raise SystemExit(f"no single record for '{key}' (pass the 10-hex id or the job file slug)")
    return hits[0]


# ---------- commands ----------

def cmd_backfill(a):
    cfg = load_config()
    p = paths(cfg)
    data = load_jobs(p)
    bad = []
    for j in data["jobs"]:
        for f, _ in doors(p, j):
            m = LINE_RE.search(f.read_text(encoding="utf-8"))
            if m and format_line(parse_line(m[0])) != m[0].rstrip():
                bad.append(f"{f.relative_to(p.vault)}: line does not round-trip")
    changed = fold_all(p, data)
    for j in changed:
        hp = j["human_path"]
        print(f"  {j['id']} {hp['verdict']:<14} checked {hp['checked']}  {j['company']}: {j['title']}")
    for b in bad:
        print("  warning:", b)
    missing = [j for j in data["jobs"] if j.get("verdict") == "pursue" and not j.get("human_path")]
    for j in missing:
        print(f"  no Human path line: {j['id']} {j['company']}: {j['title']} (job file {j.get('job_file') or 'none'})")
    if a.dry_run:
        print(f"dry run: {len(changed)} records would change")
        return
    if changed:
        save_jobs(p, data)
    print(f"backfill: {len(changed)} records updated; {len(missing)} Pursues without a line")


def cmd_set(a):
    cfg = load_config()
    p = paths(cfg)
    data = load_jobs(p)
    j = resolve(data, a.role)
    cur = dict(j.get("human_path") or {})
    attached = {"yes": True, "no": False}.get(a.attached) if a.attached else cur.get("attached")
    if any(x is not None for x in (a.verdict, a.people, a.qualifier, a.checked, a.ref)):
        v = norm_verdict(a.verdict) if a.verdict else cur.get("verdict")
        if not v:
            raise SystemExit(f"--verdict must be one of: {', '.join(VERDICTS)}")
        checked = a.checked or date.today().isoformat()
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", checked):
            raise SystemExit("--checked must be YYYY-MM-DD")
        qualifier = a.qualifier if a.qualifier is not None else (cur.get("qualifier") if v == cur.get("verdict") else None)
        hp = {"verdict": v, "qualifier": qualifier or None,
              "people": (a.people if a.people is not None else cur.get("people")) or None,
              "checked": checked, "ref": a.ref or None, "attached": attached}
    elif a.attached:
        if not cur:
            raise SystemExit("no human_path on this record yet: pass --verdict and --people first")
        hp = {**{k: cur.get(k) for k in KEYS}, "attached": attached}
    else:
        raise SystemExit("nothing to set: pass --verdict/--people/--checked, or --attached")

    line = format_line(hp)
    hp = parse_line(line)  # store exactly what the line says, so the next build's fold is a no-op
    print(f"{j['id']} {j['company']}: {j['title']}")
    print(line)
    if j.get("verdict") != "pursue":
        print(f"  note: this role's verdict is {j.get('verdict')}, not pursue; the board only badges Pursues")
    ds = doors(p, j)
    if not ds:
        print("  note: no job file in the vault for this role; the line lives on the record only until one exists")
    if a.dry_run:
        print("dry run: would write jobs.json" + "".join(f" and {f.relative_to(p.vault)}" for f, _ in ds))
        return
    j["human_path"] = hp
    save_jobs(p, data)
    for f, is_readme in ds:
        wrote = write_door(f, line, is_readme)
        print(f"  {f.relative_to(p.vault)}: {'updated' if wrote else 'unchanged (no Status line to anchor to)' if is_readme and not LINE_RE.search(f.read_text(encoding='utf-8')) else 'unchanged'}")
    if a.no_build:
        print("build skipped; run py engine/build.py")
        return
    cmd = [sys.executable, str(REPO / "engine" / "build.py")] + (["--no-push"] if a.no_push else [])
    raise SystemExit(subprocess.call(cmd, cwd=str(REPO)))


def cmd_show(a):
    cfg = load_config()
    p = paths(cfg)
    data = load_jobs(p)
    ps = [j for j in data["jobs"] if j.get("verdict") == "pursue"]
    by = {v: [] for v in VERDICTS + ("unchecked",)}
    for j in ps:
        by[(j.get("human_path") or {}).get("verdict") or "unchecked"].append(j)
    print(f"{len(ps)} Pursues: " + ", ".join(f"{k} {len(v)}" for k, v in by.items()))
    for j in by["unchecked"]:
        print(f"  unchecked: {j['id']} {j['company']}: {j['title']}")


def main():
    ap = argparse.ArgumentParser(description="The warm-path gate's Human path, on jobs.json records and front-door lines.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backfill", help="fold every front-door line into jobs.json")
    b.add_argument("--dry-run", action="store_true")
    s = sub.add_parser("set", help="set the Human path for one role and rewrite its front-door lines")
    s.add_argument("role", help="10-hex record id or job file slug")
    s.add_argument("--verdict", help="warm active | warm reachable | cold")
    s.add_argument("--people", help="names and routes, one sentence or a few clauses")
    s.add_argument("--qualifier", help='parenthetical after the verdict, e.g. "weak"; empty string clears it')
    s.add_argument("--checked", help="YYYY-MM-DD, default today")
    s.add_argument("--ref", help="vault-relative file behind the check, e.g. network/warm-path-audit-2026-09-14.md")
    s.add_argument("--attached", choices=("yes", "no"), help="the application went out with (or without) a person attached")
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--no-build", action="store_true")
    s.add_argument("--no-push", action="store_true")
    sub.add_parser("show", help="Pursue counts by verdict")
    a = ap.parse_args()
    {"backfill": cmd_backfill, "set": cmd_set, "show": cmd_show}[a.cmd](a)


if __name__ == "__main__":
    main()
