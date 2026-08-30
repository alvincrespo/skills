#!/usr/bin/env python3
"""
Bootstrap a GitHub repo + Project (v2) from tracker/issues.py.

    gh auth login
    gh auth refresh -s project      # project scope isn't in gh's default scopes
    gh repo create <owner>/pr-agent --private --clone
    cd pr-agent
    python scripts/bootstrap_github_project.py --repo <owner>/pr-agent

What it does, in order:
  1. Creates (or updates, via --force) a small set of labels.
  2. Creates the "v1 — Local End-to-End Run" milestone, or reuses it if a
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
  4. For each epic in tracker/issues.py, in list order: creates the epic as
     an issue labeled "epic", links it as blocked-by whatever its
     "depends_on" list names (each dependency is guaranteed to already
     exist, since EPICS is ordered so nothing depends on a later epic),
     then creates each of its child issues linked to it via GitHub's
     sub-issue relationship (`gh issue create --parent`).
  5. Creates the standalone release-validation issue, linked as blocked-by
     every epic.
  6. Adds every issue created to the Project board.

Step 4's epic-to-epic blocked-by links are what make the sequencing in
tracker/issues.py's module docstring (Setup blocks everything; Config &
Safety blocks Testing; Observability/CLI/Docs are parallel-safe) show up
as real, visible blocks on the epic issues themselves — not just an
ordering convention someone has to remember from a doc.

Idempotency: labels use --force, so re-running is safe. Milestones and the
project are looked up by title/name first. Issues are looked up by exact
title before creating, so a second run mostly no-ops instead of
duplicating — but it's still meant as a one-time bootstrap, not a sync tool
you run on every edit to tracker/issues.py. If you change scope later,
edit or close issues by hand for anything that already exists.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from tracker.issues import EPICS, MILESTONE, RELEASE_VALIDATION_ISSUE  # noqa: E402


def run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd)}\n{result.stderr.strip()}")
    return result.stdout.strip()


def ensure_labels(owner: str, repo: str) -> None:
    labels = [
        ("epic", "5319E7", "A tracked body of work with child issues"),
        ("task", "0E8A16", "A single actionable unit of work"),
        ("safety-critical", "B60205", "Touches the merge/push/allowlist safety boundary"),
        ("priority:P0", "D93F0B", "Blocks the v1 release milestone"),
        ("priority:P1", "FBCA04", "Should land before v1, not release-blocking"),
        ("priority:P2", "C5DEF5", "Nice to have / stretch"),
        ("size:S", "C2E0C6", "About one session"),
        ("size:M", "FEF2C0", "About two to three sessions"),
        ("size:L", "F9D0C4", "Open-ended, may need its own breakdown"),
    ]
    for name, color, desc in labels:
        run(["gh", "label", "create", name, "--repo", f"{owner}/{repo}",
             "--color", color, "--description", desc, "--force"])
    print(f"  labels: {len(labels)} ensured")


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
    parser.add_argument("--project-title", default=None,
                         help="Defaults to the repo name itself if not given -- "
                              "NEVER hardcode a specific project name as the default here again; "
                              "that's exactly what caused one repo's issues to land in another "
                              "repo's project board.")
    args = parser.parse_args()

    owner, repo = args.repo.split("/", 1)
    project_title = args.project_title or repo
    issue_url = lambda n: f"https://github.com/{owner}/{repo}/issues/{n}"  # noqa: E731

    print(f"Bootstrapping {owner}/{repo}...\n")

    print("Labels:")
    ensure_labels(owner, repo)

    print("\nMilestone:")
    milestone_number = ensure_milestone(owner, repo, MILESTONE["title"], MILESTONE["description"])

    print("\nProject:")
    project_number = ensure_project(owner, project_title)
    link_project_to_repo(owner, repo, project_number)

    epic_issue_numbers: list[int] = []
    epic_number_by_title: dict[str, int] = {}
    total_created = 0

    for epic in EPICS:
        print(f"\nEpic: {epic['title']}")
        epic_number = create_issue(
            owner, repo, epic["title"], epic["body"],
            ["epic"] + epic.get("labels", []), MILESTONE["title"],
        )
        add_to_project(owner, project_number, issue_url(epic_number))
        epic_issue_numbers.append(epic_number)
        epic_number_by_title[epic["title"]] = epic_number
        total_created += 1

        # Epic-to-epic dependencies. EPICS is ordered so every name in
        # "depends_on" refers to an epic already created above — if that
        # ever stops being true, the KeyError below is the signal to fix
        # the ordering in tracker/issues.py rather than the script.
        depends_on = epic.get("depends_on", [])
        if depends_on:
            blocker_numbers = [str(epic_number_by_title[title]) for title in depends_on]
            link_blocked_by(owner, repo, epic_number, blocker_numbers)
            print(f"    blocked by: {', '.join(depends_on)}")

        for child in epic["issues"]:
            child_number = create_issue(
                owner, repo, child["title"], child["body"],
                ["task"] + child.get("labels", []), MILESTONE["title"],
                parent=epic_number,
            )
            add_to_project(owner, project_number, issue_url(child_number))
            total_created += 1

    print(f"\nRelease validation issue:")
    validation_number = create_issue(
        owner, repo, RELEASE_VALIDATION_ISSUE["title"], RELEASE_VALIDATION_ISSUE["body"],
        RELEASE_VALIDATION_ISSUE["labels"], MILESTONE["title"],
    )
    add_to_project(owner, project_number, issue_url(validation_number))
    link_blocked_by(owner, repo, validation_number, [str(n) for n in epic_issue_numbers])
    total_created += 1

    print(f"\nDone. {total_created} issues ensured across {len(EPICS)} epics.")
    print(f"Milestone: https://github.com/{owner}/{repo}/milestone/{milestone_number}")
    print(f"Project:   https://github.com/orgs/{owner}/projects/{project_number}"
          f" (or /users/{owner}/projects/{project_number} for a personal account)")


if __name__ == "__main__":
    main()
