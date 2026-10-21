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
    ("today", "today"), ("inbox", "inbox"), ("pipeline", "pipeline"), ("pipeline/research", "pipeline-research"),
    ("pipeline/{research}", "opportunity"), ("people", "people"), ("map", "map"),
]
PHONE = [("today", "phone-today"), ("inbox", "phone-inbox"), ("pipeline", "phone-pipeline"), ("people", "phone-people")]


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
        page.goto(f"http://127.0.0.1:{PORT}/#today")
        page.wait_for_timeout(2500)
        ids = page.evaluate("""() => ({
            interviewing: (JOBS.find(j => j.stage === 'interviewing') || JOBS[0]).id,
            inbox: (JOBS.find(j => !j.verdict && !j.stage && j.score >= 8) || JOBS[0]).id,
            research: (JOBS.find(j => j.plan && j.plan.status === 'proposed' && !(j.plan.input || []).length) || JOBS[0]).id })""")
        for route, name in DESKTOP:
            page.evaluate("h => { location.hash = '#' + h; }", route.format(**ids))
            page.wait_for_timeout(1800 if "map" in route else 1200)
            page.screenshot(path=str(OUT / f"{name}.png"))
            print("desktop", name)
        ctx.close()
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
        page = ctx.new_page()
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.goto(f"http://127.0.0.1:{PORT}/#today")
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
