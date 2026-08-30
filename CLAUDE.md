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

No `package.json`-synced versioning. These skills are Python-scripted, not
JS-tooled, and there's no other reason for a `package.json` to exist here.
`.claude-plugin/plugin.json`'s `version` field is the sole source of truth.
