#!/usr/bin/env python3
"""Load every prototype layout in Chromium, fail on page errors, save screenshots.

Usage: smoke_prototypes.py [screenshot-dir]   Needs: pip install playwright && playwright install chromium
"""
import functools
import http.server
import pathlib
import sys
import threading

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent / "prototypes"


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    out = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if out:
        out.mkdir(parents=True, exist_ok=True)
    handler = functools.partial(QuietHandler, directory=str(ROOT))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for html in sorted(ROOT.glob("*-PROTOTYPE.html")):
            page = browser.new_page(viewport={"width": 1366, "height": 800})
            page.on("pageerror", lambda e, n=html.name: errors.append(f"{n}: {e}"))
            page.on("console", lambda m, n=html.name: errors.append(f"{n}: {m.text}") if m.type == "error" else None)
            page.goto(f"{base}/{html.name}")
            if not page.inner_text("#app").strip():
                errors.append(f"{html.name}: nothing rendered")
            for i in range(page.locator("[data-v]").count()):
                page.locator("[data-v]").nth(i).click()
                if not page.inner_text("#app").strip():
                    errors.append(f"{html.name}: layout {i} rendered nothing")
                if out:
                    page.screenshot(path=str(out / f"{html.stem}-{i}.png"), full_page=True)
            page.close()
        browser.close()
    server.shutdown()
    for e in errors:
        print(e, file=sys.stderr)
    print(f"{'FAILED' if errors else 'passed'}: {len(list(ROOT.glob('*-PROTOTYPE.html')))} pages")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
