# ADR 0005: Invocation control on the release skills

## Status
Accepted

## Context
The four `axc-cut-release*` skills cut a release in two phases.
`axc-cut-release` is a router: it works out the target version and phase,
then hands off to `axc-cut-release-bump` (Phase 1: open a PR bumping the
version) or `axc-cut-release-tag` (Phase 2: run `axc-cut-release-preflight`,
then push the `vX.Y.Z` tag). The handoffs use the Skill tool, and that's
how the v0.2.0 release ran.

Pushing the tag triggers `.github/workflows/release.yml`, which publishes a
public GitHub Release. Under ADR 0002, an action like that should need an
explicit request (`disable-model-invocation: true`). But that flag stops
Claude invoking a skill, so it might also break the router's handoff.
Issue #80 tested this before deciding.

### Spike (2026-10-08, Claude Code 2.1.294)
Three project-level skills, in a scratch directory outside this repo:

| Skill | `disable-model-invocation` | Body |
|---|---|---|
| `spike-router` | `true` | Invoke `spike-control`, then `spike-target`, with the Skill tool, and report each reply or the refusal |
| `spike-control` | absent | Reply `SPIKE-CONTROL-RAN` |
| `spike-target` | `true` | Reply `SPIKE-TARGET-RAN` |

Run with `claude -p "/spike-router" --output-format stream-json --verbose`.
The slash command expanded in `-p` mode, so no interactive session was
needed.

| Step | Result |
|---|---|
| `/spike-router` (flagged, invoked by the user) | Ran |
| → `Skill(spike-control)` (no flag) | Ran: `SPIKE-CONTROL-RAN` |
| → `Skill(spike-target)` (flagged) | **Refused**: `Skill spike-target cannot be used with Skill tool due to disable-model-invocation. Ask the user to run /spike-target themselves — it cannot be invoked via the Skill tool. Do not replicate this skill's workflow by other means — it is reserved for explicit user invocation.` |

So:
1. A flagged skill can't be reached through the Skill tool, even from a
   skill the user invoked explicitly. Flagging `axc-cut-release-tag` would
   break the router's Phase 2 handoff.
2. A skill the user invoked can still hand off to an unflagged skill, so
   a flagged tag skill can still run `axc-cut-release-preflight`.
3. The refusal tells Claude not to recreate a flagged skill's workflow
   some other way. That rules out inlining the tag steps into the router,
   which would also mean maintaining them in two places.

## Decision
`axc-cut-release-tag` is the only release skill that pushes something
public, so it's the only one flagged. The router doesn't hand Phase 2
off. It stops and tells the user to run `/axc-cut-release-tag <V>`,
naming the exact version.

| Skill | `disable-model-invocation` | Why |
|---|---|---|
| `axc-cut-release` | absent | Only resolves the version and phase. Phase 1 hands off to the bump skill; Phase 2 hands back to the user. |
| `axc-cut-release-bump` | absent | Opens a PR, which is reversible (close it), and never pushes to `main` |
| `axc-cut-release-preflight` | absent | Read-only |
| `axc-cut-release-tag` | `true` | Pushes the tag that publishes a public GitHub Release |

## Reasoning
This follows ADR 0002's rule exactly: the irreversible, public step needs
an explicit request every time, and the reversible or read-only steps
don't. It costs one extra command per release, typing
`/axc-cut-release-tag 0.4.0` instead of having the router continue, which
is the same opt-in ADR 0002 asks for elsewhere.

Rejected alternatives:
- **Keep all four model-invoked** and rely on the tag skill's own gate
  (green preflight, then an explicit yes). #66's draft ADR takes that
  approach for `axc-dependabot-sweep`, with one approval up front. That
  works for Dependabot PRs, where the approval covers a batch Claude then
  works through. Here the irreversible step is a single action that can
  simply be left to the user, so there's no need for the exception.
- **Flag the router and inline the tag phase into it.** The refusal
  message says not to recreate a flagged skill's workflow by other means,
  and inlining would also duplicate the tag skill's steps.

## Consequences
- `/axc-cut-release <V>` in Phase 2 stops with the instruction to run
  `/axc-cut-release-tag <V>`. Phase 1 is unchanged.
- Claude can start Phase 1 on its own ("cut a release" in conversation),
  but the most it can do without an explicit request is open a PR.
- `axc-cut-release-tag` can't be reached through any other skill. The
  `/axc-cut-release-tag` command is the only way in.
- #99 applies this table to the four SKILL.md files, and adds a test that
  checks the frontmatter against it. If this table changes, that test has
  to change too. #99 also rewrites the router's "Route" section: Phase 2
  becomes "tell the user to run `/axc-cut-release-tag <V>`" instead of
  "run the `axc-cut-release-tag` skill". The router's SKILL.md describes
  the Phase 2 handoff in three places, and all three need changing: the
  frontmatter `description` ("delegates to … `axc-cut-release-tag`"), the
  intro's Phase 2 bullet, and "Route".
- `.claude/CLAUDE.md`'s invocation paragraph gains this sentence, after
  the one about `axc-og-cards`:

  > `axc-cut-release-tag` sets it too, because pushing the tag publishes a
  > public release; the other three release skills don't, and the router
  > hands Phase 2 back to you as `/axc-cut-release-tag <V>` instead of
  > invoking it (`docs/adr/0005-release-skills-invocation-control.md`).
