#!/usr/bin/env python3
"""
Unit tests for bootstrap_github_project.py.

Run directly:
    python3 -m unittest scripts/test_bootstrap_github_project.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
import bootstrap_github_project as bgp  # noqa: E402


def _completed(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


SAMPLE_DATA = {
    "milestone": {"title": "v1 -- Test Milestone", "description": "desc"},
    "epics": [
        {
            "title": "Epic: One",
            "labels": ["priority:P0"],
            "depends_on": [],
            "body": "epic body",
            "issues": [
                {"title": "Story: One-A", "labels": ["size:S"], "body": "story body"},
            ],
        },
    ],
    "release_validation_issue": {
        "title": "Release validation",
        "labels": ["priority:P0"],
        "body": "validation body",
    },
}


class LoadDataValidationTests(unittest.TestCase):
    def _write(self, content: str) -> str:
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        f.write(content)
        f.close()
        self.addCleanup(lambda: Path(f.name).unlink(missing_ok=True))
        return f.name

    def test_loads_valid_data_file(self) -> None:
        path = self._write(json.dumps(SAMPLE_DATA))
        data = bgp.load_data(path)
        self.assertEqual(data["milestone"]["title"], "v1 -- Test Milestone")
        self.assertEqual(len(data["epics"]), 1)

    def test_missing_top_level_key_raises_clear_error(self) -> None:
        bad = {k: v for k, v in SAMPLE_DATA.items() if k != "release_validation_issue"}
        path = self._write(json.dumps(bad))
        with self.assertRaises(ValueError) as ctx:
            bgp.load_data(path)
        self.assertIn("release_validation_issue", str(ctx.exception))

    def test_invalid_json_raises_clear_error(self) -> None:
        path = self._write("{not json")
        with self.assertRaises(ValueError) as ctx:
            bgp.load_data(path)
        self.assertIn("not valid JSON", str(ctx.exception))

    def test_missing_file_raises_clear_error(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            bgp.load_data("/no/such/file.json")
        self.assertIn("couldn't read data file", str(ctx.exception))

    def test_non_object_top_level_raises_clear_error(self) -> None:
        path = self._write(json.dumps([1, 2, 3]))
        with self.assertRaises(ValueError) as ctx:
            bgp.load_data(path)
        self.assertIn("top level", str(ctx.exception))

    def test_epic_missing_required_field_raises_clear_error(self) -> None:
        bad = json.loads(json.dumps(SAMPLE_DATA))
        del bad["epics"][0]["body"]
        path = self._write(json.dumps(bad))
        with self.assertRaises(ValueError) as ctx:
            bgp.load_data(path)
        message = str(ctx.exception)
        self.assertIn("epics[0]", message)
        self.assertIn("body", message)

    def test_epic_issue_missing_title_raises_clear_error(self) -> None:
        bad = json.loads(json.dumps(SAMPLE_DATA))
        del bad["epics"][0]["issues"][0]["title"]
        path = self._write(json.dumps(bad))
        with self.assertRaises(ValueError) as ctx:
            bgp.load_data(path)
        message = str(ctx.exception)
        self.assertIn("issues[0]", message)
        self.assertIn("title", message)

    def test_depends_on_referencing_unknown_epic_raises_clear_error(self) -> None:
        bad = json.loads(json.dumps(SAMPLE_DATA))
        bad["epics"][0]["depends_on"] = ["Epic: Nonexistent"]
        path = self._write(json.dumps(bad))
        with self.assertRaises(ValueError) as ctx:
            bgp.load_data(path)
        self.assertIn("Epic: Nonexistent", str(ctx.exception))

    def test_release_validation_issue_missing_labels_raises_clear_error(self) -> None:
        bad = json.loads(json.dumps(SAMPLE_DATA))
        del bad["release_validation_issue"]["labels"]
        path = self._write(json.dumps(bad))
        with self.assertRaises(ValueError) as ctx:
            bgp.load_data(path)
        message = str(ctx.exception)
        self.assertIn("release_validation_issue", message)
        self.assertIn("labels", message)


class MainFlowTests(unittest.TestCase):
    """Feed a small valid --data fixture through main() end-to-end with gh mocked out."""

    def _write_data(self, data: dict) -> str:
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        f.write(json.dumps(data))
        f.close()
        self.addCleanup(lambda: Path(f.name).unlink(missing_ok=True))
        return f.name

    def _gh_side_effect(self, calls: list):
        issue_numbers = iter(range(100, 200))

        def side_effect(cmd, capture_output=True, text=True):
            calls.append(cmd)
            if cmd[:3] == ["gh", "label", "create"]:
                return _completed()
            if cmd[:4] == ["gh", "api", "--method", "GET"]:
                return _completed("[]")
            if cmd[:4] == ["gh", "api", "--method", "POST"]:
                return _completed(json.dumps({"number": 1, "title": "v1 -- Test Milestone"}))
            if cmd[:3] == ["gh", "project", "list"]:
                return _completed(json.dumps({"projects": []}))
            if cmd[:3] == ["gh", "project", "create"]:
                return _completed(json.dumps({"number": 7, "title": "widgets"}))
            if cmd[:3] == ["gh", "project", "link"]:
                return _completed()
            if cmd[:3] == ["gh", "issue", "list"]:
                return _completed("[]")
            if cmd[:3] == ["gh", "issue", "create"]:
                number = next(issue_numbers)
                return _completed(f"https://github.com/acme/widgets/issues/{number}")
            if cmd[:3] == ["gh", "project", "item-add"]:
                return _completed()
            if cmd[:3] == ["gh", "issue", "edit"]:
                return _completed()
            raise AssertionError(f"unexpected command: {cmd}")

        return side_effect

    def test_valid_data_flows_into_issue_creation(self) -> None:
        data_path = self._write_data(SAMPLE_DATA)
        calls: list = []
        argv = ["bootstrap_github_project.py", "--repo", "acme/widgets", "--data", data_path]
        with mock.patch.object(sys, "argv", argv), \
             mock.patch("bootstrap_github_project.subprocess.run",
                         side_effect=self._gh_side_effect(calls)):
            bgp.main()

        create_calls = [c for c in calls if c[:3] == ["gh", "issue", "create"]]
        # epic + 1 child issue + release validation issue = 3 issue creates
        self.assertEqual(len(create_calls), 3)

        epic_call = create_calls[0]
        self.assertIn("Epic: One", epic_call)
        self.assertIn("epic body", epic_call)
        self.assertIn("epic", epic_call)         # base "epic" label
        self.assertIn("priority:P0", epic_call)  # epic's own label
        self.assertIn("v1 -- Test Milestone", epic_call)

        child_call = create_calls[1]
        self.assertIn("Story: One-A", child_call)
        self.assertIn("story body", child_call)
        self.assertIn("task", child_call)
        self.assertIn("size:S", child_call)
        self.assertIn("--parent", child_call)

        validation_call = create_calls[2]
        self.assertIn("Release validation", validation_call)
        self.assertIn("validation body", validation_call)
        self.assertIn("priority:P0", validation_call)

        # release validation issue is linked as blocked-by every epic
        edit_calls = [c for c in calls if c[:3] == ["gh", "issue", "edit"]]
        self.assertTrue(any("--add-blocked-by" in c for c in edit_calls))

    def test_malformed_data_rejected_before_any_gh_call(self) -> None:
        bad_data = {"milestone": {"title": "x"}}  # missing description + other top-level keys
        data_path = self._write_data(bad_data)
        argv = ["bootstrap_github_project.py", "--repo", "acme/widgets", "--data", data_path]
        with mock.patch.object(sys, "argv", argv), \
             mock.patch("bootstrap_github_project.subprocess.run") as mock_run, \
             self.assertRaises(SystemExit) as ctx:
            bgp.main()

        self.assertNotEqual(ctx.exception.code, 0)
        mock_run.assert_not_called()

    def test_invalid_json_rejected_before_any_gh_call(self) -> None:
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        f.write("{not json")
        f.close()
        self.addCleanup(lambda: Path(f.name).unlink(missing_ok=True))
        argv = ["bootstrap_github_project.py", "--repo", "acme/widgets", "--data", f.name]
        with mock.patch.object(sys, "argv", argv), \
             mock.patch("bootstrap_github_project.subprocess.run") as mock_run, \
             self.assertRaises(SystemExit) as ctx:
            bgp.main()

        self.assertNotEqual(ctx.exception.code, 0)
        mock_run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
