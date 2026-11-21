#!/usr/bin/env bash
# Build the React SPA and copy assets into acta/web/static for acta serve.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UI_DIR="${ROOT}/ui"
STATIC_DIR="${ROOT}/acta/web/static"

command -v npm >/dev/null 2>&1 || {
  printf 'Error: npm required\n' >&2
  exit 1
}

cd "${UI_DIR}"
npm ci
npm run build

mkdir -p "${STATIC_DIR}"
# Replace previous build artifacts; keep directory itself.
find "${STATIC_DIR}" -mindepth 1 -maxdepth 1 ! -name '.gitkeep' -exec rm -rf {} +
cp -R "${UI_DIR}/dist/." "${STATIC_DIR}/"

printf 'UI built → %s/index.html\n' "${STATIC_DIR}"
