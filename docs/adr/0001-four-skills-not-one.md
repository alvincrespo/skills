# ADR 0001: Four skills, not one

## Status
Accepted

## Context
The original ask was a single "bootstrap a GitHub project" capability,
covering repo creation, labels, milestone, project board, and issue
creation from a plan. Building it as one skill was the simplest first
instinct.

## Decision
Split into four: `project-epic-planner`, `github-repo-init`,
`github-labels-setup`, `github-project-bootstrap`.

## Reasoning
Repo creation and issue-bootstrapping are genuinely separate concerns —
sometimes a repo already exists and only needs issues populated onto it.
This isn't hypothetical: the `pr-agent` repo that produced this one had to
be deleted and recreated mid-stream while debugging the bootstrap script,
entirely independent of the issue content it would eventually hold.

Labels are useful completely standalone — "set up my standard labels on
this repo" is a complete request with no milestone or project board
involved. Milestone creation, project-board creation, and issue creation
are NOT similarly separable: each depends on the previous step already
existing (an issue can't attach to a milestone that doesn't exist yet,
can't be added to a board that isn't linked yet). Splitting those three
into separately-triggered skills would move that ordering dependency from
"the script enforces it" to "the user or Claude has to remember the right
order every time" — a worse place for it to live, given how many subtle
ways this exact sequence broke in practice before the underlying script
was correct: a rejected `state=all` query parameter, `gh api` silently
switching to POST because `-f` flags were present, `--milestone` wanting a
title instead of a number, and a missing project-to-repo link step. Four
separate, real bugs, all within one three-step sequence.

## Consequences
`github-project-bootstrap` internally calls `github-labels-setup`'s script
as a first step, rather than either duplicating label logic or requiring
a separate manual trigger every time a project gets bootstrapped.
