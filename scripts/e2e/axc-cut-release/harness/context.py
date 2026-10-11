"""State shared by the stages of one run."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .config import Options, Paths
from .github import GitHub
from .log import Logger
from .report import Report


@dataclass
class RunContext:
    options: Options
    paths: Paths
    log: Logger
    report: Report
    gh: GitHub
    login: str = ""                     # set by preflight
    name: str = ""                      # set by the sandbox
    created_repo: str | None = None     # "owner/name"; set only once GitHub confirms it exists
    session_costs: dict[str, float] = field(default_factory=dict)
    tool_errors: dict[str, tuple[str, ...]] = field(default_factory=dict)
    aborted: str = ""                   # why the run stopped early, if it did
    teardown_ok: bool = True

    @property
    def full_name(self) -> str:
        return f"{self.login}/{self.name}"

    @property
    def project_path(self) -> Path:
        return self.paths.tmp / self.name

    @property
    def logs_dir(self) -> Path:
        return self.paths.log_root / self.name
