# `.claude/release.json` reference

The four release skills (`axc-cut-release`, `axc-cut-release-bump`, `axc-cut-release-preflight`,
`axc-cut-release-tag`) and their helper script, `axc-cut-release/scripts/release_tool.py`, all read one
config file at the root of the repo being released: `.claude/release.json`. It holds everything that
differs from one project to the next. If it is missing, the skills detect the stack (`package.json`
means npm, `go.mod` means Go) and offer to write one; the npm and Go examples below are those defaults.

## Conventions

- **`{V}`** is the version **without** a `v` prefix (`0.4.0`, not `v0.4.0`). Where a field supports
  `{V}`, it is replaced by the version being released.
- **Paths** (`version.files[].path`, `release.workflow`) are relative to the repo root. A
  `release.workflow` path may not point outside the repo.
- The file must be a JSON object. A config that is missing a required field, or has the wrong type for
  one, makes the helper exit `2` with a message naming the field.

## Fields

"Required" means the helper rejects the config without it. Every helper subcommand loads and checks
these, so treat them as required for any use.

| Field | Type | Required | Read by | `{V}` |
|---|---|---|---|---|
| `repo` | string, `owner/name` | no | preflight, tag, helper `phase` | no |
| `mainBranch` | string | **yes** | all four | no |
| `version.files[]` | non-empty list of objects | **yes** | all four, helper | no |
| `version.files[].path` | string, repo-relative | **yes** | all four, helper | no |
| `version.files[].match` | string with exactly one `{V}` | **yes** | all four, helper | **yes**, once |
| `version.bumpCommand` | string containing `{V}` | no | bump (helper `bump`) | **yes** |
| `commit.branch` | string | **yes** | router, bump | **yes** |
| `commit.title` | string | for the bump skill | bump | **yes** |
| `checks.lint` | string, a shell command | no | preflight | no |
| `checks.build` | string, a shell command | no | bump, preflight | no |
| `checks.test` | string, a shell command | no | bump, preflight | no |
| `checks.integrity` | string, a shell command | no | preflight | no |
| `release.tagFormat` | string | **yes** | router, bump, preflight, tag | **yes** |
| `release.artifact` | string: `npm`, `github-release`, or other | no | tag | no |
| `release.workflow` | string, repo-relative path | for preflight | preflight (helper `workflow-checks`), tag | no |
| `release.workflowChecks[]` | list of non-empty strings | no | preflight (helper `workflow-checks`) | no |

## Field details

**`repo`**: `owner/name` of the GitHub repo. Preflight compares it with `git remote origin` and
reports a mismatch as a warning (a fork or rename). The helper's `phase` passes it to
`gh pr list --repo` when it looks for an already-open release PR. The tag skill uses it in its
confirmation message and the link to the workflow's runs.

**`mainBranch`**: the branch releases are cut from, usually `main`. Releases only ever reach it
through a PR.

**`version.files[]`**: every file that holds the version, each as a `path` and a `match`. List all of
them (a source constant *and* the test that asserts it), so they stay in sync: `check-versions` fails
if they disagree.

**`version.files[].match`**: the text around the version, with `{V}` where the version sits, for
example `"version": "{V}"` or `const Version = "{V}"`. The helper matches `{V}` against `X.Y.Z` or
`X.Y.Z-prerelease` (no leading zeros) and uses the **first** match in the file. `bump` rewrites only
that version text and leaves the rest of the line alone. The match is a literal string: it is not a
regex, so it needs no escaping, but it must be specific enough that the first hit is the real version.

**`version.bumpCommand`**: optional. When set, `bump` runs this command instead of editing the files
itself, then still checks every file in `version.files[]`. Use it when a tool also updates a lockfile
(`npm version {V} --no-git-tag-version`). `{V}` is replaced, the command runs through the shell from
the repo root with a five-minute limit, and the helper prints it to stderr first. It must contain
`{V}`.

**`commit.branch`** and **`commit.title`**: the release PR's branch and its commit and PR title, for
example `release/v{V}` and `release: v{V}`. The router looks for an open PR on `commit.branch` so it
doesn't open a second one. The helper requires `commit.branch` but does not check `commit.title`; the
bump skill needs it.

**`checks.*`**: shell command lines, run from the repo root, all optional. The bump skill runs `build`
and `test` before committing. Preflight runs all four, skipping any that is empty or missing, but only
when its git-state, version and workflow checks found no hard failure; a missing optional tool for
`lint` is a warning, not a failure. `integrity` is for checks on what will ship, such as
`npm pack --dry-run` or `go mod verify`.

**`release.tagFormat`**: the tag name, for example `v{V}`.

**`release.artifact`**: only changes the wording of the tag skill's confirmation. `npm` says the tag
publishes the package to npm; `github-release` says it publishes a GitHub Release; any other value is
named as given.

**`release.workflow`** and **`release.workflowChecks[]`**: the workflow file that publishes the release,
and strings that must appear in it. `workflow-checks` reads the file and reports each string as found or
missing. It is a plain substring check: no regex, no YAML parsing, and a string that only appears in a
comment still counts. Use it to guard the settings a release depends on (a `tags:` trigger,
`contents: write`, a publish step, your test step).

## Examples

### Example 1: this repo

This is `.claude/release.json` in this repo, copied in full. It changes as the repo does (new test
files, new workflow checks), so **re-copy it whenever that file changes**. A test fails if the two differ.

```json
{
  "repo": "alvincrespo/skills",
  "mainBranch": "main",
  "version": {
    "files": [
      { "path": ".claude-plugin/plugin.json", "match": "\"version\": \"{V}\"" }
    ]
  },
  "commit": {
    "branch": "release/v{V}",
    "title": "release: v{V}"
  },
  "checks": {
    "lint": "shellcheck github-repo-init/scripts/setup_repo.sh scripts/*.sh",
    "build": "claude plugin validate . --strict && claude plugin validate .claude-plugin/plugin.json --strict",
    "test": "python3 -m unittest project-epic-planner/scripts/test_render_plan.py github-project-bootstrap/scripts/test_bootstrap_github_project.py github-labels-setup/scripts/test_ensure_labels.py axc-cut-release/scripts/test_release_tool.py axc-dependabot-sweep/scripts/test_config.py axc-dependabot-sweep/scripts/test_list_prs.py axc-dependabot-sweep/scripts/test_wait_for_pr.py axc-dependabot-sweep/scripts/test_worktree.py && npm ci --prefix axc-og-cards && npm test --prefix axc-og-cards && scripts/test-link-skills.sh",
    "integrity": "gitleaks git --redact --no-banner . && scripts/package-standalone-skills.sh"
  },
  "release": {
    "tagFormat": "v{V}",
    "artifact": "github-release",
    "workflow": ".github/workflows/release.yml",
    "workflowChecks": [
      "tags: [\"v*\"]",
      "contents: write",
      "Tag matches plugin.json version",
      "actions/setup-node",
      "npm ci --prefix axc-og-cards",
      "npm test --prefix axc-og-cards",
      "scripts/package-standalone-skills.sh",
      "gh release create",
      "dist/*.skill",
      "scripts/test-link-skills.sh",
      "axc-cut-release/scripts/test_release_tool.py"
    ]
  }
}
```

### Example 2: an npm package

The npm defaults the router uses when it detects a `package.json`. `npm version` updates
`package.json` and the lockfile together, so the bump is a `bumpCommand`; `version.files[]` still names
`package.json` so the result is verified. The `workflowChecks` strings are examples of what an npm
publish workflow with provenance contains: use ones that match yours.

```json
{
  "repo": "acme/widgets",
  "mainBranch": "main",
  "version": {
    "files": [
      { "path": "package.json", "match": "\"version\": \"{V}\"" }
    ],
    "bumpCommand": "npm version {V} --no-git-tag-version"
  },
  "commit": {
    "branch": "release/v{V}",
    "title": "release: v{V}"
  },
  "checks": {
    "lint": "npm run lint",
    "build": "npm run build",
    "test": "npm run test",
    "integrity": "npm pack --dry-run"
  },
  "release": {
    "tagFormat": "v{V}",
    "artifact": "npm",
    "workflow": ".github/workflows/release.yml",
    "workflowChecks": [
      "tags: [\"v*\"]",
      "id-token: write",
      "npm publish --provenance"
    ]
  }
}
```

### Example 3: a Go module

The Go defaults. The version lives in a source constant, which the router can't infer, so you tell it
where. The constant **and** the test that asserts it are both listed, so a bump that misses one
fails `check-versions` instead of failing CI later. There is no `bumpCommand`: the helper edits the two
literals itself.

```json
{
  "repo": "acme/tool",
  "mainBranch": "main",
  "version": {
    "files": [
      { "path": "version.go", "match": "const Version = \"{V}\"" },
      { "path": "version_test.go", "match": "const wantVersion = \"{V}\"" }
    ]
  },
  "commit": {
    "branch": "release/v{V}",
    "title": "release: v{V}"
  },
  "checks": {
    "lint": "go vet ./...",
    "build": "go build ./...",
    "test": "go test -race ./...",
    "integrity": "go mod verify"
  },
  "release": {
    "tagFormat": "v{V}",
    "artifact": "github-release",
    "workflow": ".github/workflows/release.yml",
    "workflowChecks": [
      "tags: [\"v*\"]",
      "contents: write",
      "action-gh-release"
    ]
  }
}
```
