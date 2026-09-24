# Cold validation run: `dog-breed-matcher` (issue #21)

The follow-up recommended by the [`mdlinkcheck` run](../validation-mdlinkcheck/findings.md):
a **fresh Claude Code session**, run by the repo owner in an empty
directory outside this repo, with the four skills installed via
`scripts/link-skills.sh` and nothing else from this repo in context. The
session was graded afterwards from its transcript and output, **without
rewriting any ticket**. It ran against the rules as revised in #58, before
the additions this run led to (see [Changes made](#changes-made-in-response)).

| File | What it is |
|---|---|
| [`dog-breed-matcher-template.yaml`](./dog-breed-matcher-template.yaml) | Step 1: the template the session drafted and the user confirmed, copied verbatim from the transcript |
| [`dog-breed-matcher-plan.json`](./dog-breed-matcher-plan.json) | Step 3: the plan exactly as the session wrote it |
| [`dog-breed-matcher-plan.md`](./dog-breed-matcher-plan.md) | Step 4: re-rendered with the current `render_plan.py`, which now nests ticket-body headings. The session's own render had the same content with flatter headings. |

**Prompt:** "help me plan out a project where I get matched by a breed of
dog based on my lifestyle", with no mention of epics, stories, or the
skill's name.

**Result:** 9 epics, 27 stories, and 1 release-validation issue (37
issues). The plan passes `render_plan.py`.

## Process

| Step | What happened | |
|---|---|---|
| Trigger | The implicit phrasing invoked `project-epic-planner` directly | ✅ |
| Required reading | Read `project-template.md` and `ticket-quality-rules.md` before anything else, then `epic-schema.md` and the default labels | ✅ |
| 1. Template | Asked 4 scoping questions (platform, matching method, data source, v1 extras), drafted the template, listed its judgment calls, and waited for confirmation | ✅ |
| 2–3. Draft and write the JSON | Built the JSON with a generator script. The first attempt failed on an f-string escaping bug in that script and was re-run; one no-op `echo "retrying"` tool call | ✅ |
| 4. Validate and render | `render_plan.py` passed | ✅ |
| 5. Self-review | One post-render fix, made in the JSON rather than the markdown: the adoption check in release validation was reworded so it "proves the check can fail", which is the executability criterion added in #58 | ✅ |
| 6. Stop | Handed off `github-repo-init` and `github-project-bootstrap` as next steps for the user, and ran neither | ✅ |

## Grades

- **Rule 1: pass.** Real seams throughout. For example, the matching
  engine is split into profile mapping, dealbreaker filters, scoring,
  explanations, and persona regression tests, and each can be closed on
  its own.
- **Rule 2: pass.** No ticket points to outside context. Test seams are
  named in full signatures: `http: Net::HTTP`, `questions:`, `cache:`,
  and ZIP `00000` as the fake provider's outage trigger. The one elision
  is `Breed.new(...)` inside a test description, where the attributes
  are given alongside it. The session also refused to assume which
  adoption APIs exist today: it planned an evaluation spike that must
  first confirm each candidate is available.
- **Rule 3: pass.** Every code story names its test file and its exact
  assertions, often with worked numbers ("scores
  `(100 * (1 - 4/16)).round == 75`"). Several checks are built to be able
  to fail: a missing `KAMAL_WEB_HOST` must raise, persona tests must fail
  against deliberately broken data, and one adoption ZIP must return real
  listings.
- **Rule 4: pass.** The deploy host, domain, registry, and adoption
  provider all come from environment variables. Release validation
  targets `<BASE_URL>` plus a second, local Docker target.
- **Rule 5: pass, and it applied #58's partial-blocking guidance
  unprompted.** The adoption UI was split into its own epic so Results &
  Sharing and Adoption Provider Integration don't wait on each other.
  Results & Sharing names the one story that needs Breed Detail Pages
  and explains why that costs no real delay.

## Defects

Neither defect is the kind of gap the #58 revision targeted. Both are
conflicts *between* tickets.

1. **An undeclared dependency.** The Breed Data epic says Deployment
   "doesn't need to wait for it". But two Deployment stories check for
   `breeds:load` output in the deploy logs: *Configure production database
   and app secrets*, which expects the entrypoint's `db:prepare` and
   `breeds:load` to succeed, and *Deploy the app and verify health check*,
   which expects `bin/kamal app logs` to show `breeds:load` completing.
   That task is created by Breed Data's *Build idempotent breed seed
   loader and rake task*, so neither story can pass until it merges.
2. **A later story silently breaks an earlier story's test.** *Define
   adoption provider interface with fake provider* asserts that
   `Adoption.provider("fake")` is a `FakeProvider`. *Add caching decorator
   for adoption searches* then makes `Adoption.provider` wrap its result
   in a `CachedProvider` unless `ADOPTION_CACHE=off`, and never mentions
   the earlier test. Once the caching story lands, that test fails.

**Instruction deviation (cosmetic):** ticket bodies use `## What` and
`## Acceptance criteria`, where `SKILL.md` specified `###`. In the
session's own render these sat at the same level as the epic headings,
which flattened the outline.

## Verdict

**Pass.** All five rules held without rewriting. The two defects are
real, but they're local and would surface on the first CI run, not after
a live bootstrap. This is a clear improvement over the `mdlinkcheck`
run's five Rule 2 gaps. It also ran with none of the same-author bias,
since the session hadn't seen this repo.

## Changes made in response

- **Rule 3:** added a *changed contracts* check. A story that changes
  behavior an earlier story's tests assert must include updating those
  tests. This catches defect 2.
- **Rule 5:** added a *hidden dependencies* check. For each acceptance
  criterion, find which story produces what it relies on; if that story
  is in an epic outside `depends_on`, the dependency is undeclared. This
  catches defect 1.
- **`render_plan.py`:** nests ticket-body headings under their epic or
  story, never touching `#` lines inside code fences, and stops doubling
  the "Release validation" prefix. `SKILL.md` now says to use `###` or
  deeper in ticket bodies.
- **Listing:** `project-epic-planner` is now in the README and in
  `.claude-plugin/plugin.json`, per `.claude/CLAUDE.md`'s rule that only
  finished skills are listed.
