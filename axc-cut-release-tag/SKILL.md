---
name: axc-cut-release-tag
description: Phase 2 of a release — preflight, then push the `vX.Y.Z` tag that triggers publishing. Driven by the repo's `.claude/release.json`. Confirms main carries the target version, runs `axc-cut-release-preflight`, gets explicit user confirmation (naming the publish consequence), then creates and pushes the annotated tag. Never tags without a green preflight and a yes. Use when the user says "/axc-cut-release-tag", or invoked by the `axc-cut-release` router for Phase 2.
---

# Release Tag (Phase 2)

Pushes the tag that triggers the release workflow. This ends in publishing the release artifact, so
it always runs preflight and gets explicit confirmation before the push.

## Adapter config (`.claude/release.json`)

Read `.claude/release.json` first (Read tool). If missing, auto-detect and offer to write one — see
`axc-cut-release` for defaults. Fields used here: `mainBranch`, `version.files[]` (`path` + `match`),
`release.tagFormat`, `release.workflow`, `release.artifact`. `{V}` = version without the `v` prefix.

## Argument

The target version `V` (e.g. `0.3.0`). If omitted, read it from `version.files[0]` and confirm.

## Steps

1. Be on `mainBranch`, clean, and up to date:
   - `git checkout <mainBranch> && git pull --ff-only origin <mainBranch>`
   - Confirm **every** `version.files[]` literal equals `V`. If not, something's off (PR not merged,
     or wrong `V`) — stop and explain.
2. **Run the `axc-cut-release-preflight` skill** with version `V`. Proceed only on a green (✅)
   verdict. On 🟡, surface the warnings and ask the user whether to continue. On ❌, stop.
3. **Confirm with the user** before pushing — name the consequence by `release.artifact`:
   - `npm` → "Pushing `<tagFormat>` triggers the release workflow, which publishes `<repo>@<V>` to
     npm. This can't be undone. Push the tag?"
   - `github-release` → "Pushing `<tagFormat>` triggers the release workflow, which builds the
     binaries and publishes the `<V>` GitHub Release. Push the tag?"
   - other → name the artifact from config.
4. On yes (substitute `{V}` in `tagFormat`):
   `git tag <tagFormat> -m "Release v<V>"`
   `git push origin <tagFormat>`
5. Report: the tag is pushed and CI is now building/publishing. Link the runs:
   `gh run list --workflow=<release.workflow basename> --limit 1`
   (or print `https://github.com/<repo>/actions/workflows/<release.workflow basename>`). Offer to
   watch it (`gh run watch`).

## What this skill does NOT do

- **Does not tag without a green preflight.** Step 2 always runs first; ❌ stops the skill.
- **Does not push without explicit confirmation.** Step 3 names the irreversible consequence.
- **Does not retag or force-push.** If `<tagFormat>` already exists, preflight blocks — re-releasing
  a version is a deliberate, destructive operation outside this skill's scope.
- **Does not publish manually.** Only the tagged CI workflow publishes, so every release goes through
  the same gated path.
