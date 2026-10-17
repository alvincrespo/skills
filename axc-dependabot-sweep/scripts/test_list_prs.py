#!/usr/bin/env python3
"""
Unit tests for list_prs.py.

Run directly:
    python3 -m unittest axc-dependabot-sweep/scripts/test_list_prs.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
import list_prs  # noqa: E402


def pr(number: int, title: str, created: str, rollup=None, **extra) -> dict:
    return {"number": number, "title": title, "url": f"https://github.com/o/r/pull/{number}",
            "createdAt": created, "headRefName": f"dependabot/{number}",
            "headRefOid": f"sha{number}", "mergeable": "MERGEABLE",
            "statusCheckRollup": rollup or [], **extra}


def completed(stdout: str = "", returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


class ClassifyTests(unittest.TestCase):
    def test_levels(self) -> None:
        cases = [
            ("1.2.3", "2.0.0", "major"),
            ("1.2.3", "1.3.0", "minor"),
            ("1.2.3", "1.2.4", "patch"),
            ("3", "4", "major"),
            ("v3.1", "v3.2", "minor"),
            ("1.0.0-beta.1", "1.0.0", "patch"),
            ("17.0.0", "17.0.0", "patch"),
            ("abc", "1.0.0", "unknown"),
        ]
        for old, new, expected in cases:
            with self.subTest(old=old, new=new):
                self.assertEqual(list_prs.classify(old, new), expected)


class ParseBumpTests(unittest.TestCase):
    def test_plain_and_prefixed_titles(self) -> None:
        self.assertEqual(list_prs.parse_bump("Bump postcss-import from 16.1.0 to 17.0.0"),
                         ("postcss-import", "16.1.0", "17.0.0"))
        self.assertEqual(list_prs.parse_bump("chore(deps): bump actions/checkout from 3 to 4"),
                         ("actions/checkout", "3", "4"))

    def test_group_title_is_not_a_bump(self) -> None:
        self.assertIsNone(list_prs.parse_bump("Bump the npm group with 3 updates"))


class CiStateTests(unittest.TestCase):
    def check(self, status: str, conclusion: str = "") -> dict:
        return {"__typename": "CheckRun", "status": status, "conclusion": conclusion}

    def test_states(self) -> None:
        ok = self.check("COMPLETED", "SUCCESS")
        self.assertEqual(list_prs.ci_state(None), "none")
        self.assertEqual(list_prs.ci_state([]), "none")
        self.assertEqual(list_prs.ci_state([ok, self.check("COMPLETED", "SKIPPED")]), "passing")
        self.assertEqual(list_prs.ci_state([ok, self.check("IN_PROGRESS")]), "pending")
        self.assertEqual(list_prs.ci_state([ok, self.check("COMPLETED", "FAILURE")]), "failing")

    def test_failure_beats_pending(self) -> None:
        self.assertEqual(list_prs.ci_state([self.check("QUEUED"),
                                            self.check("COMPLETED", "FAILURE")]), "failing")

    def test_status_context(self) -> None:
        self.assertEqual(list_prs.ci_state([{"__typename": "StatusContext", "state": "SUCCESS"}]),
                         "passing")
        self.assertEqual(list_prs.ci_state([{"__typename": "StatusContext", "state": "PENDING"}]),
                         "pending")
        self.assertEqual(list_prs.ci_state([{"__typename": "StatusContext", "state": "FAILURE"}]),
                         "failing")


class ListPrsTests(unittest.TestCase):
    def test_oldest_first_with_number_as_tiebreak(self) -> None:
        prs = [pr(3, "Bump c from 1 to 2", "2026-09-28T10:00:00Z"),
               pr(1, "Bump a from 1 to 2", "2026-09-28T12:00:00Z"),
               pr(2, "Bump b from 1 to 2", "2026-09-28T10:00:00Z")]
        with mock.patch("list_prs.subprocess.run", return_value=completed(json.dumps(prs))):
            result = list_prs.list_prs(["app/dependabot"])
        self.assertEqual([p["number"] for p in result], [2, 3, 1])

    def test_builds_exact_gh_command_per_author_and_dedupes(self) -> None:
        shared = pr(5, "Bump a from 1.0.0 to 1.0.1", "2026-09-28T10:00:00Z")
        with mock.patch("list_prs.subprocess.run",
                        return_value=completed(json.dumps([shared]))) as mock_run:
            result = list_prs.list_prs(["app/dependabot", "app/renovate"], "o/r")
        self.assertEqual(len(result), 1)
        mock_run.assert_any_call(
            ["gh", "pr", "list", "--state", "open", "--author", "app/dependabot",
             "--limit", "200", "--json", list_prs.PR_FIELDS, "--repo", "o/r"],
            capture_output=True, text=True,
        )
        mock_run.assert_any_call(
            ["gh", "pr", "list", "--state", "open", "--author", "app/renovate",
             "--limit", "200", "--json", list_prs.PR_FIELDS, "--repo", "o/r"],
            capture_output=True, text=True,
        )

    def test_summary_fields(self) -> None:
        raw = pr(7, "Bump postcss-import from 16.1.0 to 17.0.0", "2026-09-28T10:00:00Z",
                 rollup=[{"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "SUCCESS"}])
        with mock.patch("list_prs.subprocess.run", return_value=completed(json.dumps([raw]))):
            [result] = list_prs.list_prs(["app/dependabot"])
        self.assertEqual(result["package"], "postcss-import")
        self.assertEqual((result["from"], result["to"]), ("16.1.0", "17.0.0"))
        self.assertEqual(result["level"], "major")
        self.assertEqual(result["ci"], "passing")
        self.assertEqual(result["head_sha"], "sha7")

    def test_unparseable_title_is_unknown(self) -> None:
        raw = pr(8, "Bump the npm group with 3 updates", "2026-09-28T10:00:00Z")
        with mock.patch("list_prs.subprocess.run", return_value=completed(json.dumps([raw]))):
            [result] = list_prs.list_prs(["app/dependabot"])
        self.assertEqual(result["level"], "unknown")
        self.assertIsNone(result["package"])

    def test_raises_on_gh_failure(self) -> None:
        with mock.patch("list_prs.subprocess.run",
                        return_value=completed(returncode=1, stderr="boom")):
            with self.assertRaises(RuntimeError):
                list_prs.list_prs(["app/dependabot"])


class RenderTableTests(unittest.TestCase):
    def test_marks_majors_and_unknowns(self) -> None:
        rows = [
            {"number": 1, "title": "t", "package": "a", "from": "1", "to": "2", "level": "major",
             "ci": "passing", "mergeable": "MERGEABLE"},
            {"number": 2, "title": "Bump the npm group", "package": None, "from": None, "to": None,
             "level": "unknown", "ci": "none", "mergeable": "UNKNOWN"},
            {"number": 3, "title": "t", "package": "b", "from": "1.0.0", "to": "1.0.1",
             "level": "patch", "ci": "pending", "mergeable": "MERGEABLE"},
        ]
        table = list_prs.render_table(rows)
        self.assertIn("| #1 | a 1 → 2 | ⚠ major |", table)
        self.assertIn("| #2 | Bump the npm group | ⚠ unknown |", table)
        self.assertIn("| #3 | b 1.0.0 → 1.0.1 | patch |", table)

    def test_empty(self) -> None:
        self.assertEqual(list_prs.render_table([]), "No open PRs.")


if __name__ == "__main__":
    unittest.main()
