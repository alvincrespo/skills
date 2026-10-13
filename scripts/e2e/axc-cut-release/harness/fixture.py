"""What goes into the throwaway project."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from .config import BASE_VERSION, SKILLS


def write_fixture(project: Path, full_name: str) -> None:
    """A tiny project the release skills can drive: a VERSION file and a release.json.

    The "release workflow" lives at ci/release.yml, outside .github/, so pushing a tag runs
    nothing on GitHub (and no `workflow` token scope is needed). The release skills only
    read that file; they never need it to run.
    """
    (project / "VERSION").write_text(f"{BASE_VERSION}\n")
    (project / "ci").mkdir(exist_ok=True)
    (project / "ci" / "release.yml").write_text(
        'on:\n  push:\n    tags: ["v*"]\npermissions:\n  contents: write\n'
    )
    config = {
        "repo": full_name,
        "mainBranch": "main",
        "version": {"files": [{"path": "VERSION", "match": "{V}"}]},
        "commit": {"branch": "release/v{V}", "title": "release: v{V}"},
        "checks": {"test": "test -f VERSION"},
        "release": {
            "tagFormat": "v{V}",
            "artifact": "github-release",
            "workflow": "ci/release.yml",
            "workflowChecks": ["contents: write", 'tags: ["v*"]'],
        },
    }
    (project / ".claude").mkdir(exist_ok=True)
    (project / ".claude" / "release.json").write_text(json.dumps(config, indent=2) + "\n")


def install_skills(repo_root: Path, project: Path) -> None:
    """Copy the skills under .claude/skills/ so the project's own Claude session finds them."""
    dest = project / ".claude" / "skills"
    dest.mkdir(parents=True, exist_ok=True)
    for skill in SKILLS:
        shutil.copytree(
            repo_root / skill, dest / skill,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "node_modules"),
        )
