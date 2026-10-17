#!/usr/bin/env python3
"""
Load, validate and propose .claude/dependabot-sweep.json.

Usage:
    config.py [--repo-dir DIR]            print the resolved config as JSON
    config.py [--repo-dir DIR] --write    also write a proposed config (only
                                          when the file is missing)

If the file exists it is validated and merged over the defaults. If it is
missing, a config is proposed from the lockfiles in the repo and printed with
"proposed": true; nothing is written unless --write is passed, and the skill
passes --write only after the user confirms the proposal.

Exit codes: 0 ok, 1 invalid config or nothing to propose.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

CONFIG_PATH = Path(".claude") / "dependabot-sweep.json"

DEFAULTS: dict[str, Any] = {
    "authors": ["app/dependabot"],
    "verify": None,
    "merge_method": None,
    "timeouts": {"rebase_minutes": 15, "ci_minutes": 20},
    "review_level": "medium",
}

MERGE_METHODS = ("squash", "merge", "rebase")
REVIEW_LEVELS = ("low", "medium", "high", "xhigh", "max")


class ConfigError(ValueError):
    pass


def _positive_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def validate(config: dict[str, Any], require_verify: bool = True) -> dict[str, Any]:
    """Merge `config` over DEFAULTS and validate. Returns the resolved config."""
    if not isinstance(config, dict):
        raise ConfigError("config must be a JSON object")
    unknown = sorted(set(config) - set(DEFAULTS))
    if unknown:
        raise ConfigError(f"unknown config keys: {', '.join(unknown)}")

    resolved = json.loads(json.dumps(DEFAULTS))
    for key, value in config.items():
        if key == "timeouts":
            if not isinstance(value, dict):
                raise ConfigError("timeouts must be an object")
            bad = sorted(set(value) - set(DEFAULTS["timeouts"]))
            if bad:
                raise ConfigError(f"unknown timeouts keys: {', '.join(bad)}")
            resolved["timeouts"].update(value)
        else:
            resolved[key] = value

    authors = resolved["authors"]
    if (not isinstance(authors, list) or not authors
            or not all(isinstance(a, str) and a.strip() for a in authors)):
        raise ConfigError("authors must be a non-empty list of non-empty strings")

    verify = resolved["verify"]
    if verify is None:
        if require_verify:
            raise ConfigError("verify is required: the command that proves a bump is safe")
    elif not isinstance(verify, str) or not verify.strip():
        raise ConfigError("verify must be a non-empty string")

    if resolved["merge_method"] is not None and resolved["merge_method"] not in MERGE_METHODS:
        raise ConfigError(f"merge_method must be null or one of {', '.join(MERGE_METHODS)}")

    for name, value in resolved["timeouts"].items():
        if not _positive_number(value):
            raise ConfigError(f"timeouts.{name} must be a positive number")

    if resolved["review_level"] not in REVIEW_LEVELS:
        raise ConfigError(f"review_level must be one of {', '.join(REVIEW_LEVELS)}")

    return resolved


def load_config(repo_dir: Path) -> dict[str, Any]:
    """Read and validate <repo_dir>/.claude/dependabot-sweep.json."""
    path = repo_dir / CONFIG_PATH
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise ConfigError(f"{path} is not valid JSON: {e}") from e
    return validate(raw)


def _package_scripts(repo_dir: Path) -> set[str]:
    try:
        data = json.loads((repo_dir / "package.json").read_text())
    except (OSError, json.JSONDecodeError):
        return set()
    scripts = data.get("scripts") if isinstance(data, dict) else None
    return set(scripts) if isinstance(scripts, dict) else set()


def _node_verify(repo_dir: Path, tool: str, install: str) -> str:
    # yarn isn't always on PATH (the website run needed `npx -y yarn@1`).
    runner = tool
    if tool == "yarn" and shutil.which("yarn") is None:
        runner = "npx -y yarn@1"
    steps = [f"{runner} {install}"]
    scripts = _package_scripts(repo_dir)
    for script in ("build", "test"):
        if script in scripts:
            steps.append(f"{runner} run {script}")
    return " && ".join(steps)


# (lockfile, manager, verify builder)
_DETECTORS = (
    ("yarn.lock", "yarn", lambda d: _node_verify(d, "yarn", "install --frozen-lockfile")),
    ("package-lock.json", "npm", lambda d: _node_verify(d, "npm", "ci")),
    ("pnpm-lock.yaml", "pnpm", lambda d: _node_verify(d, "pnpm", "install --frozen-lockfile")),
    ("Gemfile.lock", "bundler", lambda d: "bundle install"),
    ("uv.lock", "uv", lambda d: "uv sync --frozen"),
    ("poetry.lock", "poetry", lambda d: "poetry install"),
)


def detect_package_managers(repo_dir: Path) -> list[str]:
    return [name for lock, name, _ in _DETECTORS if (repo_dir / lock).exists()]


def propose_config(repo_dir: Path) -> dict[str, Any]:
    """Propose a config from the lockfiles. `verify` is None if none are found."""
    steps = [build(repo_dir) for lock, _, build in _DETECTORS if (repo_dir / lock).exists()]
    proposal = json.loads(json.dumps(DEFAULTS))
    proposal["verify"] = " && ".join(steps) if steps else None
    return proposal


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo-dir", default=".", help="repo root (default: cwd)")
    parser.add_argument("--write", action="store_true",
                        help="write the proposed config when the file is missing")
    args = parser.parse_args()

    repo_dir = Path(args.repo_dir)
    path = repo_dir / CONFIG_PATH
    try:
        if path.exists():
            print(json.dumps({"proposed": False, "path": str(path), "config": load_config(repo_dir)},
                             indent=2))
            return
        proposal = propose_config(repo_dir)
        if proposal["verify"] is None:
            print(f"error: {path} is missing and no known lockfile was found to propose a "
                  "`verify` command from; create the file by hand", file=sys.stderr)
            sys.exit(1)
        validate(proposal)
        if args.write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(proposal, indent=2) + "\n")
        print(json.dumps({"proposed": True, "written": args.write, "path": str(path),
                          "detected": detect_package_managers(repo_dir), "config": proposal},
                         indent=2))
    except ConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
