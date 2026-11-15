"""Replace text in an issue body, such as the spec or a ticket.

Usage: python scripts/issue_edit.py <issue> <edits.json>
       python scripts/issue_edit.py --self-check

edits.json is a list of [old, new] pairs, written with the Write tool. Each old text must
appear exactly once, or nothing is written.
"""
import json
import subprocess
import sys

# ponytail: GitHub has no conditional issue update, so a write in the gap between
# read and edit is still lost. The verify step only spots a lost edit of our own.


def apply_edits(body, edits):
    for old, new in edits:
        count = body.count(old)
        if count != 1:
            raise ValueError(f"found {count} times, expected once: {old[:60]!r}")
        body = body.replace(old, new)
    return body


def gh(*args, stdin=None):
    return subprocess.run(
        ["gh", "issue", *args], input=stdin, capture_output=True, text=True, encoding="utf-8", check=True
    ).stdout


def read_body(issue):
    return gh("view", issue, "--json", "body", "-q", ".body").replace("\r\n", "\n").rstrip("\n")


def main(issue, edits_file):
    with open(edits_file, encoding="utf-8") as f:
        edits = json.load(f)
    gh("edit", issue, "--body-file", "-", stdin=apply_edits(read_body(issue), edits))
    body = read_body(issue)
    if any(new and new not in body for _, new in edits):
        sys.exit("edit missing after write: another session may have overwritten it, so retry")


def self_check():
    assert apply_edits("a b c", [["b", "B"], ["c", ""]]) == "a B "
    # Missing text, and text found twice.
    for body, edits in (("a b", [["x", "y"]]), ("a a", [["a", "z"]])):
        try:
            apply_edits(body, edits)
        except ValueError:
            continue
        raise AssertionError(f"must raise: {edits}")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-check"]:
        self_check()
        print("ok")
    else:
        main(*sys.argv[1:])
