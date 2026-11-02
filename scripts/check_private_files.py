#!/usr/bin/env python3
"""Fail if tracked or staged files look like personal data.

Usage: check_private_files.py [--staged | --self-test]
"""
import re
import subprocess
import sys

BLOCKED_EXT = (".pdf", ".doc", ".docx", ".rtf", ".odt", ".pages")
BLOCKED_NAME = re.compile(r"(^|[-_./\s])(resume|cv)([-_./\s]|$)", re.I)
EMAIL = re.compile(rb"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+\.[A-Za-z0-9.-]*[A-Za-z]{2,})")
ALLOWED_EMAIL_DOMAINS = {b"example.com", b"example.org", b"anthropic.com", b"users.noreply.github.com"}


def problems(path, content):
    found = []
    if path.lower().endswith(BLOCKED_EXT) or BLOCKED_NAME.search(path):
        found.append(f"{path}: file type or name looks like a resume")
    for m in EMAIL.finditer(content):
        if m.group(1).lower() not in ALLOWED_EMAIL_DOMAINS:
            found.append(f"{path}: email address at {m.group(1).decode(errors='replace')}")
    return found


def git(*args):
    return subprocess.run(["git", *args], check=True, capture_output=True).stdout


def main():
    if "--self-test" in sys.argv:
        assert problems("my-cv.pdf", b"")
        assert problems("Resume_2026.txt", b"")
        assert problems("notes.md", b"mail me@" + b"gmail.com")
        assert not problems("CONTEXT.md", b"sam@example.com, a resume is mentioned here")
        assert not problems("scripts/recover.py", b"")
        print("self-test passed")
        return 0
    if "--staged" in sys.argv:
        paths = git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z").decode().split("\0")
        prefix = ":"
    else:
        paths = git("ls-files", "-z").decode().split("\0")
        prefix = "HEAD:"
    found = []
    for path in filter(None, paths):
        spec = prefix + path
        try:
            content = git("show", spec)
        except subprocess.CalledProcessError:
            content = open(path, "rb").read()
        found += problems(path, content)
    for line in found:
        print(line, file=sys.stderr)
    if found:
        print("Personal data stays out of this repo. Remove these before committing.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
