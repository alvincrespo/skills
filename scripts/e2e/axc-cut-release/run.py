#!/usr/bin/env python3
"""Run the axc-cut-release end-to-end test. See README.md next to this file.

    python3 scripts/e2e/axc-cut-release/run.py --dry-run
    python3 scripts/e2e/axc-cut-release/run.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
