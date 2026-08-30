#!/usr/bin/env python3
"""
Bootstrap a GitHub repo + Project (v2) from a --data JSON file.

    gh auth login
    gh auth refresh -s project      # project scope isn't in gh's default scopes
    gh repo create <owner>/pr-agent --private --clone
    cd pr-agent
    python scripts/bootstrap_github_project.py --repo <owner>/pr-agent --data plan.json \
        [--labels-file path/to/labels.json]

The --data file is a JSON object with three top-level keys:

    {
      "milestone": {"title": "...", "description": "..."},
      "epics": [
        {
          "title": "Epic: ...", "labels": [...], "depends_on": ["Epic: ..."],
          "body": "...",
          "issues": [{"title": "...", "labels": [...], "body": "..."}]
        }
      ],
      "release_validation_issue": {"title": "...", "labels": [...], "body": "..."}
    }

"depends_on" entries must name an epic defined earlier in "epics" -- the
list is read in order, and each dependency is expected to already exist by
the time it's referenced (see step 4 below).

What it does, in order:
  1. Creates (or updates, via --force) a small set of labels, by shelling
     out to github-labels-setup/scripts/ensure_labels.py with the file
     given via --labels-file (or that skill's own labels/default.json if
     --labels-file is omitted) -- this script owns no label taxonomy data
     of its own.
  2. Creates the milestone named in "milestone", or reuses it if a
     milestone with that title already exists.
  3. Creates (or reuses) a GitHub Project (v2) named after --project-title,
     defaulting to the repo's own name if not given -- never hardcode a
     specific title as the default here; a repo-agnostic default is the
     whole reason this script works safely across more than one repo, and
     a hardcoded one already caused two different repos' issues to land in
     the same project board once. Links it to this repository so it shows
     up under the repo's own Projects tab -- Projects (v2) are
     account-level, not repo-level, so creating one and adding issues to
     it does NOT do this automatically.
  4. For each epic in "epics", in list order: creates the epic as an issue
     labeled "epic", links it as blocked-by whatever its "depends_on" list
     names (each dependency is guaranteed to already exist, since "epics"
     is expected to be ordered so nothing depends on a later epic), then
     creates each of its child issues linked to it via GitHub's sub-issue
     relationship (`gh issue create --parent`).
  5. Creates the standalone release-validation issue, linked as blocked-by
     every epic.
  6. Adds every issue created to the Project board.

Step 4's epic-to-epic blocked-by links are what make the dependency
ordering encoded in the --data file's "depends_on" fields show up as real,
visible blocks on the epic issues themselves — not just an ordering
convention someone has to remember from a doc.

Idempotency: labels use --force, so re-running is safe. Milestones and the
project are looked up by title/name first. Issues are looked up by exact
title before creating, so a second run mostly no-ops instead of
duplicating — but it's still meant as a one-time bootstrap, not a sync tool
you run on every edit to the --data file. If you change scope later, edit
or close issues by hand for anything that already exists.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd)}\n{result.stderr.strip()}")
    return result.stdout.strip()


REQUIRED_TOP_LEVEL_KEYS = ("milestone", "epics", "release_validation_issue")


def _require_dict(data_file: str, where: str, value: object) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{data_file!r}: {where} must be an object, got {type(value).__name__}")
    return value


def _require_list(data_file: str, where: str, value: object) -> list:
    if not isinstance(value, list):
        raise ValueError(f"{data_file!r}: {where} must be a list, got {type(value).__name__}")
    return value


def _require_fields(data_file: str, where: str, obj: dict, fields: tuple[str, ...]) -> None:
    missing = [field for field in fields if field not in obj]
    if missing:
        raise ValueError(f"{data_file!r}: {where} is missing required field(s): "
                          f"{', '.join(missing)}")


def _validate_milestone(data_file: str, milestone: object) -> None:
    milestone = _require_dict(data_file, '"milestone"', milestone)
    _require_fields(data_file, '"milestone"', milestone, ("title", "description"))


def _validate_issue_entry(data_file: str, where: str, issue: object,
                           fields: tuple[str, ...]) -> None:
    issue = _require_dict(data_file, where, issue)
    _require_fields(data_file, where, issue, fields)
    if "labels" in issue:
        _require_list(data_file, f"{where} \"labels\"", issue["labels"])


def _validate_epics(data_file: str, epics: object) -> None:
    epics = _require_list(data_file, '"epics"', epics)
    seen_titles: set[str] = set()
    for index, epic in enumerate(epics):
        where = f'"epics[{index}]"'
        epic = _require_dict(data_file, where, epic)
        _require_fields(data_file, where, epic, ("title", "body", "issues"))
        if "labels" in epic:
            _require_list(data_file, f"{where} \"labels\"", epic["labels"])
        if "depends_on" in epic:
            depends_on = _require_list(data_file, f"{where} \"depends_on\"", epic["depends_on"])
            unknown = [name for name in depends_on if name not in seen_titles]
            if unknown:
                raise ValueError(
                    f"{data_file!r}: {where} \"depends_on\" references epic(s) not defined "
                    f"earlier in \"epics\": {', '.join(unknown)}"
                )
        issues = _require_list(data_file, f"{where} \"issues\"", epic["issues"])
        for issue_index, issue in enumerate(issues):
            _validate_issue_entry(data_file, f"{where}.issues[{issue_index}]", issue,
                                   ("title", "body"))
        seen_titles.add(epic["title"])


def load_data(data_file: str) -> dict:
    path = Path(data_file)
    try:
        raw = path.read_text()
    except OSError as exc:
        raise ValueError(f"couldn't read data file {data_file!r}: {exc}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{data_file!r} is not valid JSON: {exc}") from exc

    data = _require_dict(data_file, "top level", data)
    _require_fields(data_file, "top level", data, REQUIRED_TOP_LEVEL_KEYS)

    _validate_milestone(data_file, data["milestone"])
    _validate_epics(data_file, data["epics"])
    _validate_issue_entry(data_file, '"release_validation_issue"',
                           data["release_validation_issue"], ("title", "body", "labels"))

    return data


ENSURE_LABELS_SCRIPT = Path(__file__).parent.parent / "github-labels-setup" / "scripts" / "ensure_labels.py"
DEFAULT_LABELS_FILE = Path(__file__).parent.parent / "github-labels-setup" / "labels" / "default.json"


def ensure_labels(owner: str, repo: str, labels_file: Path) -> None:
    # Label taxonomy data (names/colors/descriptions) lives in exactly one
    # place: github-labels-setup/labels/default.json (or whatever file
    # --labels-file points at), owned and applied by that skill's own
    # ensure_labels.py. This just shells out to it rather than duplicating
    # any of that data here.
    run([sys.executable, str(ENSURE_LABELS_SCRIPT),
         "--repo", f"{owner}/{repo}", "--labels-file", str(labels_file)])
    print(f"  labels: ensured from {labels_file}")


def ensure_milestone(owner: str, repo: str, title: str, description: str) -> int:
    # GitHub's milestones API takes state=open or state=closed individually —
    # state=all is not accepted. Query both and merge, since an existing
    # milestone we'd want to reuse could be in either state.
    #
    # --method GET is explicit and load-bearing here, not decorative: gh api
    # defaults to POST whenever -f/--field flags are present (its logic is
    # "there's field data, so this must be a write"), which silently turned
    # this into an attempted milestone CREATE with no title — hence the
    # confusing '"title" wasn\'t supplied' error on what looked like a plain
    # list call. Passing -f query parameters on a GET always needs an
    # explicit --method GET to override that default.
    existing = []
    for state in ("open", "closed"):
        results = json.loads(run([
            "gh", "api", "--method", "GET", f"repos/{owner}/{repo}/milestones",
            "--paginate", "-f", f"state={state}",
        ]) or "[]")
        existing.extend(results)
    for m in existing:
        if m["title"] == title:
            print(f"  milestone: reused #{m['number']} \"{title}\"")
            return m["number"]
    created = json.loads(run([
        "gh", "api", "--method", "POST", f"repos/{owner}/{repo}/milestones",
        "-f", f"title={title}", "-f", f"description={description}",
    ]))
    print(f"  milestone: created #{created['number']} \"{title}\"")
    return created["number"]


def ensure_project(owner: str, title: str) -> int:
    existing = json.loads(run(["gh", "project", "list", "--owner", owner, "--format", "json"]))
    for p in existing.get("projects", []):
        if p["title"] == title:
            print(f"  project: reused #{p['number']} \"{title}\"")
            return p["number"]
    created = json.loads(run([
        "gh", "project", "create", "--owner", owner, "--title", title, "--format", "json",
    ]))
    print(f"  project: created #{created['number']} \"{title}\"")
    return created["number"]


def link_project_to_repo(owner: str, repo: str, project_number: int) -> None:
    # Projects (v2) are account-level, not repo-level — creating one under
    # --owner and adding issues to it does NOT make it show up under the
    # repo's own Projects tab. That's a separate, explicit relationship,
    # and this is the step that creates it. Safe to call on an
    # already-linked project; the underlying mutation is idempotent.
    run(["gh", "project", "link", str(project_number), "--owner", owner, "--repo", repo])
    print(f"  project #{project_number} linked to {owner}/{repo}")


def find_existing_issue(owner: str, repo: str, title: str) -> int | None:
    out = run([
        "gh", "issue", "list", "--repo", f"{owner}/{repo}",
        "--search", f'"{title}" in:title', "--state", "all",
        "--json", "number,title",
    ])
    for item in json.loads(out or "[]"):
        if item["title"] == title:
            return item["number"]
    return None


def create_issue(owner: str, repo: str, title: str, body: str, labels: list[str],
                  milestone_title: str, parent: int | None = None) -> int:
    existing = find_existing_issue(owner, repo, title)
    if existing is not None:
        print(f"    = exists: #{existing} {title}")
        return existing

    # --milestone takes the milestone's TITLE, not its numeric ID — passing
    # a number here makes gh look for a milestone literally named "1" and
    # fail with a confusing "not found". This is different from --parent
    # just below, which genuinely does want the issue *number*.
    cmd = ["gh", "issue", "create", "--repo", f"{owner}/{repo}",
           "--title", title, "--body", body, "--milestone", milestone_title]
    for label in labels:
        cmd += ["--label", label]
    if parent is not None:
        cmd += ["--parent", str(parent)]

    url = run(cmd)
    match = re.search(r"/issues/(\d+)", url)
    if not match:
        raise RuntimeError(f"couldn't parse issue number from: {url}")
    number = int(match.group(1))
    print(f"    + created: #{number} {title}")
    return number


def add_to_project(owner: str, project_number: int, issue_url: str) -> None:
    try:
        run(["gh", "project", "item-add", str(project_number), "--owner", owner, "--url", issue_url])
    except RuntimeError as exc:
        # addProjectV2ItemById isn't idempotent server-side the way
        # everything else in this script is (labels use --force, milestone/
        # project/issues are all look-up-then-create-or-reuse) -- but the
        # end state this call wants (issue IS in the project) already holds
        # when this error fires, so treat it as success rather than
        # aborting the whole run over it.
        if "already exists" in str(exc):
            return
        raise


def link_blocked_by(owner: str, repo: str, issue_number: int, blocker_numbers: list[str]) -> None:
    if not blocker_numbers:
        return
    run(["gh", "issue", "edit", str(issue_number), "--repo", f"{owner}/{repo}",
         "--add-blocked-by", ",".join(blocker_numbers)])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", required=True, help="owner/name, e.g. alvincrespo/pr-agent")
    parser.add_argument("--data", required=True,
                         help="Path to a JSON file with \"milestone\", \"epics\", and "
                              "\"release_validation_issue\" top-level keys (see module "
                              "docstring for the exact shape)")
    parser.add_argument("--project-title", default=None,
                         help="Defaults to the repo name itself if not given -- "
                              "NEVER hardcode a specific project name as the default here again; "
                              "that's exactly what caused one repo's issues to land in another "
                              "repo's project board.")
    parser.add_argument("--labels-file", default=None,
                         help="Path to a JSON file listing label objects "
                              "({name, color, description}), passed through to "
                              "github-labels-setup/scripts/ensure_labels.py. Defaults to that "
                              "skill's own labels/default.json if not given.")
    args = parser.parse_args()

    try:
        data = load_data(args.data)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    milestone = data["milestone"]
    epics = data["epics"]
    release_validation_issue = data["release_validation_issue"]

    owner, repo = args.repo.split("/", 1)
    project_title = args.project_title or repo
    labels_file = Path(args.labels_file) if args.labels_file else DEFAULT_LABELS_FILE
    issue_url = lambda n: f"https://github.com/{owner}/{repo}/issues/{n}"  # noqa: E731

    print(f"Bootstrapping {owner}/{repo}...\n")

    print("Labels:")
    ensure_labels(owner, repo, labels_file)

    print("\nMilestone:")
    milestone_number = ensure_milestone(owner, repo, milestone["title"], milestone["description"])

    print("\nProject:")
    project_number = ensure_project(owner, project_title)
    link_project_to_repo(owner, repo, project_number)

    epic_issue_numbers: list[int] = []
    epic_number_by_title: dict[str, int] = {}
    total_created = 0

    for epic in epics:
        print(f"\nEpic: {epic['title']}")
        epic_number = create_issue(
            owner, repo, epic["title"], epic["body"],
            ["epic"] + epic.get("labels", []), milestone["title"],
        )
        add_to_project(owner, project_number, issue_url(epic_number))
        epic_issue_numbers.append(epic_number)
        epic_number_by_title[epic["title"]] = epic_number
        total_created += 1

        # Epic-to-epic dependencies. "epics" is expected to be ordered so
        # every name in "depends_on" refers to an epic already created
        # above -- load_data() already rejects a --data file where that
        # ordering doesn't hold, so the KeyError below should never fire
        # in practice.
        depends_on = epic.get("depends_on", [])
        if depends_on:
            blocker_numbers = [str(epic_number_by_title[title]) for title in depends_on]
            link_blocked_by(owner, repo, epic_number, blocker_numbers)
            print(f"    blocked by: {', '.join(depends_on)}")

        for child in epic["issues"]:
            child_number = create_issue(
                owner, repo, child["title"], child["body"],
                ["task"] + child.get("labels", []), milestone["title"],
                parent=epic_number,
            )
            add_to_project(owner, project_number, issue_url(child_number))
            total_created += 1

    print(f"\nRelease validation issue:")
    validation_number = create_issue(
        owner, repo, release_validation_issue["title"], release_validation_issue["body"],
        release_validation_issue["labels"], milestone["title"],
    )
    add_to_project(owner, project_number, issue_url(validation_number))
    link_blocked_by(owner, repo, validation_number, [str(n) for n in epic_issue_numbers])
    total_created += 1

    print(f"\nDone. {total_created} issues ensured across {len(epics)} epics.")
    print(f"Milestone: https://github.com/{owner}/{repo}/milestone/{milestone_number}")
    print(f"Project:   https://github.com/orgs/{owner}/projects/{project_number}"
          f" (or /users/{owner}/projects/{project_number} for a personal account)")


if __name__ == "__main__":
    main()
