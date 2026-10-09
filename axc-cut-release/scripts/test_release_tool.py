#!/usr/bin/env python3
"""
Unit tests for release_tool.py. Real git in temp dirs; no network.

Run directly:
    python3 -m unittest axc-cut-release/scripts/test_release_tool.py
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import release_tool  # noqa: E402

REAL_CONFIG = Path(__file__).resolve().parents[2] / ".claude" / "release.json"


def run_git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True
    )


def run_cli(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = release_tool.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class RepoTestCase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        self.origin = tmp / "origin.git"
        self.repo = tmp / "work"
        subprocess.run(
            ["git", "init", "--bare", "-b", "main", str(self.origin)],
            check=True, capture_output=True,
        )
        self.repo.mkdir()
        run_git(self.repo, "init", "-b", "main")
        run_git(self.repo, "config", "user.email", "t@example.com")
        run_git(self.repo, "config", "user.name", "Test")
        run_git(self.repo, "remote", "add", "origin", str(self.origin))

        (self.repo / ".claude").mkdir()
        shutil.copy(REAL_CONFIG, self.repo / ".claude" / "release.json")
        self.plugin = self.repo / ".claude-plugin" / "plugin.json"
        self.plugin.parent.mkdir()
        self.plugin.write_text('{\n  "name": "x",\n  "version": "0.3.0"\n}\n')
        run_git(self.repo, "add", "-A")
        run_git(self.repo, "commit", "-m", "init")
        run_git(self.repo, "push", "-u", "origin", "main")


class CurrentTests(RepoTestCase):
    def test_prints_version_using_real_config(self) -> None:
        code, out, _ = run_cli("current", "--repo-root", str(self.repo))
        self.assertEqual((code, out), (0, "0.3.0\n"))

    def test_ref_reads_committed_version_not_working_tree(self) -> None:
        self.plugin.write_text('{\n  "version": "9.9.9"\n}\n')
        code, out, _ = run_cli(
            "current", "--ref", "origin/main", "--repo-root", str(self.repo)
        )
        self.assertEqual((code, out), (0, "0.3.0\n"))
        _, out, _ = run_cli("current", "--repo-root", str(self.repo))
        self.assertEqual(out, "9.9.9\n")

    def test_unmatched_pattern_exits_2_naming_file(self) -> None:
        cfg = json.loads(REAL_CONFIG.read_text())
        cfg["version"]["files"][0]["match"] = "nope {V}"
        path = self.repo / "custom.json"
        path.write_text(json.dumps(cfg))
        code, out, err = run_cli(
            "current", "--repo-root", str(self.repo), "--config", str(path)
        )
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn(".claude-plugin/plugin.json", err)

    def test_missing_tag_format_exits_2_naming_key(self) -> None:
        cfg = json.loads(REAL_CONFIG.read_text())
        del cfg["release"]["tagFormat"]
        path = self.repo / "custom.json"
        path.write_text(json.dumps(cfg))
        code, _, err = run_cli(
            "current", "--repo-root", str(self.repo), "--config", str(path)
        )
        self.assertEqual(code, 2)
        self.assertIn("release.tagFormat", err)


class VersionRegexTests(unittest.TestCase):
    def test_captures_prerelease(self) -> None:
        m = release_tool.version_regex('"version": "{V}"').search('"version": "1.2.3-rc.1"')
        self.assertEqual(m.group(1), "1.2.3-rc.1")

    def test_rejects_two_part_version(self) -> None:
        self.assertIsNone(release_tool.version_regex('"version": "{V}"').search('"version": "1.2"'))


if __name__ == "__main__":
    unittest.main()
