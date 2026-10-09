# CLAUDE.md — how this repo is maintained

Skills live as flat top-level folders, with no bucket subdirectories.
`docs/adr/0006-stay-flat-at-nine-skills.md` records why, lists every path
that assumes the flat layout, and says when to revisit: more than 15
skills in `plugin.json`, or two skills in different domains needing the
same folder name.

Every finished skill must have:
- an entry in the top-level `README.md`, its name linked to its `SKILL.md`
- an entry in `.claude-plugin/plugin.json`'s `skills` array

A skill still being built or iterated on should not appear in either.
That's the entire "promoted" distinction from larger skills repos, right-
sized down to "is it done or not" for a small repo.

**Invocation control matters here.** `github-repo-init` and
`github-project-bootstrap` create real GitHub artifacts with only partly
reversible consequences. Both must set `disable-model-invocation: true`
in their `SKILL.md` frontmatter — reachable only when a human explicitly
asks, never inferred by Claude from conversational context. `axc-og-cards`
sets it too, because every run can spend real money on image generation
(`docs/adr/0003-axc-og-cards-node-and-cost-controls.md`).
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
or renaming one. It replaces existing symlinks but refuses to touch a real
directory at a link's path (a copy installed by hand): it skips it, says
so, and exits 1, so move the copy aside and re-run.
`scripts/test-link-skills.sh` tests this against a throwaway `HOME`.

Standalone `.skill` packaging (`scripts/package-standalone-skills.sh`) is
only for skills that are fully self-contained and model-invoked. A skill
that uses a sibling skill's code, sets `disable-model-invocation`, or needs
installed dependencies (`axc-og-cards`' npm packages) ships only via the
plugin or the skills CLI: a `.skill` install can't bring its siblings or
dependencies along, or enforce the flag. Add a new skill to the script's
`STANDALONE` list only if none of that applies.

No `package.json`-synced versioning. The skills are Python-scripted except
`axc-og-cards`, which is Node (ADR 0003) and has its own `package.json`: a
private, unversioned list of its runtime dependencies, not a version source.
`.claude-plugin/plugin.json`'s `version` field is the sole source of truth.

`axc-og-cards` has an end-to-end harness in `scripts/e2e/axc-og-cards/` (see
its README). It clones a test site, runs the skill in headless Claude
sessions and writes a report. The free cases need no API key and can't
spend; the paid cases cost about $0.40 of image generation per full run.
Run it before releasing a change to that skill, with the key in the
environment, never on the command line.

Cut releases with `/axc-cut-release`, configured by `.claude/release.json`:
the first run opens a PR bumping `plugin.json`'s `version`; after it
merges, the second run preflights and pushes the `vX.Y.Z` tag. The tag
triggers `.github/workflows/release.yml`, which checks the tag against
`plugin.json`, runs the tests (Python, and `axc-og-cards`' Node tests under
`npm ci --prefix axc-og-cards`), packages the standalone skills, and
publishes the GitHub Release. Don't create releases by hand. If you change
the checks, the packaging script, or the workflow, keep `release.json`'s
`checks` and `workflowChecks` in sync with them.
