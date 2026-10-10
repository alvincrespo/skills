#!/usr/bin/env python3
"""
Deterministic helpers for the release skills.

    python3 axc-cut-release/scripts/release_tool.py <subcommand> [args]
        [--config PATH] [--repo-root PATH]

Exit codes: 0 success, 1 a check failed, 2 bad input or config.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


class ReleaseToolError(Exception):
    """Bad input, bad config, or a failed git command."""


@dataclass(frozen=True)
class VersionFile:
    path: str   # relative to repo_root
    match: str  # contains exactly one "{V}"


def git(args: list[str], repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            text=True,
        )
    except UnicodeDecodeError as exc:
        raise ReleaseToolError(f"git {' '.join(args)} produced non-UTF-8 output: {exc}")
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise ReleaseToolError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout


def _require(config: dict, dotted: str):
    node = config
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            raise ReleaseToolError(f"config is missing required key '{dotted}'")
        node = node[part]
    return node


def _require_str(config: dict, dotted: str) -> str:
    value = _require(config, dotted)
    if not isinstance(value, str) or not value:
        raise ReleaseToolError(f"config key '{dotted}' must be a non-empty string")
    return value


def load_config(path: Path) -> dict:
    try:
        config = json.loads(path.read_text())
    except FileNotFoundError:
        raise ReleaseToolError(f"config not found: {path}")
    except UnicodeDecodeError as exc:
        raise ReleaseToolError(f"config {path} is not valid UTF-8: {exc}")
    except json.JSONDecodeError as exc:
        raise ReleaseToolError(f"config {path} is not valid JSON: {exc}")
    if not isinstance(config, dict):
        raise ReleaseToolError(f"config {path} must be a JSON object")

    _require_str(config, "mainBranch")
    files = _require(config, "version.files")
    if not isinstance(files, list) or not files:
        raise ReleaseToolError("config key 'version.files' must be a non-empty list")
    for i, entry in enumerate(files):
        for key in ("path", "match"):
            if not isinstance(entry, dict) or key not in entry:
                raise ReleaseToolError(
                    f"config is missing required key 'version.files[{i}].{key}'"
                )
            if not isinstance(entry[key], str) or not entry[key]:
                raise ReleaseToolError(
                    f"config key 'version.files[{i}].{key}' must be a non-empty string"
                )
    _require_str(config, "commit.branch")
    _require_str(config, "release.tagFormat")
    return config


def version_regex(match: str) -> re.Pattern:
    if match.count("{V}") != 1:
        raise ReleaseToolError(f"match {match!r} must contain exactly one '{{V}}'")
    pattern = re.escape(match).replace(
        re.escape("{V}"), r"(\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)"
    )
    return re.compile(pattern)


def read_version(repo_root: Path, vf: VersionFile, ref: str | None = None) -> str:
    if ref is None:
        try:
            text = (repo_root / vf.path).read_text()
        except OSError as exc:
            raise ReleaseToolError(f"cannot read {vf.path}: {exc}")
        except UnicodeDecodeError as exc:
            raise ReleaseToolError(f"{vf.path} is not valid UTF-8: {exc}")
        source = vf.path
    else:
        text = git(["show", f"{ref}:{vf.path}"], repo_root)
        source = f"{vf.path} at {ref}"
    found = version_regex(vf.match).search(text)
    if not found:
        raise ReleaseToolError(f"{source}: pattern {vf.match!r} did not match")
    return found.group(1)


_NUM = r"(?:0|[1-9]\d*)"
_PRE_ID = r"[0-9A-Za-z-]+"
SEMVER_RE = re.compile(rf"{_NUM}\.{_NUM}\.{_NUM}(?:-{_PRE_ID}(?:\.{_PRE_ID})*)?")
KEYWORDS = ("patch", "minor", "major")


def next_version(cur: str, arg: str | None) -> str:
    if arg is not None and arg not in KEYWORDS:
        if not SEMVER_RE.fullmatch(arg):
            raise ReleaseToolError(
                f"{arg!r} is not a bump keyword (patch, minor, major) "
                "or an explicit X.Y.Z[-prerelease] version"
            )
        return arg
    if not SEMVER_RE.fullmatch(cur):
        raise ReleaseToolError(f"current version {cur!r} is not X.Y.Z[-prerelease]")
    if "-" in cur:
        raise ReleaseToolError(
            f"current version {cur} has a prerelease suffix, so a bump is ambiguous; "
            "pass an explicit version instead"
        )
    x, y, z = (int(n) for n in cur.split("."))
    bump = arg or "patch"
    if bump == "major":
        return f"{x + 1}.0.0"
    if bump == "minor":
        return f"{x}.{y + 1}.0"
    return f"{x}.{y}.{z + 1}"


def cmd_next(args: argparse.Namespace, repo_root: Path, config: dict) -> int:
    entry = config["version"]["files"][0]
    vf = VersionFile(path=entry["path"], match=entry["match"])
    if args.arg is not None and args.arg not in KEYWORDS:
        # An explicit version doesn't depend on the current one, so don't touch git.
        print(next_version("", args.arg))
        return 0
    ref = args.ref or f"origin/{config['mainBranch']}"
    print(next_version(read_version(repo_root, vf, ref), args.arg))
    return 0


def cmd_current(args: argparse.Namespace, repo_root: Path, config: dict) -> int:
    entry = config["version"]["files"][0]
    vf = VersionFile(path=entry["path"], match=entry["match"])
    print(read_version(repo_root, vf, args.ref))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--repo-root", type=Path, default=None)
    common.add_argument("--config", type=Path, default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    current = sub.add_parser("current", parents=[common], help="print the current version")
    current.add_argument("--ref", default=None, help="read from this git ref")
    current.set_defaults(func=cmd_current)

    nxt = sub.add_parser("next", parents=[common], help="print the next version")
    nxt.add_argument("arg", nargs="?", default=None, help="patch|minor|major|X.Y.Z")
    nxt.add_argument("--ref", default=None, help="read from this ref (default origin/<mainBranch>)")
    nxt.set_defaults(func=cmd_next)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = (args.repo_root or Path.cwd()).resolve()
    config_path = args.config or repo_root / ".claude" / "release.json"
    try:
        config = load_config(config_path)
        return args.func(args, repo_root, config)
    except ReleaseToolError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
