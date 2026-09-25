---
name: github-repo-init
description: Create a new GitHub repository from the current project directory's contents, push it, and set its topics. Use when the user explicitly says "create a new GitHub repo", "init a repo for this project", "bootstrap a new repository", "push this project to GitHub as a new repo", or otherwise directly asks to create and push a new GitHub repository — never inferred from surrounding conversation. Creates a real, only partly reversible GitHub artifact, so it requires an explicit, in-the-moment request every time.
disable-model-invocation: true
---

# GitHub Repo Init

Create a GitHub repository from the current directory's contents, push it,
and set its topics — via this skill's `scripts/setup_repo.sh`.

Per `docs/adr/0002-invocation-control-on-github-actions.md`, this skill is
marked `disable-model-invocation: true`: it creates a real, externally
visible GitHub repository, which is only partly reversible (deleting a
populated repo is possible but destructive and easy to regret). Claude
must never fire this skill from inferred conversational context — only run
it when a human explicitly asks, in so many words, in the current turn.

## Invocation

Run with the project to be published as the current working directory
— not from an empty directory, and not from this skill's own folder. Call
the script by its path inside this skill:

```bash
${CLAUDE_SKILL_DIR}/scripts/setup_repo.sh <owner>/repo-name \
    [--description "..."] [--topics "a,b,c"]
```

`<owner>/repo-name` is required; the script exits with a usage message if
it's missing.

### `--description`

Repo description passed to `gh repo create --description`. It must be a
single line: a description containing a control character (such as a
newline from a wrapped paste) is rejected before anything is created,
since GitHub would reject it only after the local `git init` and commit.

- Default: `"A small, growing collection of Claude Skills for real
  engineering workflows."`

### `--topics`

Comma-separated topics passed to `gh repo edit --add-topic` (one
`--add-topic` per entry). Whitespace around each entry is trimmed and empty
entries are dropped; a list with no non-empty topics is rejected before
anything is created.

- Default: `claude-skills,claude-code,ai-agent-tooling,github-automation`

Omitting either flag falls back to its documented default above rather
than erroring.

## What the script does

1. Checks local git state *before* creating anything on GitHub (because
   `gh repo create` creates the remote repo first, a later local failure
   would leave an empty repo behind):
   - No `.git`: runs `git init`, `git add -A`, and an initial commit
     (`Initial commit`).
   - Existing `.git`: used as-is, not re-initialized. The script exits
     with an error if it has no commits yet or already has an `origin`
     remote. Uncommitted changes produce a warning — they are not pushed,
     so commit anything that should be published first.
2. Runs `gh repo create <owner>/repo-name --public --description "..."
   --source=. --remote=origin --push`, creating the repo from the current
   directory's contents and pushing it in one step.
3. Runs `gh repo edit <owner>/repo-name` with one `--add-topic` per entry
   in `--topics`, setting the repo's topics.
4. Prints the new repo's URL, a pointer to run the `github-labels-setup`
   skill next, and the manual follow-up items below.

Requires the `gh` CLI (authenticated) and `git`.

## Manual follow-up (intentionally not automated)

The script's final output calls out two things it deliberately does
*not* do:

- **Branch protection on `main`** — not set up, since there's no CI check
  yet to require as a condition.
- **A pre-push secret scan** of the initial commit (e.g. `gitleaks` or
  `trufflehog`) — run this yourself before trusting the content is safe on
  a public remote.

These stay manual on purpose rather than being folded into the script.

## Next step

Once the repo exists, run the `github-labels-setup` skill next to apply
this project's label taxonomy to it.
