"""The throwaway project: created on entry, always removed on exit."""

from __future__ import annotations

import shutil
from datetime import datetime
from types import TracebackType

from .claude_runner import ClaudeRunner
from .config import NAME_PREFIX, SKILLS
from .context import RunContext
from .errors import HarnessError
from .fixture import install_skills
from .git_repo import GitRepo


class Sandbox:
    """`with Sandbox(ctx) as box:` gives a local git repo wired to a fresh private GitHub repo.

    Leaving the block deletes both (unless `--keep`), whether the test passed, failed or was
    interrupted. If setup itself fails halfway, whatever was already created is cleaned up too.
    """

    def __init__(self, ctx: RunContext) -> None:
        self.ctx = ctx
        self.repo: GitRepo
        self.claude: ClaudeRunner

    def __enter__(self) -> "Sandbox":
        try:
            self._setup()
        except BaseException:
            self._teardown()
            raise
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None,
                 tb: TracebackType | None) -> bool:
        self._teardown()
        return False   # never swallow the exception

    # --- setup ---------------------------------------------------------------------

    def _setup(self) -> None:
        ctx, log = self.ctx, self.ctx.log
        log.step("Setting up the project")

        tmp = ctx.paths.tmp
        if tmp.exists():
            log.info(f"  tmp/ exists: {tmp}")
        else:
            log.info(f"  tmp/ does not exist, creating it: {tmp}")
            tmp.mkdir()

        ctx.name = f"{NAME_PREFIX}{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        ctx.logs_dir.mkdir(parents=True)
        log.attach_file(ctx.logs_dir / "run.log")
        ctx.project_path.mkdir()
        log.info(f"  project folder: {ctx.project_path}")
        log.info(f"  logs (kept after teardown): {ctx.logs_dir}")

        self.repo = GitRepo(ctx.project_path)
        self.repo.init()
        (ctx.project_path / "README.md").write_text(
            f"# {ctx.name}\n\nThrowaway repository for the axc-cut-release end-to-end test.\n")
        log.info("  ✓ git repository initialised with a README")

        ctx.gh.create_private_repo(
            ctx.name, "Throwaway axc-cut-release e2e repo (safe to delete)")
        ctx.created_repo = ctx.full_name   # from here on, teardown owns deleting it
        host = "git@github.com:" if ctx.options.ssh else "https://github.com/"
        self.repo.add_remote(f"{host}{ctx.full_name}.git")
        log.info(f"  ✓ created private repo {ctx.full_name}")

        # Skills stay out of git so the working tree is clean, as the skills require.
        install_skills(ctx.paths.repo_root, ctx.project_path)
        self.repo.exclude(".claude/skills/")
        log.info(f"  ✓ installed {len(SKILLS)} skills into .claude/skills/")

        self.claude = ClaudeRunner(ctx.options, log, ctx.logs_dir)

    # --- teardown ------------------------------------------------------------------

    def _teardown(self) -> None:
        ctx, log = self.ctx, self.ctx.log
        if not ctx.name:
            return
        log.step("Tearing down")
        if ctx.options.keep:
            log.info("  --keep: leaving everything in place")
            log.info(f"    local:  {ctx.project_path}")
            if ctx.created_repo:
                log.info(f"    GitHub: https://github.com/{ctx.created_repo}")
            return
        self._remove_local_folder()
        self._delete_remote_repo()

    def _remove_local_folder(self) -> None:
        ctx, log = self.ctx, self.ctx.log
        path = ctx.project_path
        if not path.exists():
            return
        if path.resolve().parent != ctx.paths.tmp.resolve() or not path.name.startswith(NAME_PREFIX):
            log.info(f"  ! refusing to delete {path}: not one of this run's folders in tmp/")
            ctx.teardown_ok = False
            return
        shutil.rmtree(path, ignore_errors=True)
        gone = not path.exists()
        log.info(f"  {'✓' if gone else '✗'} removed {path}")
        if not gone:
            log.info(f'    Remove it by hand:  rm -rf "{path}"')
        ctx.teardown_ok &= gone

    def _delete_remote_repo(self) -> None:
        ctx, log = self.ctx, self.ctx.log
        if not ctx.created_repo:
            return
        owner, _, name = ctx.created_repo.partition("/")
        if owner != ctx.login or not name.startswith(NAME_PREFIX):
            log.info(f"  ! refusing to delete {ctx.created_repo}: not a repo this harness creates")
            ctx.teardown_ok = False
            return
        manual = f"Delete it by hand:  gh repo delete {ctx.created_repo} --yes"
        try:
            ctx.gh.delete_repo(ctx.created_repo)
            still_there = ctx.gh.repo_exists(ctx.created_repo)
        except HarnessError as exc:
            log.info(f"  ✗ could not delete {ctx.created_repo}: {exc}\n    {manual}")
            ctx.teardown_ok = False
            return
        if still_there:
            log.info(f"  ✗ STILL EXISTS: {ctx.created_repo}\n    {manual}")
            ctx.teardown_ok = False
        else:
            log.info(f"  ✓ deleted {ctx.created_repo}")
