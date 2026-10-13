"""A thin client over `gh api`. REST only: `gh repo create` / `gh pr merge` use GraphQL."""

from __future__ import annotations

import json
import re
from typing import Any

from . import shell
from .errors import HarnessError


class GitHub:
    def api(self, path: str, method: str = "GET", fields: tuple[str, ...] = (),
            raw: bool = False) -> Any:
        """Call the REST API. `fields` are `gh` flags such as ("-f", "name=x", "-F", "private=true")."""
        cmd = ["gh", "api", "-X", method]
        if raw:
            cmd += ["-H", "Accept: application/vnd.github.raw+json"]
        cmd += [*fields, path]
        out = shell.run(cmd)
        if raw:
            return out
        return json.loads(out) if out.strip() else None

    # --- account -------------------------------------------------------------------

    def login(self) -> str:
        try:
            return shell.run(["gh", "api", "user", "-q", ".login"]).strip()
        except HarnessError as exc:
            raise HarnessError(f"gh is not logged in ({exc}). Run `gh auth login`.") from None

    def token_scopes(self) -> set[str] | None:
        """The token's OAuth scopes, or None if GitHub doesn't report them (fine-grained tokens)."""
        headers = shell.run(["gh", "api", "-i", "user"], check=False)
        match = re.search(r"(?im)^x-oauth-scopes:\s*(.*)$", headers)
        if not match:
            return None
        return {s.strip() for s in match.group(1).split(",") if s.strip()}

    # --- repository ----------------------------------------------------------------

    def create_private_repo(self, name: str, description: str) -> None:
        self.api("user/repos", "POST",
                 ("-f", f"name={name}", "-F", "private=true", "-f", f"description={description}"))

    def delete_repo(self, full_name: str) -> None:
        self.api(f"repos/{full_name}", "DELETE")

    def repo_exists(self, full_name: str) -> bool:
        return shell.succeeds(["gh", "api", f"repos/{full_name}"])

    # --- reads used by the checks --------------------------------------------------

    def open_prs(self, full_name: str, owner: str, branch: str) -> list[dict]:
        return self.api(f"repos/{full_name}/pulls?state=open&head={owner}:{branch}") or []

    def compare(self, full_name: str, base: str, head: str) -> dict:
        return self.api(f"repos/{full_name}/compare/{base}...{head}")

    def file_text(self, full_name: str, path: str, ref: str) -> str:
        return self.api(f"repos/{full_name}/contents/{path}?ref={ref}", raw=True).strip()

    def commits(self, full_name: str, branch: str) -> list[dict]:
        return self.api(f"repos/{full_name}/commits?sha={branch}&per_page=100") or []

    # --- the one write the scenario does -------------------------------------------

    def squash_merge(self, full_name: str, number: int) -> dict:
        return self.api(f"repos/{full_name}/pulls/{number}/merge", "PUT",
                        ("-f", "merge_method=squash")) or {}
