# CLAUDE.md — how this repo is maintained

Skills live as flat top-level folders — no bucket subdirectories yet (see
`docs/adr/0001-four-skills-not-one.md` and the "defer until there's an
actual second reason" note in `PROJECT_PLAN.md`). Revisit this once a
second, genuinely different domain of skill shows up — not preemptively.

Every finished skill must have:
- an entry in the top-level `README.md`, its name linked to its `SKILL.md`
- an entry in `.claude-plugin/plugin.json`'s `skills` array

A skill still being built or iterated on should not appear in either.
That's the entire "promoted" distinction from larger skills repos, right-
sized down to "is it done or not" for a four-skill repo.

**Invocation control matters here.** `github-repo-init` and
`github-project-bootstrap` create real GitHub artifacts with only partly
reversible consequences. Both must set `disable-model-invocation: true`
in their `SKILL.md` frontmatter — reachable only when a human explicitly
asks, never inferred by Claude from conversational context.
`project-epic-planner` and `github-labels-setup` are lower-stakes
(planning is reversible, labels are trivially editable) and stay
model-invoked. See `docs/adr/0002-invocation-control-on-github-actions.md`.

Run `claude plugin validate . --strict` after touching either
`.claude-plugin/plugin.json` or `.claude-plugin/marketplace.json`. Do not
guess their schema from memory or from a similar-looking example — confirm
against current Claude Code plugin documentation before writing either
file. This repo already hit real, non-obvious API/CLI behavior four
separate times while building the underlying bootstrap script by assuming
documented-elsewhere behavior applied directly; treat plugin manifest
schemas with the same caution.

To (re)link every skill into the local harness skill directories
(`~/.claude/skills`, `~/.agents/skills`), run `scripts/link-skills.sh`. It
discovers skill folders by presence of a `SKILL.md`, so it needs no edits
when a new skill folder is added — just re-run it after adding, removing,
or renaming one.

Standalone `.skill` packaging (`scripts/package-standalone-skills.sh`) is
only for skills that are fully self-contained and model-invoked. A skill
that uses a sibling skill's code, or sets `disable-model-invocation`,
ships only via the plugin: a `.skill` install can't bring its siblings
along or enforce the flag. Add a new skill to the script's `STANDALONE`
list only if neither applies.

No `package.json`-synced versioning. These skills are Python-scripted, not
JS-tooled, and there's no other reason for a `package.json` to exist here.
`.claude-plugin/plugin.json`'s `version` field is the sole source of truth.

Cut releases with `/axc-cut-release`, configured by `.claude/release.json`:
it opens a PR bumping that `version` field, then, once merged, runs
preflight and pushes the `vX.Y.Z` tag. The tag triggers
`.github/workflows/release.yml`, which checks the tag matches the version,
runs the tests, packages the standalone skills, and publishes the GitHub
Release. Don't create releases by hand.

Cut releases with `/axc-cut-release`, configured by `.claude/release.json`:
the first run opens a PR bumping `plugin.json`'s `version`; after it
merges, the second run preflights and pushes the `vX.Y.Z` tag. The tag
triggers `.github/workflows/release.yml`, which checks the tag against
`plugin.json`, runs the tests, packages the standalone skills, and
publishes the GitHub Release. If you change the checks, the packaging
script, or the workflow, keep `release.json`'s `checks` and
`workflowChecks` in sync with them.
