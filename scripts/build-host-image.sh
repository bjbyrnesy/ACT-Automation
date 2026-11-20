#!/usr/bin/env bash
# Build the clab linux jumphost image (multitool + mcast-tools) for local Podman.
set -euo pipefail

readonly ROOT="$(cd "$(dirname "$0")/.." && pwd)"
readonly TAG="${ACTA_HOST_IMAGE:-localhost/acta-host-multitool:v0.10.0-mcast0.2.3}"
readonly CONTAINERFILE="${ROOT}/images/host-multitool/Containerfile"

command -v podman >/dev/null 2>&1 || {
  printf 'Error: podman required\n' >&2
  exit 1
}

printf 'Building %s\n' "${TAG}"
podman build \
  -t "${TAG}" \
  -f "${CONTAINERFILE}" \
  "${ROOT}/images/host-multitool"

printf 'Verifying mcast-tools CLIs\n'
podman run --rm --entrypoint sh "${TAG}" -c \
  'command -v mcast-send && command -v mcast-receive && command -v mcast-status'

printf 'OK: %s\n' "${TAG}"
