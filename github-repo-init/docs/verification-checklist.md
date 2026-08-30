# Verification checklist: `setup_repo.sh` end-to-end (read-only)

**Date:** 2026-08-30
**Issue:** [#16 — "Verify against a fresh throwaway repo end-to-end"](https://github.com/alvincrespo/skills/issues/16)
**Script verified:** `github-repo-init/scripts/setup_repo.sh` as it exists on
`issue-14-remove-bootstrap-chain-call` (commit `641df49`).

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
STUB git commit -m Initial commit: skills repo scaffolding + tracker
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
STUB git commit -m Initial commit: skills repo scaffolding + tracker
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
STUB git commit -m Initial commit: skills repo scaffolding + tracker
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
STUB git commit -m Initial commit: skills repo scaffolding + tracker
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
exits before either is invoked). Stdout:

```
Usage: setup_repo.sh <owner>/repo-name [--description "..."] [--topics "a,b,c"]
```

Confirms the required-argument guard fails closed with no side effects.

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
**This document does not mark issue #16's acceptance criteria as
satisfied.** The live run — repo creation, push, topic, and license
verification, and cleanup — is still the owner's to do.

## Commands for the repo owner to run by hand

To actually complete issue #16's acceptance criteria, from inside this
project directory (the one containing `github-repo-init/scripts/`), once
`setup_repo.sh` has landed on `main`:

```bash
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
# from the pushed initial commit — setup_repo.sh itself passes no
# --license flag; the license comes from this project's own LICENSE
# file being part of the pushed content), and pushedAt is recent.
#
# Optionally also confirm the push landed with the expected history:
gh repo clone <owner>/skills-throwaway-verify /tmp/skills-throwaway-verify-check
git -C /tmp/skills-throwaway-verify-check log --oneline

# 3. Delete the disposable repo to clean up.
gh repo delete <owner>/skills-throwaway-verify --yes
```

Given the stubbed-argument-parsing evidence above, the expected outcome is
that step 1 produces exactly the `gh repo create` / `gh repo edit
--add-topic` commands shown in scenario 2 (both flags given, since the
example above passes both), and step 2's output should reflect the
`--description` and `--topics` values passed in step 1 plus license
detection from the repo's own `LICENSE` file — consistent with, but not a
substitute for, actually running it.
