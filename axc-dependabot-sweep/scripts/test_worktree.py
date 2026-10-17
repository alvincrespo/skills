#!/usr/bin/env python3
"""
Unit tests for worktree.py. These use real git against throwaway local repos
(an "origin" and a clone), so no network or GitHub is involved.

Run directly:
    python3 -m unittest axc-dependabot-sweep/scripts/test_worktree.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import worktree  # noqa: E402

GIT_ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}


def sh(cwd: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, env=GIT_ENV, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


class WorktreeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name).resolve()
        self.origin = base / "origin.git"
        self.repo = base / "myrepo"
        self.root = base / "sweep"

        sh(base, "init", "--bare", "-b", "main", str(self.origin))
        sh(base, "clone", str(self.origin), str(self.repo))
        (self.repo / "a.txt").write_text("1")
        sh(self.repo, "add", ".")
        sh(self.repo, "commit", "-m", "init")
        sh(self.repo, "push", "origin", "main")

        sh(self.repo, "switch", "-c", "dependabot/bump-x")
        (self.repo / "a.txt").write_text("2")
        sh(self.repo, "commit", "-am", "bump")
        self.bump_sha = sh(self.repo, "rev-parse", "HEAD")
        sh(self.repo, "push", "origin", "dependabot/bump-x")
        sh(self.repo, "switch", "main")

    def test_create_checks_out_the_fetched_tip_detached(self) -> None:
        result = worktree.create(self.repo, self.root, 12, "dependabot/bump-x")
        self.assertEqual(result["path"], str(self.root / "myrepo-pr-12"))
        self.assertEqual(result["sha"], self.bump_sha)
        self.assertEqual((Path(result["path"]) / "a.txt").read_text(), "2")
        self.assertEqual(sh(Path(result["path"]), "branch", "--show-current"), "")

    def test_create_at_a_specific_sha(self) -> None:
        main_sha = sh(self.repo, "rev-parse", "main")
        result = worktree.create(self.repo, self.root, 12, "dependabot/bump-x", main_sha)
        self.assertEqual(result["sha"], main_sha)
        self.assertEqual((Path(result["path"]) / "a.txt").read_text(), "1")

    def test_create_refuses_an_existing_path(self) -> None:
        worktree.create(self.repo, self.root, 12, "dependabot/bump-x")
        with self.assertRaises(RuntimeError):
            worktree.create(self.repo, self.root, 12, "dependabot/bump-x")

    def test_create_fails_for_an_unknown_branch(self) -> None:
        with self.assertRaises(RuntimeError):
            worktree.create(self.repo, self.root, 12, "dependabot/nope")
        self.assertFalse((self.root / "myrepo-pr-12").exists())

    def test_remove_deletes_even_a_dirty_worktree(self) -> None:
        path = Path(worktree.create(self.repo, self.root, 12, "dependabot/bump-x")["path"])
        (path / "a.txt").write_text("dirty")
        (path / "untracked.txt").write_text("x")
        worktree.remove(self.repo, self.root, 12)
        self.assertFalse(path.exists())
        self.assertNotIn(str(path), sh(self.repo, "worktree", "list", "--porcelain"))

    def test_remove_is_idempotent(self) -> None:
        worktree.remove(self.repo, self.root, 99)

    def test_remove_cleans_an_unregistered_directory_under_root(self) -> None:
        path = self.root / "myrepo-pr-5"
        path.mkdir(parents=True)
        (path / "junk").write_text("x")
        worktree.remove(self.repo, self.root, 5)
        self.assertFalse(path.exists())

    def test_prune_removes_every_sweep_worktree_and_nothing_else(self) -> None:
        a = Path(worktree.create(self.repo, self.root, 1, "dependabot/bump-x")["path"])
        b = Path(worktree.create(self.repo, self.root, 2, "dependabot/bump-x")["path"])
        elsewhere = Path(self._tmp.name) / "keep"
        sh(self.repo, "worktree", "add", "--detach", str(elsewhere), "main")

        result = worktree.prune(self.repo, self.root)

        self.assertEqual(sorted(result["removed"]), sorted([str(a), str(b)]))
        self.assertFalse(a.exists() or b.exists())
        self.assertTrue(elsewhere.exists())
        self.assertTrue(self.repo.exists())

    def test_prune_removes_crash_leftovers(self) -> None:
        leftover = self.root / "myrepo-pr-7"
        leftover.mkdir(parents=True)
        worktree.prune(self.repo, self.root)
        self.assertFalse(leftover.exists())

    def test_prune_leaves_other_repos_directories(self) -> None:
        other = self.root / "otherrepo-pr-7"
        other.mkdir(parents=True)
        worktree.prune(self.repo, self.root)
        self.assertTrue(other.exists())

    def test_prune_with_no_root(self) -> None:
        self.assertEqual(worktree.prune(self.repo, self.root), {"removed": []})


if __name__ == "__main__":
    unittest.main()
