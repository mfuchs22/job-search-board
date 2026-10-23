"""Push the board to Supabase: one `jobs` row per live record, five `board_meta` rows (summary, companies, paths,
contact_changes from contact_refresh.py, briefs),
the Notion mirrors (`contacts`, `opportunities`, `meetings`, `tasks`), and the org charts (`org_charts`, through
org_chart.push_all). The mirror rows are built by notion_mirror.py. Between refreshes the same shape is written
by supabase/functions/notion-hook (webhook and the 5-minute reconcile). This push remains the full rebuild.

    py engine/push_board.py       push from the current jobs.json (build.py does this after the markdown views)

Idempotent: rows are upserted by primary key and jobs rows whose id is no longer live are deleted.
The page (web/) reads these tables; the owner's verdicts go the other way (ingest_db.py) and stage moves
through the opportunity-write function into Notion.
"""
import re
from pathlib import Path

from common import load_config, paths, load_jobs
from notion_mirror import mirror_rows
from notion_sync import load_all as load_notion
from render_dashboard import board_payload, render_job_md
import briefs
import contact_refresh
import org_chart
import stage_history
import pulse_history
import supabase as sb

LI_SLUG = re.compile(r"linkedin\.com/in/([^/?#\s)]+)", re.I)


def network_pages(cfg, p, people):
    """Hand-written person pages, rendered, keyed by Notion contact id: the job search's people/*.md first, then
    Personal-OS Knowledge/People/*.md. Matched on the LinkedIn slug, then on the name as a file slug.
    The board shows them on the person pane."""
    roots = [(p.vault, "people")] + ([(Path(cfg["personal_os"]), "Knowledge/People")] if cfg.get("personal_os") else [])
    files = {}
    for root, rel in roots:
        d = root / rel
        for f in (sorted(d.glob("*.md")) if d.exists() else []):
            files.setdefault(f.stem.lower(), (root, f"{rel}/{f.stem}"))
    by_li = {}
    for stem, (root, rel) in files.items():
        m = LI_SLUG.search((root / f"{rel}.md").read_text(encoding="utf-8"))
        if m:
            by_li.setdefault(m.group(1).lower(), stem)
    out = {}
    for c in people:
        m = LI_SLUG.search(c.get("linkedin") or "")
        stem = (m and by_li.get(m.group(1).lower())) or re.sub(r"[^a-z0-9]+", "-", (c.get("name") or "").lower()).strip("-")
        if stem in files:
            root, rel = files[stem]
            out[c["id"]] = {"file": rel, "html": render_job_md(root, rel)}
    return out


def push_notion(cfg, p, built):
    """Mirror the four Notion pulls (notion_sync.py) into `contacts`, `opportunities`, `meetings` and `tasks`, plus
    the rendered person pages as board_meta network_pages. Rows come from notion_mirror.mirror_rows. `updated_at`
    is the page's Notion `edited` time when the pull recorded one, so a later webhook is not treated as stale.
    A table's rows are deleted only after a real pull, so a missing file never empties the board. This is the
    backstop for a delete the live hook missed."""
    contacts, opps, meets, tasks = load_notion(p)
    pages = network_pages(cfg, p, contacts.get("people") or [])
    try:
        sb.upsert("board_meta", [{"key": "network_pages", "payload": pages, "updated_at": built}], cfg=cfg)
        rows_by_table = mirror_rows(contacts, opps, meets, tasks, built)
        asof = {"contacts": contacts.get("asof"), "opportunities": opps.get("asof"),
                "meetings": meets.get("asof"), "tasks": tasks.get("asof")}
        for table, rows in rows_by_table.items():
            if rows:
                sb.upsert(table, rows, cfg=cfg)
            if asof[table]:
                sb.delete_not_in(table, [r["id"] for r in rows], cfg=cfg)
        people, opp_rows = rows_by_table["contacts"], rows_by_table["opportunities"]
        meet_rows, task_rows = rows_by_table["meetings"], rows_by_table["tasks"]
        return (f"{len(people)} contacts ({len(pages)} with a vault page), {len(opp_rows)} opportunities, "
                f"{len(meet_rows)} meetings, {len(task_rows)} career tasks")
    except SystemExit as e:  # a table not migrated yet, or a Supabase hiccup: jobs are already pushed
        return f"notion mirrors not pushed ({e})"


def push_orgs(cfg):
    """The saved org charts (data/org/, engine/org_chart.py) flagged against the vault as it stands now, so a new
    people page or research row shows on the chart at the next build. Never fails the push."""
    try:
        return org_chart.push_all(cfg)
    except (SystemExit, OSError, ValueError) as e:
        return f"org charts not pushed ({e})"


def push_history(cfg, p, data, built):
    """Stage history (stage_history.py): record today's stage for every pursued role, push it as board_meta
    stage_history for the card ages and the Overview. Never fails the push."""
    try:
        contacts, opps, _, tasks = load_notion(p)
        h, moved = stage_history.update(p, data, opps)
        ph = pulse_history.update(p, data, contacts, opps, tasks)
        sb.upsert("board_meta", [{"key": "stage_history", "payload": h, "updated_at": built},
                                 {"key": "pulse_history", "payload": ph, "updated_at": built}], cfg=cfg)
        return f"stage history {len(h['roles'])} roles, {moved} moved; pulse {len(ph['days'])} days"
    except (SystemExit, OSError, ValueError, KeyError) as e:
        return f"stage history not pushed ({e})"


def push(cfg, p, data, health=None):
    """health: what build.py learned this run (Notion pull, page fills) for the summary's health block."""
    jobs, companies, people, summary = board_payload(cfg, p, data, health)
    built = summary["built_at"]
    rows = [{"id": j["id"], "company_key": j.get("company_key") or j["company"], "payload": j, "updated_at": built}
            for j in jobs]
    sb.upsert("jobs", rows, cfg=cfg)
    stale = sb.delete_not_in("jobs", [j["id"] for j in jobs], cfg=cfg)
    sb.upsert("board_meta", [
        {"key": "summary", "payload": summary, "updated_at": built},
        {"key": "companies", "payload": companies, "updated_at": built},
        {"key": "paths", "payload": people, "updated_at": built},
        {"key": "contact_changes", "payload": contact_refresh.board_payload(p), "updated_at": built},
    ], cfg=cfg)
    try:  # the Today briefs (briefs.py): the cards' options and the page behind "Open brief"
        sb.upsert("board_meta", [{"key": "briefs", "payload": briefs.load(p), "updated_at": built}], cfg=cfg)
    except (SystemExit, OSError, ValueError) as e:
        print(f"briefs not pushed ({e})")
    hist = push_history(cfg, p, data, built)
    n_inbox = sum(1 for j in jobs if not j["verdict"] and not j["excluded"] and (j["score"] or 0) >= summary["min_score"])
    return (f"supabase {len(jobs)} jobs ({n_inbox} to review, {len(stale)} retired), postings through {summary['data_asof']}; "
            f"{push_notion(cfg, p, built)}; {push_orgs(cfg)}; {hist}")


def main():
    cfg = load_config()
    p = paths(cfg)
    data = load_jobs(p)
    print(push(cfg, p, data))


if __name__ == "__main__":
    main()
