"""Records the outcome of each check as the run goes."""

from __future__ import annotations

from dataclasses import dataclass, field

from .log import Logger


@dataclass(frozen=True)
class Result:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class Report:
    log: Logger
    results: list[Result] = field(default_factory=list)

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        """Record one check and print it. Returns `ok` so callers can branch on it."""
        self.results.append(Result(name, bool(ok), detail))
        line = f"  {'✓' if ok else '✗'} {name}"
        if detail and not ok:
            line += f"\n      {detail}"
        self.log.info(line)
        return bool(ok)

    @property
    def failed(self) -> list[Result]:
        return [r for r in self.results if not r.ok]

    @property
    def passed_count(self) -> int:
        return len(self.results) - len(self.failed)
