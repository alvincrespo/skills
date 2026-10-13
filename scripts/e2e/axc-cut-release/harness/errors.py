"""Exceptions raised by the harness."""

from __future__ import annotations


class HarnessError(Exception):
    """Infrastructure failed (a tool, git, gh, setup): the run can't continue.

    A failed *check* is not an error; it is recorded on the Report and the run goes on.
    """
