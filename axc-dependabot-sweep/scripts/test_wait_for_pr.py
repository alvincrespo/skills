#!/usr/bin/env python3
"""
Unit tests for wait_for_pr.py. Time and `gh` are faked: no real sleeping.

Run directly:
    python3 -m unittest axc-dependabot-sweep/scripts/test_wait_for_pr.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
import wait_for_pr  # noqa: E402

PASS = {"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "SUCCESS"}
FAIL = {"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "FAILURE"}
RUNNING = {"__typename": "CheckRun", "status": "IN_PROGRESS", "conclusion": ""}


def view(sha: str = "aaa", rollup=None, mergeable: str = "MERGEABLE", state: str = "OPEN") -> dict:
    return {"state": state, "headRefOid": sha, "mergeable": mergeable,
            "statusCheckRollup": rollup if rollup is not None else [PASS]}


class Clock:
    """Fake clock: sleep() advances time; fetch() is scripted per poll."""

    def __init__(self, views: list[dict]) -> None:
        self.t = 0.0
        self.views = list(views)
        self.polls = 0

    def now(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.t += s

    def fetch(self) -> dict:
        self.polls += 1
        # Repeat the last view once the script runs out.
        return self.views.pop(0) if len(self.views) > 1 else self.views[0]


def ci(clock: Clock, sha: str = "aaa", timeout: float = 600, interval: float = 30) -> dict:
    return wait_for_pr.wait_for_ci(clock.fetch, sha, timeout, interval, clock.sleep, clock.now)


class WaitForCiTests(unittest.TestCase):
    def test_ready_immediately(self) -> None:
        clock = Clock([view()])
        result = ci(clock)
        self.assertEqual(result, {"outcome": "ready", "sha": "aaa", "ci": "passing",
                                  "mergeable": "MERGEABLE"})
        self.assertEqual(clock.polls, 1)

    def test_waits_for_running_checks(self) -> None:
        clock = Clock([view(rollup=[PASS, RUNNING]), view(rollup=[PASS, RUNNING]), view()])
        self.assertEqual(ci(clock)["outcome"], "ready")
        self.assertEqual(clock.polls, 3)

    def test_unknown_mergeable_keeps_polling_even_when_checks_pass(self) -> None:
        clock = Clock([view(mergeable="UNKNOWN"), view(mergeable="UNKNOWN"), view()])
        self.assertEqual(ci(clock)["outcome"], "ready")
        self.assertEqual(clock.polls, 3)

    def test_check_failure(self) -> None:
        clock = Clock([view(rollup=[RUNNING, FAIL])])
        result = ci(clock)
        self.assertEqual(result["outcome"], "checks_failed")
        self.assertEqual(result["ci"], "failing")

    def test_conflict_returns_without_waiting_for_checks(self) -> None:
        clock = Clock([view(rollup=[RUNNING], mergeable="CONFLICTING")])
        self.assertEqual(ci(clock)["outcome"], "conflicting")
        self.assertEqual(clock.polls, 1)

    def test_head_change_is_never_trusted(self) -> None:
        # Old SHA's checks passed, but the head has since moved.
        clock = Clock([view(sha="bbb")])
        result = ci(clock, sha="aaa")
        self.assertEqual(result["outcome"], "head_changed")
        self.assertEqual(result["sha"], "bbb")

    def test_head_change_mid_wait(self) -> None:
        clock = Clock([view(rollup=[RUNNING]), view(sha="bbb")])
        self.assertEqual(ci(clock)["outcome"], "head_changed")

    def test_closed_pr(self) -> None:
        clock = Clock([view(state="MERGED")])
        self.assertEqual(ci(clock)["outcome"], "closed")

    def test_timeout(self) -> None:
        clock = Clock([view(rollup=[RUNNING])])
        result = ci(clock, timeout=100, interval=30)
        self.assertEqual(result["outcome"], "timeout")
        self.assertEqual(result["ci"], "pending")
        self.assertEqual(clock.polls, 5)  # t = 0, 30, 60, 90, 120

    def test_no_checks_needs_to_settle(self) -> None:
        # Checks may simply not be registered yet right after a push.
        clock = Clock([view(rollup=[]), view(rollup=[]), view(rollup=[RUNNING]), view()])
        result = ci(clock)
        self.assertEqual(result["outcome"], "ready")
        self.assertEqual(result["ci"], "passing")

    def test_no_checks_at_all_is_ready_once_settled(self) -> None:
        clock = Clock([view(rollup=[])])
        result = ci(clock)
        self.assertEqual(result["outcome"], "ready")
        self.assertEqual(result["ci"], "none")
        self.assertEqual(clock.polls, wait_for_pr.SETTLE_POLLS)


def rebase(clock: Clock, old: str = "aaa", rebase_timeout: float = 300,
           ci_timeout: float = 600, interval: float = 30) -> dict:
    return wait_for_pr.wait_for_rebase(clock.fetch, old, rebase_timeout, ci_timeout, interval,
                                       clock.sleep, clock.now)


class WaitForRebaseTests(unittest.TestCase):
    def test_new_sha_then_ready(self) -> None:
        clock = Clock([view("aaa", mergeable="CONFLICTING"), view("aaa", mergeable="CONFLICTING"),
                       view("bbb", rollup=[RUNNING]), view("bbb")])
        result = rebase(clock)
        self.assertEqual(result["outcome"], "ready")
        self.assertEqual(result["sha"], "bbb")

    def test_old_sha_checks_do_not_count(self) -> None:
        # Old head is green and mergeable; we still wait for it to move.
        clock = Clock([view("aaa"), view("aaa"), view("bbb")])
        result = rebase(clock)
        self.assertEqual(result["sha"], "bbb")
        self.assertEqual(clock.polls, 4)  # 3 to see the move, 1 fresh read of the new head

    def test_rebase_timeout(self) -> None:
        clock = Clock([view("aaa")])
        result = rebase(clock, rebase_timeout=60)
        self.assertEqual(result["outcome"], "rebase_timeout")
        self.assertEqual(result["sha"], "aaa")

    def test_follows_a_second_rebase(self) -> None:
        clock = Clock([view("bbb", rollup=[RUNNING]), view("ccc")])
        result = rebase(clock)
        self.assertEqual(result["outcome"], "ready")
        self.assertEqual(result["sha"], "ccc")

    def test_new_head_conflicts_again(self) -> None:
        clock = Clock([view("bbb", mergeable="CONFLICTING")])
        self.assertEqual(rebase(clock)["outcome"], "conflicting")

    def test_new_head_fails_checks(self) -> None:
        clock = Clock([view("bbb", rollup=[FAIL])])
        self.assertEqual(rebase(clock)["outcome"], "checks_failed")

    def test_ci_timeout_after_rebase(self) -> None:
        clock = Clock([view("bbb", rollup=[RUNNING])])
        self.assertEqual(rebase(clock, ci_timeout=60)["outcome"], "timeout")


class FetchTests(unittest.TestCase):
    def test_builds_exact_gh_command(self) -> None:
        done = subprocess.CompletedProcess(args=[], returncode=0, stdout=json.dumps(view()), stderr="")
        with mock.patch("list_prs.subprocess.run", return_value=done) as mock_run:
            wait_for_pr.make_fetch(12, "o/r")()
        mock_run.assert_called_once_with(
            ["gh", "pr", "view", "12", "--json", wait_for_pr.VIEW_FIELDS, "--repo", "o/r"],
            capture_output=True, text=True,
        )


if __name__ == "__main__":
    unittest.main()
