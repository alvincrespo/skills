# Clearing a Dependabot backlog with one approval: `axc-dependabot-sweep`

Dependabot pull requests are easy to open and tedious to land. Each one needs a review, a local check, a wait for CI, and a merge. Doing that for eight PRs in a row exposes a problem: merges invalidate each other. When PR A merges, PR B's lockfile may conflict. When Dependabot rebases B, its head SHA changes, and every earlier review and CI result for B is stale.

`axc-dependabot-sweep` is a skill in this repo that does that loop for you. It works through every open Dependabot PR oldest first. It reviews each one, fixes what the review finds, verifies the result locally, waits for CI, and merges. You approve once, at the start.

## Where it came from

The design comes from a manual run on `alvincrespo/website` on 2026-09-28: eight PRs, three GitHub Actions bumps and five npm bumps. Two things went wrong, and the skill is built around them ([ADR 0004](../adr/0004-axc-dependabot-sweep.md)):

- **A lockfile conflict.** Once #1477 merged, #1478 stopped being mergeable because of a `yarn.lock` conflict. Commenting `@dependabot rebase` fixed it.
- **A runtime mismatch.** #1481 bumped `postcss-import` to 17, which requires Node 22 or later. CI was pinned to Node 20. The fix was not in the bump at all: CI had to move to `node-version-file: .node-version`.

The first is a mechanics problem. The second is a judgement problem. The skill splits its work the same way.

## Division of labor: scripts and judgement

The skill's instructions say it directly: the scripts do the mechanical parts, and Claude decides what a review finding means and where a fix belongs. There are four Python scripts, all printing JSON.

| Script | What it does |
| --- | --- |
| `config.py` | Loads and validates `.claude/dependabot-sweep.json`. If the file is missing, it proposes one from the repo's lockfiles. It writes only with `--write`, after you confirm. |
| `list_prs.py` | Lists open PRs by the configured authors, oldest first. It parses the package, the from and to versions, and the semver level from the title. Group bumps and unparseable titles are marked `unknown` and never treated as safe. |
| `wait_for_pr.py` | Polls one PR until a specific head SHA has finished its checks and GitHub has decided mergeability. Results for any other SHA are ignored. |
| `worktree.py` | Creates and removes a throwaway git worktree per PR, so each bump is verified in isolation and your checkout is never touched. |

`wait_for_pr.py` reports one of `ready`, `checks_failed`, `conflicting`, `head_changed`, `closed`, `timeout` or `rebase_timeout`. Only `ready` exits 0. Each script has a test file next to it.

## The one gate

The skill can start on its own. That is a deliberate exception to [ADR 0002](../adr/0002-invocation-control-on-github-actions.md), which made the repo's other GitHub-acting skills user-invoked only. What makes it safe is one rule: nothing changes until you say yes to the plan.

Before touching anything, it shows a single message with:

- the ordered PR table: number, bump, semver level (with a ⚠ on majors and unknowns), and CI state
- the resolved config
- the merge method
- a plain statement of what it will be allowed to do: review each PR, run `verify` in a worktree, comment `@dependabot rebase` on conflicts, push small bump-only fixes, open and merge a separate PR for CI or tooling fixes, merge each green PR, and delete merged branches

Anything other than a clear yes counts as a no. Passing `--dry-run` prints every command it would run for each PR, in order, without creating worktrees, commenting, pushing or merging. It does not ask for approval.

## The loop

After approval, the skill runs `verify` once on the default branch. If the baseline is red, it stops, because a red baseline makes every per-PR result meaningless.

Then, for each PR, oldest first:

1. Create a worktree at the PR's head SHA.
2. Review it.
3. Classify and fix any findings.
4. Run the configured `verify` command in the worktree.
5. Wait for CI on that exact SHA.
6. Merge.

Reviews can overlap: while one PR waits on CI, the next PR's review starts. Merges never overlap. They happen one at a time.

### The merge gate

A PR merges only when all four conditions hold for its current head SHA:

- the review is clean, or its findings are fixed
- every check has finished and passed
- `verify` passed in the PR worktree
- GitHub reports `mergeable == MERGEABLE`

The merge command is `gh pr merge N --<method> --delete-branch --match-head-commit <sha>`. The `--match-head-commit` flag makes GitHub itself refuse the merge if the head moved after the checks. If the wait returns `head_changed`, the review and verification are discarded and that PR starts over on the new SHA.

## Review

The skill prefers Claude Code's `/code-review` at the configured level, `medium` by default. When that isn't available, it falls back to its own checklist against the diff and the package changelog:

- **Runtime range:** the new version's `engines` field against the CI runtime and the repo's pinned version. This is the check that would have caught #1481.
- **Breaking changes:** each one checked against the options the repo actually uses, by searching the repo.
- **Lockfile:** only the bumped package and its real dependents changed, with no leftover duplicates.
- **Supply chain:** maintainer changes, a different publish method, new install scripts, odd gaps or jumps in releases, a changed package name or repo URL. Any of these means stop and ask, not fix.

Major and `unknown` bumps get a full changelog read.

## Where a fix goes

The most distinctive part of the skill is that a finding is classified by where it belongs. There are three outcomes:

- **Infrastructure** (CI runtime pins, repo tooling): open a separate PR to the default branch, merge it, then comment `@dependabot rebase` on the bump PR. This keeps Dependabot as the only author on its branch. Dependabot stops rebasing a branch once someone else has pushed to it.
- **Only exists because of the bump** (a renamed config key, an API change): commit the fix onto the bump branch with a plain push, and move that PR to the end of the queue. Its new head is a new SHA to review.
- **Non-trivial** (app code, multi-file changes, anything ambiguous): stop and ask. Skipping is allowed only after you say so.

For conflicts, the skill comments `@dependabot rebase` and waits for a new head. Before merging it checks that the diff is still the same bump, since a rebase can change the lockfile. A PR that already carries fix commits is rebased locally instead, because `@dependabot recreate` would discard those commits.

## Hard limits

The skill's hard rules are short:

- Only PRs by the configured authors (default `app/dependabot`). Nobody else's.
- Never force-push.
- Never use `--admin` or bypass branch protection or a required check.
- Never run two merges at once.
- If something unexpected happens, stop and tell you.

When a PR can't be landed, whether from red CI after a fix, a rebase timeout, or a `verify` failure it can't fix, the skill skips it, comments on it, and moves on. It does not retry in a loop.

## Configuration and output

Config lives in `.claude/dependabot-sweep.json` in the target repo. The keys are `authors`, `verify`, `merge_method`, `timeouts` (defaults: 20 minutes for CI, 15 for a rebase) and `review_level`. `verify` is required and owns the toolchain: the skill runs it exactly as written and doesn't substitute its own install or build commands. When the file is missing, the skill proposes one from the lockfiles and says plainly that `verify` is a guess.

The merge method defaults to squash if the repo allows it, otherwise the first allowed of merge or rebase.

Comments are posted only on PRs that were fixed or skipped. Clean PRs merge quietly. At the end, the skill prints a summary table with the PR, the bump, the outcome (`merged`, `merged after fix`, or `skipped`), and a link to any fix, then prunes its worktrees.

## Requirements

- `gh`, logged in
- Python 3 for the scripts
- A `verify` command in `.claude/dependabot-sweep.json`

## Summary

The skill automates a repetitive loop while keeping the decisions that matter with a person or with an explicit rule. A single up-front approval authorizes the run. Every result is pinned to a head SHA. A fix is routed by where it belongs. Anything non-trivial goes back to you.

The skill is at [`axc-dependabot-sweep/SKILL.md`](../../axc-dependabot-sweep/SKILL.md).
