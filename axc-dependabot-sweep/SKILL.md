---
name: axc-dependabot-sweep
description: Clear a repo's backlog of open Dependabot PRs end to end — oldest first, review each bump, fix what the review finds, verify locally, wait for CI on the exact head SHA, merge, repeat until none are left. Shows the ordered PR table and gets one explicit yes before touching anything. Use when the user says "resolve the dependabot PRs", "sweep dependabot", "merge the dependency bumps", "clear the dependabot backlog", or asks to review and merge open Dependabot PRs. Pass --dry-run to see the plan and every command without changing anything.
---

# Dependabot Sweep

Work through every open Dependabot PR in a repo: review, fix, verify, wait for
CI, merge, next. The design and the reasons behind each rule are in
`docs/adr/0004-axc-dependabot-sweep.md`; this file is what to do and where to
use judgement. The scripts do the mechanical parts (listing, polling,
worktrees); you decide what a review finding means and where a fix belongs.

This skill **can start on its own**, which is a deliberate exception to ADR
0002, and that is only safe because of **one rule you may not skip: nothing is
changed until the user has said yes to the plan in step 3.**

## Scripts

All print JSON on stdout and errors on stderr. Run from the target repo's
checkout.

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/config.py [--write]
python3 ${CLAUDE_SKILL_DIR}/scripts/list_prs.py [--author A ...] [--format json|table]
python3 ${CLAUDE_SKILL_DIR}/scripts/wait_for_pr.py --pr N --sha SHA [--until ci|rebase] \
    [--ci-minutes M] [--rebase-minutes M]
python3 ${CLAUDE_SKILL_DIR}/scripts/worktree.py create --pr N --branch REF [--sha SHA]
python3 ${CLAUDE_SKILL_DIR}/scripts/worktree.py remove --pr N
python3 ${CLAUDE_SKILL_DIR}/scripts/worktree.py prune
```

`wait_for_pr.py` exits 0 only for `ready`; any other outcome exits 2 with the
outcome in the JSON (`checks_failed`, `conflicting`, `head_changed`, `closed`,
`timeout`, `rebase_timeout`). It blocks, so run it in the background and
review the next PR while it polls.

## Hard rules

- Never merge a PR unless **all four** hold for its *current* head SHA: review
  clean (or findings fixed), every check finished and passed, `verify` passed
  in the PR worktree, `mergeable == MERGEABLE`.
- Merge with `gh pr merge N --match-head-commit <sha>` so GitHub itself
  refuses if the head moved after the gate. A reviewed or green result for any
  other SHA is worthless; if the head changed, the review starts over.
- Merges happen **one at a time**. Never two in flight.
- Only PRs by the configured authors. Never touch anyone else's PR.
- Never `@dependabot recreate` (it discards fix commits), never force-push,
  never `--admin` or otherwise bypass branch protection or a required check.
- If anything unexpected happens, stop and tell the user. Do not improvise.

## Workflow

### 1. Config
Run `config.py`. If `.claude/dependabot-sweep.json` exists it is validated and
printed. If it is missing, `config.py` prints a *proposal* built from the
lockfiles (not written): show it, say plainly that `verify` is a guess, and let
the user edit it. Write it with `config.py --write` only after they confirm. If
it exits 1 (invalid, or no lockfile to propose from), fix it with the user;
do not continue with a guessed `verify`.

### 2. List
Run `list_prs.py --format table` (and keep the JSON). If there are none, say
so and stop. Note the default branch with `gh repo view --json
defaultBranchRef -q .defaultBranchRef.name`, and the merge method: the
config's `merge_method`, else squash if the repo allows it
(`gh repo view --json squashMergeAllowed,mergeCommitAllowed,rebaseMergeAllowed`),
else the first allowed of merge/rebase.

### 3. Approval — the one gate
Show, in one message: the ordered table (number, bump, level with ⚠ on
majors/unknown, CI state), the resolved config, the merge method, and what you
are about to be allowed to do, stated plainly:

> I will review each PR, run `<verify>` in a throwaway worktree, comment
> `@dependabot rebase` on PRs that conflict, push small bump-only fixes to a
> bump branch, open and merge a separate PR for CI/tooling fixes, merge each PR
> once it is green, and delete merged branches. I will stop and ask for
> anything that is not a small fix.

Then ask for an explicit yes. Anything other than a clear yes is a no. Without
`--dry-run`, stop here until you have it.

**`--dry-run`:** do steps 1–3 and print, for each PR in order, every command
you *would* run (worktree create, review, verify, wait, merge, any comment),
substituting `<sha>` where it is not known yet. Do not create worktrees, post
comments, push, or merge, and do not ask for approval. End with the table.

### 4. Preflight
Run `verify` once on the default branch in a worktree
(`worktree.py create --pr 0 --branch <default>`, then remove it). If it fails,
**stop**: a red baseline makes every per-PR result meaningless. Report the
output; do not start the loop.

### 5. The loop
Take PRs oldest first. For each PR, record `reviewed_sha` = its head SHA when
you start, and:

1. **Worktree.** `worktree.py create --pr N --branch <head_ref> --sha <sha>`.
2. **Review** (below). Findings go into a list; a clean review has none.
3. **Classify and fix** each finding (below).
4. **Verify.** Run the config's `verify` in the PR worktree. A failure here is
   a finding too: fix it if it is a small fix, else skip the PR.
5. **Wait.** `wait_for_pr.py --pr N --sha <sha>`. While it polls, start the
   next PR's review (concurrency is for reviews, never merges).
6. **Gate and merge.** On `ready`, and only if the head SHA still equals the
   one you reviewed and verified: `gh pr merge N --<method> --delete-branch
   --match-head-commit <sha>`. Then `worktree.py remove --pr N`.
7. After a merge, later PRs may now conflict: go to the conflict flow when
   `wait_for_pr.py` says `conflicting`.

Outcomes of the wait:
- `head_changed`: someone or something moved the head. Discard the review and
  verify; start that PR again from step 1 on the new SHA.
- `checks_failed`: see Failures.
- `conflicting`: conflict flow.
- `timeout`: see Failures.

### 6. Summary
Always end with a table: PR, bump, outcome (`merged`, `merged after fix`,
`skipped`), what was done or why skipped, link to any fix commit or fix PR.
Run `worktree.py prune`. Say plainly if anything was skipped.

## Review

Prefer Claude Code's `/code-review <review_level> <PR>` (invoke through the
Skill tool) when it is available. If it is not, run this checklist against the
PR diff and the package's published changelog:

- **Runtime range:** the new version's `engines` / required language version
  against the CI workflow's runtime and the repo's pinned version
  (`.node-version`, `.ruby-version`, `.tool-versions`, …). (#1481: postcss-import
  17 needs Node ≥ 22, CI pinned 20.)
- **Breaking changes:** read the changelog between the two versions, then check
  each breaking change against the options the repo *actually uses*. Search the
  repo; do not skim.
- **Lockfile:** only the bumped package and its real dependents changed; no
  leftover duplicate versions of it; the lockfile matches the manifest.
- **Supply chain:** maintainer changes, a release published by a different
  method than before, new install/postinstall scripts, a suspicious gap or jump
  in releases, a package name or repo URL that changed. Any of these is a stop
  and ask, not a fix.

A major or `unknown` bump gets the full changelog read. A patch from a quiet
package may only need the lockfile and runtime checks, but still look.

## Where a fix goes

Classify each finding by where it belongs, then act:

- **Infrastructure** — CI/workflow runtime pins, repo tooling: open a separate
  PR to the default branch from a fresh branch, wait for it, merge it, then
  comment `@dependabot rebase` on the bump PR and wait with `--until rebase`.
  This keeps Dependabot as the only author on its branch. (#1481: moving CI to
  `node-version-file: .node-version`.)
- **Only exists because of the bump** — a renamed config key, an API change:
  commit the fix onto the bump branch (from the worktree, `git push origin
  HEAD:<head_ref>`; plain push, never force), **move that PR to the end of the
  queue**, and treat its new head as a new SHA to review. Dependabot will stop
  rebasing the branch now; if it later conflicts, rebase it locally.
- **Non-trivial** — app code, anything touching several files, anything
  ambiguous or that you are not sure about: **stop and ask the user.** Skipping
  is allowed only after they say so, or for the failures below.

## Conflict flow

Comment `@dependabot rebase` (`gh pr comment N --body "@dependabot rebase"`),
then `wait_for_pr.py --pr N --sha <old sha> --until rebase`. A new head is a new
SHA: before merging, confirm `gh pr diff N` is still the same bump (same
package, same versions) and re-review if anything else is in it, since
rebases can change the lockfile. If a PR already has fix commits from you, do
not use `@dependabot rebase`; rebase locally instead.

## Failures — skip and keep going

CI red after a fix, a rebase that times out, `verify` failing in a way you
cannot fix, or a wait that times out: **skip the PR**, post a comment on it, and
continue with the rest. Do not retry in a loop.

## PR comments

Post a comment only when a PR was fixed or skipped; clean PRs merge quietly.
State what was found, link the fix commit or fix PR, and give the verify
result:

```
Fixed before merge:
- Found: <finding>
- Fix: <commit or PR link>
- `<verify command>`: passed
```

```
Skipped by dependabot-sweep:
- Why: <failure, with the relevant output>
- State: <what was tried, and what is left>
```

## Notes

- `verify` owns the toolchain. Run it exactly as configured; do not substitute
  your own install or build commands.
- CI state in the table from `list_prs.py` is only a hint. The gate uses
  `wait_for_pr.py` on the head SHA you reviewed.
- Failing to find a lockfile, a missing `gh` login, or a repo with no Dependabot
  PRs are all reasons to stop and say so, not to continue.
