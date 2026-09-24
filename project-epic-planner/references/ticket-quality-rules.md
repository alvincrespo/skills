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

**Second motivating example.** Self-contained *looking* isn't enough. A
validation run of this skill, planning `mdlinkcheck` (a Markdown
link-checker CLI and GitHub Action), produced tickets with exact signatures and file shapes and no "as
discussed" anywhere, and five of them still couldn't be finished as
written. A test demanded a mock transport that no signature accepted. A
signature was literally elided as `run_external_checks(...)`. A default
path never said what it was relative to. A "verify on TestPyPI" step
used a tag that also triggered the real PyPI publish. A reference-link
parser relied on a token "position" that markdown-it-py doesn't have. And
a README self-check passed a file where only a directory was supported,
so it could never fail. Every one of these is a gap *inside* a ticket, not
a pointer outside it.

**Check.** Two passes per ticket:

1. **Nothing outside it.** Search for phrases that point outside the
   ticket: "as discussed", "like before", "the usual way", "see the
   conversation", "you'll remember". Each one is missing content — put the
   content in. A reference to another ticket or a file in the repo is
   fine; a reference to something that only existed in a chat is not.
2. **Every acceptance criterion is executable from the ticket.** Walk each
   criterion as if implementing it cold, using only what this ticket (and
   the tickets it names) define:
   - A test that needs a seam — an injectable client or transport, an env
     var, a fixture — names that seam in a signature the plan spells out.
   - No elided signatures (`(...)`, "etc."): every function a criterion
     depends on has its full parameter list somewhere in the plan.
   - Every default that's a path or location says what it's relative to,
     including when the thing it's normally relative to (a config file)
     is absent.
   - A step that touches an external service — a package index, a
     deploy target, a third-party API — names exactly which one and how
     it's targeted, and doesn't collide with another trigger in the plan
     (e.g. a tag pattern that also fires the real release).
   - A prescribed library or API mechanism is one you've confirmed
     exists. If you haven't, describe the outcome needed instead of the
     mechanism.
   - The check can actually fail: its inputs are ones the plan supports,
     so a pass means something.

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
the observable result. A test or check that can't fail as specified —
wrong input type, nothing to match — doesn't count, however specific it
reads; see Rule 2's executability pass.

**Changed contracts.** When a story changes behavior that an earlier
story's tests assert — wrapping a return value, renaming a key, adding a
required argument — its acceptance criteria include updating those tests,
naming them. In the `dog-breed-matcher` cold run, one story tested that
`Adoption.provider("fake")` returns a `FakeProvider`; a later caching
story made `Adoption.provider` wrap every result in a `CachedProvider`
and never mentioned the earlier test, which would then fail. For each
story, check what it changes against the assertions in the stories
before it.

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

**Partial blocking.** `depends_on` is epic-level: if an epic depends on
another, every story in it waits. So for each dependency, also ask
whether it holds for *all* the epic's stories. In the `mdlinkcheck` run,
CLI & Reporting was blocked by External Link Checking, but its
`--no-external` path and both reporters didn't need it. When only some
stories need the blocker, either move those stories into a later epic
(so the rest start sooner) or, if keeping them together is worth the
delay, say in the epic body which stories actually need the blocker and
that the rest are held back deliberately.

**Hidden dependencies.** The reverse also happens: an epic declared
parallel-safe whose acceptance criteria quietly need another epic's
output. So for each acceptance criterion, ask what it relies on — a
task, a table, a log line, a route — and which story produces it. If
that story is in an epic outside this one's `depends_on` (directly or
transitively), the dependency is real and undeclared. In the
`dog-breed-matcher` cold run, the Deployment epic was declared
parallel-safe with Breed Data, but two of its stories required
`breeds:load` in the deploy logs — a task Breed Data's seed-loader story
creates. Either add the dependency, or rewrite the criterion so it holds
without the other epic (and move the check to a story that runs after
both).

---

## Before handing a plan back for review

Run through all five in order, for every ticket, and fix what fails before
showing the plan. Don't hand over a plan with a note saying which rules it
breaks.

1. Every story can be closed without its siblings.
2. No ticket points to context outside itself, and every acceptance
   criterion can be executed — and can fail — using only what the plan
   defines (seams, full signatures, relative-to for defaults, exact
   external targets, confirmed mechanisms).
3. Every leaf story that changes code has a named, specific test
   criterion, and any story that changes an earlier story's tested
   behavior updates those tests.
4. No specific repo, owner, or path is hardcoded as *the* target.
5. Every `depends_on` entry has a "because" in the epic body, holds for
   every story in the epic (or the body says which stories it's for),
   nothing is blocked just because of where it appears in the document,
   and no acceptance criterion relies on output from an epic that isn't
   (transitively) in `depends_on`.

If the plan only passes after substantial rewriting by the user, that's a
signal this document needs revising, not just that one plan.
