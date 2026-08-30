#!/usr/bin/env python3
"""
Create or update a GitHub label taxonomy on a repo from a JSON config file.

    python scripts/ensure_labels.py --repo <owner>/<repo> --labels-file labels/default.json

The labels file is a JSON list of objects, each with a "name", "color"
(hex, no leading "#") and "description" -- e.g.:

    [
      {"name": "epic", "color": "5319E7", "description": "A tracked body of work with child issues"}
    ]

Each entry becomes:

    gh label create <name> --repo <owner>/<repo> --color <color> --description <description> --force

--force makes this idempotent: re-running against a repo that already has
some or all of these labels just updates color/description in place rather
than failing on "label already exists".
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REQUIRED_FIELDS = ("name", "color", "description")


def run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd)}\n{result.stderr.strip()}")
    return result.stdout.strip()


def load_labels(labels_file: str) -> list[dict[str, str]]:
    path = Path(labels_file)
    try:
        raw = path.read_text()
    except OSError as exc:
        raise ValueError(f"couldn't read labels file {labels_file!r}: {exc}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{labels_file!r} is not valid JSON: {exc}") from exc

    if not isinstance(data, list):
        raise ValueError(f"{labels_file!r} must contain a JSON list of label objects, "
                          f"got {type(data).__name__}")

    for index, entry in enumerate(data):
        if not isinstance(entry, dict):
            raise ValueError(f"{labels_file!r} entry {index} must be an object, "
                              f"got {type(entry).__name__}")
        missing = [field for field in REQUIRED_FIELDS if field not in entry]
        if missing:
            raise ValueError(
                f"{labels_file!r} entry {index} ({entry!r}) is missing required "
                f"field(s): {', '.join(missing)}"
            )

    return data


def ensure_labels(owner: str, repo: str, labels: list[dict[str, str]]) -> None:
    for label in labels:
        run(["gh", "label", "create", label["name"], "--repo", f"{owner}/{repo}",
             "--color", label["color"], "--description", label["description"], "--force"])
    print(f"  labels: {len(labels)} ensured")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", required=True, help="owner/name, e.g. alvincrespo/pr-agent")
    parser.add_argument("--labels-file", required=True,
                         help="Path to a JSON file listing label objects "
                              "({name, color, description})")
    args = parser.parse_args()

    try:
        owner, repo = args.repo.split("/", 1)
    except ValueError:
        parser.error(f"--repo must be in owner/repo form, got {args.repo!r}")

    try:
        labels = load_labels(args.labels_file)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Ensuring labels on {owner}/{repo}...\n")
    ensure_labels(owner, repo, labels)


if __name__ == "__main__":
    main()
