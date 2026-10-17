#!/usr/bin/env python3
"""
List open PRs by the configured authors, oldest first, with the version bump
and its semver level parsed from the title.

Usage:
    list_prs.py [--repo OWNER/REPO] [--author AUTHOR ...] [--format json|table]

Authors default to app/dependabot. --repo defaults to the repo `gh` detects
from the current directory.

Each PR is reported as:
    number, title, url, created_at, head_ref, head_sha, mergeable,
    package, from, to, level ("major"|"minor"|"patch"|"unknown"), ci

`level` comes from titles like "Bump foo from 1.2.3 to 2.0.0". Group bumps
("Bump the npm group with 3 updates") and anything unparseable are "unknown"
and are never treated as safe. `ci` is "passing", "failing", "pending" or
"none", from the PR's current check rollup.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from typing import Any

DEFAULT_AUTHOR = "app/dependabot"

PR_FIELDS = "number,title,url,createdAt,headRefName,headRefOid,mergeable,statusCheckRollup"

_BUMP = re.compile(r"\b[Bb]ump\s+(?P<package>\S+)\s+from\s+(?P<from>\S+)\s+to\s+(?P<to>\S+)")
_VERSION = re.compile(r"^v?(\d+)(?:\.(\d+))?(?:\.(\d+))?")

_FAILING = {"FAILURE", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE", "ERROR"}
_PASSING = {"SUCCESS", "NEUTRAL", "SKIPPED"}


def run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed: {result.stderr.strip()}")
    return result.stdout


def parse_bump(title: str) -> tuple[str, str, str] | None:
    """Return (package, from, to) from a Dependabot title, or None."""
    m = _BUMP.search(title)
    if not m:
        return None
    return m["package"], m["from"], m["to"]


def classify(old: str, new: str) -> str:
    """Semver level of old -> new. Missing minor/patch count as 0 ("3" -> "4" is major)."""
    a, b = _VERSION.match(old), _VERSION.match(new)
    if not a or not b:
        return "unknown"
    old_parts = [int(p or 0) for p in a.groups()]
    new_parts = [int(p or 0) for p in b.groups()]
    for level, x, y in zip(("major", "minor", "patch"), old_parts, new_parts):
        if x != y:
            return level
    return "patch"  # same numbers, e.g. a prerelease tag changed


def ci_state(rollup: list[dict[str, Any]] | None) -> str:
    """Collapse a statusCheckRollup into passing/failing/pending/none."""
    if not rollup:
        return "none"
    pending = False
    for check in rollup:
        if check.get("__typename") == "StatusContext":
            state = (check.get("state") or "").upper()
            if state in ("SUCCESS",):
                continue
            if state in ("FAILURE", "ERROR"):
                return "failing"
            pending = True
            continue
        if (check.get("status") or "").upper() != "COMPLETED":
            pending = True
            continue
        conclusion = (check.get("conclusion") or "").upper()
        if conclusion in _FAILING:
            return "failing"
        if conclusion not in _PASSING:
            pending = True
    return "pending" if pending else "passing"


def summarize(pr: dict[str, Any]) -> dict[str, Any]:
    bump = parse_bump(pr["title"])
    package, old, new = bump if bump else (None, None, None)
    return {
        "number": pr["number"],
        "title": pr["title"],
        "url": pr["url"],
        "created_at": pr["createdAt"],
        "head_ref": pr["headRefName"],
        "head_sha": pr["headRefOid"],
        "mergeable": pr["mergeable"],
        "package": package,
        "from": old,
        "to": new,
        "level": classify(old, new) if bump else "unknown",
        "ci": ci_state(pr.get("statusCheckRollup")),
    }


def list_prs(authors: list[str], repo: str | None = None) -> list[dict[str, Any]]:
    """Open PRs by any of `authors`, oldest first (PR number breaks ties)."""
    by_number: dict[int, dict[str, Any]] = {}
    for author in authors:
        cmd = ["gh", "pr", "list", "--state", "open", "--author", author,
               "--limit", "200", "--json", PR_FIELDS]
        if repo:
            cmd += ["--repo", repo]
        for pr in json.loads(run(cmd)):
            by_number[pr["number"]] = pr
    ordered = sorted(by_number.values(), key=lambda p: (p["createdAt"], p["number"]))
    return [summarize(pr) for pr in ordered]


def render_table(prs: list[dict[str, Any]]) -> str:
    if not prs:
        return "No open PRs."
    rows = ["| # | Bump | Level | CI | Mergeable |", "|---|---|---|---|---|"]
    for pr in prs:
        bump = f"{pr['package']} {pr['from']} → {pr['to']}" if pr["package"] else pr["title"]
        level = f"⚠ {pr['level']}" if pr["level"] in ("major", "unknown") else pr["level"]
        rows.append(f"| #{pr['number']} | {bump} | {level} | {pr['ci']} | {pr['mergeable']} |")
    return "\n".join(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", help="OWNER/REPO (default: detected by gh)")
    parser.add_argument("--author", action="append", dest="authors",
                        help=f"PR author, repeatable (default: {DEFAULT_AUTHOR})")
    parser.add_argument("--format", choices=("json", "table"), default="json")
    args = parser.parse_args()

    try:
        prs = list_prs(args.authors or [DEFAULT_AUTHOR], args.repo)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
    print(render_table(prs) if args.format == "table" else json.dumps(prs, indent=2))


if __name__ == "__main__":
    main()
