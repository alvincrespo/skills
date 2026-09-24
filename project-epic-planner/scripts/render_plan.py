#!/usr/bin/env python3
"""
Validate a plan JSON file and render it as a reviewable markdown document.

    python3 <path-to>/project-epic-planner/scripts/render_plan.py \
        --data plan.json [--out plan.md] [--labels-file path/to/labels.json]

The plan JSON is the exact file github-project-bootstrap consumes via
--data (schema: github-project-bootstrap/references/epic-schema.md). The
markdown is derived from it and never edited by hand: change the JSON,
re-run this script. That way the document a human reviews is guaranteed
to match what bootstrap would create.

Validation, in order -- any failure prints the problem and exits 1
without writing the markdown:
  1. Shape and depends_on ordering, via github-project-bootstrap's own
     load_data(), so this check can't drift from what bootstrap enforces.
  2. Every issue title (epics, stories, release validation) is unique.
     Bootstrap looks up existing issues by exact title, so a duplicate
     would be silently reused instead of created.
  3. Every label used -- including the `epic`/`task` label bootstrap adds
     to every epic/story itself -- exists in the labels file (default:
     github-labels-setup/labels/default.json). An unknown label makes
     `gh issue create` fail partway through a live bootstrap run.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

SKILLS_ROOT = Path(__file__).parent.parent.parent
BOOTSTRAP_SCRIPTS_DIR = SKILLS_ROOT / "github-project-bootstrap" / "scripts"
DEFAULT_LABELS_FILE = SKILLS_ROOT / "github-labels-setup" / "labels" / "default.json"

sys.path.insert(0, str(BOOTSTRAP_SCRIPTS_DIR))
from bootstrap_github_project import load_data  # noqa: E402


def _all_issues(plan: dict) -> list[tuple[dict, str | None]]:
    """Every issue bootstrap would create, paired with the label it adds itself."""
    issues: list[tuple[dict, str | None]] = []
    for epic in plan["epics"]:
        issues.append((epic, "epic"))
        issues.extend((story, "task") for story in epic["issues"])
    issues.append((plan["release_validation_issue"], None))
    return issues


def check_plan(plan: dict, label_names: set[str]) -> list[str]:
    """Checks load_data() doesn't cover. Returns a list of problems (empty = ok)."""
    # load_data() checks that titles and labels exist, not their types; the
    # checks below assume strings, so report bad types first and stop there.
    problems: list[str] = []
    for issue, _ in _all_issues(plan):
        if not isinstance(issue["title"], str):
            problems.append(f"title must be a string, got {issue['title']!r}")
        elif not all(isinstance(label, str) for label in issue.get("labels", [])):
            problems.append(f"{issue['title']!r} labels must all be strings: {issue['labels']!r}")
    if problems:
        return problems

    counts = Counter(issue["title"] for issue, _ in _all_issues(plan))
    for title, count in counts.items():
        if count > 1:
            problems.append(f"duplicate issue title ({count}x): {title!r}")

    # Includes the epic/task label bootstrap adds on its own: a labels file
    # without them passes every explicit label and still fails the first
    # `gh issue create`.
    for issue, implicit in _all_issues(plan):
        labels = ([implicit] if implicit else []) + issue.get("labels", [])
        unknown = [label for label in labels if label not in label_names]
        if unknown:
            problems.append(
                f"{issue['title']!r} uses label(s) not in the labels file: {', '.join(unknown)}"
            )

    return problems


_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_HEADING = re.compile(r"^( {0,3})(#{1,6})(?=\s|$)")


def _nest(body: str, parent_level: int) -> str:
    """Shift a body's markdown headings so the shallowest sits one level below parent_level.

    Ticket bodies are written to stand alone as GitHub issues, so they may use
    `##` headings. Rendered under a `####` story heading, those would flatten
    the document's outline. Lines inside fenced code blocks are never touched
    (a Ruby or shell comment is not a heading). Levels are capped at 6.
    """
    lines = body.split("\n")
    fence = None
    heading_rows: list[tuple[int, re.Match]] = []
    for i, line in enumerate(lines):
        m = _FENCE.match(line)
        if m:
            marker = m.group(1)
            if fence is None:
                fence = marker
            elif (marker[0] == fence[0] and len(marker) >= len(fence)
                  and not line[m.end():].strip()):
                # A closing fence can't carry an info string (CommonMark), so
                # a ```ruby line inside a plain ``` block is content, not a close.
                fence = None
            continue
        if fence is None and (h := _HEADING.match(line)):
            heading_rows.append((i, h))
    if not heading_rows:
        return body
    shift = parent_level + 1 - min(len(h.group(2)) for _, h in heading_rows)
    if shift <= 0:
        return body
    for i, h in heading_rows:
        level = min(len(h.group(2)) + shift, 6)
        lines[i] = h.group(1) + "#" * level + lines[i][h.end():]
    return "\n".join(lines)


def _cell(text: str) -> str:
    return text.replace("|", "\\|")


def _labels(always: str | None, extra: list[str]) -> str:
    names = ([always] if always else []) + extra
    return ", ".join(f"`{name}`" for name in names) or "—"


def render(plan: dict) -> str:
    lines: list[str] = []
    w = lines.append
    epics = plan["epics"]
    milestone = plan["milestone"]
    rv = plan["release_validation_issue"]
    story_count = sum(len(epic["issues"]) for epic in epics)

    w("<!-- Generated by project-epic-planner/scripts/render_plan.py from the plan JSON.")
    w("     Edit the JSON and re-run the script — don't edit this file directly. -->")
    w("")
    w(f"# {milestone['title']}")
    w("")
    w(f"{len(epics)} epics, {story_count} stories, 1 release-validation issue — "
      f"{len(epics) + story_count + 1} issues in total.")
    w("")
    w(f"> {milestone['description']}")
    w("")
    w("## Dependency graph")
    w("")
    w("| # | Epic | Blocked by | Stories |")
    w("|---|---|---|---|")
    for i, epic in enumerate(epics, start=1):
        blocked_by = ", ".join(epic.get("depends_on", [])) or "—"
        w(f"| {i} | {_cell(epic['title'])} | {_cell(blocked_by)} | {len(epic['issues'])} |")
    w(f"| — | {_cell(rv['title'])} | every epic | — |")
    w("")
    w("---")
    w("")

    for i, epic in enumerate(epics, start=1):
        w(f"## {i}. {epic['title']}")
        w("")
        w(f"**Labels:** {_labels('epic', epic.get('labels', []))}  ")
        w(f"**Blocked by:** {', '.join(epic.get('depends_on', [])) or '—'}")
        w("")
        w(_nest(epic["body"], 2))
        w("")
        # Stories get their own section so they don't land under the epic
        # body's last heading in the document outline.
        w(f"### Stories in this epic ({len(epic['issues'])})")
        w("")
        for j, story in enumerate(epic["issues"], start=1):
            w(f"#### {i}.{j} {story['title']}")
            w("")
            w(f"**Labels:** {_labels('task', story.get('labels', []))}")
            w("")
            w(_nest(story["body"], 4))
            w("")
        w("---")
        w("")

    rv_heading = rv["title"]
    if not rv_heading.lower().startswith("release validation"):
        rv_heading = f"Release validation: {rv_heading}"
    w(f"## {rv_heading}")
    w("")
    w(f"**Labels:** {_labels(None, rv.get('labels', []))}  ")
    w("**Blocked by:** every epic above")
    w("")
    w(_nest(rv["body"], 2))
    w("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--data", required=True, help="Path to the plan JSON file.")
    parser.add_argument("--out", help="Write the markdown here instead of stdout.")
    parser.add_argument("--labels-file",
                        help="Labels JSON the plan's labels must come from. Defaults to "
                             "github-labels-setup/labels/default.json.")
    args = parser.parse_args()

    labels_file = Path(args.labels_file) if args.labels_file else DEFAULT_LABELS_FILE
    try:
        plan = load_data(args.data)
        label_names = {label["name"] for label in json.loads(labels_file.read_text())}
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    problems = check_plan(plan, label_names)
    if problems:
        print(f"Error: {args.data!r} failed validation:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        sys.exit(1)

    markdown = render(plan)
    if args.out:
        Path(args.out).write_text(markdown + "\n")
        print(f"Wrote {args.out}")
    else:
        print(markdown)


if __name__ == "__main__":
    main()
