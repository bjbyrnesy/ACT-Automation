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
