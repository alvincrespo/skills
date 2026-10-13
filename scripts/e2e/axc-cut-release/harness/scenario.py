"""The test itself: which scenarios run, in what order, and what each must prove.

`run()` cuts one release for real (bump PR -> merge -> tag), then reuses that project's state for
three more scenarios. The steps live in stages.py; to add a check, add it to the scenario it
belongs to; to add a scenario, write a method and call it from `run()`.
"""

from __future__ import annotations

import re

from .claude_runner import ClaudeRunner
from .config import FIRST_RELEASE, NO_REPLY_NOTE, SECOND_RELEASE, Release
from .context import RunContext
from .git_repo import GitRepo
from .stages import BUMP_SKILL, PREFLIGHT_SKILL, TAG_SKILL, Stages


class ReleaseScenario:
    def __init__(self, ctx: RunContext, repo: GitRepo, claude: ClaudeRunner) -> None:
        self.ctx = ctx
        self.repo = repo
        self.report = ctx.report
        self.stages = Stages(ctx, repo, claude)

    def run(self) -> None:
        if not self.happy_path(FIRST_RELEASE):
            return
        if self.ctx.options.happy_path_only:
            return
        self.already_released_stops(FIRST_RELEASE)
        self.preflight_blocks_a_tagged_version(FIRST_RELEASE)
        self.tag_waits_for_confirmation(SECOND_RELEASE)

    # --- scenarios -----------------------------------------------------------------

    def happy_path(self, release: Release) -> bool:
        """Bump PR -> merge -> tag, through the real skills. Returns False if it couldn't finish."""
        self.stages.push_initial_commit()
        self.stages.push_readme_change()
        number = self.stages.open_bump_pr(release, "phase1-bump", "phase 1")
        if number is None:
            self.report.check("phase 2 skipped: there is no PR to merge", False)
            return False
        if not self.stages.merge(number):
            return False
        self.stages.tag_release(release, "phase2-tag", "phase 2")
        return True

    def already_released_stops(self, release: Release) -> None:
        """Asking for a version that is already tagged must stop at the router and change nothing."""
        self.ctx.log.step(f"Extra: /axc-cut-release {release.version} when {release.tag} is already "
                          "released (the router should stop)")
        before = self.repo.remote_refs()
        session = self.stages.run_skill("extra-released", f"/axc-cut-release {release.version}",
                                        "already released")
        delegated = [s for s in session.skills_used if s in (BUMP_SKILL, TAG_SKILL, PREFLIGHT_SKILL)]
        self.report.check("already released: the router stopped without delegating", not delegated,
                          f"delegated to {delegated}")
        self.report.check("already released: the reply says the version is released",
                          bool(re.search(r"\breleased\b", session.final_text, re.I))
                          and release.version in session.final_text, session.final_text[:300])
        self.report.check("already released: nothing on the remote changed",
                          self.repo.remote_refs() == before)

    def preflight_blocks_a_tagged_version(self, release: Release) -> None:
        """Preflight on a version whose tag exists must say Blocked, cite the tag, and be read-only."""
        self.ctx.log.step(f"Extra: /axc-cut-release-preflight {release.version} when {release.tag} "
                          "already exists (should be Blocked)")
        remote_before, head_before = self.repo.remote_refs(), self.repo.head()
        session = self.stages.run_skill("extra-preflight-blocked",
                                        f"/axc-cut-release-preflight {release.version}",
                                        "preflight on a tagged version")
        text = session.final_text
        self.report.check("preflight on a tagged version: the verdict is Blocked",
                          bool(re.search(r"\bBlocked\b", text)) and "Ready to release" not in text,
                          text[:300])
        self.report.check(f"preflight on a tagged version: it cites the existing tag {release.tag}",
                          release.tag in text, text[:300])
        self.report.check(
            "preflight is read-only: the remote, HEAD and working tree are unchanged",
            self.repo.remote_refs() == remote_before and self.repo.head() == head_before
            and not self.repo.git("status", "--porcelain"))

    def tag_waits_for_confirmation(self, release: Release) -> None:
        """With nobody to answer, the tag skill must run preflight, ask, and not tag or push."""
        number = self.stages.open_bump_pr(release, "extra-gate-bump", "confirmation gate (bump)")
        if number is None or not self.stages.merge(number):
            self.report.check("confirmation gate skipped: couldn't prepare the release", False)
            return
        self.ctx.log.step(f"Extra: /axc-cut-release {release.version} with nobody to confirm "
                          f"(should ask, then stop without tagging)")
        before = self.repo.remote_refs()
        session = self.stages.run_skill("extra-gate", f"/axc-cut-release {release.version}",
                                        "confirmation gate", note=NO_REPLY_NOTE)
        text = session.final_text
        self.report.check("confirmation gate: preflight ran before the question",
                          PREFLIGHT_SKILL in session.skills_used,
                          f"skills used: {list(session.skills_used)}")
        self.report.check(f"confirmation gate: it asked about pushing {release.tag} and stopped",
                          release.tag in text and "?" in text, text[:300])
        local_tags = self.repo.git("tag", "-l", release.tag)
        self.report.check(f"confirmation gate: {release.tag} was not created locally or pushed",
                          not local_tags and f"refs/tags/{release.tag}" not in self.repo.remote_refs("refs/tags/*"),
                          f"local: {local_tags!r}")
        self.report.check("confirmation gate: the remote is unchanged", self.repo.remote_refs() == before)
