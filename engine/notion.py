"""Notion API helpers shared by the engine (network_notion.py, notion_opps.py).

Stdlib only. Every call is paced (Notion allows about three requests a second) and a 429 or 5xx is retried with
the server's Retry-After, so a backfill of a few dozen pages never trips the limit.

config.json:
    "notion": {"token_file": "~/.notion_integration_token", "network_data_source": "<id>",
               "opportunities_data_source": "<id>", "companies_data_source": "<id>",
               "meetings_data_source": "<id>", "tasks_data_source": "<id>"}
"""
import json
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

API = "https://api.notion.com/v1"
VERSION = "2025-09-03"
PACE = 0.35
_last = [0.0]


def token(cfg):
    n = cfg.get("notion") or {}
    if not n.get("token_file"):
        raise SystemExit("config.json notion block needs token_file (see config.example.json)")
    return Path(n["token_file"]).expanduser().read_text(encoding="utf-8").strip()


def source(cfg, key):
    """A data source id from the notion block, or a clear error naming the missing key."""
    v = (cfg.get("notion") or {}).get(key)
    if not v:
        raise SystemExit(f"config.json notion block needs {key} (see config.example.json)")
    return v


def call(tok, path, body=None, method="GET", tries=5):
    data = None if body is None else json.dumps(body).encode("utf-8")
    for attempt in range(tries):
        wait = PACE - (time.monotonic() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.monotonic()
        req = Request(f"{API}{path}", data=data, method=method,
                      headers={"Authorization": f"Bearer {tok}", "Notion-Version": VERSION,
                               "Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except HTTPError as e:
            if (e.code == 429 or e.code >= 500) and attempt < tries - 1:
                time.sleep(float(e.headers.get("Retry-After") or 2 ** attempt))
                continue
            raise SystemExit(f"notion {path}: HTTP {e.code} {e.read().decode('utf-8', 'replace')[:200]}")


def query_all(tok, data_source, body=None):
    pages, cursor = [], None
    while True:
        res = call(tok, f"/data_sources/{data_source}/query",
                   {"page_size": 100, **(body or {}), **({"start_cursor": cursor} if cursor else {})}, "POST")
        pages += [p for p in res.get("results") or [] if not (p.get("in_trash") or p.get("archived"))]
        if not res.get("has_more"):
            return pages
        cursor = res.get("next_cursor")


def children(tok, block_id):
    out, cursor = [], None
    while True:
        res = call(tok, f"/blocks/{block_id}/children?page_size=100" + (f"&start_cursor={cursor}" if cursor else ""))
        out += res.get("results") or []
        if not res.get("has_more"):
            return out
        cursor = res.get("next_cursor")


def plain(prop):
    """A Notion property value as plain data. Keep in step with plain() in supabase/functions/network-write."""
    if not prop:
        return None
    t = prop.get("type")
    v = prop.get(t)
    if t in ("title", "rich_text"):
        return "".join(x.get("plain_text", "") for x in v or []) or None
    if t in ("select", "status"):
        return (v or {}).get("name")
    if t == "multi_select":
        return ", ".join(o["name"] for o in v or []) or None
    if t == "date":
        return (v or {}).get("start")
    if t == "relation":
        return [x["id"] for x in v or []]
    if t == "formula":
        return (v or {}).get((v or {}).get("type"))
    if t == "rollup":
        v = v or {}
        if v.get("type") == "date":
            return (v.get("date") or {}).get("start")
        if v.get("type") == "number":
            return v.get("number")
        if v.get("type") == "array":
            vals = sorted(str(x) for x in (plain(i) for i in v.get("array") or []) if x)
            return vals[-1] if vals else None
        return None
    return v


def text(s):
    return [{"type": "text", "text": {"content": str(s)[:2000]}}] if s else []


def prop(kind, value):
    """A property value for a page write. None clears it."""
    if kind == "title":
        return {"title": text(value)}
    if kind == "rich_text":
        return {"rich_text": text(value)}
    if kind == "select":
        return {"select": {"name": value} if value else None}
    if kind == "date":
        return {"date": {"start": value} if value else None}
    if kind == "url":
        return {"url": value or None}
    if kind == "number":
        return {"number": value}
    if kind == "checkbox":
        return {"checkbox": bool(value)}
    if kind == "relation":
        return {"relation": [{"id": i} for i in value or []]}
    raise ValueError(kind)
