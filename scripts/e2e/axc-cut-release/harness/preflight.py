"""Checks that run before anything is created."""

from __future__ import annotations

import shutil

from . import shell
from .context import RunContext
from .errors import HarnessError

REQUIRED_TOOLS = ("git", "gh", "claude")


def check_environment(ctx: RunContext) -> None:
    ctx.log.step("Checking the environment")
    for tool in REQUIRED_TOOLS:
        if not shutil.which(tool):
            raise HarnessError(f"`{tool}` is not installed or not on PATH")
    ctx.log.info("  ✓ git, gh and claude are installed")

    ctx.login = ctx.gh.login()
    ctx.log.info(f"  ✓ gh is logged in as {ctx.login}")

    scopes = ctx.gh.token_scopes()
    if scopes is None:
        ctx.log.info("  ! can't read the token's scopes (fine-grained token?); make sure it can "
                     "create and delete repos, or teardown will leave one behind")
    elif "delete_repo" not in scopes:
        raise HarnessError(
            "the gh token lacks the `delete_repo` scope, so teardown couldn't remove the repo "
            "it creates. Run: gh auth refresh -h github.com -s delete_repo")
    else:
        ctx.log.info("  ✓ the gh token can delete repos")

    # The throwaway project goes in tmp/, which must never be committed.
    if not shell.succeeds(["git", "-C", str(ctx.paths.repo_root), "check-ignore", "-q", "tmp/.probe"]):
        raise HarnessError("tmp/ is not gitignored in this repo. Add a `tmp/` line to .gitignore first.")
    ctx.log.info("  ✓ tmp/ is gitignored")
