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

# Self-contained config so most tests don't track edits to the live one.
FIXTURE_CONFIG = {
    "mainBranch": "main",
    "version": {
        "files": [{"path": "pkg/version.json", "match": '"version": "{V}"'}]
    },
    "commit": {"branch": "release/v{V}"},
    "release": {"tagFormat": "v{V}"},
}


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
        (self.repo / ".claude" / "release.json").write_text(json.dumps(FIXTURE_CONFIG))
        self.plugin = self.repo / "pkg" / "version.json"
        self.plugin.parent.mkdir()
        self.plugin.write_text('{\n  "name": "x",\n  "version": "0.3.0"\n}\n')
        run_git(self.repo, "add", "-A")
        run_git(self.repo, "commit", "-m", "init")
        run_git(self.repo, "push", "-u", "origin", "main")


class CurrentTests(RepoTestCase):
    def test_prints_version_using_real_config(self) -> None:
        # The one test tied to the live config, per the acceptance criteria.
        shutil.copy(REAL_CONFIG, self.repo / ".claude" / "release.json")
        real = json.loads(REAL_CONFIG.read_text())["version"]["files"][0]["path"]
        target = self.repo / real
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('{\n  "version": "0.3.0"\n}\n')
        code, out, _ = run_cli("current", "--repo-root", str(self.repo))
        self.assertEqual((code, out), (0, "0.3.0\n"))

    def test_prints_version(self) -> None:
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

    def _run_with_config(self, cfg: dict) -> tuple[int, str, str]:
        path = self.repo / "custom.json"
        path.write_text(json.dumps(cfg))
        return run_cli("current", "--repo-root", str(self.repo), "--config", str(path))

    def test_unmatched_pattern_exits_2_naming_file(self) -> None:
        cfg = json.loads(json.dumps(FIXTURE_CONFIG))
        cfg["version"]["files"][0]["match"] = "nope {V}"
        code, out, err = self._run_with_config(cfg)
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("pkg/version.json", err)

    def test_missing_tag_format_exits_2_naming_key(self) -> None:
        cfg = json.loads(json.dumps(FIXTURE_CONFIG))
        del cfg["release"]["tagFormat"]
        code, _, err = self._run_with_config(cfg)
        self.assertEqual(code, 2)
        self.assertIn("release.tagFormat", err)

    def test_non_string_config_values_exit_2(self) -> None:
        for mutate, key in [
            (lambda c: c["version"]["files"][0].update(match=5), "version.files[0].match"),
            (lambda c: c["version"]["files"][0].update(path=None), "version.files[0].path"),
            (lambda c: c.update(mainBranch=["main"]), "mainBranch"),
            (lambda c: c["commit"].update(branch=1), "commit.branch"),
            (lambda c: c["release"].update(tagFormat=""), "release.tagFormat"),
        ]:
            with self.subTest(key=key):
                cfg = json.loads(json.dumps(FIXTURE_CONFIG))
                mutate(cfg)
                code, _, err = self._run_with_config(cfg)
                self.assertEqual(code, 2)
                self.assertIn(key, err)
                self.assertNotIn("Traceback", err)

    def test_non_utf8_version_file_exits_2(self) -> None:
        self.plugin.write_bytes(b'\xff\xfe "version": "1.0.0"')
        code, _, err = run_cli("current", "--repo-root", str(self.repo))
        self.assertEqual(code, 2)
        self.assertIn("pkg/version.json", err)

    def test_non_utf8_config_exits_2(self) -> None:
        path = self.repo / "bad.json"
        path.write_bytes(b"\xff\xfe{}")
        code, _, err = run_cli(
            "current", "--repo-root", str(self.repo), "--config", str(path)
        )
        self.assertEqual(code, 2)
        self.assertIn("UTF-8", err)


class NextVersionTests(unittest.TestCase):
    def test_table(self) -> None:
        for cur, arg, want in [
            ("0.3.0", "patch", "0.3.1"),
            ("0.3.0", "minor", "0.4.0"),
            ("0.3.9", "major", "1.0.0"),
            ("0.3.0", "0.5.0-rc.1", "0.5.0-rc.1"),
            ("0.3.0", None, "0.3.1"),
            ("1.0.0-rc.1", "2.0.0", "2.0.0"),
            ("1.4.7", "minor", "1.5.0"),
            ("1.4.7", "major", "2.0.0"),
            ("1.4.7", "patch", "1.4.8"),
        ]:
            with self.subTest(cur=cur, arg=arg):
                self.assertEqual(release_tool.next_version(cur, arg), want)

    def test_keyword_on_prerelease_asks_for_explicit_version(self) -> None:
        for arg in ("minor", None):
            with self.subTest(arg=arg):
                with self.assertRaisesRegex(release_tool.ReleaseToolError, "explicit version"):
                    release_tool.next_version("1.0.0-rc.1", arg)

    def test_bad_explicit_versions_rejected(self) -> None:
        for arg in (
            "1.2", "v1.2.3", "banana", "1.2.3\n", "01.2.3", "1.02.3",
            "1.0.0-", "1.0.0--.", "1.0.0-a..b", "1.0.0-.a", " 1.2.3",
        ):
            with self.subTest(arg=arg):
                with self.assertRaises(release_tool.ReleaseToolError):
                    release_tool.next_version("0.3.0", arg)


class NextCommandTests(RepoTestCase):
    def test_explicit_version_does_not_need_git(self) -> None:
        # No config-reachable ref and no git repo at all: still echoes the version.
        bare = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, bare, ignore_errors=True)
        cfg = bare / "release.json"
        cfg.write_text(json.dumps(FIXTURE_CONFIG))
        code, out, _ = run_cli(
            "next", "2.0.0-rc.1", "--repo-root", str(bare), "--config", str(cfg)
        )
        self.assertEqual((code, out), (0, "2.0.0-rc.1\n"))

    def test_keyword_with_missing_ref_exits_2(self) -> None:
        code, _, err = run_cli(
            "next", "patch", "--ref", "origin/nope", "--repo-root", str(self.repo)
        )
        self.assertEqual(code, 2)
        self.assertIn("origin/nope", err)

    def test_defaults_to_origin_main_ignoring_working_tree(self) -> None:
        self.plugin.write_text('{\n  "version": "9.9.9"\n}\n')
        code, out, _ = run_cli("next", "minor", "--repo-root", str(self.repo))
        self.assertEqual((code, out), (0, "0.4.0\n"))

    def test_no_arg_bumps_patch(self) -> None:
        code, out, _ = run_cli("next", "--repo-root", str(self.repo))
        self.assertEqual((code, out), (0, "0.3.1\n"))

    def test_explicit_ref(self) -> None:
        code, out, _ = run_cli("next", "major", "--ref", "HEAD", "--repo-root", str(self.repo))
        self.assertEqual((code, out), (0, "1.0.0\n"))

    def test_bad_explicit_version_exits_2(self) -> None:
        code, out, err = run_cli("next", "v1.2.3", "--repo-root", str(self.repo))
        self.assertEqual((code, out), (2, ""))
        self.assertIn("v1.2.3", err)

    def test_prerelease_current_exits_2(self) -> None:
        self.plugin.write_text('{\n  "version": "1.0.0-rc.1"\n}\n')
        run_git(self.repo, "commit", "-qam", "rc")
        run_git(self.repo, "push", "origin", "main")
        code, _, err = run_cli("next", "minor", "--repo-root", str(self.repo))
        self.assertEqual(code, 2)
        self.assertIn("explicit version", err)


class VersionRegexTests(unittest.TestCase):
    def test_captures_prerelease(self) -> None:
        m = release_tool.version_regex('"version": "{V}"').search('"version": "1.2.3-rc.1"')
        self.assertEqual(m.group(1), "1.2.3-rc.1")

    def test_rejects_two_part_version(self) -> None:
        self.assertIsNone(release_tool.version_regex('"version": "{V}"').search('"version": "1.2"'))


if __name__ == "__main__":
    unittest.main()
