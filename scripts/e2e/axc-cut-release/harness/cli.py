"""Command line entry point: parse options, run the stages, turn the outcome into an exit code."""

from __future__ import annotations

import argparse
import signal

from . import preflight
from .config import (BASE_VERSION, EXIT_ABORTED, EXIT_CHECKS_FAILED, EXIT_INTERRUPTED, EXIT_OK,
                     NAME_PREFIX, NEXT_VERSION, TAG, Options, Paths)
from .context import RunContext
from .errors import HarnessError
from .github import GitHub
from .log import Logger
from .report import Report
from .sandbox import Sandbox
from .scenario import ReleaseScenario


def parse_args(argv: list[str] | None) -> Options:
    p = argparse.ArgumentParser(
        description="End-to-end test of the axc-cut-release skills on a throwaway GitHub repo.")
    p.add_argument("--dry-run", action="store_true",
                   help="check the environment and print the plan; create nothing")
    p.add_argument("--keep", action="store_true",
                   help="skip teardown, to inspect the repo and folder afterwards")
    p.add_argument("--ssh", action="store_true", help="use an SSH remote instead of HTTPS")
    p.add_argument("--model", help="model for the headless Claude sessions")
    p.add_argument("--max-budget-usd", type=float, default=3.0,
                   help="spend cap per Claude session (default 3)")
    p.add_argument("--timeout-min", type=int, default=15,
                   help="kill a Claude session after this many minutes")
    ns = p.parse_args(argv)
    return Options(dry_run=ns.dry_run, keep=ns.keep, ssh=ns.ssh, model=ns.model,
                   max_budget_usd=ns.max_budget_usd, timeout_min=ns.timeout_min)


def print_plan(ctx: RunContext) -> None:
    log = ctx.log
    log.step("Plan (dry run, nothing created)")
    log.info(f"  1. create {ctx.paths.tmp}/{NAME_PREFIX}<timestamp>/ and a private repo of that "
             f"name on {ctx.login}")
    log.info("  2. push an initial commit, change the README, push again")
    log.info(f"  3. `/axc-cut-release patch`  -> verify a PR bumping {BASE_VERSION} -> {NEXT_VERSION}")
    log.info("  4. merge that PR through the API")
    log.info(f"  5. `/axc-cut-release {NEXT_VERSION}`  -> verify tag {TAG} on the remote")
    log.info("  6. delete the folder and the repo")
    log.info(f"  Two Claude sessions, each capped at ${ctx.options.max_budget_usd}.")


def summarize(ctx: RunContext) -> int:
    log, report = ctx.log, ctx.report
    log.step("Result")
    if ctx.aborted:
        log.info(f"  ABORTED before all checks ran: {ctx.aborted.splitlines()[0][:300]}")
    teardown = "" if not ctx.name else f"; teardown {'ok' if ctx.teardown_ok else 'INCOMPLETE'}"
    log.info(f"  {report.passed_count}/{len(report.results)} checks that ran passed{teardown}")
    for result in report.failed:
        log.info(f"  ✗ {result.name}")
    if ctx.session_costs:
        costs = ", ".join(f"{k} ${v:.2f}" for k, v in ctx.session_costs.items())
        log.info(f"  agent cost: {costs} (total ${sum(ctx.session_costs.values()):.2f})")
    if ctx.name:
        log.info(f"  logs: {ctx.logs_dir}")
    return EXIT_OK if not report.failed and ctx.teardown_ok else EXIT_CHECKS_FAILED


def main(argv: list[str] | None = None, paths: Paths | None = None) -> int:
    options = parse_args(argv)
    log = Logger()
    ctx = RunContext(options=options, paths=paths or Paths.default(), log=log,
                     report=Report(log), gh=GitHub())

    # SIGTERM should clean up like Ctrl-C does.
    previous = signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    exit_code = EXIT_OK
    try:
        preflight.check_environment(ctx)
        if options.dry_run:
            print_plan(ctx)
            return EXIT_OK
        with Sandbox(ctx) as box:
            ReleaseScenario(ctx, box.repo, box.claude).run()
    except HarnessError as exc:
        log.info(f"\nerror: {exc}")
        ctx.aborted = str(exc)
        exit_code = EXIT_ABORTED
    except KeyboardInterrupt:
        log.info("\ninterrupted; the sandbox has been torn down")
        ctx.aborted = "interrupted"
        exit_code = EXIT_INTERRUPTED
    finally:
        signal.signal(signal.SIGTERM, previous)

    summary = summarize(ctx)
    log.close()
    return exit_code or summary
