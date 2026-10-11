"""Git operations on the throwaway project."""

from __future__ import annotations

from pathlib import Path

from . import shell


class GitRepo:
    def __init__(self, path: Path) -> None:
        self.path = path

    def git(self, *args: str, check: bool = True) -> str:
        return shell.run(["git", *args], cwd=self.path, check=check).strip()

    def init(self, branch: str = "main") -> None:
        self.git("init", "-q", "-b", branch)
        if not self.git("config", "user.email", check=False):
            self.git("config", "user.email", "e2e@example.invalid")
            self.git("config", "user.name", "axc-cut-release e2e")

    def add_remote(self, url: str) -> None:
        self.git("remote", "add", "origin", url)

    def exclude(self, pattern: str) -> None:
        """Ignore `pattern` for this clone only (not committed)."""
        with open(self.path / ".git" / "info" / "exclude", "a", encoding="utf-8") as fh:
            fh.write(pattern + "\n")

    def commit_all(self, message: str) -> None:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)

    def push(self, *args: str) -> None:
        self.git("push", "-q", *args)

    def head(self) -> str:
        return self.git("rev-parse", "HEAD")

    def remote_refs(self, *patterns: str) -> dict[str, str]:
        """`git ls-remote origin <patterns>` as {ref: sha}. Annotated tags also list `<ref>^{}`."""
        refs: dict[str, str] = {}
        for line in self.git("ls-remote", "origin", *patterns).splitlines():
            sha, _, ref = line.partition("\t")
            refs[ref] = sha
        return refs

    def remote_head(self, branch: str = "main") -> str | None:
        return self.remote_refs(f"refs/heads/{branch}").get(f"refs/heads/{branch}")

    def remote_tag_message(self, tag: str) -> str | None:
        """The subject of the *remote's* tag object, or None if the remote has no such tag.

        Fetched into a scratch ref so a tag that exists only in this clone can't satisfy it.
        """
        scratch = f"refs/e2e/{tag}"
        if not shell.succeeds(["git", "fetch", "-q", "origin", f"+refs/tags/{tag}:{scratch}"],
                              cwd=self.path):
            return None
        return self.git("for-each-ref", "--format=%(contents:subject)", scratch)
