#!/usr/bin/env bash
# Build the React SPA and copy assets into acta/web/static for acta serve.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UI_DIR="${ROOT}/ui"
STATIC_DIR="${ROOT}/acta/web/static"

ensure_npm() {
  if command -v npm >/dev/null 2>&1; then
    return 0
  fi
  # macOS: install Node via Homebrew when available.
  if [[ "$(uname -s)" == "Darwin" ]] && command -v brew >/dev/null 2>&1; then
    printf 'npm not found; installing Node.js with Homebrew (brew install node)…\n' >&2
    brew install node
    if command -v npm >/dev/null 2>&1; then
      return 0
    fi
    printf 'Error: brew install node finished but npm is still not on PATH\n' >&2
    exit 1
  fi
  printf 'Error: npm required to build the Web UI (Node.js 20+)\n' >&2
  printf '\nInstall Node, then re-run this script:\n' >&2
  printf '  macOS:   brew install node\n' >&2
  printf '  Fedora:  sudo dnf install nodejs\n' >&2
  printf '  Debian:  sudo apt-get install -y nodejs npm   # if package is Node 20+\n' >&2
  printf '  Or use fnm/nvm — see README → Install → Node.js 20+\n' >&2
  exit 1
}

ensure_npm

cd "${UI_DIR}"
npm ci
npm run build

mkdir -p "${STATIC_DIR}"
# Clear previous build (do not use `find` — interactive shells often alias it to fd).
python3 - <<'PY' "${STATIC_DIR}"
import pathlib, shutil, sys
static = pathlib.Path(sys.argv[1])
for child in static.iterdir():
    if child.name == ".gitkeep":
        continue
    if child.is_dir() and not child.is_symlink():
        shutil.rmtree(child)
    else:
        child.unlink(missing_ok=True)
PY
cp -R "${UI_DIR}/dist/." "${STATIC_DIR}/"

printf 'UI built → %s/index.html\n' "${STATIC_DIR}"
