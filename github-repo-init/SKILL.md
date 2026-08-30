---
name: github-repo-init
description: Create a new GitHub repository from the current project directory's contents, push it, and set its topics. Use when the user explicitly says "create a new GitHub repo", "init a repo for this project", "bootstrap a new repository", "push this project to GitHub as a new repo", or otherwise directly asks to create and push a new GitHub repository — never inferred from surrounding conversation. Creates a real, only partly reversible GitHub artifact, so it requires an explicit, in-the-moment request every time.
disable-model-invocation: true
---

# GitHub Repo Init

Create a GitHub repository from the current directory's contents, push it,
and set its topics — via `github-repo-init/scripts/setup_repo.sh`.

Per `docs/adr/0002-invocation-control-on-github-actions.md`, this skill is
marked `disable-model-invocation: true`: it creates a real, externally
visible GitHub repository, which is only partly reversible (deleting a
populated repo is possible but destructive and easy to regret). Claude
must never fire this skill from inferred conversational context — only run
it when a human explicitly asks, in so many words, in the current turn.

## Invocation

Run from inside the project directory to be published — the one
containing this `github-repo-init/scripts/` folder and the rest of the
project's contents. Not from an empty directory.

```bash
./github-repo-init/scripts/setup_repo.sh <owner>/repo-name \
    [--description "..."] [--topics "a,b,c"]
```

`<owner>/repo-name` is required; the script exits with a usage message if
it's missing.

### `--description`

Repo description passed to `gh repo create --description`.

- Default: `"A small, growing collection of Claude Skills for real
  engineering workflows."`

### `--topics`

Comma-separated topics passed to `gh repo edit --add-topic` (one
`--add-topic` per entry).

- Default: `claude-skills,claude-code,ai-agent-tooling,github-automation`

Omitting either flag falls back to its documented default above rather
than erroring.

## What the script does

1. Checks for an existing `.git` in the current directory. If none exists,
   runs `git init`, `git add -A`, and an initial commit
   (`Initial commit: skills repo scaffolding + tracker`). If `.git`
   already exists, it's used as-is — not re-initialized.
2. Runs `gh repo create <owner>/repo-name --public --description "..."
   --source=. --remote=origin --push`, creating the repo from the current
   directory's contents and pushing it in one step.
3. Runs `gh repo edit <owner>/repo-name` with one `--add-topic` per entry
   in `--topics`, setting the repo's topics.
4. Prints the new repo's URL, a pointer to run the `github-labels-setup`
   skill next, and the manual-follow-up items below.

Requires the `gh` CLI (authenticated) and `git`.

## Manual follow-up (intentionally not automated)

The script's final output calls out three things it deliberately does
*not* do:

- **Branch protection on `main`** — not set up, since there's no CI check
  yet to require as a condition.
- **A pre-push secret scan** of the initial commit (e.g. `gitleaks` or
  `trufflehog`) — run this yourself before trusting the content is safe on
  a public remote.
- **`.claude-plugin/plugin.json` and `marketplace.json`** — deliberately
  not created here. Their schema needs confirming against current Claude
  Code plugin documentation, not assumed from memory or a similar-looking
  example; that's a separate, later piece of work.

These stay manual on purpose rather than being folded into the script.

## Next step

Once the repo exists, run the `github-labels-setup` skill next to apply
this project's label taxonomy to it.
