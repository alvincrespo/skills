---
name: axc-cut-release-bump
description: Phase 1 of a release — open the version-bump PR, driven by the repo's `.claude/release.json`. Branches off main, bumps the version in the configured file(s) (or runs the configured bump command), sanity-checks, commits, and opens a PR. Stops there — the user merges it, then runs `/axc-cut-release` again to tag. Never pushes to main. Use when the user says "/axc-cut-release-bump", or invoked by the `axc-cut-release` router for Phase 1.
---

# Release Bump (Phase 1)

Opens the PR that puts the new version on `main`. Tagging is a separate, later step
(`axc-cut-release-tag`), so this skill never tags and never pushes to `main` directly.

## Adapter config (`.claude/release.json`)

Read `.claude/release.json` first (Read tool). If missing, auto-detect (`package.json` → npm,
`go.mod` → go) and offer to write one before proceeding — see `axc-cut-release` for the defaults.
Fields used here: `mainBranch`, `version.files[]` (`path` + `match`), `version.bumpCommand` (optional),
`commit.branch`, `commit.title`, `checks.build`, `checks.test`. `{V}` = version without the `v` prefix.

## Argument

The target version `V` (e.g. `0.3.0`). If omitted, resolve it the way `axc-cut-release` does
(next patch off `origin/<mainBranch>`'s version) and confirm before acting.

## Precondition

Working tree clean (`git status --porcelain` empty). If dirty, stop and ask the user to commit/stash
first — this skill won't sweep unrelated changes into a release branch.

## Steps

1. `git fetch origin <mainBranch>`, then branch off it (substitute `{V}` in `commit.branch`):
   `git checkout -b <commit.branch> origin/<mainBranch>`
2. Bump the version with the router's helper script, then verify it:
   ```bash
   python3 "${CLAUDE_SKILL_DIR}/../axc-cut-release/scripts/release_tool.py" bump <V>
   python3 "${CLAUDE_SKILL_DIR}/../axc-cut-release/scripts/release_tool.py" check-versions <V>
   ```
   `bump` rewrites only the version literal in **every** `version.files[]` entry (or, if
   `version.bumpCommand` is set, runs that command instead and verifies the result — this also covers
   any lockfile it updates). If a file's `match` pattern isn't found it exits `2` having written
   nothing. `check-versions` must exit `0`, every file `✓`; on anything else, stop and report the
   output. Don't hand-edit the files to get past a failure.
3. Sanity-check before committing: run `checks.build` and `checks.test` (and a formatter check if the
   stack has one, e.g. `gofmt -l <dir>` or `npm run format -- --check`). If they fail, stop and report.
4. Commit (substitute `{V}` in `commit.title`):
   `git commit -am "<commit.title>"`
   - If the session's instructions ask for a commit trailer (such as `Co-Authored-By:`), add it to this
     commit message too — the title above is the subject line, not the whole message.
5. Push and open the PR:
   `git push -u origin <commit.branch>`
   `gh pr create --base <mainBranch> --head <commit.branch> --title "<commit.title>" --body "<body>"`
   - Body: one line stating the bump (`cur → V`) and that merging unblocks tagging `<tagFormat>`.
     Note CI must be green before merge.
6. **Stop.** Report the PR URL and the exact next step:
   > PR #NN opened. Review and merge it, then run `/axc-cut-release <V>` to tag and publish.
   (Naming the **explicit** `V` avoids a keyword re-run recomputing a fresh bump.)

Opening a PR is reversible (close it), so this proceeds without a yes/no gate — but always show the
resolved version and branch name first.

## What this skill does NOT do

- **Does not push to `main`.** The bump always lands via a PR the user merges.
- **Does not tag or publish.** That's Phase 2 (`axc-cut-release-tag`), after the PR merges.
- **Does not merge the PR.** The user controls the merge.
