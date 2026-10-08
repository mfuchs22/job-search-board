"""Screenshot every tab of the demo board for the README, and report page errors.

    py -m pip install playwright && py -m playwright install chromium     once
    py demo/screenshots.py [--serve]                                        writes screenshots/*.png

Serves web/ on a local port, opens each route at desktop and phone sizes, and fails if the page threw.
"""
import http.server
import socketserver
import sys
import threading
from functools import partial
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "screenshots"
PORT = 8749
DESKTOP = [
    ("overview", "overview"), ("inbox", "inbox"), ("board", "shortlist"), ("active", "in-process"), ("active/{interviewing}", "in-process-role"),
    ("job/{inbox}", "role-detail"), ("closed", "closed"), ("screened", "passed"), ("startups", "startups-review"), ("startups/lumen-agents", "startup-profile"),
    ("watchlist", "watchlist"), ("network", "network"), ("todos", "todos"), ("map", "map"),
]
PHONE = [("overview", "phone-overview"), ("inbox", "phone-inbox"), ("board", "phone-shortlist"), ("todos", "phone-todos")]


def serve():
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT / "web"))
    httpd = socketserver.TCPServer(("127.0.0.1", PORT), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def main():
    OUT.mkdir(exist_ok=True)
    httpd = serve()
    errs = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
        page = ctx.new_page()
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.goto(f"http://127.0.0.1:{PORT}/#overview")
        page.wait_for_timeout(2500)
        ids = page.evaluate("""() => ({
            interviewing: (JOBS.find(j => j.stage === 'interviewing') || JOBS[0]).id,
            inbox: (JOBS.find(j => !j.verdict && !j.stage && j.score >= 8) || JOBS[0]).id })""")
        for route, name in DESKTOP:
            page.evaluate("h => { location.hash = '#' + h; }", route.format(**ids))
            page.wait_for_timeout(1800 if "map" in route else 1200)
            page.screenshot(path=str(OUT / f"{name}.png"))
            print("desktop", name)
        ctx.close()
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
        page = ctx.new_page()
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.goto(f"http://127.0.0.1:{PORT}/#overview")
        page.wait_for_timeout(2500)
        for route, name in PHONE:
            page.evaluate("h => { location.hash = '#' + h; }", route)
            page.wait_for_timeout(1200)
            page.screenshot(path=str(OUT / f"{name}.png"))
            print("phone", name)
        browser.close()
    httpd.shutdown()
    if errs:
        print("page errors:\n  " + "\n  ".join(dict.fromkeys(errs)))
        sys.exit(1)
    print("no page errors")


if __name__ == "__main__":
    main()
