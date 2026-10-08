# ADR 0004: `axc-dependabot-sweep` — model-invocable, behind one up-front approval

## Status
Proposed. Tracked in #66.

## Context
Dependabot PRs pile up, and working through them safely is mechanical but
fiddly:
- Merges invalidate each other's lockfiles.
- Rebases change head SHAs, so earlier CI results and reviews go stale.
- Some bumps need a fix somewhere else in the repo, such as a CI runtime
  version.

A person has to review, verify and merge each PR in order, while polling
GitHub for mergeability and check status.

The plan comes from a manual run on `alvincrespo/website` (2026-09-28): 8 PRs
(#1474–#1481), 3 GitHub Actions bumps and 5 npm bumps. Two things went wrong
that the skill has to handle:
- #1478 stopped merging because of a `yarn.lock` conflict after #1477
  merged. `@dependabot rebase` fixed it.
- #1481 (postcss-import 17) needs Node ≥ 22, but CI pinned Node 20. The fix
  was to move CI to `node-version-file: .node-version`.

## Decision
Add a skill, `axc-dependabot-sweep`:

1. **Invocation: Claude can start it on its own, with one approval up
   front.** This is a deliberate exception to ADR 0002, which made every
   GitHub-acting skill user-invoked only. Before touching anything, the
   skill shows the ordered PR table (number, bump, semver level with ⚠ on
   majors, current CI state) and the resolved config, and gets one explicit
   yes. After that it stops only for non-trivial fixes or anything
   unexpected. The reasoning: Dependabot opens these PRs and CI verifies
   them, and the approval is required before anything changes.
2. **Scope:** authors come from config, default `app/dependabot`. The rebase
   and conflict handling is Dependabot-specific (`@dependabot rebase`) until
   another bot is needed.
3. **Order:** oldest first.
4. **Concurrency:** the next PR's review runs while the current one waits on
   CI or a rebase. Merges happen strictly one at a time. If a PR's head SHA
   changes after its review, it gets reviewed again.
5. **Review:** use Claude Code's `/code-review medium <PR>` when it's
   available. Otherwise use the skill's own dependency-bump checklist:
   - engines/runtime range compared with the CI and local runtimes
   - breaking changes in the changelog, checked against the options the
     repo actually uses
   - lockfile consistency, with no leftover duplicate versions
   - supply-chain signals: maintainer, publish method, install scripts,
     surprising gaps between releases
6. **Merge gate:** all of the following:
   - the review is clean, or its findings are fixed
   - every check has finished and passed on the **current head SHA**
   - the config's `verify` command passes in the PR worktree
   - GitHub reports `mergeable == MERGEABLE`
7. **Where fixes go, classified by where they belong:**
   - **Infrastructure fixes** (CI or workflow runtime pins, repo tooling):
     open a separate PR to the default branch, merge it, then comment
     `@dependabot rebase` on the bump PR so Dependabot keeps owning it.
     Dependabot stops rebasing a branch once someone else has pushed to it,
     and `@dependabot recreate` throws those commits away.
   - **Fixes that only exist because of the bump** (renamed config key, API
     change): push them onto the bump branch and move that PR to the end of
     the queue. If it later conflicts, rebase it locally.
   - **Non-trivial fixes** (app code, multi-file changes, anything
     ambiguous): stop and ask.
8. **Conflicts:** comment `@dependabot rebase` and wait for a new head SHA
   that is mergeable with CI finished. Then confirm the diff is still the
   same bump and merge.
9. **Merge method:** the repo default, preferring squash, with an optional
   config override. Delete the branch after merging.
10. **Failures** (CI red after a fix, rebase times out, `verify` fails): skip
    the PR with an explanatory PR comment and keep going. Report everything
    in a summary table at the end.
11. **PR comments:** posted only when a PR was fixed or skipped. The comment
    covers the finding, a link to the fix commit or fix PR, and the verify
    result. Clean PRs merge quietly.
12. **Toolchain:** the config's `verify` string owns it (for example
    `npx -y yarn@1 …` when yarn isn't on PATH). A preflight runs `verify`
    once on the default branch before the loop starts.

Config lives in `.claude/dependabot-sweep.json` in the target repo. If it is
missing, the skill detects the package managers from the lockfiles, proposes
a config and asks for confirmation before writing it.

## Consequences
- Dependabot backlogs get cleared with a single approval, and merges can't
  race each other.
- Review and CI results tied to an old head SHA are never trusted, so
  re-reviewing after a rebase costs extra time.
- The skill breaks the ADR 0002 precedent. The single up-front approval is
  what keeps it safe, and it can't be skipped.
