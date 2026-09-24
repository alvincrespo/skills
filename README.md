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
- [github-labels-setup](./github-labels-setup/SKILL.md) — create or update
  a repo's label taxonomy from a JSON config, idempotently.
- [github-project-bootstrap](./github-project-bootstrap/SKILL.md) — turn a
  JSON plan into a milestone, a linked Project (v2) board, and every
  epic/story issue. User-invoked only.

More are in progress: see [PROJECT_PLAN.md](./PROJECT_PLAN.md) and
[TRACKER.md](./TRACKER.md). A skill is listed here only once it's finished.

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

Install all four together. They reuse each other's code rather than
duplicating it: `github-project-bootstrap` runs `github-labels-setup`'s
script, and `project-epic-planner` validates plans with
`github-project-bootstrap`'s loader. Each expects the other to be
installed next to it.

### Standalone `.skill` files

Only `github-labels-setup` is available as a standalone `.skill` file,
because it's the only skill that works on its own. The two GitHub skills
also can't be packaged: they set `disable-model-invocation` so Claude
never creates repos or issues unprompted, and the `.skill` format has no
equivalent. To build it:

```bash
scripts/package-standalone-skills.sh   # writes dist/github-labels-setup.skill
```

## License

MIT — see [LICENSE](./LICENSE).
