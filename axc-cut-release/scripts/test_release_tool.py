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


class BumpTests(RepoTestCase):
    GO_MATCH = 'const Version = "{V}"'

    def setUp(self) -> None:
        super().setUp()
        self.go = self.repo / "version.go"
        self.go.write_text('package x\n\nconst Version = "0.3.0"\n\nconst Other = "0.3.0"\n')
        self.cfg = json.loads(json.dumps(FIXTURE_CONFIG))
        self.cfg["version"]["files"].append({"path": "version.go", "match": self.GO_MATCH})
        self.cfg_path = self.repo / "two.json"
        self.cfg_path.write_text(json.dumps(self.cfg))
        run_git(self.repo, "add", "-A")
        run_git(self.repo, "commit", "-qm", "two files")

    def run_cmd(self, *argv: str) -> tuple[int, str, str]:
        return run_cli(*argv, "--repo-root", str(self.repo), "--config", str(self.cfg_path))

    def diff_changed_lines(self) -> list[str]:
        out = subprocess.run(
            ["git", "-C", str(self.repo), "diff", "--unified=0"],
            capture_output=True, text=True, check=True,
        ).stdout
        return [l for l in out.splitlines() if l[:1] in "+-" and l[:3] not in ("+++", "---")]

    def test_bump_updates_both_files_with_exactly_two_changed_lines(self) -> None:
        code, out, _ = self.run_cmd("bump", "0.4.0")
        self.assertEqual(code, 0)
        self.assertIn("✓ pkg/version.json = 0.4.0", out)
        self.assertIn("✓ version.go = 0.4.0", out)
        changed = self.diff_changed_lines()
        self.assertEqual(len(changed), 4, changed)  # two removed + two added
        self.assertIn('const Other = "0.3.0"', self.go.read_text())

    def test_missing_pattern_in_second_file_leaves_first_unchanged(self) -> None:
        self.go.write_text("package x\n")
        before = self.plugin.read_text()
        code, _, err = self.run_cmd("bump", "0.4.0")
        self.assertEqual(code, 2)
        self.assertIn("version.go", err)
        self.assertEqual(self.plugin.read_text(), before)

    def test_bump_rejects_bad_version(self) -> None:
        code, _, err = self.run_cmd("bump", "v0.4.0")
        self.assertEqual(code, 2)
        self.assertIn("v0.4.0", err)
        self.assertEqual(self.diff_changed_lines(), [])

    def test_check_versions_fails_before_and_passes_after_bump(self) -> None:
        code, out, _ = self.run_cmd("check-versions", "0.4.0")
        self.assertEqual(code, 1)
        self.assertIn("✗ pkg/version.json = 0.3.0 (expected 0.4.0)", out)
        self.assertIn("✗ version.go = 0.3.0 (expected 0.4.0)", out)
        self.run_cmd("bump", "0.4.0")
        code, out, _ = self.run_cmd("check-versions", "0.4.0")
        self.assertEqual(code, 0)
        self.assertEqual(out.count("✓"), 2)

    def test_check_versions_flags_disagreeing_files(self) -> None:
        self.go.write_text('const Version = "0.5.0"\n')
        code, out, _ = self.run_cmd("check-versions", "0.3.0")
        self.assertEqual(code, 1)
        self.assertIn("disagree", out)

    def test_check_versions_reports_unreadable_file_without_aborting(self) -> None:
        self.go.write_text("nothing here\n")
        code, out, _ = self.run_cmd("check-versions", "0.3.0")
        self.assertEqual(code, 1)
        self.assertIn("✓ pkg/version.json = 0.3.0", out)
        self.assertIn("✗ version.go", out)

    def test_bump_command_runs_and_is_verified(self) -> None:
        helper = self.repo / "set_version.py"
        helper.write_text(
            "import re, sys, pathlib\n"
            "v = sys.argv[1]\n"
            "for name, pat in [('pkg/version.json', r'(\"version\": \")[^\"]+'),\n"
            "                  ('version.go', r'(Version = \")[^\"]+')]:\n"
            "    p = pathlib.Path(name)\n"
            "    p.write_text(re.sub(pat, lambda m: m.group(1) + v, p.read_text(), count=1))\n"
        )
        self.cfg["version"]["bumpCommand"] = f'"{sys.executable}" set_version.py {{V}}'
        self.cfg_path.write_text(json.dumps(self.cfg))
        code, out, _ = self.run_cmd("bump", "0.4.0")
        self.assertEqual(code, 0, out)
        code, _, _ = self.run_cmd("check-versions", "0.4.0")
        self.assertEqual(code, 0)

    def test_two_entries_for_one_file_both_apply(self) -> None:
        self.go.write_text('const Version = "0.3.0"\nconst Api = "0.3.0"\n')
        self.cfg["version"]["files"] = [
            {"path": "version.go", "match": 'const Version = "{V}"'},
            {"path": "version.go", "match": 'const Api = "{V}"'},
        ]
        self.cfg_path.write_text(json.dumps(self.cfg))
        code, _, _ = self.run_cmd("bump", "0.4.0")
        self.assertEqual(code, 0)
        self.assertEqual(
            self.go.read_text(), 'const Version = "0.4.0"\nconst Api = "0.4.0"\n'
        )

    def test_crlf_line_endings_preserved(self) -> None:
        self.go.write_bytes(b'package x\r\nconst Version = "0.3.0"\r\n')
        self.run_cmd("bump", "0.4.0")
        self.assertEqual(
            self.go.read_bytes(), b'package x\r\nconst Version = "0.4.0"\r\n'
        )

    def test_write_failure_rolls_back_and_exits_2(self) -> None:
        from unittest import mock
        real = release_tool._write_atomic

        def flaky(path, text):
            if path == self.go:
                raise OSError("disk full")
            return real(path, text)

        before = self.plugin.read_text()
        with mock.patch.object(release_tool, "_write_atomic", flaky):
            code, _, err = self.run_cmd("bump", "0.4.0")
        self.assertEqual(code, 2)
        self.assertIn("rolled back", err)
        self.assertEqual(self.plugin.read_text(), before)

    def test_failed_rollback_is_reported_not_claimed(self) -> None:
        from unittest import mock
        real = release_tool._write_atomic
        calls = {"plugin": 0}

        def flaky(path, text):
            if path == self.go:
                raise OSError("disk full")
            calls["plugin"] += 1
            if calls["plugin"] > 1:  # the restore write
                raise OSError("read-only")
            return real(path, text)

        with mock.patch.object(release_tool, "_write_atomic", flaky):
            code, _, err = self.run_cmd("bump", "0.4.0")
        self.assertEqual(code, 2)
        self.assertNotIn("rolled back", err)
        self.assertIn("could not be restored", err)
        self.assertIn("pkg/version.json", err)

    def test_failed_atomic_write_leaves_file_and_no_temp(self) -> None:
        from unittest import mock
        before = self.go.read_text()
        with mock.patch.object(release_tool.os, "replace", side_effect=OSError("nope")):
            with self.assertRaises(OSError):
                release_tool._write_atomic(self.go, "changed")
        self.assertEqual(self.go.read_text(), before)
        self.assertEqual(list(self.repo.glob("*.release-tmp")), [])

    def test_bump_command_is_echoed_to_stderr(self) -> None:
        self.cfg["version"]["bumpCommand"] = "true {V}"
        self.cfg_path.write_text(json.dumps(self.cfg))
        _, _, err = self.run_cmd("bump", "0.4.0")
        self.assertIn("running bumpCommand: true 0.4.0", err)

    def test_literal_suffix_after_placeholder(self) -> None:
        self.go.write_text('const Version = "0.3.0-SNAPSHOT"\n')
        self.cfg["version"]["files"] = [
            {"path": "version.go", "match": 'const Version = "{V}-SNAPSHOT"'}
        ]
        self.cfg_path.write_text(json.dumps(self.cfg))
        code, out, _ = self.run_cmd("check-versions", "0.3.0")
        self.assertEqual((code, out), (0, "✓ version.go = 0.3.0\n"))
        self.run_cmd("bump", "0.4.0")
        self.assertEqual(self.go.read_text(), 'const Version = "0.4.0-SNAPSHOT"\n')

    def test_bump_command_without_placeholder_rejected_at_load(self) -> None:
        self.cfg["version"]["bumpCommand"] = "true"
        self.cfg_path.write_text(json.dumps(self.cfg))
        for argv in (("bump", "0.4.0"), ("check-versions", "0.4.0")):
            with self.subTest(argv=argv):
                code, _, err = self.run_cmd(*argv)
                self.assertEqual(code, 2)
                self.assertIn("bumpCommand", err)

    def test_bump_command_that_leaves_files_stale_exits_1(self) -> None:
        self.cfg["version"]["bumpCommand"] = "true {V}"
        self.cfg_path.write_text(json.dumps(self.cfg))
        code, out, _ = self.run_cmd("bump", "0.4.0")
        self.assertEqual(code, 1)
        self.assertIn("✗", out)

    def test_failing_bump_command_exits_2(self) -> None:
        self.cfg["version"]["bumpCommand"] = "exit 3 # {V}"
        self.cfg_path.write_text(json.dumps(self.cfg))
        code, _, err = self.run_cmd("bump", "0.4.0")
        self.assertEqual(code, 2)
        self.assertIn("bumpCommand", err)


class TagStatusTests(RepoTestCase):
    def cli(self, *argv: str) -> tuple[int, str, str]:
        return run_cli(*argv, "--repo-root", str(self.repo))

    def test_absent_local_remote_both(self) -> None:
        self.assertEqual(self.cli("tag-status", "0.3.0")[:2], (0, "absent\n"))
        run_git(self.repo, "tag", "v0.3.0")
        self.assertEqual(self.cli("tag-status", "0.3.0")[:2], (0, "local\n"))
        run_git(self.repo, "push", "origin", "v0.3.0")
        self.assertEqual(self.cli("tag-status", "0.3.0")[:2], (0, "both\n"))
        run_git(self.repo, "tag", "-d", "v0.3.0")
        self.assertEqual(self.cli("tag-status", "0.3.0")[:2], (0, "remote\n"))

    def test_tag_only_on_origin_reports_remote(self) -> None:
        run_git(self.repo, "tag", "v0.4.0")
        run_git(self.repo, "push", "origin", "v0.4.0")
        run_git(self.repo, "tag", "-d", "v0.4.0")
        self.assertEqual(self.cli("tag-status", "0.4.0")[:2], (0, "remote\n"))

    def test_annotated_tag_on_origin(self) -> None:
        run_git(self.repo, "tag", "-a", "v0.5.0", "-m", "x")
        run_git(self.repo, "push", "origin", "v0.5.0")
        self.assertEqual(self.cli("tag-status", "0.5.0")[:2], (0, "both\n"))

    def test_namespaced_tag_does_not_match(self) -> None:
        run_git(self.repo, "tag", "pre/v0.3.0")
        run_git(self.repo, "push", "origin", "pre/v0.3.0")
        self.assertEqual(self.cli("tag-status", "0.3.0")[:2], (0, "absent\n"))

    def test_bad_version_exits_2(self) -> None:
        self.assertEqual(self.cli("tag-status", "banana")[0], 2)


class PhaseTests(RepoTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.plugin.write_text('{\n  "version": "0.4.0"\n}\n')
        run_git(self.repo, "commit", "-qam", "bump")
        run_git(self.repo, "push", "origin", "main")

    def phase(self, v: str, gh_result: str = "") -> tuple[int, str, str]:
        from unittest import mock
        with mock.patch.object(release_tool, "gh", return_value=gh_result) as m:
            result = run_cli("phase", v, "--repo-root", str(self.repo))
        self.gh_calls = m.call_args_list
        return result

    def test_tag_then_released_then_bump(self) -> None:
        self.assertEqual(self.phase("0.4.0")[:2], (0, "tag\n"))
        run_git(self.repo, "tag", "v0.4.0")
        self.assertEqual(self.phase("0.4.0")[:2], (0, "released\n"))
        run_git(self.repo, "push", "origin", "v0.4.0")
        run_git(self.repo, "tag", "-d", "v0.4.0")
        self.assertEqual(self.phase("0.4.0")[:2], (0, "released\n"))
        self.assertEqual(self.phase("0.5.0")[:2], (0, "bump\n"))

    def test_bump_with_open_pr(self) -> None:
        code, out, _ = self.phase("0.5.0", gh_result="63\n")
        self.assertEqual((code, out), (0, "bump\nopen-pr 63\n"))
        args = self.gh_calls[0].args[0]
        self.assertEqual(args[args.index("--head") + 1], "release/v0.5.0")

    def test_gh_not_called_when_version_is_on_main(self) -> None:
        self.phase("0.4.0")
        self.assertEqual(self.gh_calls, [])

    def test_phase_fetches_origin_main(self) -> None:
        # Advance origin/main from a second clone; phase must see it without a manual fetch.
        other = self.repo.parent / "other"
        subprocess.run(["git", "clone", "-q", str(self.origin), str(other)], check=True)
        run_git(other, "config", "user.email", "t@example.com")
        run_git(other, "config", "user.name", "Test")
        (other / "pkg" / "version.json").write_text('{\n  "version": "0.5.0"\n}\n')
        run_git(other, "commit", "-qam", "bump 0.5.0")
        run_git(other, "push", "origin", "main")
        self.assertEqual(self.phase("0.5.0")[:2], (0, "tag\n"))

    def test_junk_gh_output_is_not_reported_as_a_pr(self) -> None:
        for junk in ("null", "abc", "6 3", ""):
            with self.subTest(junk=junk):
                self.assertEqual(self.phase("0.5.0", gh_result=junk)[:2], (0, "bump\n"))

    def test_local_only_tag_counts_as_released(self) -> None:
        # Spec: any existing tag (local, remote or both) means released.
        run_git(self.repo, "tag", "v0.4.0")
        self.assertEqual(release_tool.tag_status(self.repo, "v0.4.0"), "local")
        self.assertEqual(self.phase("0.4.0")[:2], (0, "released\n"))

    def test_version_older_than_main_exits_2_without_calling_gh(self) -> None:
        code, out, err = self.phase("0.3.9")
        self.assertEqual((code, out), (2, ""))
        self.assertIn("older than", err)
        self.assertEqual(self.gh_calls, [])

    def test_prerelease_of_the_version_on_main_is_older(self) -> None:
        code, out, err = self.phase("0.4.0-rc.1")
        self.assertEqual((code, out), (2, ""))
        self.assertIn("older than", err)

    def test_prerelease_after_a_prerelease_on_main(self) -> None:
        self.plugin.write_text('{\n  "version": "0.5.0-rc.2"\n}\n')
        run_git(self.repo, "commit", "-qam", "rc2")
        run_git(self.repo, "push", "origin", "main")
        self.assertEqual(self.phase("0.5.0-rc.1")[0], 2)
        self.assertEqual(self.phase("0.5.0-rc.10")[:2], (0, "bump\n"))
        self.assertEqual(self.phase("0.5.0")[:2], (0, "bump\n"))

    def test_unreachable_origin_exits_2_with_hint(self) -> None:
        run_git(self.repo, "remote", "set-url", "origin", str(self.repo.parent / "gone.git"))
        code, _, err = self.phase("0.4.0")
        self.assertEqual(code, 2)
        self.assertIn("'origin' remote", err)

    def test_tag_status_unreachable_origin_exits_2_with_hint(self) -> None:
        run_git(self.repo, "remote", "set-url", "origin", str(self.repo.parent / "gone.git"))
        code, _, err = run_cli("tag-status", "0.4.0", "--repo-root", str(self.repo))
        self.assertEqual(code, 2)
        self.assertIn("'origin' remote", err)

    def test_gh_failure_still_reports_bump_with_a_warning(self) -> None:
        from unittest import mock
        err = release_tool.ReleaseToolError("gh is not installed or not on PATH")
        with mock.patch.object(release_tool, "gh", side_effect=err):
            code, out, stderr = run_cli("phase", "0.5.0", "--repo-root", str(self.repo))
        self.assertEqual((code, out), (0, "bump\n"))
        self.assertIn("warning: could not check for an open release PR", stderr)
        self.assertIn("gh is not installed", stderr)


class PhaseMultiFileTests(RepoTestCase):
    def setUp(self) -> None:
        super().setUp()
        cfg = json.loads(json.dumps(FIXTURE_CONFIG))
        cfg["version"]["files"].append({"path": "version.go", "match": 'Version = "{V}"'})
        (self.repo / ".claude" / "release.json").write_text(json.dumps(cfg))
        (self.repo / "version.go").write_text('const Version = "0.3.0"\n')
        run_git(self.repo, "add", "-A")
        run_git(self.repo, "commit", "-qm", "two files")
        run_git(self.repo, "push", "origin", "main")

    def phase(self, v: str) -> tuple[int, str, str]:
        from unittest import mock
        with mock.patch.object(release_tool, "gh", return_value=""):
            return run_cli("phase", v, "--repo-root", str(self.repo))

    def test_partial_bump_on_main_is_an_error(self) -> None:
        self.plugin.write_text('{\n  "version": "0.4.0"\n}\n')
        run_git(self.repo, "commit", "-qam", "half bump")
        run_git(self.repo, "push", "origin", "main")
        code, _, err = self.phase("0.4.0")
        self.assertEqual(code, 2)
        self.assertIn("version.go=0.3.0", err)

    def test_all_files_on_main_proceeds_to_tag(self) -> None:
        self.plugin.write_text('{\n  "version": "0.4.0"\n}\n')
        (self.repo / "version.go").write_text('const Version = "0.4.0"\n')
        run_git(self.repo, "commit", "-qam", "bump")
        run_git(self.repo, "push", "origin", "main")
        self.assertEqual(self.phase("0.4.0")[:2], (0, "tag\n"))


class WorkflowChecksTests(unittest.TestCase):
    REPO = REAL_CONFIG.parents[1]
    WORKFLOW = ".github/workflows/release.yml"

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.cfg = json.loads(json.dumps(FIXTURE_CONFIG))
        self.cfg["release"].update(
            workflow=self.WORKFLOW,
            workflowChecks=["tags: [\"v*\"]", "contents: write", "gh release create"],
        )
        self.workflow = self.tmp / self.WORKFLOW
        self.workflow.parent.mkdir(parents=True)
        self.workflow.write_text(
            'on:\n  push:\n    tags: ["v*"]\npermissions:\n  contents: write\n'
            "steps:\n  - run: gh release create $TAG\n"
        )

    def run_cmd(self, root: Path | None = None) -> tuple[int, str, str]:
        cfg_path = self.tmp / "release.json"
        cfg_path.write_text(json.dumps(self.cfg))
        return run_cli(
            "workflow-checks", "--repo-root", str(root or self.tmp), "--config", str(cfg_path)
        )

    def test_real_config_and_workflow_pass(self) -> None:
        # The one test tied to the live files, per the acceptance criteria.
        real = json.loads(REAL_CONFIG.read_text())
        code, out, err = run_cli(
            "workflow-checks", "--repo-root", str(self.REPO), "--config", str(REAL_CONFIG)
        )
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out.count("✓"), len(real["release"]["workflowChecks"]))
        self.assertNotIn("✗", out)

    def test_all_checks_present(self) -> None:
        code, out, _ = self.run_cmd()
        self.assertEqual(code, 0)
        self.assertEqual(out.count("✓"), 3)

    def test_missing_check_exits_1_and_is_marked(self) -> None:
        self.workflow.write_text(self.workflow.read_text().replace("contents: write", "contents: read"))
        code, out, _ = self.run_cmd()
        self.assertEqual(code, 1)
        self.assertIn("✗ contents: write (not found in .github/workflows/release.yml)", out)
        self.assertIn("✓ gh release create", out)

    def test_missing_workflow_file_exits_2(self) -> None:
        self.workflow.unlink()
        code, out, err = self.run_cmd()
        self.assertEqual((code, out), (2, ""))
        self.assertIn(".github/workflows/release.yml", err)

    def test_workflow_path_outside_repo_exits_2(self) -> None:
        outside = self.tmp / "outside.yml"
        outside.write_text("contents: write\n")
        repo = self.tmp / "repo"
        repo.mkdir()
        for bad in ("../outside.yml", str(outside)):
            with self.subTest(path=bad):
                self.cfg["release"]["workflow"] = bad
                code, out, err = self.run_cmd(root=repo)
                self.assertEqual((code, out), (2, ""))
                self.assertIn("inside the repo", err)

    def test_missing_workflow_key_exits_2_naming_it(self) -> None:
        del self.cfg["release"]["workflow"]
        code, _, err = self.run_cmd()
        self.assertEqual(code, 2)
        self.assertIn("release.workflow", err)

    def test_no_checks_configured_passes_with_notice(self) -> None:
        del self.cfg["release"]["workflowChecks"]
        code, out, _ = self.run_cmd()
        self.assertEqual(code, 0)
        self.assertIn("no release.workflowChecks", out)

    def test_bad_checks_type_exits_2(self) -> None:
        self.cfg["release"]["workflowChecks"] = ["ok", 5]
        code, _, err = self.run_cmd()
        self.assertEqual(code, 2)
        self.assertIn("release.workflowChecks", err)


class AsciiStdoutTests(unittest.TestCase):
    def test_glyphs_do_not_crash_under_ascii_stdout(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        (tmp / "wf.yml").write_text("a\n")
        cfg = tmp / "release.json"
        full = json.loads(json.dumps(FIXTURE_CONFIG))
        full["release"].update(workflow="wf.yml", workflowChecks=["a", "b"])
        cfg.write_text(json.dumps(full))
        result = subprocess.run(
            [sys.executable, str(Path(release_tool.__file__)), "workflow-checks",
             "--repo-root", str(tmp), "--config", str(cfg)],
            capture_output=True, text=True, env={"PYTHONIOENCODING": "ascii", "PATH": "/usr/bin:/bin"},
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("b (not found in wf.yml)", result.stdout)


class VersionRegexTests(unittest.TestCase):
    def test_captures_prerelease(self) -> None:
        m = release_tool.version_regex('"version": "{V}"').search('"version": "1.2.3-rc.1"')
        self.assertEqual(m.group(1), "1.2.3-rc.1")

    def test_rejects_leading_zero_version(self) -> None:
        pattern = release_tool.version_regex('"version": "{V}"')
        self.assertIsNone(pattern.search('"version": "01.2.3"'))
        self.assertIsNone(pattern.search('"version": "1.02.3"'))

    def test_rejects_two_part_version(self) -> None:
        self.assertIsNone(release_tool.version_regex('"version": "{V}"').search('"version": "1.2"'))


if __name__ == "__main__":
    unittest.main()
