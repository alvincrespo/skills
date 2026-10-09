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
- **An explicit version** — `0.3.0`, or a prerelease like `0.3.0-rc.1`. Must match
  `^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$`. Prerelease tags (containing `alpha`/`beta`/`rc`) are usually
  auto-flagged as prereleases by the release workflow — no extra handling here.
- **Nothing** — infer intent (see Phase detection). On a fresh cut, propose the next **patch** off
  the current version and confirm before doing anything.

## Resolve target version `V`

1. `git fetch origin <mainBranch>`, then read the version from `origin/<mainBranch>`'s
   `version.files[0].path` → call it `cur`. Use `git show origin/<mainBranch>:<path>` and extract the
   literal using `version.files[0].match` (the `{V}` placeholder marks where the version sits). Read
   from `origin/<mainBranch>`, not the working tree, so a dirty/stale local checkout can't skew the math.
2. Compute `V`:
   - Keyword arg → bump `cur` (`patch`: z+1; `minor`: y+1, z=0; `major`: x+1, y=0, z=0).
   - Explicit arg → `V = arg` (validate the regex above; reject otherwise).
   - No arg → if `cur` is **not yet tagged** (`<tagFormat>` missing locally and on origin), infer the
     user wants to tag the already-merged version: `V = cur`. Otherwise propose `V = patch-bump(cur)`
     and **confirm with the user before proceeding**.

## Phase detection

Compare `V` to `cur` (= `origin/<mainBranch>`'s version):

- **`cur == V`** → the bump is already on `main`. Route to **Phase 2**. But first: if tag
  `<tagFormat>` already exists (local or origin), this version is already released — stop and say so
  (retagging is a separate, destructive op, out of scope).
- **`cur != V`** → the bump isn't on `main` yet. Route to **Phase 1**. First check for an existing
  open release PR (`gh pr list --head <commit.branch> --state open`). If one exists, don't open a
  duplicate — tell the user to merge it, then re-run to tag.

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

- Read `origin/<mainBranch>`'s version without checking it out: `git show origin/<mainBranch>:<path>`,
  then apply the `match` pattern. No extra network round trip after `git fetch`.
- Tag existence check covers both local and remote: `git tag -l <tagFormat>` and
  `git ls-remote --tags origin <tagFormat>`.
- Semver bump math: split `cur` on `.`; a prerelease suffix on `cur` makes keyword bumps ambiguous —
  if `cur` has a `-suffix`, ask for an explicit `V` rather than guessing.
- Run independent read-only checks (fetch, tag lookup, PR lookup) together in one message.
- Keep messages tight: state version, phase, action. The user is cutting a release, not reading a tutorial.
