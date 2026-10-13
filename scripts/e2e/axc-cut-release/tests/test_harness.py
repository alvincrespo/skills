#!/usr/bin/env python3
"""
Tests for the e2e harness itself. No network, no GitHub, no Claude: `gh` and `claude` are
replaced by the fakes in tests/fakes/ (local bare repos stand in for GitHub). They check the
harness's setup, checks and teardown, not the release skills.

Run:
    python3 -m unittest discover -s scripts/e2e/axc-cut-release/tests
"""

from __future__ import annotations

import contextlib
import io
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from harness import cli  # noqa: E402
from harness.claude_runner import ClaudeRunner, split_tool_errors, tool_result_text  # noqa: E402
from harness.config import (EXIT_ABORTED, EXIT_CHECKS_FAILED, EXIT_INTERRUPTED, EXIT_OK,  # noqa: E402
                            NAME_PREFIX, SKILLS, Options, Paths)
from harness.context import RunContext  # noqa: E402
from harness.github import GitHub  # noqa: E402
from harness.log import Logger  # noqa: E402
from harness.report import Report  # noqa: E402
from harness.sandbox import Sandbox  # noqa: E402

REAL_REPO = Paths.default().repo_root


class HarnessCase(unittest.TestCase):
    """A fake repo root (real skills, gitignored tmp/) with fake gh and claude first on PATH."""

    ignore_tmp = True

    def setUp(self) -> None:
        base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, base, ignore_errors=True)
        self.root = base / "repo"
        self.state = base / "state"
        self.root.mkdir()
        (self.state / "git" / "tester").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.root)], check=True)
        (self.root / ".gitignore").write_text("tmp/\n" if self.ignore_tmp else "")
        for skill in SKILLS:
            shutil.copytree(REAL_REPO / skill, self.root / skill,
                            ignore=shutil.ignore_patterns("__pycache__", "node_modules"))
        self.set_env(
            PATH=f"{HERE / 'fakes'}{os.pathsep}{os.environ['PATH']}",
            FAKE_STATE=str(self.state),
            # send "https://github.com/..." to the local bare repos
            GIT_CONFIG_COUNT="1",
            GIT_CONFIG_KEY_0=f"url.{self.state}/git/.insteadOf",
            GIT_CONFIG_VALUE_0="https://github.com/",
        )

    # --- helpers -------------------------------------------------------------------

    def set_env(self, **env: str) -> None:
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_harness(self, *argv: str) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = cli.main(list(argv), paths=Paths(self.root))
        return rc, out.getvalue()

    @property
    def tmp(self) -> Path:
        return self.root / "tmp"

    def remote_repos(self) -> list[str]:
        return sorted(p.name for p in (self.state / "git" / "tester").iterdir())

    def project_folders(self) -> list[str]:
        if not self.tmp.exists():
            return []
        return sorted(p.name for p in self.tmp.iterdir() if p.name != "e2e-logs")

    def assert_nothing_left_behind(self) -> None:
        self.assertEqual(self.remote_repos(), [], "a GitHub repo was left behind")
        self.assertEqual(self.project_folders(), [], "a project folder was left behind")


class FullRunTests(HarnessCase):
    def test_passing_run_checks_everything_and_cleans_up(self) -> None:
        rc, out = self.run_harness()
        self.assertEqual(rc, EXIT_OK, out)
        self.assertNotIn("✗", out)
        self.assertIn("checks that ran passed; teardown ok", out)
        self.assertTrue((self.tmp / "e2e-logs").is_dir(), "logs should be kept")
        self.assert_nothing_left_behind()

    def test_creates_tmp_when_missing(self) -> None:
        self.assertFalse(self.tmp.exists())
        rc, out = self.run_harness()
        self.assertEqual(rc, EXIT_OK, out)
        self.assertIn("tmp/ does not exist, creating it", out)

    def test_uses_existing_tmp(self) -> None:
        self.tmp.mkdir()
        rc, out = self.run_harness()
        self.assertEqual(rc, EXIT_OK, out)
        self.assertIn("tmp/ exists", out)

    def test_keep_leaves_the_project_and_repo(self) -> None:
        rc, out = self.run_harness("--keep")
        self.assertEqual(rc, EXIT_OK, out)
        self.assertEqual(len(self.remote_repos()), 1)
        self.assertEqual(len(self.project_folders()), 1)
        self.assertIn("--keep: leaving everything in place", out)

    def test_tag_never_pushed_fails_the_remote_checks_and_still_cleans_up(self) -> None:
        self.set_env(FAKE_CLAUDE_MODE="no-tag-push")
        rc, out = self.run_harness()
        self.assertEqual(rc, EXIT_CHECKS_FAILED, out)
        self.assertIn("✗ exactly one tag on the remote, v0.1.1", out)
        self.assertIn("✗ v0.1.1 is annotated and points at main's head", out)
        self.assertIn("✗ the remote tag's message is 'Release v0.1.1'", out)
        self.assert_nothing_left_behind()

    def test_failed_claude_session_is_reported_and_cleaned_up(self) -> None:
        self.set_env(FAKE_CLAUDE_MODE="fail")
        rc, out = self.run_harness()
        self.assertEqual(rc, EXIT_CHECKS_FAILED, out)
        self.assertIn("✗ phase 1: the Claude session finished", out)
        self.assert_nothing_left_behind()

    def test_gh_failing_mid_test_is_an_abort_not_a_pass(self) -> None:
        self.set_env(FAKE_GH_FAIL="compare")
        rc, out = self.run_harness()
        self.assertEqual(rc, EXIT_ABORTED, out)
        self.assertIn("ABORTED before all checks ran", out)
        self.assert_nothing_left_behind()

    def test_ctrl_c_kills_the_claude_session_and_cleans_up(self) -> None:
        self.set_env(FAKE_CLAUDE_MODE="interrupt")
        previous = signal.signal(signal.SIGINT, signal.default_int_handler)
        self.addCleanup(signal.signal, signal.SIGINT, previous)
        rc, out = self.run_harness()
        self.assertEqual(rc, EXIT_INTERRUPTED, out)
        self.assert_nothing_left_behind()
        pid = int((self.state / "claude.pid").read_text())
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.1)
        self.fail("the claude child was left running")

    def test_a_failed_repo_delete_is_reported_with_the_manual_command(self) -> None:
        self.set_env(FAKE_GH_FAIL="DELETE")
        rc, out = self.run_harness()
        self.assertEqual(rc, EXIT_CHECKS_FAILED, out)
        self.assertIn("could not delete", out)
        self.assertIn("gh repo delete tester/axc-cut-release-e2e-", out)
        self.assertIn("teardown INCOMPLETE", out)


class ExtraScenarioTests(HarnessCase):
    def test_a_default_run_includes_all_three_extra_scenarios(self) -> None:
        rc, out = self.run_harness()
        self.assertEqual(rc, EXIT_OK, out)
        for heading in ("Extra: /axc-cut-release 0.1.1 when v0.1.1 is already released",
                        "Extra: /axc-cut-release-preflight 0.1.1 when v0.1.1 already exists",
                        "Extra: /axc-cut-release 0.1.2 with nobody to confirm"):
            self.assertIn(heading, out)
        for check in ("already released: the router stopped without delegating",
                      "preflight on a tagged version: the verdict is Blocked",
                      "preflight is read-only",
                      "confirmation gate: preflight ran before the question",
                      "confirmation gate: v0.1.2 was not created locally or pushed"):
            self.assertIn(f"✓ {check}", out)
        self.assertIn("extra-gate", out)   # its cost is reported

    def test_happy_path_only_skips_them(self) -> None:
        rc, out = self.run_harness("--happy-path-only")
        self.assertEqual(rc, EXIT_OK, out)
        self.assertNotIn("Extra:", out)
        self.assertNotIn("extra-gate", out)
        self.assertIn("phase2-tag", out)

    def test_the_plan_counts_the_sessions(self) -> None:
        _, full = self.run_harness("--dry-run")
        _, short = self.run_harness("--dry-run", "--happy-path-only")
        self.assertIn("6 Claude sessions", full)
        self.assertIn("2 Claude sessions", short)

    def test_a_router_that_carries_on_when_already_released_fails_that_scenario(self) -> None:
        self.set_env(FAKE_CLAUDE_MODE="continue-when-released")
        rc, out = self.run_harness()
        self.assertEqual(rc, EXIT_CHECKS_FAILED, out)
        self.assertIn("✗ already released: the router stopped without delegating", out)
        self.assert_nothing_left_behind()

    def test_preflight_that_does_not_block_a_tagged_version_fails_that_scenario(self) -> None:
        self.set_env(FAKE_CLAUDE_MODE="preflight-green")
        rc, out = self.run_harness()
        self.assertEqual(rc, EXIT_CHECKS_FAILED, out)
        self.assertIn("✗ preflight on a tagged version: the verdict is Blocked", out)
        self.assert_nothing_left_behind()

    def test_a_tag_pushed_without_waiting_for_confirmation_fails_that_scenario(self) -> None:
        self.set_env(FAKE_CLAUDE_MODE="ignore-gate")
        rc, out = self.run_harness()
        self.assertEqual(rc, EXIT_CHECKS_FAILED, out)
        self.assertIn("✗ confirmation gate: v0.1.2 was not created locally or pushed", out)
        self.assertIn("✗ confirmation gate: the remote is unchanged", out)
        self.assert_nothing_left_behind()

    def test_work_done_without_the_skills_fails_the_delegation_checks(self) -> None:
        self.set_env(FAKE_CLAUDE_MODE="no-delegation")
        rc, out = self.run_harness("--happy-path-only")
        self.assertEqual(rc, EXIT_CHECKS_FAILED, out)
        self.assertIn("✗ phase 1: the router delegated to axc-cut-release-bump", out)
        self.assertIn("✗ phase 2: the router ran axc-cut-release-tag, which ran preflight first", out)


class ToolErrorTests(HarnessCase):
    def test_a_clean_session_reports_none(self) -> None:
        rc, out = self.run_harness()
        self.assertEqual(rc, EXIT_OK, out)
        self.assertIn("tool errors: phase1-bump none; phase2-tag none", out)

    def test_tool_errors_are_summarised_but_do_not_fail_the_run(self) -> None:
        self.set_env(FAKE_CLAUDE_TOOL_ERRORS="1")
        rc, out = self.run_harness()
        self.assertEqual(rc, EXIT_OK, out)
        self.assertIn("tool errors: phase1-bump 3 (1 expected, 2 unexpected); "
                      "phase2-tag 3 (1 expected, 2 unexpected)", out)
        # identical messages are grouped, and the expected 404 is not listed as a problem
        self.assertIn("phase1-bump: This Bash command contains multiple operations", out)
        self.assertIn("(x2)", out)
        self.assertNotIn("phase1-bump: Exit code 1", out)
        self.assertIn("not failures", out)
        self.assert_nothing_left_behind()


class PreflightTests(HarnessCase):
    def test_dry_run_creates_nothing(self) -> None:
        rc, out = self.run_harness("--dry-run")
        self.assertEqual(rc, EXIT_OK, out)
        self.assertIn("Plan (dry run, nothing created)", out)
        self.assertFalse(self.tmp.exists())
        self.assertEqual(self.remote_repos(), [])

    def test_missing_delete_repo_scope_stops_before_creating_anything(self) -> None:
        self.set_env(FAKE_GH_SCOPES="repo")
        rc, out = self.run_harness()
        self.assertEqual(rc, EXIT_ABORTED, out)
        self.assertIn("delete_repo", out)
        self.assertEqual(self.remote_repos(), [])
        self.assertFalse(self.tmp.exists())


class TmpNotIgnoredTests(HarnessCase):
    ignore_tmp = False

    def test_refuses_to_run_when_tmp_is_not_gitignored(self) -> None:
        rc, out = self.run_harness()
        self.assertEqual(rc, EXIT_ABORTED, out)
        self.assertIn("not gitignored", out)
        self.assertEqual(self.remote_repos(), [])


class SandboxSafetyTests(unittest.TestCase):
    """Teardown must never delete something this harness didn't create."""

    @staticmethod
    def make_ctx(root: Path, **state) -> RunContext:
        log = Logger()
        ctx = RunContext(options=Options(), paths=Paths(root), log=log, report=Report(log),
                         gh=mock.Mock(spec=GitHub), login="tester")
        for key, value in state.items():
            setattr(ctx, key, value)
        return ctx

    def test_refuses_to_delete_a_repo_without_the_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(io.StringIO()):
            ctx = self.make_ctx(Path(d), name="other", created_repo="tester/other")
            Sandbox(ctx)._delete_remote_repo()
        ctx.gh.delete_repo.assert_not_called()
        self.assertFalse(ctx.teardown_ok)

    def test_refuses_to_delete_a_repo_owned_by_someone_else(self) -> None:
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(io.StringIO()):
            ctx = self.make_ctx(Path(d), name=f"{NAME_PREFIX}1", created_repo=f"other/{NAME_PREFIX}1")
            Sandbox(ctx)._delete_remote_repo()
        ctx.gh.delete_repo.assert_not_called()
        self.assertFalse(ctx.teardown_ok)

    def test_refuses_to_remove_a_folder_outside_tmp(self) -> None:
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(io.StringIO()):
            root = Path(d)
            (root / "tmp").mkdir()
            victim = root / f"{NAME_PREFIX}escape"
            victim.mkdir()
            ctx = self.make_ctx(root, name=f"../{NAME_PREFIX}escape")
            Sandbox(ctx)._remove_local_folder()
            self.assertTrue(victim.exists())
        self.assertFalse(ctx.teardown_ok)


class UnitTests(unittest.TestCase):
    def test_token_scopes_are_parsed(self) -> None:
        headers = "HTTP/2 200\nX-OAuth-Scopes: repo, gist ,delete_repo\n\n{}"
        with mock.patch("harness.github.shell.run", return_value=headers):
            self.assertEqual(GitHub().token_scopes(), {"repo", "gist", "delete_repo"})

    def test_missing_scopes_header_means_unknown(self) -> None:
        with mock.patch("harness.github.shell.run", return_value="HTTP/2 200\n\n{}"):
            self.assertIsNone(GitHub().token_scopes())

    def test_report_counts_passes_and_failures(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            report = Report(Logger())
            report.check("a", True)
            report.check("b", False, "why")
        self.assertEqual((report.passed_count, [r.name for r in report.failed]), (1, ["b"]))

    def test_the_default_paths_point_at_a_checkout_with_the_skills(self) -> None:
        for skill in SKILLS:
            self.assertTrue((REAL_REPO / skill / "SKILL.md").is_file(), skill)

    def test_tool_result_text_handles_strings_and_part_lists(self) -> None:
        self.assertEqual(tool_result_text({"content": "a\n b"}), "a b")
        self.assertEqual(tool_result_text({"content": [{"type": "text", "text": "x"},
                                                       {"type": "text", "text": "y"}]}), "x y")
        self.assertEqual(tool_result_text({}), "")

    def test_the_release_yml_404_is_expected_and_other_errors_are_not(self) -> None:
        not_found = "HTTP 404: workflow release.yml not found on the default branch"
        expected, unexpected = split_tool_errors([not_found, "Exit code 2"])
        self.assertEqual((expected, unexpected), ([not_found], ["Exit code 2"]))

    def test_claude_command_isolates_settings_and_caps_spend(self) -> None:
        cmd = ClaudeRunner(Options(model="m", max_budget_usd=1.5), Logger(), Path(".")).command("p")
        self.assertEqual(cmd[cmd.index("--setting-sources") + 1], "project,local")
        self.assertEqual(cmd[cmd.index("--max-budget-usd") + 1], "1.5")
        self.assertEqual(cmd[cmd.index("--model") + 1], "m")


if __name__ == "__main__":
    unittest.main()
