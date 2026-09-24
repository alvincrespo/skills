# alvincrespo/skills

A small, growing collection of Claude Skills for real engineering
workflows — starting with a pipeline for turning a project idea into a
fully-tracked, live GitHub Project board: plan the epics and stories,
initialize the repo, set up labels, and bootstrap the board itself.

## Skills

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

Or install the skills individually:

```bash
npx skills add alvincrespo/skills --agent claude-code
```

## License

MIT — see [LICENSE](./LICENSE).
