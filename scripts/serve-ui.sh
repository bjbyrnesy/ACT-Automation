#!/usr/bin/env bash
# Sync UI deps, build the SPA, and run the local Web UI (one command, no PATH tricks).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

command -v uv >/dev/null 2>&1 || {
  printf 'Error: uv required\n' >&2
  printf 'Install everything with: bash scripts/install-deps.sh\n' >&2
  exit 1
}

uv sync --extra ui
bash "${ROOT}/scripts/build-ui.sh"
exec "${ROOT}/.venv/bin/acta" serve "$@"
