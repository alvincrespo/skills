# ADR 0002: Invocation control on the two GitHub-acting skills

## Status
Accepted

## Context
`github-repo-init` and `github-project-bootstrap` both create real,
externally visible GitHub artifacts (repositories, issues, labels,
milestones, project boards) with only partly reversible consequences —
deleting a populated repo or a project board is possible but destructive
and easy to regret. `project-epic-planner` and `github-labels-setup` are
lower-stakes: a plan is just a reviewable document until something else
acts on it, and labels are trivially editable or deletable without
collateral damage.

## Decision
`github-repo-init` and `github-project-bootstrap` are marked
`disable-model-invocation: true` in their `SKILL.md` frontmatter.
`project-epic-planner` and `github-labels-setup` remain model-invoked.

## Reasoning
Model-invocation means Claude can decide, on its own, from conversational
context, to fire a skill — appropriate for low-stakes, easily reversible
actions, wrong for actions that touch a real GitHub account with
consequences a person should explicitly opt into every time. This mirrors
a pattern already used elsewhere in this project's own tooling: the
`pr-agent` agent defaults to a dry-run mode for exactly the same reason —
irreversible or hard-to-reverse actions get an explicit opt-in, not an
inferred one.

## Consequences
A user must explicitly ask for repo creation or project bootstrapping in
so many words; Claude will never infer that intent and act on it
unprompted, even if the surrounding conversation strongly implies it.
