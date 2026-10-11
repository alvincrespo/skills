"""The test itself: what to do, and what must be true afterwards.

Each stage is one method that does something and then records checks on `self.report`.
To add a check, add it to the stage it belongs to; to add a stage, write a method and call
it from `run()`.
"""

from __future__ import annotations

import json

from .claude_runner import ClaudeRunner, Session
from .config import BASE_VERSION, NEXT_VERSION, RELEASE_BRANCH, TAG
from .context import RunContext
from .fixture import write_fixture
from .git_repo import GitRepo


class ReleaseScenario:
    """Bump PR -> merge -> tag, driven through the real skills."""

    def __init__(self, ctx: RunContext, repo: GitRepo, claude: ClaudeRunner) -> None:
        self.ctx = ctx
        self.repo = repo
        self.claude = claude
        self.gh = ctx.gh
        self.report = ctx.report
        self.log = ctx.log

    def run(self) -> None:
        self.push_initial_commit()
        self.push_readme_change()
        pr_number = self.run_bump_phase()
        if pr_number is None:
            self.report.check("phase 2 skipped: there is no PR to merge", False)
            return
        if not self.merge(pr_number):
            return
        self.run_tag_phase()

    # --- stages --------------------------------------------------------------------

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

    def run_bump_phase(self) -> int | None:
        """`/axc-cut-release patch` should open a PR. Returns its number, or None."""
        self.log.step(f"Phase 1: /axc-cut-release patch   "
                      f"(expects a PR bumping {BASE_VERSION} -> {NEXT_VERSION})")
        main_before = self.repo.remote_head()
        session = self.claude.run(self.ctx.project_path, "phase1-bump", "/axc-cut-release patch")
        self._record_session("phase 1", "phase1-bump", session)

        heads = self.repo.remote_refs(f"refs/heads/{RELEASE_BRANCH}")
        pushed = f"refs/heads/{RELEASE_BRANCH}" in heads
        self.report.check(f"branch {RELEASE_BRANCH} was pushed", pushed)

        prs = self.gh.open_prs(self.ctx.full_name, self.ctx.login, RELEASE_BRANCH)
        self.report.check("exactly one open PR from that branch", len(prs) == 1, f"found {len(prs)}")
        pr = prs[0] if len(prs) == 1 else None
        if pr:
            self.report.check("the PR targets main", pr["base"]["ref"] == "main", pr["base"]["ref"])
            self.report.check(f"the PR title is 'release: v{NEXT_VERSION}'",
                              pr["title"] == f"release: v{NEXT_VERSION}", pr["title"])
        if pushed:
            self._check_bump_diff()

        self.report.check("main was not touched", self.repo.remote_head() == main_before)
        self.report.check("no tag exists yet", not self.repo.remote_refs("refs/tags/*"))
        return pr["number"] if pr else None

    def merge(self, number: int) -> bool:
        """The step a human does between the two phases."""
        self.log.step(f"Merging PR #{number} (the part a human does between the two phases)")
        out = self.gh.squash_merge(self.ctx.full_name, number)
        return self.report.check(f"PR #{number} merged", bool(out.get("merged")), json.dumps(out))

    def run_tag_phase(self) -> None:
        """`/axc-cut-release <V>` should tag and push."""
        self.log.step(f"Phase 2: /axc-cut-release {NEXT_VERSION}   "
                      f"(expects preflight, then tag {TAG} pushed)")
        session = self.claude.run(self.ctx.project_path, "phase2-tag",
                                  f"/axc-cut-release {NEXT_VERSION}")
        self._record_session("phase 2", "phase2-tag", session)
        self._check_tag(self.repo.remote_refs("refs/tags/*"))

        version = self.gh.file_text(self.ctx.full_name, "VERSION", "main")
        self.report.check(f"VERSION on main is {NEXT_VERSION}", version == NEXT_VERSION, version)
        commits = self.gh.commits(self.ctx.full_name, "main")
        self.report.check(
            "main has exactly 3 commits (initial, README, the squashed bump PR): "
            "nothing was pushed to it directly",
            len(commits) == 3, f"{len(commits)} commits")

    # --- helpers -------------------------------------------------------------------

    def _record_session(self, phase: str, label: str, session: Session) -> None:
        self.ctx.session_costs[label] = session.cost_usd
        self.ctx.tool_errors[label] = session.tool_errors
        self.report.check(
            f"{phase}: the Claude session finished", session.finished_cleanly,
            f"exit {session.exit_code}, timed out: {session.timed_out}, "
            f"is_error: {session.is_error}. See {self.ctx.logs_dir}/{label}.stream.jsonl")

    def _check_bump_diff(self) -> None:
        cmp_ = self.gh.compare(self.ctx.full_name, "main", RELEASE_BRANCH)
        files = cmp_["files"]
        self.report.check(
            "the PR changes exactly one file, VERSION, by one line",
            len(files) == 1 and files[0]["filename"] == "VERSION"
            and files[0]["additions"] == 1 and files[0]["deletions"] == 1,
            json.dumps([(f["filename"], f["additions"], f["deletions"]) for f in files]))
        self.report.check("the PR holds exactly one commit", cmp_["ahead_by"] == 1,
                          f"ahead by {cmp_['ahead_by']}")
        version = self.gh.file_text(self.ctx.full_name, "VERSION", RELEASE_BRANCH)
        self.report.check(f"VERSION on the branch is {NEXT_VERSION}", version == NEXT_VERSION, version)

    def _check_tag(self, tags: dict[str, str]) -> None:
        peeled = f"refs/tags/{TAG}^{{}}"   # present only for an annotated tag
        self.report.check(f"exactly one tag on the remote, {TAG}",
                          sorted(tags) == sorted([f"refs/tags/{TAG}", peeled]), json.dumps(sorted(tags)))
        main_head = self.repo.remote_head()
        self.report.check(f"{TAG} is annotated and points at main's head",
                          bool(main_head) and tags.get(peeled) == main_head,
                          f"peeled {tags.get(peeled)} vs main {main_head}")
        message = self.repo.remote_tag_message(TAG)
        self.report.check(f"the remote tag's message is 'Release v{NEXT_VERSION}'",
                          message == f"Release v{NEXT_VERSION}",
                          message or "tag not fetched from the remote")
