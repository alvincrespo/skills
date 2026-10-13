"""Runs one headless Claude session and records what it did."""

from __future__ import annotations

import json
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import shell
from .config import ALLOWED_TOOLS, AUTOMATION_NOTE, EXPECTED_TOOL_ERRORS, Options
from .log import Logger


@dataclass(frozen=True)
class Session:
    exit_code: int
    timed_out: bool
    is_error: bool | None
    cost_usd: float
    final_text: str
    tool_errors: tuple[str, ...] = ()   # results of tool calls that failed, e.g. a denied command
    skills_used: tuple[str, ...] = ()   # skills the agent invoked, in order

    @property
    def finished_cleanly(self) -> bool:
        return self.exit_code == 0 and not self.timed_out and not self.is_error


@dataclass
class _StreamSummary:
    final_text: str = ""
    cost: float | None = None
    is_error: bool | None = None
    subtype: str | None = None
    tool_errors: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)


def tool_result_text(item: dict) -> str:
    """The text of a tool_result block, whether `content` is a string or a list of parts."""
    content = item.get("content", "")
    if isinstance(content, list):
        content = " ".join(p.get("text", "") for p in content if isinstance(p, dict))
    return " ".join(str(content).split())


def split_tool_errors(errors: tuple[str, ...] | list[str]) -> tuple[list[str], list[str]]:
    """(expected, unexpected): `expected` match a pattern in EXPECTED_TOOL_ERRORS."""
    expected = [e for e in errors if any(p.search(e) for p in EXPECTED_TOOL_ERRORS)]
    unexpected = [e for e in errors if e not in expected]
    return expected, unexpected


class ClaudeRunner:
    def __init__(self, options: Options, log: Logger, logs_dir: Path) -> None:
        self.options = options
        self.log = log
        self.logs_dir = logs_dir

    def command(self, prompt: str) -> list[str]:
        cmd = [
            "claude", "-p", prompt, "--output-format", "stream-json", "--verbose",
            "--allowedTools", ",".join(ALLOWED_TOOLS),
            "--max-budget-usd", str(self.options.max_budget_usd),
            "--no-session-persistence",
            # project + local only: your user-level copies of the skills must not be picked up
            "--setting-sources", "project,local",
            "--strict-mcp-config",
        ]
        if self.options.model:
            cmd += ["--model", self.options.model]
        return cmd

    def run(self, project: Path, label: str, skill_args: str, note: str = AUTOMATION_NOTE) -> Session:
        prompt = f"{skill_args}\n\n{note}"
        (self.logs_dir / f"{label}.prompt.txt").write_text(prompt)
        self.log.info(f"  running: {skill_args}   (in {project.name}, "
                      f"budget ${self.options.max_budget_usd})")

        started = time.time()
        timed_out = threading.Event()
        with open(self.logs_dir / f"{label}.stderr.txt", "w") as stderr_file:
            proc = subprocess.Popen(
                self.command(prompt), cwd=project, env=shell.child_env(),
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=stderr_file, text=True,
            )

            def kill() -> None:
                timed_out.set()
                proc.kill()

            timer = threading.Timer(self.options.timeout_min * 60, kill)
            timer.daemon = True
            timer.start()
            summary = _StreamSummary()
            try:
                summary = self._follow(proc, label)
            finally:
                timer.cancel()
                if proc.poll() is None:   # Ctrl-C or an error: never leave the session running
                    proc.kill()
                code = proc.wait()
                if proc.stdout:
                    proc.stdout.close()

        (self.logs_dir / f"{label}.final.txt").write_text(summary.final_text)
        cost = float(summary.cost or 0)
        self.log.info(f"    finished in {time.time() - started:.0f}s, exit {code}, "
                      f"{summary.subtype or 'no result event'}, "
                      f"cost ${summary.cost if summary.cost is not None else '?'}")
        return Session(code, timed_out.is_set(), summary.is_error, cost, summary.final_text,
                       tuple(summary.tool_errors), tuple(summary.skills))

    def _follow(self, proc: subprocess.Popen, label: str) -> _StreamSummary:
        """Read claude's stream-json, saving it and logging progress."""
        summary = _StreamSummary()
        with open(self.logs_dir / f"{label}.stream.jsonl", "w") as stream:
            for line in proc.stdout:
                stream.write(line)
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                self._log_event(event, summary)
        return summary

    def _log_event(self, event: dict, summary: _StreamSummary) -> None:
        if event.get("type") == "assistant":
            for item in event.get("message", {}).get("content", []):
                if item.get("type") == "tool_use":
                    if item.get("name") == "Skill":
                        summary.skills.append(str(item.get("input", {}).get("skill", "")))
                    what = item.get("input", {}).get("command") or json.dumps(item.get("input", {}))
                    self.log.info(f"    agent -> {item.get('name')}: {str(what)[:200]}")
                elif item.get("type") == "text":
                    self.log.info(f"    agent says: {' '.join(item['text'].split())[:240]}")
        elif event.get("type") == "user":
            content = event.get("message", {}).get("content", [])
            for item in content if isinstance(content, list) else []:
                if isinstance(item, dict) and item.get("type") == "tool_result" and item.get("is_error"):
                    text = tool_result_text(item)
                    summary.tool_errors.append(text)
                    self.log.info(f"    tool error: {text[:200]}")
        elif event.get("type") == "result":
            summary.final_text = event.get("result", "") or ""
            summary.cost = event.get("total_cost_usd")
            summary.is_error = event.get("is_error")
            summary.subtype = event.get("subtype")
