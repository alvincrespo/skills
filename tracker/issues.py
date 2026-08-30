"""
Tracker content for alvincrespo/skills, as data rather than prose.

Same pattern as pr-agent/tracker/issues.py: this is the source of truth for
what gets created in GitHub, read by scripts/bootstrap_github_project.py
(copied over unmodified — it's already fully generic via --repo and --data
positional args, nothing here needed to change in that script).

Structure and standards carried over unchanged from the pr-agent tracker:
- Every leaf story is self-contained (exact commands/schemas, no "you'll
  remember from the conversation" phrasing)
- Testing is an acceptance criterion on every leaf story, not an afterthought
- depends_on encodes a REAL dependency graph — EPICS is ordered so nothing
  depends on a later epic, which is what makes the bootstrap script's
  single-pass creation order safe
"""

MILESTONE = {
    "title": "v1 \u2014 Four Skills Shipped & Shareable",
    "description": (
        "Definition of done: all four skills (project-epic-planner, "
        "github-repo-init, github-labels-setup, github-project-bootstrap) "
        "exist with complete SKILL.md files, pass "
        "`claude plugin validate . --strict`, and have been chain-tested "
        "end-to-end (repo-init -> plan -> review -> labels + bootstrap) "
        "against a real throwaway repo. See SKILLS_PLAN.md for the full "
        "reasoning behind the four-skill split and the invocation-control "
        "decisions."
    ),
}

# ---------------------------------------------------------------------------
# Epic 1: Skill -- github-labels-setup
# ---------------------------------------------------------------------------

_EPIC_1_ISSUES = [
    {
        "title": "Write SKILL.md for github-labels-setup",
        "labels": ["size:S"],
        "body": (
            "### Acceptance criteria\n"
            "- [ ] Frontmatter includes `name` and a \"pushy\" `description` "
            "per skill-creator's guidance (explicit triggers: \"set up "
            "labels\", \"standardize labels across repos\", \"as part of "
            "setting up issue tracking\")\n"
            "- [ ] No `disable-model-invocation` flag \u2014 this skill is "
            "low-stakes (labels are trivially editable) and stays "
            "model-invoked, per ADR 0002\n"
            "- [ ] Body documents the labels-config JSON shape: a list of "
            "`{\"name\": str, \"color\": str (hex, no #), \"description\": "
            "str}` objects\n"
            "- [ ] Body points to the default taxonomy template (next "
            "story) as the starting point, explicitly overridable"
        ),
    },
    {
        "title": "Extract label-creation into scripts/ensure_labels.py",
        "labels": ["size:S"],
        "body": (
            "Pull the `ensure_labels()` logic out of "
            "`bootstrap_github_project.py` into its own standalone script "
            "that reads a labels config file instead of a hardcoded tuple "
            "list.\n\n"
            "```bash\n"
            "python scripts/ensure_labels.py --repo <owner>/<repo> "
            "--labels-file labels/default.json\n"
            "```\n\n"
            "Each entry becomes `gh label create <name> --repo <owner>/<repo> "
            "--color <color> --description <description> --force` \u2014 "
            "the exact `--force` idempotent pattern already proven across "
            "every bootstrap run against `alvincrespo/pr-agent`, unchanged.\n\n"
            "### Acceptance criteria\n"
            "- [ ] Script takes `--repo` and `--labels-file` as required "
            "arguments\n"
            "- [ ] Reads and validates the JSON file (missing `name`, "
            "`color`, or `description` on any entry is a clear error, not "
            "a KeyError traceback)\n"
            "- [ ] Unit test: mocked `gh label create` calls, asserts the "
            "exact command built per label entry"
        ),
    },
    {
        "title": "Ship a default labels config template",
        "labels": ["size:S"],
        "body": (
            "`labels/default.json` \u2014 the nine-label taxonomy already "
            "proven on `pr-agent`: `epic`, `task`, `safety-critical`, "
            "`priority:P0`, `priority:P1`, `priority:P2`, `size:S`, "
            "`size:M`, `size:L`, with the same colors and descriptions "
            "already in production use.\n\n"
            "### Acceptance criteria\n"
            "- [ ] Valid JSON, matches the schema from the previous story\n"
            "- [ ] Referenced from `github-labels-setup`'s `SKILL.md` as "
            "the default \u2014 explicitly documented as a starting point "
            "to copy and edit, not a fixed requirement"
        ),
    },
    {
        "title": "Regression-test against alvincrespo/pr-agent's real labels",
        "labels": ["size:S"],
        "body": (
            "### Acceptance criteria\n"
            "- [ ] Run `ensure_labels.py` against the already-existing "
            "`alvincrespo/pr-agent` repo with `labels/default.json`\n"
            "- [ ] Confirm all nine labels resolve as `--force`-idempotent "
            "\u2014 no duplicates created, no drift from what's already "
            "on that repo from the original bootstrap runs\n"
            "- [ ] Findings noted in this issue before trusting the "
            "extracted script anywhere else"
        ),
    },
]

# ---------------------------------------------------------------------------
# Epic 2: Skill -- github-project-bootstrap
# ---------------------------------------------------------------------------

_EPIC_2_ISSUES = [
    {
        "title": "Define the epics/stories JSON schema",
        "labels": ["size:M"],
        "body": (
            "Document the JSON shape that replaces the current "
            "`tracker/issues.py` Python module \u2014 same fields, "
            "portable format:\n\n"
            "```json\n"
            "{\n"
            '  "milestone": {"title": "...", "description": "..."},\n'
            '  "epics": [\n'
            "    {\n"
            '      "title": "Epic: ...", "labels": [...], '
            '"depends_on": ["Epic: ..."], "body": "...",\n'
            '      "issues": [{"title": "...", "labels": [...], "body": "..."}]\n'
            "    }\n"
            "  ],\n"
            '  "release_validation_issue": {"title": "...", "labels": [...], "body": "..."}\n'
            "}\n"
            "```\n\n"
            "### Acceptance criteria\n"
            "- [ ] Schema documented in `references/epic-schema.md` \u2014 "
            "field names, types, and the same ordering constraint the "
            "Python version relied on (`depends_on` may only reference an "
            "already-defined epic earlier in the `epics` list)\n"
            "- [ ] A JSON Schema (`.json` file, `$schema` draft "
            "referenced) included for actual validation, not just prose"
        ),
    },
    {
        "title": "Convert bootstrap_github_project.py to read a --data JSON file",
        "labels": ["size:M"],
        "body": (
            "Replace `from tracker.issues import EPICS, MILESTONE, "
            "RELEASE_VALIDATION_ISSUE` with a `--data <path.json>` CLI "
            "argument, loaded with `json.load()`. Every downstream use of "
            "`EPICS`, `MILESTONE`, and `RELEASE_VALIDATION_ISSUE` becomes a "
            "lookup into the loaded dict instead of a module attribute.\n\n"
            "### Acceptance criteria\n"
            "- [ ] `--data` is a required argument alongside the existing "
            "`--repo`\n"
            "- [ ] All existing `gh` command logic \u2014 the milestone "
            "state=open/closed fix, the `--method GET` fix, the "
            "milestone-title-not-number fix, the project-link step \u2014 "
            "is carried over completely unchanged; this story is a data-"
            "source swap, not a rewrite of proven logic\n"
            "- [ ] A malformed or schema-invalid `--data` file produces a "
            "clear validation error before any `gh` command runs, not a "
            "confusing failure mid-bootstrap"
        ),
    },
    {
        "title": "Call into github-labels-setup instead of an inline label list",
        "labels": ["size:S"],
        "body": (
            "Remove `ensure_labels()`'s hardcoded label tuples from this "
            "script entirely. Shell out to (or import directly, if both "
            "scripts end up in the same package) "
            "`github-labels-setup/scripts/ensure_labels.py`, passing "
            "through a `--labels-file` argument that defaults to that "
            "skill's `labels/default.json` if none is given.\n\n"
            "### Acceptance criteria\n"
            "- [ ] No label-taxonomy data duplicated between the two "
            "skills \u2014 one script owns label creation, this one calls "
            "it\n"
            "- [ ] `--labels-file` is optional here, with the default "
            "template used when omitted"
        ),
    },
    {
        "title": "Write SKILL.md for github-project-bootstrap",
        "labels": ["size:S", "safety-critical"],
        "body": (
            "### Acceptance criteria\n"
            "- [ ] Frontmatter includes `disable-model-invocation: true` "
            "\u2014 this skill creates real, only partly reversible "
            "GitHub artifacts (milestone, project board, dozens of "
            "issues), per ADR 0002. Never Claude-invoked from context, "
            "only ever explicitly requested\n"
            "- [ ] Body documents the required `--data` file shape, "
            "linking to the schema story above rather than re-describing it"
        ),
    },
    {
        "title": "Regression-test: convert pr-agent's tracker data to JSON",
        "labels": ["size:M"],
        "body": (
            "### Acceptance criteria\n"
            "- [ ] `pr-agent/tracker/issues.py`'s content converted to the "
            "new JSON schema\n"
            "- [ ] Run the converted script against a **disposable test "
            "repo** (not the real `alvincrespo/pr-agent` \u2014 avoid "
            "duplicate-run interference with the already-populated real "
            "board) and confirm it produces the same 51 issues, the same "
            "dependency graph, and the same blocked-by links as the "
            "original run did"
        ),
    },
]

# ---------------------------------------------------------------------------
# Epic 3: Skill -- github-repo-init
# ---------------------------------------------------------------------------

_EPIC_3_ISSUES = [
    {
        "title": "Generalize setup_repo.sh's description and topics into parameters",
        "labels": ["size:S"],
        "body": (
            "Replace the hardcoded `DESCRIPTION` variable and fixed "
            "`--add-topic` list with `--description` and `--topics` "
            "(comma-separated) flags, with sensible defaults documented "
            "in the script's own usage comment.\n\n"
            "### Acceptance criteria\n"
            "- [ ] `./setup_repo.sh <owner>/<repo> --description \"...\" "
            "--topics \"a,b,c\"` works\n"
            "- [ ] Omitting either flag falls back to a documented default "
            "rather than erroring"
        ),
    },
    {
        "title": "Remove the chained call to bootstrap_github_project.py",
        "labels": ["size:S"],
        "body": (
            "The current script ends by calling the bootstrap script "
            "directly \u2014 that coupling existed because both were one "
            "combined workflow. Now that they're separately-triggered "
            "skills, this script should end once the repo exists, is "
            "pushed, and has its topics set.\n\n"
            "### Acceptance criteria\n"
            "- [ ] Script no longer references "
            "`bootstrap_github_project.py` at all\n"
            "- [ ] Final output tells the user the repo is ready and "
            "names the next skill to run, rather than running it for them"
        ),
    },
    {
        "title": "Write SKILL.md for github-repo-init",
        "labels": ["size:S", "safety-critical"],
        "body": (
            "### Acceptance criteria\n"
            "- [ ] Frontmatter includes `disable-model-invocation: true` "
            "\u2014 creates a real repository, per ADR 0002\n"
            "- [ ] Body documents the `--description`/`--topics` "
            "parameters and the manual-follow-up items (branch "
            "protection, secret scan) already called out in `pr-agent`'s "
            "version of this script"
        ),
    },
    {
        "title": "Verify against a fresh throwaway repo end-to-end",
        "labels": ["size:S"],
        "body": (
            "### Acceptance criteria\n"
            "- [ ] Run the generalized script against a disposable test "
            "repo name\n"
            "- [ ] Confirm repo creation, push, topics, and license all "
            "land correctly\n"
            "- [ ] Delete the test repo afterward"
        ),
    },
]

# ---------------------------------------------------------------------------
# Epic 4: Skill -- project-epic-planner
# ---------------------------------------------------------------------------

_EPIC_4_ISSUES = [
    {
        "title": "Write the ticket-quality-rules reference doc",
        "labels": ["size:M"],
        "body": (
            "`references/ticket-quality-rules.md` \u2014 encode the five "
            "standing rules from SKILLS_PLAN.md as explicit skill "
            "instructions, each with the concrete example from this "
            "project that motivated it:\n\n"
            "1. One story per independently-testable unit of work "
            "(\"port the tools\" became 10 stories, one per tool)\n"
            "2. Every ticket is self-contained \u2014 exact commands and "
            "schemas, never \"you'll remember from the conversation\"\n"
            "3. Testing is an acceptance criterion on every leaf story, "
            "not an afterthought\n"
            "4. Repo/config choices are runtime parameters, never "
            "hardcoded into a ticket (the `glypto`-hardcoding mistake, "
            "generalized)\n"
            "5. A real dependency graph, not just reading order \u2014 "
            "which epics genuinely block others vs. which are "
            "parallel-safe, and why\n\n"
            "### Acceptance criteria\n"
            "- [ ] All five rules present, each with its motivating "
            "example\n"
            "- [ ] Referenced from `project-epic-planner`'s `SKILL.md` as "
            "required reading before generating any ticket"
        ),
    },
    {
        "title": "Define the project-template input schema",
        "labels": ["size:S"],
        "body": (
            "The YAML shape from SKILLS_PLAN.md:\n\n"
            "```yaml\n"
            "project_name: string\n"
            "one_line_description: string\n"
            "objective: string\n"
            "in_scope: [string]\n"
            "out_of_scope: [string]\n"
            "known_pieces: [string]   # optional\n"
            "repo:\n"
            "  visibility: public | private\n"
            "  license: string\n"
            "target_milestone_name: string\n"
            "```\n\n"
            "### Acceptance criteria\n"
            "- [ ] Schema documented in `references/project-template.md`\n"
            "- [ ] Includes one fully filled-in worked example, using "
            "this exact skills-repo project as the sample"
        ),
    },
    {
        "title": "Write SKILL.md for project-epic-planner",
        "labels": ["size:S"],
        "body": (
            "### Acceptance criteria\n"
            "- [ ] No `disable-model-invocation` flag \u2014 planning is "
            "reversible (it produces a reviewable document, nothing acts "
            "on it automatically) and stays model-invoked, per ADR 0002\n"
            "- [ ] Trigger description covers implicit phrasing (\"help "
            "me plan this\", \"what would the roadmap look like\") not "
            "just literal \"epics\"/\"stories\" mentions\n"
            "- [ ] Output format documented: a JSON file matching the "
            "schema from github-project-bootstrap's Epic 2, plus a "
            "rendered markdown doc for human review"
        ),
    },
    {
        "title": "Test against a different, unrelated small project",
        "labels": ["size:M"],
        "body": (
            "### Acceptance criteria\n"
            "- [ ] Generate a full plan for a project that isn't "
            "`pr-agent` or this skills repo itself\n"
            "- [ ] Review ticket quality against the five rules from the "
            "reference doc without personally rewriting any ticket\n"
            "- [ ] Findings recorded in this issue \u2014 if quality "
            "doesn't hold without manual correction, that's a signal to "
            "revise the reference doc, not just this one output"
        ),
    },
]

# ---------------------------------------------------------------------------
# Epic 5: Skills repo scaffolding & governance
# ---------------------------------------------------------------------------

_EPIC_5_ISSUES = [
    {
        "title": "Write README.md",
        "labels": ["size:S"],
        "body": (
            "### Acceptance criteria\n"
            "- [ ] States the repo's purpose and points to "
            "`PROJECT_PLAN.md`/`TRACKER.md` while no skills have landed "
            "yet\n"
            "- [ ] Install instructions included, ready to make sense "
            "once the first skill ships\n"
            "- [ ] Updated with a linked entry per skill as each one "
            "closes \u2014 this issue itself only covers the initial "
            "skeleton, not the ongoing updates"
        ),
    },
    {
        "title": "Write CLAUDE.md",
        "labels": ["size:S"],
        "body": (
            "The governance rules right-sized from SKILLS_PLAN.md's "
            "\"adopt now\" list \u2014 no bucket-folder language (deferred, "
            "see ADR 0001's sibling reasoning in PROJECT_PLAN.md), a flat "
            "promoted/not-promoted rule (\"finished skill = README entry + "
            "plugin.json entry\"), the invocation-control rule from ADR "
            "0002, the `claude plugin validate . --strict` step, and "
            "`scripts/link-skills.sh` usage instructions.\n\n"
            "### Acceptance criteria\n"
            "- [ ] All five elements above present\n"
            "- [ ] Explicitly states no `package.json`-synced versioning "
            "\u2014 `plugin.json`'s `version` field is the sole source of "
            "truth, and why (no other JS tooling exists in this repo)"
        ),
    },
    {
        "title": "Add LICENSE",
        "labels": ["size:S"],
        "body": (
            "### Acceptance criteria\n"
            "- [ ] MIT license file present, matching the choice already "
            "made for `pr-agent`"
        ),
    },
    {
        "title": "Write scripts/link-skills.sh",
        "labels": ["size:S"],
        "body": (
            "Symlinks every top-level folder containing a `SKILL.md` into "
            "`~/.claude/skills` and `~/.agents/skills`, so a `git pull` "
            "keeps installed skills current without a reinstall.\n\n"
            "### Acceptance criteria\n"
            "- [ ] Script discovers skill folders by presence of "
            "`SKILL.md`, not a hardcoded list \u2014 it should need no "
            "edits when a new skill folder is added\n"
            "- [ ] Safe to run with zero skill folders present (today's "
            "state) \u2014 no-ops cleanly rather than erroring"
        ),
    },
    {
        "title": "Write ADR 0001: four skills, not one",
        "labels": ["size:S"],
        "body": (
            "### Acceptance criteria\n"
            "- [ ] `docs/adr/0001-four-skills-not-one.md` present, "
            "formalizing the reasoning already worked out in "
            "SKILLS_PLAN.md and this conversation"
        ),
    },
    {
        "title": "Write ADR 0002: invocation control on the GitHub-acting skills",
        "labels": ["size:S"],
        "body": (
            "### Acceptance criteria\n"
            "- [ ] `docs/adr/0002-invocation-control-on-github-actions.md` "
            "present, documenting why `github-repo-init` and "
            "`github-project-bootstrap` are user-invoked-only while the "
            "other two stay model-invoked"
        ),
    },
]

# ---------------------------------------------------------------------------
# Epic 6: Repo creation & validation
# ---------------------------------------------------------------------------

_EPIC_6_ISSUES = [
    {
        "title": "Create and push alvincrespo/skills",
        "labels": ["size:S"],
        "body": (
            "```bash\n"
            "gh repo create alvincrespo/skills \\\n"
            "  --public \\\n"
            '  --description "A small, growing collection of Claude '
            'Skills for real engineering workflows." \\\n'
            "  --source=. \\\n"
            "  --remote=origin \\\n"
            "  --push\n"
            "```\n\n"
            "Ideally run via `github-repo-init`'s own script once it "
            "exists (Epic 3) \u2014 same bootstrapping situation "
            "`pr-agent` was in: the very first push of a repo can't use a "
            "skill that isn't installed anywhere yet, so running the "
            "underlying script directly is expected and fine.\n\n"
            "### Acceptance criteria\n"
            "- [ ] Repo created and pushed with the scaffolding from "
            "Epic 5 as the initial commit"
        ),
    },
    {
        "title": "Set repository topics",
        "labels": ["size:S"],
        "body": (
            "### Acceptance criteria\n"
            "- [ ] Topics set: `claude-skills`, `claude-code`, "
            "`ai-agent-tooling`, `github-automation`"
        ),
    },
    {
        "title": "Create plugin manifests and validate",
        "labels": ["size:M"],
        "body": (
            "`.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` "
            "\u2014 the actual \"shareable\" mechanism, the whole point of "
            "this repo existing.\n\n"
            "**Do not guess the schema.** This conversation already hit "
            "real, non-obvious `gh` CLI behavior four separate times by "
            "assuming documented-elsewhere behavior applied directly "
            "(`state=all`, POST-by-default with `-f` flags, `--milestone` "
            "wanting a title not a number). Confirm the current exact "
            "`plugin.json`/`marketplace.json` schema against Claude Code's "
            "own plugin documentation before writing either file.\n\n"
            "### Acceptance criteria\n"
            "- [ ] Schema confirmed against current official docs, not "
            "assumed from this repo's memory of a similar-looking example\n"
            "- [ ] Both manifests present, `skills` array starting empty "
            "or with placeholders, filled in as each skill epic closes\n"
            "- [ ] `claude plugin validate . --strict` passes"
        ),
    },
    {
        "title": "Pre-push secret scan of the initial commit",
        "labels": ["size:S", "safety-critical"],
        "body": (
            "### Acceptance criteria\n"
            "- [ ] Initial commit scanned by hand or with a tool "
            "(`gitleaks`, `trufflehog`) before trusting it on a public "
            "remote \u2014 same habit carried over from `pr-agent`'s repo-"
            "creation story"
        ),
    },
]

# ---------------------------------------------------------------------------

EPICS = [
    {
        "title": "Epic: Skill \u2014 github-labels-setup",
        "labels": ["priority:P0", "size:M"],
        "depends_on": [],
        "body": (
            "Standalone, reusable independent of the other three \u2014 "
            "\"set up my standard labels on this repo\" is a complete "
            "request with no milestone, board, or issues involved.\n\n"
            "Built first: smallest scope, cleanly extractable from code "
            "that already works, and a dependency of "
            "github-project-bootstrap, so building it first gives that "
            "epic something real to call into rather than a stub."
        ),
        "issues": _EPIC_1_ISSUES,
    },
    {
        "title": "Epic: Skill \u2014 github-project-bootstrap",
        "labels": ["priority:P0", "size:L"],
        "depends_on": ["Epic: Skill \u2014 github-labels-setup"],
        "body": (
            "Milestone, linked Project v2 board, and every epic/story "
            "issue with real sub-issue and blocked-by relationships. The "
            "part with zero remaining unknowns \u2014 every `gh` CLI quirk "
            "in the underlying script was discovered against a live API "
            "across four actual `pr-agent` bootstrap runs, not guessed at.\n\n"
            "Depends on github-labels-setup: this skill calls into that "
            "one for label creation rather than duplicating the logic."
        ),
        "issues": _EPIC_2_ISSUES,
    },
    {
        "title": "Epic: Skill \u2014 github-repo-init",
        "labels": ["priority:P0", "size:S"],
        "depends_on": [],
        "body": (
            "Repo creation and baseline scaffolding, decoupled from "
            "issue-bootstrapping on purpose \u2014 `pr-agent`'s repo had to "
            "be deleted and recreated twice mid-debugging, independent of "
            "any issue content, which is exactly the scenario this "
            "separation exists for."
        ),
        "issues": _EPIC_3_ISSUES,
    },
    {
        "title": "Epic: Skill \u2014 project-epic-planner",
        "labels": ["priority:P0", "size:L"],
        "depends_on": [],
        "body": (
            "The highest-leverage and most subjective of the four \u2014 "
            "this is where the actual lessons from building `pr-agent`'s "
            "tracker (one story per tool, self-contained tickets, testing "
            "as AC, real dependency graphs) get encoded as standing rules "
            "instead of one-off corrections. Expect more iteration here "
            "than the other three."
        ),
        "issues": _EPIC_4_ISSUES,
    },
    {
        "title": "Epic: Skills repo scaffolding & governance",
        "labels": ["priority:P0", "size:S"],
        "depends_on": [],
        "body": (
            "README, CLAUDE.md, LICENSE, the local-dev linking script, and "
            "two ADRs formalizing decisions already reasoned through in "
            "SKILLS_PLAN.md. Parallel-safe with all three skill epics \u2014 "
            "none of this depends on any skill actually being built yet."
        ),
        "issues": _EPIC_5_ISSUES,
    },
    {
        "title": "Epic: Repo creation & validation",
        "labels": ["priority:P0", "size:S"],
        "depends_on": ["Epic: Skills repo scaffolding & governance"],
        "body": (
            "Blocked by scaffolding on purpose: the initial commit needs "
            "README/CLAUDE.md/LICENSE to exist before there's anything "
            "worth pushing."
        ),
        "issues": _EPIC_6_ISSUES,
    },
]

RELEASE_VALIDATION_ISSUE = {
    "title": "Release validation: all four skills built, packaged, and chain-tested",
    "labels": ["priority:P0", "size:S"],
    "body": (
        "The actual ship-it milestone. Do not close until every item below "
        "is checked against real, working skills \u2014 not a plan.\n\n"
        "### Acceptance criteria\n"
        "- [ ] All four skills exist with complete `SKILL.md` files and "
        "pass `claude plugin validate . --strict`\n"
        "- [ ] Full chain tested end-to-end on a throwaway repo: "
        "repo-init \u2192 plan \u2192 review \u2192 labels + bootstrap\n"
        "- [ ] Each skill packaged as a standalone `.skill` file via "
        "`package_skill.py`, in addition to the plugin/marketplace route\n"
        "- [ ] `README.md` updated with all four skill entries, each "
        "linked to its `SKILL.md`\n"
        "- [ ] `plugin.json`'s `skills` array includes all four"
    ),
}
