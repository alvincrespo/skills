# alvincrespo/skills

A small, growing collection of Claude Skills for real engineering
workflows — starting with a pipeline for turning a project idea into a
fully-tracked, live GitHub Project board: plan the epics and stories,
initialize the repo, set up labels, and bootstrap the board itself.

## Skills

- [project-epic-planner](./project-epic-planner/SKILL.md) — turn a rough
  project idea into a reviewable epic/story plan with a real dependency
  graph, as JSON that `github-project-bootstrap` consumes plus a rendered
  markdown doc. Produces a document only.
- [github-repo-init](./github-repo-init/SKILL.md) — create a GitHub repo
  from the current project directory, push it, and set its topics.
  User-invoked only.
- [github-labels-setup](./github-labels-setup/SKILL.md) — create or update
  a repo's label taxonomy from a JSON config, idempotently.
- [github-project-bootstrap](./github-project-bootstrap/SKILL.md) — turn a
  JSON plan into a milestone, a linked Project (v2) board, and every
  epic/story issue. User-invoked only.
- [axc-og-cards](./axc-og-cards/SKILL.md) — generate a unique Open Graph
  card for each blog post. The text is rendered from your own fonts; only
  the illustration comes from a paid OpenRouter image model, with spend
  limited by a budget and recorded in a ledger. For Bridgetown sites; needs
  Node 20.9+ and an `OPENROUTER_API_KEY`. User-invoked only.
- [axc-cut-release](./axc-cut-release/SKILL.md) — cut a release in any
  project, driven by its `.claude/release.json`. Works out the version and
  which phase the release is in, opens the version-bump PR, and once that
  merges tells you the command to tag. Needs `git` and `gh`.
- [axc-cut-release-bump](./axc-cut-release-bump/SKILL.md) — open the
  version-bump PR (Phase 1): branch off `main`, bump every version file,
  run the build and test checks, commit, and open the PR. Never pushes to
  `main`.
- [axc-cut-release-preflight](./axc-cut-release-preflight/SKILL.md) —
  read-only safety checks before tagging: git state, the version files,
  the release workflow, then your lint, build, test and integrity
  commands. Ends in Ready, Mostly ready, or Blocked.
- [axc-cut-release-tag](./axc-cut-release-tag/SKILL.md) — run preflight,
  then push the annotated `vX.Y.Z` tag that triggers the release workflow,
  after an explicit yes. User-invoked only.
- [axc-dependabot-sweep](./axc-dependabot-sweep/SKILL.md) — clear a repo's
  open Dependabot PRs oldest first: review each bump, fix what the review
  finds, verify locally, wait for CI on the exact head SHA, then merge. Shows
  the ordered plan and gets one explicit yes before changing anything;
  `--dry-run` previews it. Needs `gh` and a `verify` command in
  `.claude/dependabot-sweep.json`.

The first four chain together: describe a project, review the generated plan, then
create the repo, apply labels, and bootstrap the issues. See
[PROJECT_PLAN.md](./PROJECT_PLAN.md) for the design.

The four `axc-cut-release*` skills work together through the repo's
`.claude/release.json`: `/axc-cut-release` works out the version and opens
the bump PR, and once you've merged it, `/axc-cut-release-tag <V>` runs
preflight and pushes the tag. A skill is listed here only once it's
finished.

## Install

This repo is its own Claude Code plugin marketplace. In Claude Code:

```
/plugin marketplace add alvincrespo/skills
/plugin install alvincrespo-skills@alvincrespo-skills
```

Or install the skills with the `skills` CLI:

```bash
npx skills add alvincrespo/skills --agent claude-code
```

The four GitHub-workflow skills should be installed together. They reuse
each other's code rather than duplicating it: `github-project-bootstrap` runs `github-labels-setup`'s
script, and `project-epic-planner` validates plans with
`github-project-bootstrap`'s loader. Each expects the other to be
installed next to it. `axc-og-cards` stands alone and can be installed on
its own. `axc-dependabot-sweep` is self-contained too, but it isn't
packaged as a `.skill`: it acts on GitHub and needs `gh`.

The four release skills (`axc-cut-release`, `axc-cut-release-bump`,
`axc-cut-release-preflight`, `axc-cut-release-tag`) should be installed
together as well: the bump and preflight skills run `release_tool.py` from
`axc-cut-release`'s folder, next to their own.

### Standalone `.skill` files

Only `github-labels-setup` is available as a standalone `.skill` file,
because it's the only skill that works on its own. The two GitHub skills
also can't be packaged: they set `disable-model-invocation` so Claude
never creates repos or issues unprompted, and the `.skill` format has no
equivalent. `axc-og-cards` can't be packaged either, for the same reason (it
spends money) and because it needs its npm dependencies. Nor can the four
release skills: they share the router's script, and `axc-cut-release-tag`
sets `disable-model-invocation` because it publishes a release. To build the one
that can be:

```bash
scripts/package-standalone-skills.sh   # writes dist/github-labels-setup.skill
```

## License

MIT — see [LICENSE](./LICENSE).
