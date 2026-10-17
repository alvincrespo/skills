#!/usr/bin/env python3
"""
Poll a PR until a *specific head SHA* has finished its checks and GitHub has
decided mergeability. Results for any other SHA are never trusted.

Usage:
    wait_for_pr.py --pr N --sha SHA [--repo OWNER/REPO] [--ci-minutes 20]
    wait_for_pr.py --pr N --sha OLD_SHA --until rebase [--rebase-minutes 15]

--until ci (default): wait on --sha itself.
--until rebase: wait for the head to move off --sha (Dependabot rebased), then
wait on the new head the same way.

Prints one JSON object: {"outcome", "sha", "ci", "mergeable"}. Outcomes:
    ready           head is SHA, every check passed, mergeable == MERGEABLE
    checks_failed   a check on SHA failed
    conflicting     mergeable == CONFLICTING (needs a rebase)
    head_changed    head is no longer SHA (it moved, or someone pushed)
    closed          the PR was merged or closed
    timeout         ci_minutes elapsed (or rebase_minutes, in rebase mode,
                    reported as rebase_timeout)

Exit codes: 0 ready, 2 any other outcome, 1 error.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any, Callable

from list_prs import ci_state, run

VIEW_FIELDS = "state,headRefOid,mergeable,statusCheckRollup"

# A PR with no checks at all looks the same as one whose checks haven't been
# registered yet, so "none" only counts as finished once it has held this long.
SETTLE_POLLS = 3

Fetch = Callable[[], dict[str, Any]]


def make_fetch(pr: int, repo: str | None) -> Fetch:
    def fetch() -> dict[str, Any]:
        cmd = ["gh", "pr", "view", str(pr), "--json", VIEW_FIELDS]
        if repo:
            cmd += ["--repo", repo]
        return json.loads(run(cmd))
    return fetch


def _result(outcome: str, view: dict[str, Any] | None, ci: str | None = None) -> dict[str, Any]:
    view = view or {}
    return {"outcome": outcome, "sha": view.get("headRefOid"),
            "ci": ci if ci is not None else ci_state(view.get("statusCheckRollup")),
            "mergeable": view.get("mergeable")}


def wait_for_ci(fetch: Fetch, sha: str, timeout_s: float, interval_s: float,
                sleep: Callable[[float], None] = time.sleep,
                now: Callable[[], float] = time.monotonic) -> dict[str, Any]:
    deadline = now() + timeout_s
    none_streak = 0
    while True:
        view = fetch()
        if view.get("state", "OPEN") != "OPEN":
            return _result("closed", view)
        if view["headRefOid"] != sha:
            return _result("head_changed", view)

        ci = ci_state(view.get("statusCheckRollup"))
        mergeable = view.get("mergeable")
        none_streak = none_streak + 1 if ci == "none" else 0

        if ci == "failing":
            return _result("checks_failed", view, ci)
        if mergeable == "CONFLICTING":
            return _result("conflicting", view, ci)
        finished = ci == "passing" or (ci == "none" and none_streak >= SETTLE_POLLS)
        if finished and mergeable == "MERGEABLE":
            return _result("ready", view, ci)

        if now() >= deadline:
            return _result("timeout", view, ci)
        sleep(interval_s)


def wait_for_rebase(fetch: Fetch, old_sha: str, rebase_timeout_s: float, ci_timeout_s: float,
                    interval_s: float, sleep: Callable[[float], None] = time.sleep,
                    now: Callable[[], float] = time.monotonic) -> dict[str, Any]:
    """Wait for the head to leave `old_sha`, then for the new head to be ready."""
    deadline = now() + rebase_timeout_s
    while True:
        view = fetch()
        if view.get("state", "OPEN") != "OPEN":
            return _result("closed", view)
        if view["headRefOid"] != old_sha:
            break
        if now() >= deadline:
            return _result("rebase_timeout", view)
        sleep(interval_s)

    # The head can move again while we wait (a second rebase); follow it, but
    # only ever report on the SHA the result names.
    ci_deadline = now() + ci_timeout_s
    sha = view["headRefOid"]
    while True:
        result = wait_for_ci(fetch, sha, max(ci_deadline - now(), 0), interval_s, sleep, now)
        if result["outcome"] == "head_changed" and now() < ci_deadline:
            sha = result["sha"]
            continue
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--sha", required=True, help="head SHA to wait on (or to wait to leave)")
    parser.add_argument("--repo", help="OWNER/REPO (default: detected by gh)")
    parser.add_argument("--until", choices=("ci", "rebase"), default="ci")
    parser.add_argument("--ci-minutes", type=float, default=20)
    parser.add_argument("--rebase-minutes", type=float, default=15)
    parser.add_argument("--interval", type=float, default=30, help="seconds between polls")
    args = parser.parse_args()

    fetch = make_fetch(args.pr, args.repo)
    try:
        if args.until == "rebase":
            result = wait_for_rebase(fetch, args.sha, args.rebase_minutes * 60,
                                     args.ci_minutes * 60, args.interval)
        else:
            result = wait_for_ci(fetch, args.sha, args.ci_minutes * 60, args.interval)
    except (RuntimeError, KeyError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["outcome"] == "ready" else 2)


if __name__ == "__main__":
    main()
