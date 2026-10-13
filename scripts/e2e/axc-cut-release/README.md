# axc-cut-release end-to-end test

Runs the release skills for real, in a throwaway **private GitHub repo** on your account, and
checks the repo ends up in the right state. It drives real headless Claude sessions, so it costs
tokens. Run it by hand before releasing a change to the release skills; it is not meant for CI.

Check the environment and print the plan, creating nothing:

```bash
python3 scripts/e2e/axc-cut-release/run.py --dry-run
```

The full run:

```bash
python3 scripts/e2e/axc-cut-release/run.py
```

Needs `git`, `gh` and `claude`, all logged in, and the `delete_repo` scope on the `gh` token
(`gh auth refresh -h github.com -s delete_repo`). The run checks for it up front, so it never
creates a repo it couldn't remove.

| Flag | Effect |
|---|---|
| `--dry-run` | check the environment and print the plan |
| `--happy-path-only` | run just bump -> merge -> tag; skip the three extra scenarios |
| `--keep` | skip teardown, to inspect the folder and repo afterwards |
| `--ssh` | use an SSH remote instead of HTTPS |
| `--model M` | model for the Claude sessions |
| `--max-budget-usd N` | spend cap per Claude session (default 3) |
| `--timeout-min N` | kill a session after N minutes (default 15) |

A full run is six Claude sessions (two with `--happy-path-only`), about $0.60 in total at the
earlier runs' prices.

Exit codes: `0` all checks passed, `1` a check failed or teardown didn't finish, `2` the run
aborted (setup failed, or a git/gh call errored mid-test), `130` interrupted.

## What a run does

1. **Set up.** Checks `tmp/` is gitignored (creates it if missing), makes
   `tmp/axc-cut-release-e2e-<timestamp>/`, `git init`s it with a README, creates a private repo of
   the same name, and copies the four skills into the project's `.claude/skills/` (excluded from git).
2. **Test.** Pushes an initial commit, edits the README and pushes again. Then the happy path:
   `/axc-cut-release patch` should open a bump PR; the script merges it through the API (the step a
   human does); `/axc-cut-release 0.1.1` should push the tag. Each stage checks the repo's state,
   and which skills the agent invoked (the router must delegate to the bump skill, and to the tag
   skill, which must run preflight first).
   Then three extra scenarios reuse the project (skip them with `--happy-path-only`):

   | Scenario | Prompt | Must prove |
   |---|---|---|
   | Already released | `/axc-cut-release 0.1.1` again | the router stops without delegating, says it's released, and nothing on the remote changes |
   | Preflight blocks | `/axc-cut-release-preflight 0.1.1` | verdict is **Blocked**, cites `v0.1.1`, and nothing changes (remote, HEAD, working tree) |
   | Confirmation gate | bump and merge `0.1.2`, then `/axc-cut-release 0.1.2` with the note that nobody will reply | preflight runs, the agent asks about pushing the tag and stops, and no tag is created locally or pushed |

   The gate scenario doesn't tell the agent to answer "no": it tells it nobody will reply, so a
   skill that waits for the user ends its turn with the question, and one that doesn't would tag.
3. **Tear down**, even on failure or Ctrl-C: deletes the folder and the GitHub repo. Logs stay in
   `tmp/e2e-logs/<run>/` (the prompt, raw stream and final message of each session, plus `run.log`).

The result also lists **tool errors**: tool calls the agent had refused or that failed, per
session. They are friction the agent works around (a denied command is retried), not failures, so
they never change the pass/fail outcome. Real problems are grouped with a repeat count; errors that
are expected given how the project is built (the 404 for `gh run list --workflow=release.yml`,
because the workflow is at `ci/release.yml`) are counted but not listed. Add to
`EXPECTED_TOOL_ERRORS` in `harness/config.py` when a new expected one appears. The full stream is
in `tmp/e2e-logs/<run>/<phase>.stream.jsonl`.

If a run is killed hard (power loss, `kill -9`) a repo can be left behind. They are all named
`axc-cut-release-e2e-*`; delete one with `gh repo delete <you>/<name> --yes`.

The project's "release workflow" is `ci/release.yml`, outside `.github/`, so pushing the tag
triggers nothing on GitHub. Phase 2's prompt tells the agent to answer yes at the tag
confirmation, so this checks the tag flow, not that the gate stops a "no".

## Layout

```
run.py              entry point (adds this folder to sys.path, calls harness.cli.main)
harness/
  cli.py            options, orchestration, exit codes
  config.py         constants, Options, Paths, exit codes
  preflight.py      checks before anything is created
  sandbox.py        the throwaway project: set up on entry, always torn down on exit
  scenario.py       which scenarios run, in what order, and what each must prove
  stages.py         reusable steps (bump PR, merge, tag), each taking a `Release`
  fixture.py        what goes in the project (VERSION, release.json, workflow stub, skills)
  claude_runner.py  one headless Claude session
  github.py         a thin `gh api` client (REST only)
  git_repo.py       git operations on the project
  shell.py          the one place plain subprocesses run
  report.py         records check results
  log.py            console + file logging
  context.py        state shared by the stages
  errors.py         HarnessError
tests/
  test_harness.py   tests for the harness itself
  fakes/gh, claude  stand-ins used by those tests
```

Dependencies point one way: `cli` -> `scenario`/`sandbox` -> the clients (`github`, `git_repo`,
`claude_runner`) -> `shell`. Nothing below `cli` reads `sys.argv`, and there is no module-level state.

## Changing it

- **Add a check:** add `self.report.check(name, ok, detail)` to the scenario or stage it belongs
  to. A failed check is recorded and the run continues; only infrastructure failures raise
  `HarnessError` (which aborts the run, still running teardown).
- **Add a scenario:** write a method on `ReleaseScenario` (see `already_released_stops`) and call it
  from `run()`. Build it from the steps in `stages.py`; a new release version goes in `config.py`.
- **Add a step:** write a method on `Stages` that takes a `Release`.
- **Add a GitHub read:** add a method to `GitHub`; keep it REST (`gh api`).
- **Change what the project contains:** edit `fixture.py`. If the skills need a new config key,
  it goes in `write_fixture`.

## Testing the harness

```bash
python3 -m unittest discover -s scripts/e2e/axc-cut-release/tests
```

These use no network, GitHub or Claude: `tests/fakes/gh` is backed by local bare repos (git's
`insteadOf` redirects `https://github.com/` to them) and `tests/fakes/claude` performs the two
phases using the project's real `release_tool.py`. They cover setup, every kind of failure
(a failed check, a failed session, a mid-test `gh` error, Ctrl-C, a failed repo delete),
teardown, the safety rules that stop it deleting anything it didn't create, the tool-error summary,
and each extra scenario both passing and failing (a router that carries on when released, a
preflight that doesn't block, a tag pushed without waiting for confirmation, work done without
invoking the skills), so a check that can't fail would show up. They don't test the
skills; only a real run does that.
