#!/usr/bin/env python3
"""Temporary compatibility entry point for :mod:`acta.clab`."""

from acta.clab import *  # noqa: F403


if __name__ == "__main__":
    raise SystemExit(main())
