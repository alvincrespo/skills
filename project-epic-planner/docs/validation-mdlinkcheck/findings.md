# Validation run: `mdlinkcheck` (issue #21)

A full plan generated with `project-epic-planner` for a project unrelated
to `pr-agent` or this repo, then graded against the five rules in
[`ticket-quality-rules.md`](../../references/ticket-quality-rules.md)
**without rewriting any ticket**. The plan files here are exactly as
generated; nothing was changed after grading.

| File | What it is |
|---|---|
| [`mdlinkcheck-template.yaml`](./mdlinkcheck-template.yaml) | Step 1: the project template |
| [`mdlinkcheck-plan.json`](./mdlinkcheck-plan.json) | Step 3: the plan, in `github-project-bootstrap`'s `--data` format |
| [`mdlinkcheck-plan.md`](./mdlinkcheck-plan.md) | Step 4: rendered by `render_plan.py` |

**Project:** `mdlinkcheck`, a Python CLI and GitHub Action that checks
Markdown docs for broken internal links, anchors, and external URLs.
Chosen because it's small but exercises every rule: parallel checking
paths (Rule 5), user-facing config (Rule 4), and a release that has to be
proven against real repos (Rules 3 and 4).

**Result:** 7 epics, 22 stories, 1 release-validation issue (30 issues).
`render_plan.py` passed it on the first run; the template passed its
validation rules.

## Caveat on this run

The same model that wrote `ticket-quality-rules.md` and `SKILL.md`
generated and graded this plan, in a session that had just been working
on those rules. That's the most favorable setting the skill will ever
get, so treat the passes below as an upper bound. A cold run (a fresh
session given only the skill) is the real test; see
[Recommendations](#recommendations).

## Grades

### Rule 1: One story per independently testable unit: **pass**

Stories are split along real seams: one per checker behavior (slugs,
file resolution, anchors), one per HTTP behavior (single URL, retries,
concurrency), separate text and JSON reporters. Each can be closed while
its siblings are open.

Borderline: *Wire up the CLI and exit codes* bundles argument parsing, the
end-to-end flow, `ignore_*` filtering, and exit codes. It has one coherent
test surface (`main()`), so it's defensible, but ignore filtering could
have been its own story.

### Rule 2: Every ticket is self-contained: **partial fail**

No ticket points to outside context (no "as discussed" or similar), and
most name exact signatures, file shapes, commands, and formats. But five
tickets would leave a cold implementer guessing, and one of those guesses
publishes to the wrong place:

1. **Publish to PyPI on version tags: contradictory verification.**
   `release.yml` publishes to PyPI on every `v*` tag. The acceptance
   criterion then says to verify with a pre-release tag `v0.1.0rc1` against
   **TestPyPI**. That tag matches `v*`, so following the ticket as written
   publishes the release candidate to real PyPI, and the ticket never says
   how TestPyPI publishing is configured (a separate job, a
   `repository-url`, a different tag pattern).
2. **Wire up the CLI and exit codes: an untestable criterion.** It
   requires an integration test asserting that an ignored URL is "never
   requested (mock transport asserts zero calls)". But the function it
   calls is defined in *Check many URLs concurrently, once each* as
   `run_external_checks(...)`, a literally elided signature, and neither
   it nor `check_urls()` takes a transport or client. The ticket requires
   a test seam it never defines.
3. **Extract reference-style links and autolinks: an unworkable
   mechanism.** Reference links are to be told apart "by checking whether
   the source text at that position uses `][` or `[ref]` form". Checked
   against markdown-it-py after grading: inline `link_open` tokens have
   `map=None`, and a reference link's token is identical to an inline
   link's (`markup=''`, `href` already resolved), so there is no
   "position" to check. The ticket states a mechanism without verifying
   that it exists. (Its autolink mechanism, `markup == "autolink"`, *is*
   correct.)
4. **Load and validate `.mdlinkcheck.toml`: an ambiguous default.**
   `root = "."` is "relative to the config file", but when no config file
   exists (the default case), what `root` is relative to (the working
   directory, or `PATH`) is never stated. Every root-absolute link
   depends on this.
5. **Write the README: a check that passes trivially.** *Missed by my
   grading; caught by the PR's code review.* Its criterion says the
   README's own links must pass `mdlinkcheck README.md --no-external` in
   CI. But the plan only defines `PATH` as a directory:
   `find_markdown_files()` globs `**/*.md` under it, which matches nothing
   under a file, and config discovery looks for `<PATH>/.mdlinkcheck.toml`.
   Built as written, that CI step checks 0 links and passes even when the
   README has broken links. The ticket relies on single-file input that
   no ticket defines.

Smaller: `expected.json` paths are fixture-root-relative, the text
reporter's paths are cwd-relative, and `Link.source` is never specified
as absolute or relative, so the integration test has to invent the
conversion.

### Rule 3: Testing is an acceptance criterion on every leaf story: **pass**

Every code story has a named, specific test: what's mocked and what's
asserted (e.g. "a transport returning 503, 503, 200 ends `ok` after
exactly 3 requests"). The four stories without "Unit test"/"Integration
test" wording (CI workflow, PyPI release, GitHub Action, README) are
infrastructure. Each still has a checkable verification: a
deliberately red CI run, a self-test workflow asserting failure and
success, and a test that cross-checks `--help` against the README. Two
of those verification steps are flawed: the PyPI story's, and the
README's self-check, which can't fail. Both are counted under Rule 2
above, since the test *exists* but can't do its job as specified.

### Rule 4: Runtime parameters, never hardcoded: **pass**

The release-validation issue takes both target repos as runtime choices,
requires two unrelated ones, and asks for them (with SHAs) to be recorded
in the issue. The README story leaves the Action's owner as `<owner>`. No
hardcoded owner, repo, or absolute path appears anywhere in the plan.
Every tunable (timeouts, concurrency, retries, include/exclude, ignores)
is a config value with a documented default.

### Rule 5: A real dependency graph: **pass, with one over-constraint**

The graph isn't a chain. Internal and External checking are parallel after
Extraction. Configuration depends only on Setup and says it's parallel-safe
with Extraction and both checkers. Every `depends_on` has a "because" in
the epic body.

Over-constrained: CLI & Reporting is blocked by External Link Checking,
but the `--no-external` path and both reporters don't need it. The same
goes for Distribution: its build/`twine check` CI step doesn't depend on
the CLI being finished. This is partly structural: `depends_on` is
epic-level, so when only some of an epic's stories need a blocker, the
whole epic waits. The rules doc doesn't say what to do about that.

## Verdict

Quality did **not** fully hold without manual correction. Rules 1, 3 and
4 held; Rule 5 held with an over-constraint. Rule 2 needed correction in
five tickets, one of which would publish a release candidate to real PyPI
if followed literally. Per this issue's criteria, that's a signal to
revise the reference doc, not just this output. None of these failures
is a phrase the current Rule 2 check searches for. They're gaps *inside*
tickets that look self-contained.

The fifth gap was found by an independent code review of this PR, not by
the grading pass. That's direct evidence for the same-author bias caveat
above: the author of the rules, grading their own plan, missed a
failure the rules should have caught.

## Recommendations

Revise `ticket-quality-rules.md`:

- **Rule 2 check:** add "can every acceptance criterion be *executed*
  using only what the ticket defines?" Concretely:
  - A test that needs a seam (an injectable transport, an env var, a
    fixture) names that seam in a signature the ticket spells out.
  - No elided signatures (`(...)`).
  - Every default says what it's relative to.
  - A verification step that touches an external service names exactly
    which service and how it's targeted.
  - Every check can actually fail: its inputs are ones the plan defines
    (not, say, a file where only a directory is supported), so a pass
    means something.
- **Rule 2 check:** a ticket that prescribes a library mechanism
  ("the token's position", "the `markup` attribute") must be one that's
  been confirmed to exist, or be phrased as the outcome needed rather
  than the mechanism.
- **Rule 5:** when only some stories in an epic need a blocker, say so in
  the epic body (and consider moving those stories into a later epic)
  rather than blocking the whole epic.

Then run a cold validation: a fresh session with only the skill installed,
given a different small project, graded the same way, with no rewriting.
That removes the same-author bias noted above.
