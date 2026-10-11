#!/usr/bin/env python3
"""
End-to-end test of the axc-cut-release skills against a real, throwaway
private GitHub repository. Run it by hand; it is not meant for CI, because it
drives real headless Claude sessions (they cost tokens).

    python3 scripts/e2e/axc-cut-release/run.py --dry-run   # checks only, creates nothing
    python3 scripts/e2e/axc-cut-release/run.py             # the full run

What one run does
  Set up     verify <repo>/tmp exists and is gitignored (create it if missing),
             make tmp/axc-cut-release-e2e-<timestamp>/, `git init` it with a
             README, create a private repo of that name on your account.
  Test       push an initial commit (README + a VERSION file + a release.json),
             change the README, commit, push, then run the skills:
               1. `/axc-cut-release patch`  -> opens a bump PR   (Phase 1)
               2. the script merges that PR through the API
               3. `/axc-cut-release 0.1.1`  -> tags and pushes   (Phase 2)
             and verify the repo ends up in the right state.
  Tear down  delete the local folder and the GitHub repo (only the ones this
             run created), even if the test failed or you pressed Ctrl-C.

Needs: git, gh (logged in, with the `delete_repo` scope), claude (logged in).
    gh auth refresh -h github.com -s delete_repo

The throwaway project's "release workflow" lives at ci/release.yml, outside
.github/, so pushing a tag runs nothing on GitHub. The tag is the only thing
that "publishes", and it is deleted with the repo.

Exit codes: 0 every check passed, 1 a check failed (or teardown did), 2 the run
aborted (setup failed, or a git/gh call errored mid-test), 130 interrupted.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
TMP = REPO_ROOT / "tmp"
LOG_ROOT = TMP / "e2e-logs"
SKILLS = [
    "axc-cut-release",
    "axc-cut-release-bump",
    "axc-cut-release-preflight",
    "axc-cut-release-tag",
]
NAME_PREFIX = "axc-cut-release-e2e-"
BASE_VERSION = "0.1.0"
NEXT_VERSION = "0.1.1"  # what `patch` should produce from BASE_VERSION

AUTOMATION_NOTE = (
    "This is an automated end-to-end test in a throwaway repository. Nobody is "
    "available to answer questions, so if the skill asks you to confirm a version "
    "or a plan, answer yes and continue. Do not stop to ask."
)
ALLOWED_TOOLS = ",".join(
    ["Bash(git:*)", "Bash(gh:*)", "Bash(python3:*)", "Bash(test:*)", "Bash(ls:*)",
     "Bash(cat:*)", "Read", "Glob", "Grep", "Skill"]
)


class SetupError(Exception):
    """Something needed before the test could run is missing or failed."""


@dataclass
class Context:
    args: argparse.Namespace
    login: str = ""
    name: str = ""
    project: Path = Path()
    logs: Path = Path()
    remote_url: str = ""
    created_repo: str | None = None   # "owner/name", set only once GitHub says it exists
    results: list[tuple[str, bool, str]] = field(default_factory=list)
    costs: dict[str, float] = field(default_factory=dict)
    teardown_ok: bool = True
    aborted: str = ""                 # set when the run stopped before finishing the checks

    @property
    def full_name(self) -> str:
        return f"{self.login}/{self.name}"


# --- output -----------------------------------------------------------------

_log_file = None


def log(msg: str = "") -> None:
    print(msg, flush=True)
    if _log_file:
        _log_file.write(msg + "\n")
        _log_file.flush()


def step(msg: str) -> None:
    log(f"\n== {msg}")


def check(ctx: Context, name: str, ok: bool, detail: str = "") -> bool:
    ctx.results.append((name, bool(ok), detail))
    log(f"  {'✓' if ok else '✗'} {name}" + (f"\n      {detail}" if detail and not ok else ""))
    return bool(ok)


# --- running things -----------------------------------------------------------

def _env() -> dict[str, str]:
    env = dict(os.environ)
    env.update(NO_COLOR="1", GIT_TERMINAL_PROMPT="0", GH_PROMPT_DISABLED="1")
    return env


def run(cmd: list[str], cwd: Path | None = None, check_rc: bool = True, timeout: int = 180) -> str:
    result = subprocess.run(
        cmd, cwd=cwd, env=_env(), capture_output=True, text=True,
        stdin=subprocess.DEVNULL, timeout=timeout,
    )
    if check_rc and result.returncode != 0:
        detail = (result.stderr.strip() or result.stdout.strip())[:600]
        raise SetupError(f"`{' '.join(cmd)}` failed (exit {result.returncode}): {detail}")
    return result.stdout


def git(ctx: Context, *args: str, check_rc: bool = True) -> str:
    return run(["git", *args], cwd=ctx.project, check_rc=check_rc).strip()


def gh_api(path: str, method: str = "GET", fields: list[str] | None = None,
           raw: bool = False, check_rc: bool = True):
    cmd = ["gh", "api", "-X", method]
    if raw:
        cmd += ["-H", "Accept: application/vnd.github.raw+json"]
    for f in fields or []:
        cmd += f.split(" ", 1)   # "-f k=v" / "-F k=v"
    cmd.append(path)
    out = run(cmd, check_rc=check_rc)
    if raw:
        return out
    return json.loads(out) if out.strip() else None


def remote_refs(ctx: Context, *patterns: str) -> dict[str, str]:
    out = git(ctx, "ls-remote", "origin", *patterns)
    refs = {}
    for line in out.splitlines():
        sha, _, ref = line.partition("\t")
        refs[ref] = sha
    return refs


# --- preflight ------------------------------------------------------------------

def preflight(ctx: Context) -> None:
    step("Checking the environment")
    for tool in ("git", "gh", "claude"):
        if not shutil.which(tool):
            raise SetupError(f"`{tool}` is not installed or not on PATH")
    log("  ✓ git, gh and claude are installed")

    try:
        ctx.login = run(["gh", "api", "user", "-q", ".login"]).strip()
    except SetupError as exc:
        raise SetupError(f"gh is not logged in ({exc}). Run `gh auth login`.")
    log(f"  ✓ gh is logged in as {ctx.login}")

    headers = run(["gh", "api", "-i", "user"], check_rc=False)
    m = re.search(r"(?im)^x-oauth-scopes:\s*(.*)$", headers)
    if m:
        scopes = {s.strip() for s in m.group(1).split(",") if s.strip()}
        if "delete_repo" not in scopes:
            raise SetupError(
                "the gh token lacks the `delete_repo` scope, so teardown couldn't remove the "
                "repo it creates. Run: gh auth refresh -h github.com -s delete_repo"
            )
        log("  ✓ the gh token can delete repos")
    else:
        log("  ! can't read the token's scopes (fine-grained token?); make sure it can create "
            "and delete repos, or teardown will leave one behind")

    # The tmp folder must be gitignored before we put a project in it.
    probe = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "check-ignore", "-q", "tmp/.probe"],
        capture_output=True, stdin=subprocess.DEVNULL,
    )
    if probe.returncode != 0:
        raise SetupError("tmp/ is not gitignored in this repo. Add a `tmp/` line to .gitignore first.")
    log("  ✓ tmp/ is gitignored")


# --- setup ----------------------------------------------------------------------

def setup(ctx: Context) -> None:
    step("Setting up the project")
    if TMP.exists():
        log(f"  tmp/ exists: {TMP}")
    else:
        log(f"  tmp/ does not exist, creating it: {TMP}")
        TMP.mkdir()

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    ctx.name = f"{NAME_PREFIX}{stamp}"
    ctx.project = TMP / ctx.name
    ctx.logs = LOG_ROOT / ctx.name
    ctx.logs.mkdir(parents=True)
    global _log_file
    _log_file = open(ctx.logs / "run.log", "w", encoding="utf-8")
    ctx.project.mkdir()
    log(f"  project folder: {ctx.project}")
    log(f"  logs (kept after teardown): {ctx.logs}")

    git(ctx, "init", "-q", "-b", "main")
    if not git(ctx, "config", "user.email", check_rc=False):
        git(ctx, "config", "user.email", "e2e@example.invalid")
        git(ctx, "config", "user.name", "axc-cut-release e2e")
    (ctx.project / "README.md").write_text(
        f"# {ctx.name}\n\nThrowaway repository for the axc-cut-release end-to-end test.\n"
    )
    log("  ✓ git repository initialised with a README")

    gh_api("user/repos", "POST", [
        f"-f name={ctx.name}", "-F private=true",
        "-f description=Throwaway axc-cut-release e2e repo (safe to delete)",
    ])
    ctx.created_repo = ctx.full_name   # from here on, teardown owns deleting it
    host = "git@github.com:" if ctx.args.ssh else "https://github.com/"
    ctx.remote_url = f"{host}{ctx.full_name}.git"
    git(ctx, "remote", "add", "origin", ctx.remote_url)
    log(f"  ✓ created private repo {ctx.full_name}")

    # Install the skills where the project's own Claude session finds them. They
    # are excluded from git so the working tree stays clean (the skills require that).
    skills_dir = ctx.project / ".claude" / "skills"
    skills_dir.mkdir(parents=True)
    for skill in SKILLS:
        shutil.copytree(
            REPO_ROOT / skill, skills_dir / skill,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "node_modules"),
        )
    with open(ctx.project / ".git" / "info" / "exclude", "a") as fh:
        fh.write(".claude/skills/\n")
    log(f"  ✓ installed {len(SKILLS)} skills into .claude/skills/")


# --- the test -------------------------------------------------------------------

def write_fixture(ctx: Context) -> None:
    (ctx.project / "VERSION").write_text(f"{BASE_VERSION}\n")
    (ctx.project / "ci").mkdir()
    (ctx.project / "ci" / "release.yml").write_text(
        'on:\n  push:\n    tags: ["v*"]\npermissions:\n  contents: write\n'
    )
    config = {
        "repo": ctx.full_name,
        "mainBranch": "main",
        "version": {"files": [{"path": "VERSION", "match": "{V}"}]},
        "commit": {"branch": "release/v{V}", "title": "release: v{V}"},
        "checks": {"test": "test -f VERSION"},
        "release": {
            "tagFormat": "v{V}",
            "artifact": "github-release",
            "workflow": "ci/release.yml",
            "workflowChecks": ["contents: write", 'tags: ["v*"]'],
        },
    }
    (ctx.project / ".claude").mkdir(exist_ok=True)
    (ctx.project / ".claude" / "release.json").write_text(json.dumps(config, indent=2) + "\n")


def run_claude(ctx: Context, label: str, skill_args: str) -> dict:
    prompt = f"{skill_args}\n\n{AUTOMATION_NOTE}"
    (ctx.logs / f"{label}.prompt.txt").write_text(prompt)
    cmd = ["claude", "-p", prompt, "--output-format", "stream-json", "--verbose",
           "--allowedTools", ALLOWED_TOOLS, "--max-budget-usd", str(ctx.args.max_budget_usd),
           "--no-session-persistence", "--setting-sources", "project,local", "--strict-mcp-config"]
    if ctx.args.model:
        cmd += ["--model", ctx.args.model]
    log(f"  running: {skill_args}   (cwd {ctx.project.name}, budget ${ctx.args.max_budget_usd})")

    stderr_file = open(ctx.logs / f"{label}.stderr.txt", "w")
    proc = subprocess.Popen(cmd, cwd=ctx.project, env=_env(), stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=stderr_file, text=True)
    timed_out = threading.Event()

    def kill() -> None:
        timed_out.set()
        proc.kill()

    timer = threading.Timer(ctx.args.timeout_min * 60, kill)
    timer.daemon = True
    timer.start()
    started = time.time()
    final_text, cost, is_error, subtype = "", None, None, None
    try:
        final_text, cost, is_error, subtype = _read_stream(ctx, label, proc)
    finally:
        timer.cancel()
        if proc.poll() is None:      # Ctrl-C or an error: don't leave the session running
            proc.kill()
        code = proc.wait()
        stderr_file.close()
    (ctx.logs / f"{label}.final.txt").write_text(final_text)
    ctx.costs[label] = float(cost or 0)
    log(f"    finished in {time.time() - started:.0f}s, exit {code}, "
        f"{subtype or 'no result event'}, cost ${cost if cost is not None else '?'}")
    return {"code": code, "timed_out": timed_out.is_set(), "is_error": is_error, "final": final_text}


def _read_stream(ctx: Context, label: str, proc: subprocess.Popen):
    """Follow claude's stream-json output, logging progress; return (final text, cost, is_error, subtype)."""
    final_text, cost, is_error, subtype = "", None, None, None
    with open(ctx.logs / f"{label}.stream.jsonl", "w") as stream:
        for line in proc.stdout:
            stream.write(line)
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get("type") == "assistant":
                for item in ev.get("message", {}).get("content", []):
                    if item.get("type") == "tool_use":
                        what = item.get("input", {}).get("command") or json.dumps(item.get("input", {}))
                        log(f"    agent -> {item.get('name')}: {str(what)[:200]}")
                    elif item.get("type") == "text":
                        log(f"    agent says: {' '.join(item['text'].split())[:240]}")
            elif ev.get("type") == "result":
                final_text = ev.get("result", "") or ""
                cost = ev.get("total_cost_usd")
                is_error = ev.get("is_error")
                subtype = ev.get("subtype")
    return final_text, cost, is_error, subtype


def verify_session(ctx: Context, label: str, session: dict) -> None:
    check(ctx, f"{label}: the Claude session finished", 
          session["code"] == 0 and not session["timed_out"] and not session["is_error"],
          f"exit {session['code']}, timed out: {session['timed_out']}, is_error: {session['is_error']}. "
          f"See {ctx.logs}/{label}.stream.jsonl")


def phase_bump(ctx: Context) -> int | None:
    step(f"Phase 1: /axc-cut-release patch   (expects a PR bumping {BASE_VERSION} -> {NEXT_VERSION})")
    main_before = remote_refs(ctx, "refs/heads/main").get("refs/heads/main")
    session = run_claude(ctx, "phase1-bump", "/axc-cut-release patch")
    verify_session(ctx, "phase 1", session)

    branch = f"release/v{NEXT_VERSION}"
    heads = remote_refs(ctx, f"refs/heads/{branch}")
    check(ctx, f"branch {branch} was pushed", f"refs/heads/{branch}" in heads)

    prs = gh_api(f"repos/{ctx.full_name}/pulls?state=open&head={ctx.login}:{branch}") or []
    pr = prs[0] if len(prs) == 1 else None
    check(ctx, "exactly one open PR from that branch", len(prs) == 1, f"found {len(prs)}")
    if pr:
        check(ctx, "the PR targets main", pr["base"]["ref"] == "main", pr["base"]["ref"])
        check(ctx, f"the PR title is 'release: v{NEXT_VERSION}'",
              pr["title"] == f"release: v{NEXT_VERSION}", pr["title"])

    if f"refs/heads/{branch}" in heads:
        cmp_ = gh_api(f"repos/{ctx.full_name}/compare/main...{branch}")
        files = cmp_["files"]
        check(ctx, "the PR changes exactly one file, VERSION, by one line",
              len(files) == 1 and files[0]["filename"] == "VERSION"
              and files[0]["additions"] == 1 and files[0]["deletions"] == 1,
              json.dumps([(f["filename"], f["additions"], f["deletions"]) for f in files]))
        check(ctx, "the PR holds exactly one commit", cmp_["ahead_by"] == 1, f"ahead by {cmp_['ahead_by']}")
        version = gh_api(f"repos/{ctx.full_name}/contents/VERSION?ref={branch}", raw=True).strip()
        check(ctx, f"VERSION on the branch is {NEXT_VERSION}", version == NEXT_VERSION, version)

    check(ctx, "main was not touched", remote_refs(ctx, "refs/heads/main").get("refs/heads/main") == main_before)
    check(ctx, "no tag exists yet", not remote_refs(ctx, "refs/tags/*"))
    return pr["number"] if pr else None


def merge_pr(ctx: Context, number: int) -> bool:
    step(f"Merging PR #{number} (the part a human does between the two phases)")
    out = gh_api(f"repos/{ctx.full_name}/pulls/{number}/merge", "PUT", ["-f merge_method=squash"])
    return check(ctx, f"PR #{number} merged", bool(out and out.get("merged")), json.dumps(out))


def phase_tag(ctx: Context) -> None:
    step(f"Phase 2: /axc-cut-release {NEXT_VERSION}   (expects preflight, then tag v{NEXT_VERSION} pushed)")
    session = run_claude(ctx, "phase2-tag", f"/axc-cut-release {NEXT_VERSION}")
    verify_session(ctx, "phase 2", session)

    tag = f"v{NEXT_VERSION}"
    tags = remote_refs(ctx, "refs/tags/*")
    check(ctx, f"exactly one tag on the remote, {tag}", list(tags) == [f"refs/tags/{tag}", f"refs/tags/{tag}^{{}}"],
          json.dumps(sorted(tags)))
    main_head = remote_refs(ctx, "refs/heads/main").get("refs/heads/main")
    check(ctx, f"{tag} is annotated and points at main's head",
          bool(main_head) and tags.get(f"refs/tags/{tag}^{{}}") == main_head,
          f"peeled {tags.get(f'refs/tags/{tag}^{{}}')} vs main {main_head}")

    # Read the message from the remote's tag object (into a scratch ref), not from the
    # local tag the skill created, so a tag that was never pushed can't pass this.
    fetched = subprocess.run(
        ["git", "-C", str(ctx.project), "fetch", "-q", "origin", f"+refs/tags/{tag}:refs/e2e/{tag}"],
        env=_env(), capture_output=True, stdin=subprocess.DEVNULL).returncode == 0
    subject = git(ctx, "for-each-ref", "--format=%(contents:subject)", f"refs/e2e/{tag}") if fetched else ""
    check(ctx, f"the remote tag's message is 'Release v{NEXT_VERSION}'",
          subject == f"Release v{NEXT_VERSION}", subject or "tag not fetched from the remote")

    version = gh_api(f"repos/{ctx.full_name}/contents/VERSION?ref=main", raw=True).strip()
    check(ctx, f"VERSION on main is {NEXT_VERSION}", version == NEXT_VERSION, version)
    commits = gh_api(f"repos/{ctx.full_name}/commits?sha=main&per_page=100") or []
    check(ctx, "main has exactly 3 commits (initial, README, the squashed bump PR): nothing was pushed to it directly",
          len(commits) == 3, f"{len(commits)} commits")


def run_test(ctx: Context) -> None:
    step("Initial commit")
    write_fixture(ctx)
    git(ctx, "add", "-A")
    git(ctx, "commit", "-q", "-m", "Initial commit")
    git(ctx, "push", "-q", "-u", "origin", "main")
    head = git(ctx, "rev-parse", "HEAD")
    check(ctx, "initial commit pushed", remote_refs(ctx, "refs/heads/main").get("refs/heads/main") == head)

    step("Change the README, commit and push")
    with open(ctx.project / "README.md", "a") as fh:
        fh.write(f"\nUpdated by the e2e run {ctx.name}.\n")
    git(ctx, "commit", "-q", "-am", "Update the README")
    git(ctx, "push", "-q", "origin", "main")
    head = git(ctx, "rev-parse", "HEAD")
    check(ctx, "README change pushed", remote_refs(ctx, "refs/heads/main").get("refs/heads/main") == head)

    number = phase_bump(ctx)
    if number is None:
        check(ctx, "phase 2 skipped: there is no PR to merge", False)
        return
    if not merge_pr(ctx, number):
        return
    phase_tag(ctx)


# --- teardown ---------------------------------------------------------------------

def teardown(ctx: Context) -> None:
    step("Tearing down")
    if ctx.args.keep:
        log(f"  --keep: leaving everything in place.\n    local:  {ctx.project}\n"
            f"    GitHub: https://github.com/{ctx.created_repo}" if ctx.created_repo else "  --keep: nothing to keep")
        return

    # Local folder: only ever a direct child of tmp/ that we named.
    project = ctx.project
    if ctx.name and project.exists():
        if project.resolve().parent == TMP.resolve() and project.name.startswith(NAME_PREFIX):
            shutil.rmtree(project, ignore_errors=True)
        else:
            log(f"  ! refusing to delete {project}: not one of this run's folders in tmp/")
            ctx.teardown_ok = False
    if ctx.name:
        gone = not project.exists()
        log(f"  {'✓' if gone else '✗'} removed {project}")
        ctx.teardown_ok &= gone

    # GitHub repo: only the one this run created, and only if the name is ours.
    if ctx.created_repo:
        owner, _, name = ctx.created_repo.partition("/")
        if not name.startswith(NAME_PREFIX) or owner != ctx.login:
            log(f"  ! refusing to delete {ctx.created_repo}: not a repo this script creates")
            ctx.teardown_ok = False
            return
        try:
            gh_api(f"repos/{ctx.created_repo}", "DELETE")
            still = subprocess.run(["gh", "api", f"repos/{ctx.created_repo}"], env=_env(),
                                   capture_output=True, stdin=subprocess.DEVNULL).returncode == 0
        except SetupError as exc:
            log(f"  ✗ could not delete {ctx.created_repo}: {exc}")
            log(f"    Delete it by hand:  gh repo delete {ctx.created_repo} --yes")
            ctx.teardown_ok = False
            return
        log(f"  {'✗' if still else '✓'} {'STILL EXISTS: ' if still else 'deleted '}{ctx.created_repo}")
        ctx.teardown_ok &= not still
        if still:
            log(f"    Delete it by hand:  gh repo delete {ctx.created_repo} --yes")


# --- main -------------------------------------------------------------------------

def summarize(ctx: Context) -> int:
    failed = [r for r in ctx.results if not r[1]]
    step("Result")
    if ctx.aborted:
        log(f"  ABORTED before all checks ran: {ctx.aborted.splitlines()[0][:300]}")
    log(f"  {len(ctx.results) - len(failed)}/{len(ctx.results)} checks that ran passed"
        + (f"; teardown {'ok' if ctx.teardown_ok else 'INCOMPLETE'}" if ctx.name else ""))
    for name, _, detail in failed:
        log(f"  ✗ {name}")
    if ctx.costs:
        log("  agent cost: " + ", ".join(f"{k} ${v:.2f}" for k, v in ctx.costs.items())
            + f" (total ${sum(ctx.costs.values()):.2f})")
    if ctx.name:
        log(f"  logs: {ctx.logs}")
    return 0 if not failed and ctx.teardown_ok else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="End-to-end test of the axc-cut-release skills on a throwaway GitHub repo.")
    p.add_argument("--dry-run", action="store_true", help="check the environment and print the plan; create nothing")
    p.add_argument("--keep", action="store_true", help="skip teardown, to inspect the repo and folder afterwards")
    p.add_argument("--ssh", action="store_true", help="use an SSH remote instead of HTTPS")
    p.add_argument("--model", help="model for the headless Claude sessions")
    p.add_argument("--max-budget-usd", type=float, default=3.0, help="spend cap per Claude session (default 3)")
    p.add_argument("--timeout-min", type=int, default=15, help="kill a Claude session after this many minutes")
    ctx = Context(args=p.parse_args(argv))

    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    rc = 0
    try:
        preflight(ctx)
        if ctx.args.dry_run:
            step("Plan (dry run, nothing created)")
            log(f"  1. create {TMP}/{NAME_PREFIX}<timestamp>/ and a private repo of that name on {ctx.login}")
            log(f"  2. push an initial commit, change the README, push again")
            log(f"  3. `/axc-cut-release patch`  -> verify a PR bumping {BASE_VERSION} -> {NEXT_VERSION}")
            log(f"  4. merge that PR through the API")
            log(f"  5. `/axc-cut-release {NEXT_VERSION}`  -> verify tag v{NEXT_VERSION} on the remote")
            log(f"  6. delete the folder and the repo")
            log(f"  Two Claude sessions, each capped at ${ctx.args.max_budget_usd}.")
            return 0
        setup(ctx)
        run_test(ctx)
    except SetupError as exc:
        log(f"\nerror: {exc}")
        ctx.aborted = str(exc)
        rc = 2
    except KeyboardInterrupt:
        log("\ninterrupted, tearing down")
        ctx.aborted = "interrupted"
        rc = 130
    finally:
        if not ctx.args.dry_run and (ctx.name or ctx.created_repo):
            teardown(ctx)
    if ctx.args.dry_run:
        return rc
    summary_rc = summarize(ctx)
    return rc or summary_rc


if __name__ == "__main__":
    sys.exit(main())
