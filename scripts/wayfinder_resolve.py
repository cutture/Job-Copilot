#!/usr/bin/env python3
"""Post a ticket's resolution, close it, and add its line to the map's Decisions so far.

Usage: wayfinder_resolve.py <ticket> <answer-file> "<one-line gist>" [--map N]
       wayfinder_resolve.py --self-test
"""
import json
import subprocess
import sys

REPO = "cutture/Job-Copilot"
MARKER = "\n## Not yet specified"


def gh(*args):
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True, encoding="utf-8").stdout.strip()


def insert_decision(body, line):
    """Add one decision line at the end of Decisions so far."""
    if body.count(MARKER) != 1:
        raise ValueError("map must have exactly one 'Not yet specified' heading")
    if line.split("](")[1].split(")")[0] + ")" in body:
        raise ValueError("this ticket is already in the map")
    head, tail = body.split(MARKER)
    return head.rstrip("\n") + "\n" + line + "\n" + MARKER + tail


def main():
    argv = sys.argv[1:]
    if argv == ["--self-test"]:
        body = "## Decisions so far\n\n- [A](u/1): a\n\n## Not yet specified\n\n- fog\n"
        out = insert_decision(body, "- [B](u/2): b")
        assert out == "## Decisions so far\n\n- [A](u/1): a\n- [B](u/2): b\n\n## Not yet specified\n\n- fog\n"
        try:
            insert_decision(out, "- [B](u/2): b")
        except ValueError:
            print("self-test passed")
            return 0
        raise AssertionError("duplicate line was accepted")
    map_no = "1"
    if "--map" in argv:
        i = argv.index("--map")
        map_no = argv[i + 1]
        del argv[i : i + 2]
    ticket, answer_file, gist = argv
    info = json.loads(gh("issue", "view", ticket, "--repo", REPO, "--json", "title,url"))
    line = f"- [{info['title']}]({info['url']}): {gist}"
    body = json.loads(gh("issue", "view", map_no, "--repo", REPO, "--json", "body"))["body"]
    updated = insert_decision(body, line)  # fails before anything is posted
    print(gh("issue", "comment", ticket, "--repo", REPO, "--body-file", answer_file))
    gh("issue", "close", ticket, "--repo", REPO)
    # Re-read so another session's map edit isn't overwritten.
    body = json.loads(gh("issue", "view", map_no, "--repo", REPO, "--json", "body"))["body"]
    updated = insert_decision(body, line)
    subprocess.run(["gh", "issue", "edit", map_no, "--repo", REPO, "--body-file", "-"], input=updated, check=True,
                   capture_output=True, text=True, encoding="utf-8")
    print("closed and added to map")
    return 0


if __name__ == "__main__":
    sys.exit(main())
