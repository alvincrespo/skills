# Verification checklist: `setup_repo.sh` end-to-end (read-only)

**Date:** 2026-08-30 (re-run 2026-09-23 after the preflight fixes; live run 2026-09-25)
**Issue:** [#16 — "Verify against a fresh throwaway repo end-to-end"](https://github.com/alvincrespo/skills/issues/16)
**Script verified:** `github-repo-init/scripts/setup_repo.sh` as it exists at the tip of
the #43 → #44 PR stack, including the local-git preflight and `--topics`
validation added during review.

## Scope of this check

Issue #16's acceptance criteria call for actually running the generalized
script against a disposable throwaway GitHub repo, confirming repo
creation/push/topics/license land correctly, and then deleting that repo.
Per the repo owner's standing, twice-confirmed preference — documented
in `github-labels-setup/docs/regression-test-pr-agent.md` and reaffirmed
for this issue — Claude does not run live mutating `gh` commands (`gh repo
create`, `gh repo delete`, or any other write call) against real or
disposable GitHub repos. The owner runs those themselves, by hand.

So this document does **not** claim the live create → verify → delete
cycle is done. Instead it does the closest safe substitute: a thorough
**read-only / non-mutating verification** of the script itself — static
analysis plus argument-parsing behavior exercised against stubbed `gh` and
`git` commands, so the exact commands the script would run against real
GitHub are captured and checked, with zero network calls and zero
filesystem side effects outside an empty throwaway temp directory.

No `gh` or `git` command was run against GitHub or against this repo's own
history as part of producing this document. Every `gh`/`git` invocation
below came from stub scripts that only append their arguments to a log
file and exit 0.

## 1. Static analysis: `shellcheck`

```bash
shellcheck github-repo-init/scripts/setup_repo.sh
```

Tool version: `shellcheck 0.11.0`.

**Result: clean.** Zero findings, exit code 0. Nothing was fixed because
nothing was flagged — the script already quotes all variable expansions,
uses `set -euo pipefail`, and builds its `TOPIC_ARGS` array correctly for
word-splitting-safe expansion (`"${TOPIC_ARGS[@]}"`).

## 2. Argument-parsing verification against stubbed `gh`/`git`

### Method

A throwaway temp directory (empty, no `.git`) was used as the working
directory. `gh` and `git` were replaced on `PATH`, ahead of the real
binaries, with two-line stub scripts:

```bash
#!/usr/bin/env bash
echo "STUB gh $*" >> "${STUB_LOG:?STUB_LOG not set}"
exit 0
```

```bash
#!/usr/bin/env bash
echo "STUB git $*" >> "${STUB_LOG:?STUB_LOG not set}"
exit 0
```

`setup_repo.sh` was then run as `bash setup_repo.sh <args>` (not sourced —
the script's own `set -euo pipefail` and `exit` calls in `usage()` make
running it as a subprocess the correct isolation boundary) with `PATH`
prefixed with the stub directory, from inside the empty temp directory.
Each invocation's stub log was cleared beforehand and printed after.

Real `gh`/`git` versions present on the machine, for reference (neither
was invoked for real anywhere in this check):

```
gh version 2.98.0 (2026-08-20)
git version 2.55.0
```

### Scenario 1 — no flags (both defaults used)

```
$ setup_repo.sh testowner/throwaway-repo-1
```

Exit code: `0`. Captured stub invocations:

```
STUB git init
STUB git add -A
STUB git commit -m Initial commit
STUB gh repo create testowner/throwaway-repo-1 --public --description A small, growing collection of Claude Skills for real engineering workflows. --source=. --remote=origin --push
STUB gh repo edit testowner/throwaway-repo-1 --add-topic claude-skills --add-topic claude-code --add-topic ai-agent-tooling --add-topic github-automation
```

Confirms: both documented defaults (description string, four-topic list)
are used verbatim when neither flag is passed, and the `.git`-absent path
runs `git init` / `git add -A` / `git commit` before creating the repo.

### Scenario 2 — both `--description` and `--topics` given

```
$ setup_repo.sh testowner/throwaway-repo-2 \
    --description "A disposable end-to-end test repo" \
    --topics "smoke-test,disposable"
```

Exit code: `0`. Captured stub invocations:

```
STUB git init
STUB git add -A
STUB git commit -m Initial commit
STUB gh repo create testowner/throwaway-repo-2 --public --description A disposable end-to-end test repo --source=. --remote=origin --push
STUB gh repo edit testowner/throwaway-repo-2 --add-topic smoke-test --add-topic disposable
```

Confirms: both custom values fully override their defaults, and the
comma-separated topics string is correctly split into one `--add-topic`
per entry (two topics in, two `--add-topic` flags out).

### Scenario 3 — only `--topics` given (description falls back to default)

```
$ setup_repo.sh testowner/throwaway-repo-3 --topics "smoke-test,disposable"
```

Exit code: `0`. Captured stub invocations:

```
STUB git init
STUB git add -A
STUB git commit -m Initial commit
STUB gh repo create testowner/throwaway-repo-3 --public --description A small, growing collection of Claude Skills for real engineering workflows. --source=. --remote=origin --push
STUB gh repo edit testowner/throwaway-repo-3 --add-topic smoke-test --add-topic disposable
```

Confirms: passing only `--topics` leaves `--description` on its documented
default rather than erroring or leaving it empty.

### Scenario 4 (bonus) — only `--description` given (topics fall back to default)

```
$ setup_repo.sh testowner/throwaway-repo-4 --description "A disposable end-to-end test repo"
```

Exit code: `0`. Captured stub invocations:

```
STUB git init
STUB git add -A
STUB git commit -m Initial commit
STUB gh repo create testowner/throwaway-repo-4 --public --description A disposable end-to-end test repo --source=. --remote=origin --push
STUB gh repo edit testowner/throwaway-repo-4 --add-topic claude-skills --add-topic claude-code --add-topic ai-agent-tooling --add-topic github-automation
```

Confirms the symmetric case of scenario 3: passing only `--description`
leaves `--topics` on its documented four-item default.

### Scenario 5 (bonus) — missing required `repo` argument

```
$ setup_repo.sh
```

Exit code: `1`. Stub log: empty (no `gh`/`git` call was made — `usage()`
exits before either is invoked). Stderr (`--help` prints the same line
to stdout and exits `0` instead):

```
Usage: setup_repo.sh <owner>/repo-name [--description "..."] [--topics "a,b,c"]
```

Confirms the required-argument guard fails closed with no side effects.

### Scenario 6 — messy `--topics` (whitespace, empty entries, trailing comma)

```
$ setup_repo.sh testowner/throwaway-repo-6 --topics " smoke-test , ,disposable,"
```

Exit code: `0`. Captured stub invocations:

```
STUB git init
STUB git add -A
STUB git commit -m Initial commit
STUB gh repo create testowner/throwaway-repo-6 --public --description A small, growing collection of Claude Skills for real engineering workflows. --source=. --remote=origin --push
STUB gh repo edit testowner/throwaway-repo-6 --add-topic smoke-test --add-topic disposable
```

Confirms: whitespace around each entry is trimmed and empty entries are
dropped, so no `--add-topic ""` or `--add-topic " disposable"` reaches
`gh`.

### Scenario 7 — `--topics` with no usable entries

```
$ setup_repo.sh testowner/throwaway-repo-7 --topics ", ,"
```

Exit code: `1`. Stub log: empty. Stderr:

```
Error: --topics contained no non-empty topics
```

Confirms the topic list is validated before `gh repo create`, so a bad
list can't leave a created-but-untopiced repo behind.

### Scenarios 8–10 — preflight against an existing `.git` (real `git`)

The stubbed `git` above exits `0` for everything, so it can't exercise the
existing-repo checks. These three used the real `git` in a throwaway temp
repo, with only `gh` stubbed:

| # | Temp repo state | Exit | Output | `gh` calls |
|---|---|---|---|---|
| 8 | one commit + `origin` remote already set | `1` | `Error: an 'origin' remote already exists (https://github.com/testowner/existing.git); remove or rename it first` | none |
| 9 | `git init`, no commits | `1` | `Error: this repository has no commits yet; commit something before publishing` | none |
| 10 | one commit + an uncommitted edit | `0` | `Warning: uncommitted changes present — they will NOT be pushed.` | `repo create`, `repo edit` (defaults) |

These matter because `gh repo create --source=. --remote=origin --push`
creates the GitHub repo *before* it adds the local remote and pushes. A
pre-existing `origin` or an empty history would otherwise fail only after
an empty repo already existed on GitHub.

### Scenario 11 — control character in `--description`

Added after the [live run](#live-run-2026-09-25) below hit it. Stubbed
`gh`/`git`, empty temp directory:

| `--description` | Exit | Output | `gh`/`git` calls |
|---|---|---|---|
| `$'Disposable\n repo'` (newline) | `1` | `Error: --description contains a control character (e.g. a newline); GitHub rejects those` | none |
| `$'a\tb'` (tab) | `1` | same | none |
| `"skills#16 smoke test — ok"` | `0` | — | `git init`/`add`/`commit`, `repo create`, `repo edit` |

Confirms a multi-line description is rejected before `git init`, rather
than by GitHub after the local commit.

### What this does and does not verify

This confirms the script builds the exact `gh repo create` and `gh repo
edit --add-topic` command lines expected for each flag combination, with
correct default fallback, correct override behavior, correct topic-list
splitting, and no `gh`/`git` call made before argument validation passes.
It does **not** (and cannot, stubbed) verify: real `gh` authentication or
scope correctness, real GitHub API behavior or error responses, whether
the pushed content actually appears on GitHub, whether topics actually
land as set, or license detection — those require the real run below.

## Why no live create → verify → delete cycle was run

Per the repo owner's standing preference — first established in
`github-labels-setup/docs/regression-test-pr-agent.md` and reaffirmed for
this issue — Claude does not execute mutating `gh` commands against real
GitHub repos, including disposable throwaway ones, even though a throwaway
repo's consequences are fully reversible. That decision is the owner's to
make and execute by hand, not Claude's to take on their behalf.
The live run below was done by the owner by hand, with Claude verifying
the results through read-only `gh` calls.

## Commands for the repo owner to run by hand

To actually complete issue #16's acceptance criteria, once
`setup_repo.sh` has landed on `main`. Don't run the script from this
checkout directly: it already has an `origin` remote (pointing at
`alvincrespo/skills`), which the preflight rejects (scenario 8). Publish
a clean clone with its remote removed instead:

```bash
# 0. Make a clean copy of this project with no origin remote.
#    Run from inside this project directory, on an up-to-date main.
tmp="$(mktemp -d)"
git clone --quiet --no-local . "$tmp/skills-throwaway-verify"
git -C "$tmp/skills-throwaway-verify" remote remove origin
cd "$tmp/skills-throwaway-verify"

# 1. Create the disposable throwaway repo and push this content to it.
#    Replace <owner> with your GitHub username/org.
./github-repo-init/scripts/setup_repo.sh <owner>/skills-throwaway-verify \
  --description "Disposable throwaway repo for setup_repo.sh verification" \
  --topics "throwaway,verification"

# 2. Confirm repo creation, push, topics, and license all landed.
gh repo view <owner>/skills-throwaway-verify \
  --json name,description,repositoryTopics,licenseInfo,pushedAt

# Expected: name matches, description matches what was passed above,
# repositoryTopics contains "throwaway" and "verification", licenseInfo
# is non-null (GitHub auto-detects the LICENSE file at this repo's root
# from the pushed content — setup_repo.sh itself passes no --license
# flag), and pushedAt is recent.
#
# Optionally confirm the pushed history matches the local clone:
git log --oneline -3
gh api repos/<owner>/skills-throwaway-verify/commits --jq '.[0:3][] | .sha[0:7] + " " + (.commit.message | split("\n")[0])'

# 3. Delete the disposable repo and the local clone to clean up.
#    `gh repo delete` needs the delete_repo scope; add it once if missing:
#      gh auth refresh -s delete_repo
cd - >/dev/null
gh repo delete <owner>/skills-throwaway-verify --yes
rm -rf "$tmp"
```

Given the stubbed-argument-parsing evidence above, the expected outcome is
that step 1 produces exactly the `gh repo create` / `gh repo edit
--add-topic` commands shown in scenario 2 (both flags given, since the
example above passes both), and step 2's output should reflect the
`--description` and `--topics` values passed in step 1 plus license
detection from the repo's own `LICENSE` file — consistent with, but not a
substitute for, actually running it.

## Live run (2026-09-25)

Run by the repo owner by hand against a disposable repo,
`alvincrespo/repo-init-smoke-test`, from a scratch directory containing
only a copy of this repo's `LICENSE` and a one-line `README.md` (no
`.git`). This satisfies issue #16's acceptance criteria.

**First attempt: failed safely, and found a gap.** The pasted command
wrapped, putting a newline inside the quoted `--description`. The script
ran `git init` and the initial commit, then `gh repo create` failed with
`GraphQL: Description control characters are not allowed
(createRepository)`. Nothing was created on GitHub. The preflight
didn't check the description, so the failure came only after the local
commit; [scenario 11](#scenario-11--control-character-in---description)
covers the fix.

**Second attempt, on one line**, re-run in the same directory, so it took
the existing-`.git` path (one commit, no `origin`):

```bash
setup_repo.sh alvincrespo/repo-init-smoke-test \
  --description "skills#16 smoke test" \
  --topics "smoke-test, github-repo-init,disposable"
```

Between the two attempts, both the no-`.git` and existing-`.git` paths ran
for real.

**Verified with read-only `gh` calls:**

| Check | Result |
|---|---|
| Repo created | Public, description `skills#16 smoke test` |
| Content pushed | `main` has `55d273d Initial commit` with `LICENSE` and `README.md`; local `main` tracks `origin/main`, in sync |
| Topics | `smoke-test`, `github-repo-init`, `disposable`; the space in `"smoke-test, github-repo-init"` was trimmed |
| License | `gh api repos/<repo>/license` reports `MIT`, detected from `LICENSE` |

**Cleanup:** the owner ran `gh auth refresh -s delete_repo`, then
`gh repo delete alvincrespo/repo-init-smoke-test --yes`, and removed the
scratch directory. Confirmed gone: `gh repo view` reports it can't resolve
the repository.
