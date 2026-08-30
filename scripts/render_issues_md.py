#!/usr/bin/env python3
"""
Render tracker/issues.py into a full, human-readable markdown listing.

    python scripts/render_issues_md.py > ISSUES.md

This exists so there's a reviewable document with every epic's and every
issue's actual title, body, and acceptance criteria — the thing to read
before running scripts/bootstrap_github_project.py and generating 35 real
GitHub issues, not after.

Deliberately generated, not hand-maintained: tracker/issues.py is the only
place issue content is written. If you edit an issue there, re-run this
script to regenerate ISSUES.md rather than editing ISSUES.md directly —
the same "one source of truth" reasoning TRACKER.md's bootstrap section
already documents for the GitHub issues themselves.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from tracker.issues import EPICS, MILESTONE, RELEASE_VALIDATION_ISSUE  # noqa: E402


def render() -> str:
    lines: list[str] = []
    w = lines.append

    w("<!-- Generated from tracker/issues.py by scripts/render_issues_md.py.")
    w("     Edit tracker/issues.py and re-run the script — don't edit this file directly. -->")
    w("")
    w("# ISSUES.md — every epic and issue, in full")
    w("")
    total_issues = sum(len(e["issues"]) for e in EPICS) + len(EPICS) + 1
    w(f"{len(EPICS)} epics, {total_issues} total issues (epics + children + "
      f"release validation). This is what `scripts/bootstrap_github_project.py` "
      f"creates in GitHub — review it here first.")
    w("")
    w(f"**Milestone:** {MILESTONE['title']}")
    w("")
    w(f"> {MILESTONE['description']}")
    w("")
    w("---")
    w("")

    for i, epic in enumerate(EPICS, start=1):
        w(f"## {i}. {epic['title']}")
        w("")
        labels = ", ".join(f"`{l}`" for l in epic.get("labels", []))
        depends = ", ".join(epic.get("depends_on", [])) or "—"
        w(f"**Labels:** `epic`, {labels}  ")
        w(f"**Blocked by:** {depends}")
        w("")
        w(epic["body"])
        w("")
        w(f"### Issues in this epic ({len(epic['issues'])})")
        w("")
        for j, issue in enumerate(epic["issues"], start=1):
            issue_labels = ", ".join(f"`{l}`" for l in issue.get("labels", []))
            w(f"#### {i}.{j} {issue['title']}")
            w("")
            w(f"**Labels:** `task`, {issue_labels}")
            w("")
            w(issue["body"])
            w("")
        w("---")
        w("")

    w("## Release validation (standalone — blocked by every epic above)")
    w("")
    v = RELEASE_VALIDATION_ISSUE
    v_labels = ", ".join(f"`{l}`" for l in v.get("labels", []))
    w(f"**Title:** {v['title']}  ")
    w(f"**Labels:** {v_labels}  ")
    w(f"**Blocked by:** {', '.join(e['title'] for e in EPICS)}")
    w("")
    w(v["body"])
    w("")

    return "\n".join(lines)


if __name__ == "__main__":
    print(render())
