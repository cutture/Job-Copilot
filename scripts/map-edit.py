"""Append one line to a section of a wayfinder map's issue body.

Usage: python scripts/map-edit.py <issue> "<section heading>" "<line>"
       python scripts/map-edit.py --self-check
"""
import subprocess
import sys

# ponytail: GitHub has no conditional issue update, so a write in the gap between
# read and edit is still lost. The verify step only spots a lost line of our own.


def append_to_section(body, section, line):
    lines = body.split("\n")
    heading = f"## {section}"
    if heading not in lines:
        raise ValueError(f"no section: {heading}")
    start = lines.index(heading) + 1
    end = next((i for i in range(start, len(lines)) if lines[i].startswith("## ")), len(lines))
    while end > start and not lines[end - 1].strip():
        end -= 1
    if end == start:
        return "\n".join(lines[:start] + ["", line] + lines[start:])
    return "\n".join(lines[:end] + [line] + lines[end:])


def gh(*args, stdin=None):
    return subprocess.run(
        ["gh", "issue", *args], input=stdin, capture_output=True, text=True, encoding="utf-8", check=True
    ).stdout


def read_body(issue):
    return gh("view", issue, "--json", "body", "-q", ".body").rstrip("\n")


def main(issue, section, line):
    gh("edit", issue, "--body-file", "-", stdin=append_to_section(read_body(issue), section, line))
    if line not in read_body(issue):
        sys.exit("line missing after write: another session may have overwritten it, so retry")


def self_check():
    body = "## A\n\n- one\n\n## B\n\n## C\n- x"
    assert append_to_section(body, "A", "- two") == "## A\n\n- one\n- two\n\n## B\n\n## C\n- x"
    assert append_to_section(body, "B", "- y") == "## A\n\n- one\n\n## B\n\n- y\n\n## C\n- x"
    assert append_to_section(body, "C", "- z") == "## A\n\n- one\n\n## B\n\n## C\n- x\n- z"
    try:
        append_to_section(body, "D", "- q")
    except ValueError:
        return
    raise AssertionError("missing section must raise")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-check"]:
        self_check()
        print("ok")
    else:
        main(*sys.argv[1:])
