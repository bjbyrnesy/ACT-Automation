#!/usr/bin/env python3
"""ACT Automation CLI entrypoint."""

from __future__ import annotations

import sys

from acta.cli import main

if __name__ == "__main__":
    sys.exit(main())
