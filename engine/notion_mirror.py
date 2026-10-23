"""The Supabase row for one Notion page, shared by the morning rebuild and the live mirror.

`push_board.push_notion` rewrites `contacts`, `opportunities`, `meetings` and `tasks` from the
four pull files on the 04:30 refresh and on Sync now. `supabase/functions/notion-hook` upserts
or deletes a single page between those rebuilds. Both build the row here (the function's copy
is `supabase/functions/_shared/notion_mirror.ts`). `tests/test_notion_mirror.py` runs the same
pages through both and fails if a row differs.

`updated_at` is the page's Notion `last_edited_time` (`payload["edited"]`) when that is present,
and the refresh time otherwise. The hook skips a write only when the incoming `last_edited_time`
is strictly older than the stored `updated_at`.

The hook does not write `network/*.json`. Those files stay `notion_sync.py`'s.
"""
import re
from datetime import datetime, timedelta, timezone

import network_notion
import notion_sync


# Same envelope push_board wrote inline before this module existed.
TABLES = ("contacts", "opportunities", "meetings", "tasks")

# A page id Notion will actually return: dashed UUID or 32 hex. Used before a value is
# interpolated into a PostgREST filter (a comma or ampersand there is a filter injection).
_PAGE_ID = re.compile(
    r"^[0-9a-fA-F]{32}$|^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
# Board record ids are 10 hex; a hand-typed Job ID is still safe in a filter if it stays this narrow.
_FILTER_VALUE = re.compile(r"^[A-Za-z0-9-]{1,80}$")

# Reconcile (notion-hook, called by pg_cron). The first pass, with no watermark, looks back
# six hours: an edge invocation cannot walk a multi-day backlog. After that the stored
# watermark is the cursor. A caught-up pass stores now minus two minutes. PAGE_CAP is one
# query page per data source; a tied page of identical timestamps steps the cursor one
# millisecond so the next pass cannot read the same page forever. The morning rebuild
# covers anything the cap skipped.
FIRST_LOOKBACK = timedelta(hours=6)
CAUGHT_UP_LAG = timedelta(minutes=2)
PAGE_CAP = 20


def _clock(payload, built):
    """Notion's last_edited_time when the pull recorded it, else the refresh time."""
    return (payload or {}).get("edited") or built


def mirror_rows(contacts, opps, meets, tasks, built):
    """The four tables' rows for a full refresh.

    `updated_at` prefers each payload's `edited` (Notion `last_edited_time`). A refresh clock
    newer than that edit would make notion-hook skip a real change the pull missed.
    """
    people = [{"id": c["id"], "payload": c, "updated_at": _clock(c, built)}
              for c in contacts.get("people") or [] if c.get("id")]
    opp_rows = [{"id": o["id"], "page_id": o["page"], "payload": o, "updated_at": _clock(o, built)}
                for o in notion_sync.one_per_job(opps.get("opps") or [])[0] if o.get("id") and o.get("page")]
    meet_rows = [{"id": m["id"], "payload": m, "updated_at": _clock(m, built)}
                 for m in meets.get("meetings") or [] if m.get("id")]
    task_rows = [{"id": t["id"], "payload": t, "updated_at": _clock(t, built)}
                 for t in tasks.get("tasks") or [] if t.get("id")]
    return {"contacts": people, "opportunities": opp_rows, "meetings": meet_rows, "tasks": task_rows}


def task_on_board(payload):
    """The To-dos slice notion_sync.TASK_FILTER asks Notion for. A page that no longer matches
    is deleted from `tasks` rather than stored: the table holds only that slice."""
    return (payload.get("area") == "career"
            and payload.get("status") != "Complete"
            and payload.get("project") != "Consulting")


def carry_lane_since(opp, live, vault, today):
    """notion_sync.pull's clock, for one page.

    Keep lane_since while the lane is unchanged. The live Supabase row is preferred; the last
    vault pull fills in when a board write stored the row without a clock. The cloud hook has
    no vault file, so it passes vault as None and carries only the Supabase payload. A lane
    that actually changed starts today. An unchanged lane that nobody has a clock for is left
    unset, so a next-step edit does not pretend the lane moved today. `today` is a UTC date,
    the same clock the morning pull uses.
    """
    was = live or {}
    if was.get("lane") == opp.get("lane") and was.get("lane_since"):
        opp["lane_since"] = was["lane_since"]
        return opp
    remembered = vault or {}
    if remembered.get("lane") == opp.get("lane") and remembered.get("lane_since"):
        opp["lane_since"] = remembered["lane_since"]
        return opp
    # A live row already on this lane, whose clock was never stored: leave it unset.
    # A missing live row falls through and starts the clock, matching the morning pull.
    if live and was.get("lane") == opp.get("lane"):
        return opp
    opp["lane_since"] = today
    return opp


def norm_id(value):
    return (value or "").replace("-", "").lower()


def source_kind(page, sources):
    """`sources` maps a data source id (dashed or not) to contacts|opportunities|meetings|tasks.
    Notion's parent carries data_source_id since API 2025-09-03 and database_id before that."""
    parent = page.get("parent") or {}
    by_norm = {norm_id(k): v for k, v in (sources or {}).items()}
    for key in ("data_source_id", "database_id"):
        kind = by_norm.get(norm_id(parent.get(key)))
        if kind:
            return kind
    return None


def valid_page_id(value):
    return bool(_PAGE_ID.match(value or ""))


def filter_eq(value):
    """`eq.<value>` for a PostgREST query param, or None when the value is not safe to interpolate."""
    if not _FILTER_VALUE.match(value or ""):
        return None
    return f"eq.{value}"


def id_forms(page_id):
    """Dashed and undashed forms. The API and a webhook have both shown up; deletes try each."""
    if not valid_page_id(page_id):
        return []
    raw = page_id.replace("-", "").lower()
    dashed = f"{raw[0:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:]}"
    return list(dict.fromkeys([page_id, dashed, raw]))


def plan_page(page, kind, *, touches=None, company_names=None, live_opp=None, vault_opp=None,
              today, built):
    """One retrieved Notion page → `{kind: upsert|delete|skip, table, row, page_id, reason}`.

    `row` is exactly one element of `mirror_rows` for that table. `built` is the fallback
    `updated_at` when the page has no `last_edited_time`.
    """
    page_id = page.get("id")
    if not valid_page_id(page_id):
        return {"kind": "skip", "table": None, "row": None, "page_id": page_id, "reason": "bad page id"}
    if page.get("in_trash") or page.get("archived"):
        return {"kind": "delete", "table": kind, "row": None, "page_id": page_id, "reason": "trashed"}
    if kind == "contacts":
        payload = network_notion.person(page)
        payload["touches"] = sorted(touches or [], key=lambda t: t["date"], reverse=True)
        row = {"id": payload["id"], "payload": payload, "updated_at": _clock(payload, built)}
        return {"kind": "upsert", "table": "contacts", "row": row, "page_id": page_id, "reason": "contact"}
    if kind == "meetings":
        payload = notion_sync.meeting(page)
        row = {"id": payload["id"], "payload": payload, "updated_at": _clock(payload, built)}
        return {"kind": "upsert", "table": "meetings", "row": row, "page_id": page_id, "reason": "meeting"}
    if kind == "tasks":
        payload = notion_sync.task(page)
        if not task_on_board(payload):
            return {"kind": "delete", "table": "tasks", "row": None, "page_id": page_id,
                    "reason": "not an open career task"}
        row = {"id": payload["id"], "payload": payload, "updated_at": _clock(payload, built)}
        return {"kind": "upsert", "table": "tasks", "row": row, "page_id": page_id, "reason": "task"}
    if kind == "opportunities":
        payload = notion_sync.opportunity(page, company_names or {})
        if not payload.get("id"):
            return {"kind": "delete", "table": "opportunities", "row": None, "page_id": page_id,
                    "reason": "no job id"}
        carry_lane_since(payload, live_opp, vault_opp, today)
        row = {"id": payload["id"], "page_id": payload["page"], "payload": payload,
               "updated_at": _clock(payload, built)}
        return {"kind": "upsert", "table": "opportunities", "row": row, "page_id": page_id,
                "reason": "opportunity"}
    return {"kind": "skip", "table": None, "row": None, "page_id": page_id, "reason": "unknown database"}


def parse_ts(value):
    """Timezone-aware UTC datetime, or None. Accepts ISO strings (`Z` or `+00:00`) and datetimes."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        d = value
    else:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def iso_ms(when):
    """UTC timestamp with millisecond precision, the shape `Date.toISOString()` emits."""
    when = parse_ts(when)
    return when.strftime("%Y-%m-%dT%H:%M:%S.") + f"{when.microsecond // 1000:03d}Z"


def older_than(incoming, stored):
    """True only when `incoming` (Notion last_edited_time) is strictly older than `stored`
    (`updated_at`). Equal or newer rewrites, so a retried event is idempotent. A missing
    clock is not older: the write proceeds."""
    a, b = parse_ts(incoming), parse_ts(stored)
    if a is None or b is None:
        return False
    return a < b


def reconcile_since(watermark, now):
    """ISO `on_or_after` for a reconcile pass. No watermark: `now` minus six hours.
    A stored watermark is already the previous pass's cursor."""
    now_dt = parse_ts(now)
    mark = parse_ts(watermark)
    if mark is None:
        return iso_ms(now_dt - FIRST_LOOKBACK)
    return iso_ms(mark)


def reconcile_next(sources, now, since=None):
    """The watermark to store after a pass, or None when a backlog page has no timestamp
    (the caller must not advance).

    `sources` is `[{has_more, newest}, ...]`. Any source with `has_more` holds the cursor
    at the oldest of those sources' newest processed `last_edited_time`, so the next query
    (`on_or_after`) repeats one page and then moves on. When that minimum is not past
    `since` (a full page of identical timestamps), the cursor steps one millisecond.
    When every source is caught up, the watermark is `now` minus two minutes.
    """
    now_dt = parse_ts(now)
    incomplete = [s for s in sources if s.get("has_more")]
    if incomplete:
        times = []
        for s in incomplete:
            t = parse_ts(s.get("newest"))
            if t is None:
                return None
            times.append(t)
        nxt = min(times)
        floor = parse_ts(since)
        if floor is not None and nxt <= floor:
            return iso_ms(floor + timedelta(milliseconds=1))
        return iso_ms(nxt)
    return iso_ms(now_dt - CAUGHT_UP_LAG)


def edited_filter(since):
    """Body for one reconcile query page: edited on or after `since`, oldest first, PAGE_CAP rows."""
    iso = since if isinstance(since, str) else iso_ms(since)
    return {
        "page_size": PAGE_CAP,
        "filter": {"timestamp": "last_edited_time", "last_edited_time": {"on_or_after": iso}},
        "sorts": [{"timestamp": "last_edited_time", "direction": "ascending"}],
    }


def today_utc(now=None):
    return iso_ms(now or datetime.now(timezone.utc))[:10]
