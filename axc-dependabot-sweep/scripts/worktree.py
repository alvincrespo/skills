#!/usr/bin/env python3
"""
Create and tear down per-PR worktrees, so each bump is verified in isolation
and the main checkout is never touched.

Usage:
    worktree.py create --pr N --branch HEAD_REF [--sha SHA] [--repo-dir DIR] [--root DIR]
    worktree.py remove --pr N [--repo-dir DIR] [--root DIR]
    worktree.py prune [--repo-dir DIR] [--root DIR]

Worktrees live under --root (default: <system temp>/dependabot-sweep) as
<repo-name>-pr-<N>, detached at the PR's head. `create` fetches the branch and
checks out --sha if given (the SHA that was reviewed), else the fetched tip; it
refuses to reuse an existing path. `remove` force-removes one worktree, even if
dirty. `prune` force-removes this repo's sweep worktrees under --root and runs
`git worktree prune`; use it at the end of a run or after a crash.

Prints one JSON object. Exit codes: 0 ok, 1 error.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def default_root() -> Path:
    return Path(tempfile.gettempdir()) / "dependabot-sweep"


def git(repo_dir: Path, *args: str) -> str:
    cmd = ["git", *args]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=repo_dir)
    if result.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def worktree_path(repo_dir: Path, root: Path, pr: int) -> Path:
    toplevel = Path(git(repo_dir, "rev-parse", "--show-toplevel"))
    return root / f"{toplevel.name}-pr-{pr}"


def create(repo_dir: Path, root: Path, pr: int, branch: str, sha: str | None = None) -> dict[str, str]:
    path = worktree_path(repo_dir, root, pr)
    if path.exists():
        raise RuntimeError(f"{path} already exists; remove it first")
    git(repo_dir, "fetch", "origin", branch)
    fetched = git(repo_dir, "rev-parse", "FETCH_HEAD")
    target = sha or fetched
    root.mkdir(parents=True, exist_ok=True)
    git(repo_dir, "worktree", "add", "--detach", str(path), target)
    return {"path": str(path), "sha": git(path, "rev-parse", "HEAD")}


def _is_under(path: Path, root: Path) -> bool:
    return root.resolve() in path.resolve().parents


def remove(repo_dir: Path, root: Path, pr: int) -> dict[str, str]:
    path = worktree_path(repo_dir, root, pr)
    try:
        git(repo_dir, "worktree", "remove", "--force", str(path))
    except RuntimeError:
        # Not registered (or already half-gone): fall back to deleting the
        # directory, but never anything outside --root.
        if path.exists() and _is_under(path, root):
            shutil.rmtree(path)
    git(repo_dir, "worktree", "prune")
    return {"removed": str(path)}


def prune(repo_dir: Path, root: Path) -> dict[str, list[str]]:
    removed: list[str] = []
    for line in git(repo_dir, "worktree", "list", "--porcelain").splitlines():
        if not line.startswith("worktree "):
            continue
        path = Path(line.removeprefix("worktree "))
        if _is_under(path, root):
            git(repo_dir, "worktree", "remove", "--force", str(path))
            removed.append(str(path))
    git(repo_dir, "worktree", "prune")
    # Directories left behind by a crash that git no longer tracks. Only this
    # repo's: --root is shared by default, and another repo's sweep may be live.
    prefix = f"{Path(git(repo_dir, 'rev-parse', '--show-toplevel')).name}-pr-"
    if root.exists():
        for leftover in root.iterdir():
            if leftover.is_dir() and leftover.name.startswith(prefix):
                shutil.rmtree(leftover)
                removed.append(str(leftover))
    return {"removed": removed}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo-dir", default=".", help="repo checkout (default: cwd)")
    parser.add_argument("--root", help="where worktrees live (default: <tmp>/dependabot-sweep)")
    sub = parser.add_subparsers(dest="command", required=True)
    p_create = sub.add_parser("create")
    p_create.add_argument("--pr", type=int, required=True)
    p_create.add_argument("--branch", required=True, help="the PR's head ref")
    p_create.add_argument("--sha", help="check out this SHA instead of the fetched tip")
    p_remove = sub.add_parser("remove")
    p_remove.add_argument("--pr", type=int, required=True)
    sub.add_parser("prune")
    args = parser.parse_args()

    repo_dir = Path(args.repo_dir)
    root = Path(args.root) if args.root else default_root()
    try:
        if args.command == "create":
            result = create(repo_dir, root, args.pr, args.branch, args.sha)
        elif args.command == "remove":
            result = remove(repo_dir, root, args.pr)
        else:
            result = prune(repo_dir, root)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
