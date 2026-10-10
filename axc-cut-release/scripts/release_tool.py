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


def _run(cmd: list[str], label: str, cwd: Path | None = None) -> str:
    """Run cmd and return stdout; every failure becomes a ReleaseToolError."""
    try:
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, stdin=subprocess.DEVNULL
        )
    except FileNotFoundError:
        raise ReleaseToolError(f"{cmd[0]} is not installed or not on PATH")
    except UnicodeDecodeError as exc:
        raise ReleaseToolError(f"{label} produced non-UTF-8 output: {exc}")
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise ReleaseToolError(f"{label} failed: {detail}")
    return result.stdout


def git(args: list[str], repo_root: Path) -> str:
    return _run(["git", "-C", str(repo_root), *args], f"git {' '.join(args)}")


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
    bump_command = config["version"].get("bumpCommand")
    if bump_command is not None and (
        not isinstance(bump_command, str) or "{V}" not in bump_command
    ):
        raise ReleaseToolError(
            "config key 'version.bumpCommand' must be a string containing '{V}'"
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
BUMP_COMMAND_TIMEOUT = 300  # seconds


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


def gh(args: list[str], repo_root: Path) -> str:
    """Run `gh <args>` in repo_root. Kept separate from git() so tests can replace it."""
    return _run(["gh", *args], f"gh {' '.join(args)}", cwd=repo_root)


def _git_origin(args: list[str], repo_root: Path) -> str:
    """git() for commands that talk to `origin`, with a hint when it can't be reached."""
    try:
        return git(args, repo_root)
    except ReleaseToolError as exc:
        raise ReleaseToolError(
            f"{exc} (needs network access to the 'origin' remote)"
        ) from None


def format_tag(config: dict, v: str) -> str:
    return config["release"]["tagFormat"].replace("{V}", v)


def tag_status(repo_root: Path, tag: str) -> str:
    """One of: absent, local, remote, both."""
    local = bool(git(["tag", "-l", tag], repo_root).strip())
    ref = f"refs/tags/{tag}"
    # ls-remote patterns match on a trailing path, so compare the ref names exactly
    # (annotated tags also list a peeled `<ref>^{}` line).
    listed = _git_origin(["ls-remote", "--tags", "origin", ref], repo_root).splitlines()
    remote = any(
        line.split("\t")[-1] in (ref, f"{ref}^{{}}") for line in listed if "\t" in line
    )
    return {(False, False): "absent", (True, False): "local",
            (False, True): "remote", (True, True): "both"}[(local, remote)]


def _triple(v: str) -> tuple[int, ...]:
    return tuple(int(n) for n in v.split("-")[0].split("."))


def release_phase(repo_root: Path, config: dict, v: str) -> list[str]:
    main = config["mainBranch"]
    _git_origin(["fetch", "origin", main], repo_root)
    files = _version_files(config)
    on_main = [read_version(repo_root, vf, f"origin/{main}") for vf in files]
    matches = [found == v for found in on_main]
    if any(matches) and not all(matches):
        detail = ", ".join(f"{vf.path}={found}" for vf, found in zip(files, on_main))
        raise ReleaseToolError(
            f"{v} is on origin/{main} in some version files but not others ({detail})"
        )
    if not any(matches):
        newest = max(on_main, key=_triple)
        if _triple(v) < _triple(newest):
            raise ReleaseToolError(
                f"{v} is older than the version already on origin/{main} ({newest})"
            )
        lines = ["bump"]
        branch = config["commit"]["branch"].replace("{V}", v)
        number = gh(
            ["pr", "list", "--head", branch, "--state", "open",
             "--json", "number", "-q", ".[0].number"],
            repo_root,
        ).strip()
        if number.isdigit():
            lines.append(f"open-pr {number}")
        return lines
    # Per the spec, any existing tag (local, remote or both) counts as released.
    return ["tag" if tag_status(repo_root, format_tag(config, v)) == "absent" else "released"]


def check_workflow(repo_root: Path, config: dict) -> tuple[list[str], bool]:
    """Plain substring check of release.workflowChecks against release.workflow."""
    rel = _require_str(config, "release.workflow")
    checks = config["release"].get("workflowChecks", [])
    if not isinstance(checks, list) or not all(isinstance(c, str) and c for c in checks):
        raise ReleaseToolError(
            "config key 'release.workflowChecks' must be a list of non-empty strings"
        )
    path = repo_root / rel
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ReleaseToolError(f"workflow file not found: {rel}")
    except (OSError, UnicodeDecodeError) as exc:
        raise ReleaseToolError(f"cannot read workflow file {rel}: {exc}")
    lines = [
        f"✓ {c}" if c in text else f"✗ {c} (not found in {rel})" for c in checks
    ]
    return lines, all(c in text for c in checks)


def cmd_workflow_checks(args: argparse.Namespace, repo_root: Path, config: dict) -> int:
    lines, ok = check_workflow(repo_root, config)
    print("\n".join(lines) if lines else "no release.workflowChecks configured")
    return 0 if ok else 1


def cmd_tag_status(args: argparse.Namespace, repo_root: Path, config: dict) -> int:
    _require_semver(args.version)
    print(tag_status(repo_root, format_tag(config, args.version)))
    return 0


def cmd_phase(args: argparse.Namespace, repo_root: Path, config: dict) -> int:
    _require_semver(args.version)
    print("\n".join(release_phase(repo_root, config, args.version)))
    return 0


def _version_files(config: dict) -> list[VersionFile]:
    return [VersionFile(path=e["path"], match=e["match"]) for e in config["version"]["files"]]


def _require_semver(v: str) -> str:
    if not SEMVER_RE.fullmatch(v):
        raise ReleaseToolError(f"{v!r} is not an X.Y.Z[-prerelease] version")
    return v


def bump_files(repo_root: Path, files: list[VersionFile], v: str) -> None:
    """Rewrite only the version literal in every file; write nothing if any file fails."""
    _require_semver(v)
    originals: dict[Path, str] = {}
    updated: dict[Path, str] = {}
    for vf in files:
        path = repo_root / vf.path
        if path not in updated:
            try:
                # newline="" keeps CRLF files byte-for-byte apart from the literal.
                with open(path, newline="", encoding="utf-8") as fh:
                    originals[path] = updated[path] = fh.read()
            except OSError as exc:
                raise ReleaseToolError(f"cannot read {vf.path}: {exc}")
            except UnicodeDecodeError as exc:
                raise ReleaseToolError(f"{vf.path} is not valid UTF-8: {exc}")
        # Chain edits per path so two entries for one file both survive.
        found = version_regex(vf.match).search(updated[path])
        if not found:
            raise ReleaseToolError(f"{vf.path}: pattern {vf.match!r} did not match")
        start, end = found.span(1)
        updated[path] = updated[path][:start] + v + updated[path][end:]
    written: list[Path] = []
    try:
        for path, text in updated.items():
            with open(path, "w", newline="", encoding="utf-8") as fh:
                written.append(path)
                fh.write(text)
    except OSError as exc:
        for path in written:
            try:
                with open(path, "w", newline="", encoding="utf-8") as fh:
                    fh.write(originals[path])
            except OSError:
                pass
        raise ReleaseToolError(f"writing version files failed, changes rolled back: {exc}")


def check_versions(repo_root: Path, files: list[VersionFile], v: str) -> tuple[list[str], bool]:
    """Return report lines and whether every file equals v and all agree."""
    lines: list[str] = []
    found_values: list[str | None] = []
    for vf in files:
        try:
            found = read_version(repo_root, vf)
        except ReleaseToolError as exc:
            lines.append(f"✗ {vf.path} = (unreadable: {exc}) (expected {v})")
            found_values.append(None)
            continue
        found_values.append(found)
        lines.append(f"✓ {vf.path} = {found}" if found == v else f"✗ {vf.path} = {found} (expected {v})")
    distinct = {f for f in found_values if f is not None}
    if len(distinct) > 1:
        lines.append("✗ version files disagree: " + ", ".join(sorted(distinct)))
    ok = all(f == v for f in found_values) and len(distinct) <= 1
    return lines, ok


def cmd_bump(args: argparse.Namespace, repo_root: Path, config: dict) -> int:
    files = _version_files(config)
    command = config["version"].get("bumpCommand")
    if command is not None:
        _require_semver(args.version)
        try:
            result = subprocess.run(
                command.replace("{V}", args.version), shell=True, cwd=repo_root,
                capture_output=True, text=True, errors="replace",
                stdin=subprocess.DEVNULL, timeout=BUMP_COMMAND_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            raise ReleaseToolError(f"bumpCommand timed out after {BUMP_COMMAND_TIMEOUT}s")
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            raise ReleaseToolError(f"bumpCommand failed (exit {result.returncode}): {detail}")
        return _print_check(repo_root, files, args.version)
    bump_files(repo_root, files, args.version)
    return _print_check(repo_root, files, args.version)


def _print_check(repo_root: Path, files: list[VersionFile], v: str) -> int:
    lines, ok = check_versions(repo_root, files, v)
    print("\n".join(lines))
    return 0 if ok else 1


def cmd_check_versions(args: argparse.Namespace, repo_root: Path, config: dict) -> int:
    _require_semver(args.version)
    return _print_check(repo_root, _version_files(config), args.version)


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

    bump = sub.add_parser("bump", parents=[common], help="write V into every version file")
    bump.add_argument("version")
    bump.set_defaults(func=cmd_bump)

    check = sub.add_parser(
        "check-versions", parents=[common], help="verify every version file equals V"
    )
    check.add_argument("version")
    check.set_defaults(func=cmd_check_versions)

    tag = sub.add_parser("tag-status", parents=[common], help="absent|local|remote|both")
    tag.add_argument("version")
    tag.set_defaults(func=cmd_tag_status)

    phase = sub.add_parser("phase", parents=[common], help="bump|tag|released for V")
    phase.add_argument("version")
    phase.set_defaults(func=cmd_phase)

    wf = sub.add_parser(
        "workflow-checks", parents=[common], help="check release.workflowChecks against the workflow"
    )
    wf.set_defaults(func=cmd_workflow_checks)
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
