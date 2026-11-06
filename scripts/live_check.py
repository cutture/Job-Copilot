"""Live check of the running app against the real models, with an invented Job Posting.

    python scripts/live_check.py              # the app at http://127.0.0.1:8765
    python scripts/live_check.py --self-test  # checks this script's own file reading

It pastes an invented posting, waits for Filter and rating, clicks Apply, waits for the
Application Pack, ticks the review and downloads both files. It prints only counts, Bands and
statuses, never Evidence or document text, then deletes its own posting through the API, which
takes the Match, Application and Pack with it. Nothing is ever marked Submitted.
"""

import html
import io
import json
import re
import sys
import time
import urllib.request
import zipfile
from collections import Counter
from typing import Any

API = "http://127.0.0.1:8765"
MARKER = "(invented test posting)"
POSTING = f"""Senior Applied AI Engineer {MARKER}
Example Labs, fully remote, from anywhere in the world. Employment, full time.
You will build LLM features with Python, design retrieval pipelines and evaluate model output.
You need 3+ years of Python, experience building LLM or retrieval systems, and experience
evaluating model output. FastAPI and Postgres are a plus. Apply at careers@example.com.
"""
# Words for the app's own screens, which must never reach a downloaded file.
APP_LABELS = ["Evidence", "Removed", "Self-reported", "self_reported", "Claim", "Verification"]
WAIT_SECONDS = 600


def call(method: str, path: str, body: Any = None) -> Any:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        API + path, data=data, method=method, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        content = response.read()
    return json.loads(content) if content else None


def get_bytes(path: str) -> bytes:
    with urllib.request.urlopen(API + path, timeout=30) as response:
        return bytes(response.read())


def docx_text(content: bytes) -> str:
    """The text of a DOCX file's body, as a reader sees it."""
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        xml = archive.read("word/document.xml").decode()
    return html.unescape(re.sub(r"<[^>]+>", " ", xml))


def wait(check: Any) -> Any:
    deadline = time.time() + WAIT_SECONDS
    while time.time() < deadline:
        value = check()
        if value is not None:
            return value
        time.sleep(3)
    raise TimeoutError("The app didn't finish in time")


def posting(posting_id: str) -> dict[str, Any]:
    postings = call("GET", "/api/job-postings")
    found: dict[str, Any] = next(p for p in postings if p["id"] == posting_id)
    return found


def check(posting_id: str) -> None:
    def rated_or_set_aside() -> dict[str, Any] | None:
        found = posting(posting_id)
        set_aside = found["status"] in ("filtered", "model_unavailable", "not_rated")
        done = found.get("match") or set_aside
        return found if done else None

    rated = wait(rated_or_set_aside)
    print("posting:", rated["status"], "band:", (rated.get("match") or {}).get("band"))
    if not rated.get("match"):
        return
    application = call("POST", "/api/applications", {"job_posting_id": posting_id})
    base = f"/api/applications/{application['id']}"
    started = time.time()

    def written() -> dict[str, Any] | None:
        found: dict[str, Any] = call("GET", base)
        return found if found["pack"]["status"] != "generating" else None

    view = wait(written)
    pack = view["pack"]
    print(f"pack: {pack['status']} in {time.time() - started:.0f}s, model: {pack['model']}")
    if pack["status"] != "ready":
        print("warning:", pack["warning"])
        return
    resume = pack["resume"]
    print("resume claims:", {key: len(value) for key, value in resume.items()})
    print("cover letter sentences:", [len(p) for p in pack["cover_letter"]["paragraphs"]])
    removed = [r["text"] for r in pack["removed_claims"]]
    print("removed claims:", dict(Counter(r["kind"] for r in pack["removed_claims"])))
    call("PUT", f"{base}/review", {"reviewed": True})
    for name in ("resume.docx", "cover-letter.docx"):
        text = docx_text(get_bytes(f"{base}/{name}"))
        leaked = sum(claim in text for claim in removed + APP_LABELS)
        print(f"{name}: {len(text.split())} words, removed claims or app labels found: {leaked}")
    print("cost:", call("GET", base)["cost_usd"])


def main() -> None:
    created = call("POST", "/api/job-postings", {"text": POSTING})
    try:
        check(created["id"])
    finally:
        # Only the posting this run made, and only while it still carries the marker.
        if MARKER in posting(created["id"])["text"]:
            urllib.request.urlopen(
                urllib.request.Request(API + f"/api/job-postings/{created['id']}", method="DELETE"),
                timeout=30,
            )
            print("cleaned up: the invented posting, its Match, Application and Pack")


def self_test() -> None:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("word/document.xml", "<w:p><w:t>R&amp;D &lt;lead&gt;</w:t></w:p>")
    assert "R&D <lead>" in docx_text(out.getvalue())
    print("live_check self-test passed")


if __name__ == "__main__":
    self_test() if sys.argv[1:] == ["--self-test"] else main()
