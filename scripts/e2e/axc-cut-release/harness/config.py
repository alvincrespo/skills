"""Constants and run options. Nothing here touches the disk or the network."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# Skills copied into the throwaway project. The tag skill reaches the preflight skill
# and the router's script through sibling folders, so all four go together.
SKILLS = (
    "axc-cut-release",
    "axc-cut-release-bump",
    "axc-cut-release-preflight",
    "axc-cut-release-tag",
)

# Every repo and folder this harness creates starts with this. Teardown refuses to
# delete anything that doesn't, so a bug can't remove something that isn't ours.
NAME_PREFIX = "axc-cut-release-e2e-"



@dataclass(frozen=True)
class Release:
    """One release the scenario cuts: the version `/axc-cut-release patch` should produce."""

    version: str
    previous: str

    @property
    def branch(self) -> str:
        return f"release/v{self.version}"

    @property
    def tag(self) -> str:
        return f"v{self.version}"

    @property
    def title(self) -> str:
        return f"release: v{self.version}"


FIRST_RELEASE = Release("0.1.1", previous="0.1.0")    # the project starts at 0.1.0
SECOND_RELEASE = Release("0.1.2", previous="0.1.1")
BASE_VERSION = FIRST_RELEASE.previous

# What each Claude session is told. The skills ask the user to confirm; nobody is there.
AUTOMATION_NOTE = (
    "This is an automated end-to-end test in a throwaway repository. Nobody is "
    "available to answer questions, so if the skill asks you to confirm a version "
    "or a plan, answer yes and continue. Do not stop to ask."
)
# For the scenario that checks the skill really waits for the user before pushing a tag.
NO_REPLY_NOTE = (
    "This is an automated end-to-end test in a throwaway repository. Nobody will reply to "
    "questions during this session. Do the work up to the point where the skill says to ask the "
    "user to confirm, ask that question, and then end your turn. Do not proceed without a reply."
)

ALLOWED_TOOLS = (
    "Bash(git:*)", "Bash(gh:*)", "Bash(python3:*)", "Bash(test:*)", "Bash(ls:*)",
    "Bash(cat:*)", "Read", "Glob", "Grep", "Skill",
)

# Tool errors that are expected given how the throwaway project is built, so the summary
# doesn't list them as problems.
EXPECTED_TOOL_ERRORS = (
    # The tag skill's last step runs `gh run list --workflow=release.yml`. The project's workflow
    # is ci/release.yml, outside .github/ on purpose (so a tag push runs nothing), which GitHub
    # reports as a 404.
    re.compile(r"workflow release\.yml not found on the default branch"),
)

# Exit codes
EXIT_OK = 0
EXIT_CHECKS_FAILED = 1   # a check failed, or teardown didn't finish
EXIT_ABORTED = 2         # setup failed, or a git/gh call errored mid-test
EXIT_INTERRUPTED = 130


@dataclass(frozen=True)
class Paths:
    """Where things live. `repo_root` holds the skills and the gitignored `tmp/`."""

    repo_root: Path

    @classmethod
    def default(cls) -> "Paths":
        # harness/config.py -> harness -> axc-cut-release -> e2e -> scripts -> <repo>
        return cls(Path(__file__).resolve().parents[4])

    @property
    def tmp(self) -> Path:
        return self.repo_root / "tmp"

    @property
    def log_root(self) -> Path:
        return self.tmp / "e2e-logs"


@dataclass(frozen=True)
class Options:
    dry_run: bool = False
    keep: bool = False
    ssh: bool = False
    model: str | None = None
    max_budget_usd: float = 3.0
    timeout_min: int = 15
    happy_path_only: bool = False
