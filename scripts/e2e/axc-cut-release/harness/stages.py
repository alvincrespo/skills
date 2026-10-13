"""Reusable steps. Each one does something to the project and records checks on the report.

The scenarios in scenario.py combine these. Steps take a `Release` so the same bump / merge / tag
code runs for more than one version.
"""

from __future__ import annotations

import json

from .claude_runner import ClaudeRunner, Session
from .config import AUTOMATION_NOTE, Release
from .context import RunContext
from .fixture import write_fixture
from .git_repo import GitRepo

BUMP_SKILL = "axc-cut-release-bump"
TAG_SKILL = "axc-cut-release-tag"
PREFLIGHT_SKILL = "axc-cut-release-preflight"


def _capitalise(text: str) -> str:
    return text[:1].upper() + text[1:]


class Stages:
    def __init__(self, ctx: RunContext, repo: GitRepo, claude: ClaudeRunner) -> None:
        self.ctx = ctx
        self.repo = repo
        self.claude = claude
        self.gh = ctx.gh
        self.report = ctx.report
        self.log = ctx.log

    # --- project history -----------------------------------------------------------

    def push_initial_commit(self) -> None:
        self.log.step("Initial commit")
        write_fixture(self.ctx.project_path, self.ctx.full_name)
        self.repo.commit_all("Initial commit")
        self.repo.push("-u", "origin", "main")
        self.report.check("initial commit pushed", self.repo.remote_head() == self.repo.head())

    def push_readme_change(self) -> None:
        self.log.step("Change the README, commit and push")
        with open(self.ctx.project_path / "README.md", "a", encoding="utf-8") as fh:
            fh.write(f"\nUpdated by the e2e run {self.ctx.name}.\n")
        self.repo.git("commit", "-q", "-am", "Update the README")
        self.repo.push("origin", "main")
        self.report.check("README change pushed", self.repo.remote_head() == self.repo.head())

    # --- running a skill -----------------------------------------------------------

    def run_skill(self, label: str, skill_args: str, what: str, note: str = AUTOMATION_NOTE) -> Session:
        """Run one Claude session and record whether it finished and which skills it used."""
        session = self.claude.run(self.ctx.project_path, label, skill_args, note)
        self.ctx.session_costs[label] = session.cost_usd
        self.ctx.tool_errors[label] = session.tool_errors
        self.report.check(
            f"{what}: the Claude session finished", session.finished_cleanly,
            f"exit {session.exit_code}, timed out: {session.timed_out}, "
            f"is_error: {session.is_error}. See {self.ctx.logs_dir}/{label}.stream.jsonl")
        return session

    # --- bump -> merge -------------------------------------------------------------

    def open_bump_pr(self, release: Release, label: str, what: str) -> int | None:
        """`/axc-cut-release patch` should open a PR for `release`. Returns its number, or None."""
        self.log.step(f"{_capitalise(what)}: /axc-cut-release patch   "
                      f"(expects a PR bumping {release.previous} -> {release.version})")
        main_before = self.repo.remote_head()
        session = self.run_skill(label, "/axc-cut-release patch", what)
        self.report.check(f"{what}: the router delegated to {BUMP_SKILL}", BUMP_SKILL in session.skills_used,
                          f"skills used: {list(session.skills_used)}")

        heads = self.repo.remote_refs(f"refs/heads/{release.branch}")
        pushed = f"refs/heads/{release.branch}" in heads
        self.report.check(f"branch {release.branch} was pushed", pushed)

        prs = self.gh.open_prs(self.ctx.full_name, self.ctx.login, release.branch)
        self.report.check("exactly one open PR from that branch", len(prs) == 1, f"found {len(prs)}")
        pr = prs[0] if len(prs) == 1 else None
        if pr:
            self.report.check("the PR targets main", pr["base"]["ref"] == "main", pr["base"]["ref"])
            self.report.check(f"the PR title is '{release.title}'", pr["title"] == release.title, pr["title"])
        if pushed:
            self._check_bump_diff(release)

        self.report.check("main was not touched", self.repo.remote_head() == main_before)
        self.report.check(f"no {release.tag} tag exists yet",
                          f"refs/tags/{release.tag}" not in self.repo.remote_refs("refs/tags/*"))
        return pr["number"] if pr else None

    def merge(self, number: int) -> bool:
        """The step a human does between the two phases."""
        self.log.step(f"Merging PR #{number} (the part a human does between the two phases)")
        out = self.gh.squash_merge(self.ctx.full_name, number)
        return self.report.check(f"PR #{number} merged", bool(out.get("merged")), json.dumps(out))

    def _check_bump_diff(self, release: Release) -> None:
        cmp_ = self.gh.compare(self.ctx.full_name, "main", release.branch)
        files = cmp_["files"]
        self.report.check(
            "the PR changes exactly one file, VERSION, by one line",
            len(files) == 1 and files[0]["filename"] == "VERSION"
            and files[0]["additions"] == 1 and files[0]["deletions"] == 1,
            json.dumps([(f["filename"], f["additions"], f["deletions"]) for f in files]))
        self.report.check("the PR holds exactly one commit", cmp_["ahead_by"] == 1,
                          f"ahead by {cmp_['ahead_by']}")
        version = self.gh.file_text(self.ctx.full_name, "VERSION", release.branch)
        self.report.check(f"VERSION on the branch is {release.version}", version == release.version, version)

    # --- tag -----------------------------------------------------------------------

    def tag_release(self, release: Release, label: str, what: str) -> None:
        """`/axc-cut-release <V>` should run preflight, then push the tag."""
        self.log.step(f"{_capitalise(what)}: /axc-cut-release {release.version}   "
                      f"(expects preflight, then tag {release.tag} pushed)")
        session = self.run_skill(label, f"/axc-cut-release {release.version}", what)
        used = list(session.skills_used)
        ran_in_order = (TAG_SKILL in used and PREFLIGHT_SKILL in used
                        and used.index(TAG_SKILL) < used.index(PREFLIGHT_SKILL))
        self.report.check(f"{what}: the router ran {TAG_SKILL}, which ran preflight first",
                          ran_in_order, f"skills used: {used}")
        self._check_tag(release, self.repo.remote_refs("refs/tags/*"))

        version = self.gh.file_text(self.ctx.full_name, "VERSION", "main")
        self.report.check(f"VERSION on main is {release.version}", version == release.version, version)
        commits = self.gh.commits(self.ctx.full_name, "main")
        self.report.check(
            "main has exactly 3 commits (initial, README, the squashed bump PR): "
            "nothing was pushed to it directly",
            len(commits) == 3, f"{len(commits)} commits")

    def _check_tag(self, release: Release, tags: dict[str, str]) -> None:
        tag = release.tag
        peeled = f"refs/tags/{tag}^{{}}"   # present only for an annotated tag
        self.report.check(f"exactly one tag on the remote, {tag}",
                          sorted(tags) == sorted([f"refs/tags/{tag}", peeled]), json.dumps(sorted(tags)))
        main_head = self.repo.remote_head()
        self.report.check(f"{tag} is annotated and points at main's head",
                          bool(main_head) and tags.get(peeled) == main_head,
                          f"peeled {tags.get(peeled)} vs main {main_head}")
        message = self.repo.remote_tag_message(tag)
        self.report.check(f"the remote tag's message is 'Release v{release.version}'",
                          message == f"Release v{release.version}",
                          message or "tag not fetched from the remote")
