#!/usr/bin/env python3
"""
Unit tests for ensure_labels.py.

Run directly:
    python3 -m unittest github-labels-setup/scripts/test_ensure_labels.py
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
import ensure_labels  # noqa: E402


class EnsureLabelsCommandTests(unittest.TestCase):
    def test_builds_exact_gh_label_create_command_per_entry(self) -> None:
        labels = [
            {"name": "epic", "color": "5319E7", "description": "A tracked body of work"},
            {"name": "task", "color": "0E8A16", "description": "A single actionable unit"},
        ]
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        with mock.patch("ensure_labels.subprocess.run", return_value=completed) as mock_run:
            ensure_labels.ensure_labels("alvincrespo", "pr-agent", labels)

        self.assertEqual(mock_run.call_count, 2)
        mock_run.assert_any_call(
            ["gh", "label", "create", "epic", "--repo", "alvincrespo/pr-agent",
             "--color", "5319E7", "--description", "A tracked body of work", "--force"],
            capture_output=True, text=True,
        )
        mock_run.assert_any_call(
            ["gh", "label", "create", "task", "--repo", "alvincrespo/pr-agent",
             "--color", "0E8A16", "--description", "A single actionable unit", "--force"],
            capture_output=True, text=True,
        )

    def test_raises_on_nonzero_exit(self) -> None:
        completed = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="boom")
        with mock.patch("ensure_labels.subprocess.run", return_value=completed):
            with self.assertRaises(RuntimeError):
                ensure_labels.ensure_labels(
                    "alvincrespo", "pr-agent",
                    [{"name": "epic", "color": "5319E7", "description": "d"}],
                )


class LoadLabelsValidationTests(unittest.TestCase):
    def _write(self, content: str) -> str:
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        f.write(content)
        f.close()
        self.addCleanup(lambda: Path(f.name).unlink(missing_ok=True))
        return f.name

    def test_loads_valid_labels_file(self) -> None:
        path = self._write(json.dumps([
            {"name": "epic", "color": "5319E7", "description": "d"},
        ]))
        labels = ensure_labels.load_labels(path)
        self.assertEqual(labels, [{"name": "epic", "color": "5319E7", "description": "d"}])

    def test_missing_field_raises_clear_error_not_keyerror(self) -> None:
        path = self._write(json.dumps([
            {"name": "epic", "color": "5319E7"},
        ]))
        with self.assertRaises(ValueError) as ctx:
            ensure_labels.load_labels(path)
        message = str(ctx.exception)
        self.assertIn("entry 0", message)
        self.assertIn("description", message)

    def test_reports_correct_index_for_later_malformed_entry(self) -> None:
        path = self._write(json.dumps([
            {"name": "epic", "color": "5319E7", "description": "d"},
            {"name": "task", "description": "d"},
        ]))
        with self.assertRaises(ValueError) as ctx:
            ensure_labels.load_labels(path)
        message = str(ctx.exception)
        self.assertIn("entry 1", message)
        self.assertIn("color", message)

    def test_non_list_json_raises_clear_error(self) -> None:
        path = self._write(json.dumps({"name": "epic"}))
        with self.assertRaises(ValueError) as ctx:
            ensure_labels.load_labels(path)
        self.assertIn("JSON list", str(ctx.exception))

    def test_invalid_json_raises_clear_error(self) -> None:
        path = self._write("{not json")
        with self.assertRaises(ValueError) as ctx:
            ensure_labels.load_labels(path)
        self.assertIn("not valid JSON", str(ctx.exception))

    def test_missing_file_raises_clear_error(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            ensure_labels.load_labels("/no/such/file.json")
        self.assertIn("couldn't read labels file", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
