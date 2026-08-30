<!-- Generated from tracker/issues.py by scripts/render_issues_md.py.
     Edit tracker/issues.py and re-run the script — don't edit this file directly. -->

# ISSUES.md — every epic and issue, in full

6 epics, 34 total issues (epics + children + release validation). This is what `scripts/bootstrap_github_project.py` creates in GitHub — review it here first.

**Milestone:** v1 — Four Skills Shipped & Shareable

> Definition of done: all four skills (project-epic-planner, github-repo-init, github-labels-setup, github-project-bootstrap) exist with complete SKILL.md files, pass `claude plugin validate . --strict`, and have been chain-tested end-to-end (repo-init -> plan -> review -> labels + bootstrap) against a real throwaway repo. See SKILLS_PLAN.md for the full reasoning behind the four-skill split and the invocation-control decisions.

---

## 1. Epic: Skill — github-labels-setup

**Labels:** `epic`, `priority:P0`, `size:M`  
**Blocked by:** —

Standalone, reusable independent of the other three — "set up my standard labels on this repo" is a complete request with no milestone, board, or issues involved.

Built first: smallest scope, cleanly extractable from code that already works, and a dependency of github-project-bootstrap, so building it first gives that epic something real to call into rather than a stub.

### Issues in this epic (4)

#### 1.1 Write SKILL.md for github-labels-setup

**Labels:** `task`, `size:S`

### Acceptance criteria
- [ ] Frontmatter includes `name` and a "pushy" `description` per skill-creator's guidance (explicit triggers: "set up labels", "standardize labels across repos", "as part of setting up issue tracking")
- [ ] No `disable-model-invocation` flag — this skill is low-stakes (labels are trivially editable) and stays model-invoked, per ADR 0002
- [ ] Body documents the labels-config JSON shape: a list of `{"name": str, "color": str (hex, no #), "description": str}` objects
- [ ] Body points to the default taxonomy template (next story) as the starting point, explicitly overridable

#### 1.2 Extract label-creation into scripts/ensure_labels.py

**Labels:** `task`, `size:S`

Pull the `ensure_labels()` logic out of `bootstrap_github_project.py` into its own standalone script that reads a labels config file instead of a hardcoded tuple list.

```bash
python scripts/ensure_labels.py --repo <owner>/<repo> --labels-file labels/default.json
```

Each entry becomes `gh label create <name> --repo <owner>/<repo> --color <color> --description <description> --force` — the exact `--force` idempotent pattern already proven across every bootstrap run against `alvincrespo/pr-agent`, unchanged.

### Acceptance criteria
- [ ] Script takes `--repo` and `--labels-file` as required arguments
- [ ] Reads and validates the JSON file (missing `name`, `color`, or `description` on any entry is a clear error, not a KeyError traceback)
- [ ] Unit test: mocked `gh label create` calls, asserts the exact command built per label entry

#### 1.3 Ship a default labels config template

**Labels:** `task`, `size:S`

`labels/default.json` — the nine-label taxonomy already proven on `pr-agent`: `epic`, `task`, `safety-critical`, `priority:P0`, `priority:P1`, `priority:P2`, `size:S`, `size:M`, `size:L`, with the same colors and descriptions already in production use.

### Acceptance criteria
- [ ] Valid JSON, matches the schema from the previous story
- [ ] Referenced from `github-labels-setup`'s `SKILL.md` as the default — explicitly documented as a starting point to copy and edit, not a fixed requirement

#### 1.4 Regression-test against alvincrespo/pr-agent's real labels

**Labels:** `task`, `size:S`

### Acceptance criteria
- [ ] Run `ensure_labels.py` against the already-existing `alvincrespo/pr-agent` repo with `labels/default.json`
- [ ] Confirm all nine labels resolve as `--force`-idempotent — no duplicates created, no drift from what's already on that repo from the original bootstrap runs
- [ ] Findings noted in this issue before trusting the extracted script anywhere else

---

## 2. Epic: Skill — github-project-bootstrap

**Labels:** `epic`, `priority:P0`, `size:L`  
**Blocked by:** Epic: Skill — github-labels-setup

Milestone, linked Project v2 board, and every epic/story issue with real sub-issue and blocked-by relationships. The part with zero remaining unknowns — every `gh` CLI quirk in the underlying script was discovered against a live API across four actual `pr-agent` bootstrap runs, not guessed at.

Depends on github-labels-setup: this skill calls into that one for label creation rather than duplicating the logic.

### Issues in this epic (5)

#### 2.1 Define the epics/stories JSON schema

**Labels:** `task`, `size:M`

Document the JSON shape that replaces the current `tracker/issues.py` Python module — same fields, portable format:

```json
{
  "milestone": {"title": "...", "description": "..."},
  "epics": [
    {
      "title": "Epic: ...", "labels": [...], "depends_on": ["Epic: ..."], "body": "...",
      "issues": [{"title": "...", "labels": [...], "body": "..."}]
    }
  ],
  "release_validation_issue": {"title": "...", "labels": [...], "body": "..."}
}
```

### Acceptance criteria
- [ ] Schema documented in `references/epic-schema.md` — field names, types, and the same ordering constraint the Python version relied on (`depends_on` may only reference an already-defined epic earlier in the `epics` list)
- [ ] A JSON Schema (`.json` file, `$schema` draft referenced) included for actual validation, not just prose

#### 2.2 Convert bootstrap_github_project.py to read a --data JSON file

**Labels:** `task`, `size:M`

Replace `from tracker.issues import EPICS, MILESTONE, RELEASE_VALIDATION_ISSUE` with a `--data <path.json>` CLI argument, loaded with `json.load()`. Every downstream use of `EPICS`, `MILESTONE`, and `RELEASE_VALIDATION_ISSUE` becomes a lookup into the loaded dict instead of a module attribute.

### Acceptance criteria
- [ ] `--data` is a required argument alongside the existing `--repo`
- [ ] All existing `gh` command logic — the milestone state=open/closed fix, the `--method GET` fix, the milestone-title-not-number fix, the project-link step — is carried over completely unchanged; this story is a data-source swap, not a rewrite of proven logic
- [ ] A malformed or schema-invalid `--data` file produces a clear validation error before any `gh` command runs, not a confusing failure mid-bootstrap

#### 2.3 Call into github-labels-setup instead of an inline label list

**Labels:** `task`, `size:S`

Remove `ensure_labels()`'s hardcoded label tuples from this script entirely. Shell out to (or import directly, if both scripts end up in the same package) `github-labels-setup/scripts/ensure_labels.py`, passing through a `--labels-file` argument that defaults to that skill's `labels/default.json` if none is given.

### Acceptance criteria
- [ ] No label-taxonomy data duplicated between the two skills — one script owns label creation, this one calls it
- [ ] `--labels-file` is optional here, with the default template used when omitted

#### 2.4 Write SKILL.md for github-project-bootstrap

**Labels:** `task`, `size:S`, `safety-critical`

### Acceptance criteria
- [ ] Frontmatter includes `disable-model-invocation: true` — this skill creates real, only partly reversible GitHub artifacts (milestone, project board, dozens of issues), per ADR 0002. Never Claude-invoked from context, only ever explicitly requested
- [ ] Body documents the required `--data` file shape, linking to the schema story above rather than re-describing it

#### 2.5 Regression-test: convert pr-agent's tracker data to JSON

**Labels:** `task`, `size:M`

### Acceptance criteria
- [ ] `pr-agent/tracker/issues.py`'s content converted to the new JSON schema
- [ ] Run the converted script against a **disposable test repo** (not the real `alvincrespo/pr-agent` — avoid duplicate-run interference with the already-populated real board) and confirm it produces the same 51 issues, the same dependency graph, and the same blocked-by links as the original run did

---

## 3. Epic: Skill — github-repo-init

**Labels:** `epic`, `priority:P0`, `size:S`  
**Blocked by:** —

Repo creation and baseline scaffolding, decoupled from issue-bootstrapping on purpose — `pr-agent`'s repo had to be deleted and recreated twice mid-debugging, independent of any issue content, which is exactly the scenario this separation exists for.

### Issues in this epic (4)

#### 3.1 Generalize setup_repo.sh's description and topics into parameters

**Labels:** `task`, `size:S`

Replace the hardcoded `DESCRIPTION` variable and fixed `--add-topic` list with `--description` and `--topics` (comma-separated) flags, with sensible defaults documented in the script's own usage comment.

### Acceptance criteria
- [ ] `./setup_repo.sh <owner>/<repo> --description "..." --topics "a,b,c"` works
- [ ] Omitting either flag falls back to a documented default rather than erroring

#### 3.2 Remove the chained call to bootstrap_github_project.py

**Labels:** `task`, `size:S`

The current script ends by calling the bootstrap script directly — that coupling existed because both were one combined workflow. Now that they're separately-triggered skills, this script should end once the repo exists, is pushed, and has its topics set.

### Acceptance criteria
- [ ] Script no longer references `bootstrap_github_project.py` at all
- [ ] Final output tells the user the repo is ready and names the next skill to run, rather than running it for them

#### 3.3 Write SKILL.md for github-repo-init

**Labels:** `task`, `size:S`, `safety-critical`

### Acceptance criteria
- [ ] Frontmatter includes `disable-model-invocation: true` — creates a real repository, per ADR 0002
- [ ] Body documents the `--description`/`--topics` parameters and the manual-follow-up items (branch protection, secret scan) already called out in `pr-agent`'s version of this script

#### 3.4 Verify against a fresh throwaway repo end-to-end

**Labels:** `task`, `size:S`

### Acceptance criteria
- [ ] Run the generalized script against a disposable test repo name
- [ ] Confirm repo creation, push, topics, and license all land correctly
- [ ] Delete the test repo afterward

---

## 4. Epic: Skill — project-epic-planner

**Labels:** `epic`, `priority:P0`, `size:L`  
**Blocked by:** —

The highest-leverage and most subjective of the four — this is where the actual lessons from building `pr-agent`'s tracker (one story per tool, self-contained tickets, testing as AC, real dependency graphs) get encoded as standing rules instead of one-off corrections. Expect more iteration here than the other three.

### Issues in this epic (4)

#### 4.1 Write the ticket-quality-rules reference doc

**Labels:** `task`, `size:M`

`references/ticket-quality-rules.md` — encode the five standing rules from SKILLS_PLAN.md as explicit skill instructions, each with the concrete example from this project that motivated it:

1. One story per independently-testable unit of work ("port the tools" became 10 stories, one per tool)
2. Every ticket is self-contained — exact commands and schemas, never "you'll remember from the conversation"
3. Testing is an acceptance criterion on every leaf story, not an afterthought
4. Repo/config choices are runtime parameters, never hardcoded into a ticket (the `glypto`-hardcoding mistake, generalized)
5. A real dependency graph, not just reading order — which epics genuinely block others vs. which are parallel-safe, and why

### Acceptance criteria
- [ ] All five rules present, each with its motivating example
- [ ] Referenced from `project-epic-planner`'s `SKILL.md` as required reading before generating any ticket

#### 4.2 Define the project-template input schema

**Labels:** `task`, `size:S`

The YAML shape from SKILLS_PLAN.md:

```yaml
project_name: string
one_line_description: string
objective: string
in_scope: [string]
out_of_scope: [string]
known_pieces: [string]   # optional
repo:
  visibility: public | private
  license: string
target_milestone_name: string
```

### Acceptance criteria
- [ ] Schema documented in `references/project-template.md`
- [ ] Includes one fully filled-in worked example, using this exact skills-repo project as the sample

#### 4.3 Write SKILL.md for project-epic-planner

**Labels:** `task`, `size:S`

### Acceptance criteria
- [ ] No `disable-model-invocation` flag — planning is reversible (it produces a reviewable document, nothing acts on it automatically) and stays model-invoked, per ADR 0002
- [ ] Trigger description covers implicit phrasing ("help me plan this", "what would the roadmap look like") not just literal "epics"/"stories" mentions
- [ ] Output format documented: a JSON file matching the schema from github-project-bootstrap's Epic 2, plus a rendered markdown doc for human review

#### 4.4 Test against a different, unrelated small project

**Labels:** `task`, `size:M`

### Acceptance criteria
- [ ] Generate a full plan for a project that isn't `pr-agent` or this skills repo itself
- [ ] Review ticket quality against the five rules from the reference doc without personally rewriting any ticket
- [ ] Findings recorded in this issue — if quality doesn't hold without manual correction, that's a signal to revise the reference doc, not just this one output

---

## 5. Epic: Skills repo scaffolding & governance

**Labels:** `epic`, `priority:P0`, `size:S`  
**Blocked by:** —

README, CLAUDE.md, LICENSE, the local-dev linking script, and two ADRs formalizing decisions already reasoned through in SKILLS_PLAN.md. Parallel-safe with all three skill epics — none of this depends on any skill actually being built yet.

### Issues in this epic (6)

#### 5.1 Write README.md

**Labels:** `task`, `size:S`

### Acceptance criteria
- [ ] States the repo's purpose and points to `PROJECT_PLAN.md`/`TRACKER.md` while no skills have landed yet
- [ ] Install instructions included, ready to make sense once the first skill ships
- [ ] Updated with a linked entry per skill as each one closes — this issue itself only covers the initial skeleton, not the ongoing updates

#### 5.2 Write CLAUDE.md

**Labels:** `task`, `size:S`

The governance rules right-sized from SKILLS_PLAN.md's "adopt now" list — no bucket-folder language (deferred, see ADR 0001's sibling reasoning in PROJECT_PLAN.md), a flat promoted/not-promoted rule ("finished skill = README entry + plugin.json entry"), the invocation-control rule from ADR 0002, the `claude plugin validate . --strict` step, and `scripts/link-skills.sh` usage instructions.

### Acceptance criteria
- [ ] All five elements above present
- [ ] Explicitly states no `package.json`-synced versioning — `plugin.json`'s `version` field is the sole source of truth, and why (no other JS tooling exists in this repo)

#### 5.3 Add LICENSE

**Labels:** `task`, `size:S`

### Acceptance criteria
- [ ] MIT license file present, matching the choice already made for `pr-agent`

#### 5.4 Write scripts/link-skills.sh

**Labels:** `task`, `size:S`

Symlinks every top-level folder containing a `SKILL.md` into `~/.claude/skills` and `~/.agents/skills`, so a `git pull` keeps installed skills current without a reinstall.

### Acceptance criteria
- [ ] Script discovers skill folders by presence of `SKILL.md`, not a hardcoded list — it should need no edits when a new skill folder is added
- [ ] Safe to run with zero skill folders present (today's state) — no-ops cleanly rather than erroring

#### 5.5 Write ADR 0001: four skills, not one

**Labels:** `task`, `size:S`

### Acceptance criteria
- [ ] `docs/adr/0001-four-skills-not-one.md` present, formalizing the reasoning already worked out in SKILLS_PLAN.md and this conversation

#### 5.6 Write ADR 0002: invocation control on the GitHub-acting skills

**Labels:** `task`, `size:S`

### Acceptance criteria
- [ ] `docs/adr/0002-invocation-control-on-github-actions.md` present, documenting why `github-repo-init` and `github-project-bootstrap` are user-invoked-only while the other two stay model-invoked

---

## 6. Epic: Repo creation & validation

**Labels:** `epic`, `priority:P0`, `size:S`  
**Blocked by:** Epic: Skills repo scaffolding & governance

Blocked by scaffolding on purpose: the initial commit needs README/CLAUDE.md/LICENSE to exist before there's anything worth pushing.

### Issues in this epic (4)

#### 6.1 Create and push alvincrespo/skills

**Labels:** `task`, `size:S`

```bash
gh repo create alvincrespo/skills \
  --public \
  --description "A small, growing collection of Claude Skills for real engineering workflows." \
  --source=. \
  --remote=origin \
  --push
```

Ideally run via `github-repo-init`'s own script once it exists (Epic 3) — same bootstrapping situation `pr-agent` was in: the very first push of a repo can't use a skill that isn't installed anywhere yet, so running the underlying script directly is expected and fine.

### Acceptance criteria
- [ ] Repo created and pushed with the scaffolding from Epic 5 as the initial commit

#### 6.2 Set repository topics

**Labels:** `task`, `size:S`

### Acceptance criteria
- [ ] Topics set: `claude-skills`, `claude-code`, `ai-agent-tooling`, `github-automation`

#### 6.3 Create plugin manifests and validate

**Labels:** `task`, `size:M`

`.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` — the actual "shareable" mechanism, the whole point of this repo existing.

**Do not guess the schema.** This conversation already hit real, non-obvious `gh` CLI behavior four separate times by assuming documented-elsewhere behavior applied directly (`state=all`, POST-by-default with `-f` flags, `--milestone` wanting a title not a number). Confirm the current exact `plugin.json`/`marketplace.json` schema against Claude Code's own plugin documentation before writing either file.

### Acceptance criteria
- [ ] Schema confirmed against current official docs, not assumed from this repo's memory of a similar-looking example
- [ ] Both manifests present, `skills` array starting empty or with placeholders, filled in as each skill epic closes
- [ ] `claude plugin validate . --strict` passes

#### 6.4 Pre-push secret scan of the initial commit

**Labels:** `task`, `size:S`, `safety-critical`

### Acceptance criteria
- [ ] Initial commit scanned by hand or with a tool (`gitleaks`, `trufflehog`) before trusting it on a public remote — same habit carried over from `pr-agent`'s repo-creation story

---

## Release validation (standalone — blocked by every epic above)

**Title:** Release validation: all four skills built, packaged, and chain-tested  
**Labels:** `priority:P0`, `size:S`  
**Blocked by:** Epic: Skill — github-labels-setup, Epic: Skill — github-project-bootstrap, Epic: Skill — github-repo-init, Epic: Skill — project-epic-planner, Epic: Skills repo scaffolding & governance, Epic: Repo creation & validation

The actual ship-it milestone. Do not close until every item below is checked against real, working skills — not a plan.

### Acceptance criteria
- [ ] All four skills exist with complete `SKILL.md` files and pass `claude plugin validate . --strict`
- [ ] Full chain tested end-to-end on a throwaway repo: repo-init → plan → review → labels + bootstrap
- [ ] Each skill packaged as a standalone `.skill` file via `package_skill.py`, in addition to the plugin/marketplace route
- [ ] `README.md` updated with all four skill entries, each linked to its `SKILL.md`
- [ ] `plugin.json`'s `skills` array includes all four

