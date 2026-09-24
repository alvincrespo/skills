# Ticket quality rules

Required reading before generating any ticket. These five rules are the
difference between the *first-draft* tracker `pr-agent` started with and
the corrected one it shipped with — every one of them was learned by
getting it wrong first. They're standing rules, not suggestions: a plan
that breaks one isn't ready for review, however good the rest of it is.

The motivating examples below come from `pr-agent`'s tracker (preserved in
[`github-project-bootstrap/docs/pr-agent-tracker.json`](../../github-project-bootstrap/docs/pr-agent-tracker.json))
and from building this repo. Read them for the *shape* of the correction,
not to copy their content.

---

## 1. One story per independently-testable unit of work

**Rule.** Split work until each story can be implemented, tested, and
closed on its own. If two pieces of work could be finished and verified
separately, they're two stories — even when they feel like "the same kind
of thing".

**Motivating example.** `pr-agent`'s first draft had a single "port the
tools" story. It became ten: one foundational story ("Design the
per-directory tool factory") plus one per tool — `list_open_prs`,
`get_pr_ci_status`, `get_failing_ci_logs`, `checkout_pr`, `read_file`,
`write_file`, `run_diagnostic_command`, `commit_and_push`, `merge_pr`. Each
tool has its own command, its own schema, and its own tests, so each can be
reviewed and merged without the other eight being done. "Port the tools"
could only ever be closed all at once, and a problem in one tool would have
held up all ten.

**Check.** For each story, ask: can this be closed while its siblings are
still open? If closing it requires finishing another story, merge them or
make the dependency explicit. If it contains an "and" joining two things
that can each be verified separately, split it.

## 2. Every ticket is self-contained

**Rule.** A ticket carries everything needed to do it: exact commands,
exact schemas, exact file paths, exact field names, and the reasoning for
any non-obvious choice. Someone picking it up cold — a new contributor, or
Claude in a fresh session with no memory of the planning conversation —
must be able to finish it from the ticket alone.

**Motivating example.** `pr-agent`'s tool stories each name the exact
command they wrap (`gh pr checks <pr_number> --json name,state,link` for
`get_pr_ci_status`) and the exact description string the model sees. Its
packaging story spells out the literal `pyproject.toml` fields and package
tree rather than "set up packaging like we discussed". The tool-factory
story explains *why* it's a factory rather than a module-level global
(parallel worktrees would share state), because that reasoning is what
stops a later contributor from "simplifying" it back.

**Check.** Search every ticket for phrases that point outside it: "as
discussed", "like before", "the usual way", "see the conversation", "you'll
remember". Each one is missing content — put the content in. A reference to
another ticket or a file in the repo is fine; a reference to something that
only existed in a chat is not.

## 3. Testing is an acceptance criterion on every leaf story

**Rule.** Every story that produces code has at least one acceptance
criterion that is a specific test: what's mocked or set up, and what's
asserted. Testing isn't a separate phase at the end, and a "Testing" epic
doesn't replace per-story tests — it adds the loop-level and integration
testing that ties them together.

**Motivating example.** Every `pr-agent` tool story ends with the same two
criteria: a unit test with `subprocess.run` mocked asserting the exact
command built, and a unit test that a failing command returns descriptive
text instead of raising. The tool-factory story makes its key property — two
calls with different directories produce independently bound closures — an
explicit test, because it's what makes parallelism safe later. The Testing
& Validation epic says outright that it "ties together the per-tool unit
tests already required as acceptance criteria", rather than being where
testing first appears.

**Check.** Every leaf story that changes code has a criterion beginning
"Unit test:", "Integration test:", or similar, naming what it asserts.
"Tests pass" or "add tests" alone doesn't count — it doesn't say what's
being verified. Stories that produce no code (docs, a manual run) instead
need a criterion that's checkable by someone else: the command to run and
the observable result.

## 4. Repo and config choices are runtime parameters, never hardcoded

**Rule.** Which repo, org, owner, account, environment, or path something
runs against is a parameter supplied at run time — a flag, a config file,
an argument. Never write a specific one into a ticket as *the* target, and
never write a ticket that leads to it being hardcoded in code.

**Motivating example.** `pr-agent`'s tracker originally hardcoded
`glypto` — one specific repo — as the target. Taken literally, a
validation run built that way tests "works against glypto", not "works".
The corrected acceptance dry-run ticket makes the
repo a runtime parameter (`--repo <path>`, checked against the allowlist),
calls `glypto` "one convenient option, not the required one", and adds a
criterion that the run is repeated against a **second, different** repo,
because behavior that only ever sees one repo can quietly depend on it.
The release-validation issue repeats that check: "pointed at a second,
unrelated repo via config only (no code changes)". The same mistake
showed up again in this repo: `setup_repo.sh` came over from `pr-agent`
with its description and topics hardcoded, and had to be generalized into
`--description` / `--topics` flags.

**Check.** Search every ticket for concrete repo names, owners, org
names, account IDs, hostnames, and absolute paths. Each one should be
either an example explicitly labeled as one, or replaced with a
placeholder (`<owner>/<repo>`) plus the flag or config key that supplies
it. When a ticket validates something against a real target, require a
second, different target too.

## 5. A real dependency graph, not just reading order

**Rule.** An epic's `depends_on` lists only the epics that genuinely block
it — work that can't meaningfully start or pass until the other is done.
Everything else is parallel-safe and must stay unblocked, even if it
"comes later" in the document. Every dependency, and every notable
*non*-dependency, is explained in the epic's body.

**Motivating example.** `pr-agent`'s epics don't form a chain. Core Agent
Loop and Agent Tools both depend only on Setup and are explicitly
parallel-safe: "`agent/core.py` doesn't know what a PR is;
`agent/tools.py` doesn't know how to call the model." Configuration &
Safety depends on both, because its guardrails extend specific tools and
gate the loop itself. Testing & Validation is blocked by Configuration &
Safety "on purpose", because its tests check the allowlist and spend cap
that epic adds. Observability depends only on Core Agent Loop and says
so outright: "pull it in alongside the P0 work rather than queuing it
behind Testing". Reading order would have put it after Testing and delayed
it for no reason.

**Check.** For each `depends_on` entry, finish the sentence "this epic
can't start (or its tests can't pass) until that one is done, because …".
If you can't, drop the entry. For each pair of epics that *aren't* linked
but look like they might be, say in the body why they're parallel-safe.
The graph must also satisfy the output schema's ordering constraint:
every `depends_on` entry names an epic earlier in the `epics` array (see
[`epic-schema.md`](../../github-project-bootstrap/references/epic-schema.md)).

---

## Before handing a plan back for review

Run through all five in order, for every ticket, and fix what fails before
showing the plan. Don't hand over a plan with a note saying which rules it
breaks.

1. Every story can be closed without its siblings.
2. No ticket points to context outside itself.
3. Every leaf story that changes code has a named, specific test criterion.
4. No specific repo, owner, or path is hardcoded as *the* target.
5. Every `depends_on` entry has a "because" in the epic body, and nothing
   is blocked just because of where it appears in the document.

If the plan only passes after substantial rewriting by the user, that's a
signal this document needs revising, not just that one plan.
