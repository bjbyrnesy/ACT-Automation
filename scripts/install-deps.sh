#!/usr/bin/env bash
# One-shot host + project dependency installer for ACT-Automation.
# Default: uv, Node 20+, Graphviz, Python via uv, `uv sync --extra dev`, SPA build.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

WITH_CLAB=0
WITH_GRAPHVIZ=1
WITH_HOOKS=0
BUILD_UI=1
SYNC_EXTRA="dev"

usage() {
  cat <<'EOF'
Usage: bash scripts/install-deps.sh [options]

Installs host tools (when missing) and the project venv so you can run acta
and the Web UI with minimal manual steps.

Options:
  --with-clab       Also install Podman; print containerlab install hint
  --no-graphviz     Skip Graphviz (dot) — not needed for the live Web UI diagram
  --ui-only         `uv sync --extra ui` instead of --extra dev
  --no-build-ui     Skip npm SPA build into acta/web/static
  --hooks           Run `pre-commit install --install-hooks` after sync
  -h, --help        Show this help

Examples:
  bash scripts/install-deps.sh
  bash scripts/install-deps.sh --with-clab --hooks
  bash scripts/serve-ui.sh          # after install-deps
EOF
}

have() {
  command -v "$1" >/dev/null 2>&1
}

log() {
  printf '==> %s\n' "$*"
}

warn() {
  printf 'Warning: %s\n' "$*" >&2
}

die() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

refresh_path() {
  # uv / brew shims often land here after a fresh install.
  export PATH="${HOME}/.local/bin:${HOME}/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:${PATH}"
}

ensure_uv() {
  refresh_path
  if have uv; then
    log "uv already installed ($(uv --version))"
    return 0
  fi
  log "Installing uv…"
  if [[ "$(uname -s)" == "Darwin" ]] && have brew; then
    brew install uv
  else
    curl -LsSf https://astral.sh/uv/install.sh | sh
  fi
  refresh_path
  have uv || die "uv installed but not on PATH — open a new shell or add ~/.local/bin"
}

ensure_python() {
  # Let uv manage a suitable interpreter (avoids hunting distro 3.15 packages).
  log "Ensuring Python 3.15+ via uv…"
  uv python install 3.15
}

pkg_install_macos() {
  have brew || die "Homebrew required on macOS (https://brew.sh) — install it, then re-run"
  local -a pkgs=()
  have npm || pkgs+=(node)
  if [[ "${WITH_GRAPHVIZ}" -eq 1 ]] && ! have dot; then
    pkgs+=(graphviz)
  fi
  if [[ "${WITH_CLAB}" -eq 1 ]] && ! have podman; then
    pkgs+=(podman)
  fi
  if ((${#pkgs[@]})); then
    log "brew install ${pkgs[*]}"
    brew install "${pkgs[@]}"
  else
    log "Homebrew packages already present (node/graphviz/podman as requested)"
  fi
}

pkg_install_fedora() {
  local -a pkgs=()
  have npm || pkgs+=(nodejs)
  if [[ "${WITH_GRAPHVIZ}" -eq 1 ]] && ! have dot; then
    pkgs+=(graphviz)
  fi
  if [[ "${WITH_CLAB}" -eq 1 ]] && ! have podman; then
    pkgs+=(podman)
  fi
  if ((${#pkgs[@]})); then
    log "sudo dnf install -y ${pkgs[*]}"
    sudo dnf install -y "${pkgs[@]}"
  fi
}

pkg_install_debian() {
  local -a pkgs=()
  have npm || pkgs+=(nodejs npm)
  if [[ "${WITH_GRAPHVIZ}" -eq 1 ]] && ! have dot; then
    pkgs+=(graphviz)
  fi
  if [[ "${WITH_CLAB}" -eq 1 ]] && ! have podman; then
    pkgs+=(podman)
  fi
  if ((${#pkgs[@]})); then
    log "sudo apt-get update && sudo apt-get install -y ${pkgs[*]}"
    sudo apt-get update
    sudo apt-get install -y "${pkgs[@]}"
  fi
  if have node; then
    local major
    major="$(node -v | sed -E 's/^v([0-9]+).*/\1/')"
    if [[ "${major}" -lt 20 ]]; then
      warn "Node $(node -v) is older than 20 — install Node 20+ (NodeSource/fnm/nvm); see README Install"
    fi
  fi
}

install_host_packages() {
  local os
  os="$(uname -s)"
  case "${os}" in
    Darwin)
      pkg_install_macos
      ;;
    Linux)
      if have dnf; then
        pkg_install_fedora
      elif have apt-get; then
        pkg_install_debian
      else
        die "Unsupported Linux (need dnf or apt-get). Install Node/uv/Graphviz manually — see README Install"
      fi
      ;;
    *)
      die "Unsupported OS (${os}). On Windows use WSL2 and re-run this script — see README Install"
      ;;
  esac
}

install_containerlab_hint() {
  [[ "${WITH_CLAB}" -eq 1 ]] || return 0
  if have containerlab || have clab; then
    log "containerlab already installed"
    return 0
  fi
  cat <<'EOF'

containerlab is not on PATH. On the lab host, install it with:

  bash -c "$(curl -sL https://get.containerlab.dev)"

macOS: start a Podman machine after brew install podman:
  podman machine init
  podman machine start

EOF
}

sync_project() {
  log "uv sync --extra ${SYNC_EXTRA}"
  uv sync --extra "${SYNC_EXTRA}"
}

build_spa() {
  [[ "${BUILD_UI}" -eq 1 ]] || return 0
  log "Building Web UI SPA…"
  bash "${ROOT}/scripts/build-ui.sh"
}

install_hooks() {
  [[ "${WITH_HOOKS}" -eq 1 ]] || return 0
  if [[ ! -x "${ROOT}/.venv/bin/pre-commit" ]]; then
    warn "pre-commit not in venv (use --extra dev); skipping hooks"
    return 0
  fi
  log "pre-commit install --install-hooks"
  "${ROOT}/.venv/bin/pre-commit" install --install-hooks
}

print_summary() {
  refresh_path
  cat <<EOF

Install complete.

  Python (uv):  $(uv run python --version 2>/dev/null || echo unknown)
  uv:           $(uv --version 2>/dev/null || echo missing)
  node:         $(node -v 2>/dev/null || echo missing)
  npm:          $(npm -v 2>/dev/null || echo missing)
  graphviz:     $(dot -V 2>&1 | head -1 || echo missing)
  podman:       $(podman --version 2>/dev/null || echo 'not installed')
  venv:         ${ROOT}/.venv

Next:
  source .venv/bin/activate
  acta --help
  bash scripts/serve-ui.sh          # Web UI on http://127.0.0.1:8765/

Details: README → Install
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-clab) WITH_CLAB=1 ;;
    --no-graphviz) WITH_GRAPHVIZ=0 ;;
    --ui-only) SYNC_EXTRA="ui" ;;
    --no-build-ui) BUILD_UI=0 ;;
    --hooks) WITH_HOOKS=1 ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      die "unknown option: $1"
      ;;
  esac
  shift
done

log "ACT-Automation dependency installer (repo: ${ROOT})"
ensure_uv
ensure_python
install_host_packages
refresh_path
install_containerlab_hint
sync_project
build_spa
install_hooks
print_summary
