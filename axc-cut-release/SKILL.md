---
name: axc-cut-release
description: Cut a release end to end in any project, driven by the repo's `.claude/release.json`. The entry point / router — resolves the target version (semver keyword like `patch`/`minor`/`major`, an explicit version like `0.3.0`, or — with no arg — the next patch), detects which phase the release is in from repo state, and delegates to `axc-cut-release-bump` (Phase 1: open a version-bump PR) or `axc-cut-release-tag` (Phase 2: preflight + push the `vX.Y.Z` tag). Respects the "PRs only, never push to main" rule. Use when the user says "/axc-cut-release", "cut a release", "ship a release", "publish a new version", or similar.
---

# Cut Release (router)

Releases are tag-driven: pushing a `vX.Y.Z` tag fires the repo's release workflow, which builds and
publishes the release artifact (npm package, GitHub Release, …). The version recorded on `main` must
already equal the tag's version — and `main` only changes through a PR. So a release is two phases:

- **Phase 1 — bump:** branch, bump the version, open a PR. The user merges it.
- **Phase 2 — tag:** once `main` carries the new version, run preflight, then push the tag. CI publishes.

This skill is the **router**: it resolves the version and detects the phase from repo state, then
hands off to the sub-skill that does the work. Run `/axc-cut-release` once to open the PR, and again
(after merging) to tag. Each sub-skill is also runnable on its own.

## Adapter config (`.claude/release.json`)

Everything tech-specific comes from the repo's `.claude/release.json` — read it first (Read tool).
If it's missing, auto-detect and **offer to write one** before doing anything:

- `package.json` present → npm defaults (`version` field; `npm version {V} --no-git-tag-version`;
  `npm run lint`/`build`/`test`; `npm pack --dry-run`; commit `release: v{V}`; artifact `npm`).
- `go.mod` present → go defaults (`go vet ./...` / `go build ./...` / `go test -race ./...`;
  `go mod verify`; artifact `github-release`) — but the version-literal location can't be inferred,
  so ask which file(s) hold it.

Show the resolved/inferred config and confirm before proceeding. Fields used here: `repo`,
`mainBranch`, `version.files[]` (`path` + `match`, where `{V}` marks the version), `commit.branch`,
`release.tagFormat`. `{V}` = version **without** the `v` prefix.

## Argument

Optional. One of:

- **A semver keyword** — `patch`, `minor`, or `major`. Computed off the current `main` version.
- **An explicit version** — `0.3.0`, or a prerelease like `0.3.0-rc.1`. Prerelease tags (containing
  `alpha`/`beta`/`rc`) are usually auto-flagged as prereleases by the release workflow — no extra
  handling here.
- **Nothing** — infer intent (see below). On a fresh cut, propose the next **patch** off the current
  version and confirm before doing anything.

## The helper script

The version, tag and phase logic lives in `scripts/release_tool.py` (standard library only, tested in
`scripts/test_release_tool.py`). Run it from the repo being released; it reads `.claude/release.json`
and git state, and takes `--repo-root PATH` / `--config PATH` if you need to point it elsewhere:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/release_tool.py" <subcommand> [args]
```

Exit `0` = ok, `1` = a check failed, `2` = bad input or config (message on stderr). On exit `2`, stop
and show the user the message — don't work around it. Don't recompute versions or phases by hand.

## Resolve target version `V`

1. `git fetch origin <mainBranch>`, so `origin/<mainBranch>` is current.
2. Get `V`:
   - **Keyword or explicit arg** → `release_tool.py next <arg>` prints `V`. It validates an explicit
     version and rejects anything malformed. If it refuses a keyword because the current version is a
     prerelease (`1.0.0-rc.1`), ask the user for an explicit version.
   - **No arg** → `release_tool.py current --ref origin/<mainBranch>` prints `cur`, then
     `release_tool.py tag-status <cur>`:
     - `absent` → the user likely wants to tag the already-merged version: propose `V = cur`.
     - anything else → propose `V = ` the output of `release_tool.py next` (a patch bump) and
       **confirm with the user before proceeding**.

## Phase detection

Run `release_tool.py phase <V>` (it fetches `origin/<mainBranch>` itself). Its first line is one of:

- **`tag`** → the bump is already on `main` and the tag doesn't exist. Route to **Phase 2**.
- **`released`** → the tag already exists (local or origin), so this version is released. Stop and say
  so (retagging is a separate, destructive op, out of scope).
- **`bump`** → the bump isn't on `main` yet. Route to **Phase 1**. If a second line `open-pr <N>`
  follows, a release PR is already open: tell the user to merge PR `N`, then re-run to tag. Don't open
  a duplicate.

State the resolved version, the detected phase, and what will happen, before routing.

## Route

- **Phase 1** → run the **`axc-cut-release-bump`** skill with version `V`.
- **Phase 2** → run the **`axc-cut-release-tag`** skill with version `V`.

The router itself performs no git mutations — every change happens inside the delegated sub-skill,
which re-reads the config and repo state independently.

## What this skill does NOT do

- **Does not act beyond routing.** All mutations (bump, commit, PR, tag, push) live in the sub-skills.
- **Does not pick a phase silently.** Always states the resolved version and detected phase first.
- **Does not push to `main`, merge PRs, or retag.** Those guarantees are enforced by the sub-skills.

## Implementation hints

- Run independent read-only checks together in one message.
- Keep messages tight: state version, phase, action. The user is cutting a release, not reading a tutorial.
