"""Leave a message for the owner: one row in Supabase `notifications`, read by his career coach bot (2026-11-02).

    py engine/notify.py <source> [--ping] [--channel job-search]      text on stdin
    py engine/notify.py --show [--hours 24]                            the last messages

Replaces the Discord posts (Personal-OS Tools/discord_post.py job-search). The routines write here; the Grok bot reads
the `notify-feed` edge function (supabase/functions/notify-feed) and passes each message on. `ping` marks the ones
worth interrupting him for (a booked interview, a reply on an Active role, a move due within 48 hours, a failure).
Nothing here is sent to anyone.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_config  # noqa: E402
import supabase as sb  # noqa: E402


def post(cfg, source, text, ping=False, channel="job-search"):
    text = (text or "").strip()
    if not text:
        return None
    rows = sb.request("POST", "notifications", body=[{"source": source, "channel": channel, "text": text[:8000],
                                                       "ping": bool(ping)}],
                      prefer="return=representation", cfg=cfg) or []
    return rows[0]["id"] if rows else None


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    args = sys.argv[1:]
    cfg = load_config()
    if "--show" in args:
        hours = int(args[args.index("--hours") + 1]) if "--hours" in args else 24
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="seconds")
        for r in sb.select("notifications", {"select": "*", "created_at": f"gte.{since}", "order": "created_at.asc"},
                           cfg=cfg):
            flag = " PING" if r.get("ping") else ""
            print(f"{r['created_at'][:16]} {r['source']}{flag}: {r['text']}")
        return
    if not args or args[0].startswith("--"):
        raise SystemExit("usage: py engine/notify.py <source> [--ping] [--channel NAME]  (text on stdin)")
    channel = args[args.index("--channel") + 1] if "--channel" in args else "job-search"
    rid = post(cfg, args[0], sys.stdin.read(), ping="--ping" in args, channel=channel)
    print(f"notification {rid}" if rid else "nothing to post")


if __name__ == "__main__":
    main()
