"""Console + file logging. One Logger is passed around; there is no module-level state."""

from __future__ import annotations

from pathlib import Path
from typing import TextIO


class Logger:
    def __init__(self) -> None:
        self._file: TextIO | None = None

    def attach_file(self, path: Path) -> None:
        self._file = open(path, "w", encoding="utf-8")

    def close(self) -> None:
        if self._file:
            self._file.close()
            self._file = None

    def info(self, msg: str = "") -> None:
        print(msg, flush=True)
        if self._file:
            self._file.write(msg + "\n")
            self._file.flush()

    def step(self, msg: str) -> None:
        self.info(f"\n== {msg}")
