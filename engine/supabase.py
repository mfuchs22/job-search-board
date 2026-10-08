"""Minimal PostgREST client for the engine: stdlib urllib, service key, bypasses RLS.

The board lives in a Supabase project (tables: jobs, board_meta, verdicts, stages; see docs/schema.md).
The engine writes jobs and board_meta (push_board.py) and reads verdicts and stages (ingest_db.py).
config.json carries `supabase.url` and `supabase.service_key` (an sb_secret_... key, or a legacy
service_role JWT; both work), or a 1Password reference (op://Agents/<item>/credential) that
common.load_config resolves through the op CLI. Nothing here is personal.
"""
import json
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from common import load_config


def settings(cfg=None):
    s = (cfg or load_config()).get("supabase") or {}
    if not (s.get("url") and s.get("service_key")):
        raise SystemExit("config.json needs supabase.url and supabase.service_key (see config.example.json)")
    return s["url"].rstrip("/"), s["service_key"]


def _headers(key, prefer=None):
    h = {"apikey": key, "Content-Type": "application/json", "Accept": "application/json"}
    if key.startswith("eyJ"):  # legacy service_role JWT wants Bearer too; sb_secret_ keys must not send it
        h["Authorization"] = f"Bearer {key}"
    if prefer:
        h["Prefer"] = prefer
    return h


def request(method, table, params=None, body=None, prefer=None, cfg=None):
    url, key = settings(cfg)
    q = f"?{urlencode(params)}" if params else ""
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = Request(f"{url}/rest/v1/{table}{q}", method=method, headers=_headers(key, prefer), data=data)
    try:
        with urlopen(req, timeout=60) as r:
            raw = r.read()
            return json.loads(raw) if raw else None
    except HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:400]
        raise SystemExit(f"supabase {method} {table}: HTTP {e.code} {detail}")


def select(table, params=None, cfg=None):
    return request("GET", table, params=params or {"select": "*"}, cfg=cfg) or []


def upsert(table, rows, chunk=50, cfg=None):
    """POST with merge-duplicates: conflicts on the primary key become updates. jsonb columns take dicts as-is."""
    for i in range(0, len(rows), chunk):
        request("POST", table, body=rows[i:i + chunk], prefer="resolution=merge-duplicates,return=minimal", cfg=cfg)
    return len(rows)


def delete_where(table, params, cfg=None):
    request("DELETE", table, params=params, prefer="return=minimal", cfg=cfg)


def delete_not_in(table, keep_ids, col="id", cfg=None):
    """Delete rows whose key is not in keep_ids. Reads the current keys first so the request never depends
    on the length of keep_ids. Returns the deleted keys."""
    have = {r[col] for r in select(table, {"select": col}, cfg=cfg)}
    stale = sorted(have - set(keep_ids))
    for i in range(0, len(stale), 100):
        delete_where(table, {col: "in.(" + ",".join(stale[i:i + 100]) + ")"}, cfg=cfg)
    return stale


def iso_z(ts):
    """Normalize a PostgREST timestamptz ('2026-09-04T01:51:04.236+00:00') to the page's JS form
    ('2026-09-04T01:51:04.236Z') so string comparison with jobs.json verdict_ts / stage_ts stays valid."""
    if not ts:
        return ""
    d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    d = d.astimezone(timezone.utc)
    return d.strftime("%Y-%m-%dT%H:%M:%S.") + f"{d.microsecond // 1000:03d}Z"
