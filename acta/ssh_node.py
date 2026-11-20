"""Interactive shell into a running containerlab node (host or switch)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass

_NODE_KIND_LABEL = "clab-node-kind"
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.@:-]*$")


@dataclass(frozen=True)
class ResolvedNode:
    container: str
    kind: str  # linux | arista_ceos | …
    runtime: str  # podman | docker


def _which_runtime(preferred: str | None) -> str:
    order = [preferred, "podman", "docker"] if preferred else ["podman", "docker"]
    seen: set[str] = set()
    for name in order:
        if not name or name in seen:
            continue
        seen.add(name)
        if shutil.which(name):
            return name
    raise FileNotFoundError(
        "neither podman nor docker found on PATH (need one to exec into lab nodes)"
    )


def list_running_containers(runtime: str) -> list[str]:
    result = subprocess.run(
        [runtime, "ps", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "unknown error").strip()
        raise RuntimeError(f"{runtime} ps failed: {err}")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def resolve_container_name(target: str, running: list[str]) -> str:
    """Match a full name or a unique suffix/substring among running containers."""
    if not _SAFE_NAME.fullmatch(target):
        raise ValueError(f"invalid node name: {target!r}")
    if target in running:
        return target
    # Exact suffix after last hyphen group, then unique substring.
    suffix_hits = [name for name in running if name.endswith(target)]
    if len(suffix_hits) == 1:
        return suffix_hits[0]
    hits = [name for name in running if target in name]
    if len(hits) == 1:
        return hits[0]
    if not hits and not suffix_hits:
        sample = ", ".join(sorted(running)[:8]) or "(none)"
        raise LookupError(
            f"no running container matching {target!r}; running: {sample}"
        )
    ambiguous = sorted(set(suffix_hits) | set(hits))
    raise LookupError(f"ambiguous node {target!r}; matches: {', '.join(ambiguous)}")


def detect_kind(runtime: str, container: str) -> str:
    result = subprocess.run(
        [
            runtime,
            "inspect",
            "--format",
            f'{{{{index .Config.Labels "{_NODE_KIND_LABEL}"}}}}|{{{{.Config.Image}}}}',
            container,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "unknown error").strip()
        raise RuntimeError(f"{runtime} inspect failed for {container}: {err}")
    raw = (result.stdout or "").strip()
    label, _, image = raw.partition("|")
    label = label.strip()
    image = image.strip().casefold()
    # Go templates print "<no value>" when a label key is missing.
    if label and label != "<no value>":
        return label
    if "ceos" in image or "eos" in image:
        return "arista_ceos"
    return "linux"


def resolve_node(
    target: str,
    *,
    runtime: str | None = None,
) -> ResolvedNode:
    chosen = _which_runtime(runtime)
    running = list_running_containers(chosen)
    container = resolve_container_name(target, running)
    kind = detect_kind(chosen, container)
    return ResolvedNode(container=container, kind=kind, runtime=chosen)


def build_exec_argv(
    node: ResolvedNode,
    *,
    command: list[str] | None = None,
    tty: bool | None = None,
) -> list[str]:
    """Build ``podman|docker exec …`` argv for an interactive or one-shot shell."""
    use_tty = sys.stdin.isatty() and sys.stdout.isatty() if tty is None else tty
    argv = [node.runtime, "exec"]
    if use_tty:
        argv.append("-it")
    else:
        argv.append("-i")
    argv.append(node.container)
    if command:
        joined = " ".join(command)
        if node.kind == "linux":
            argv.extend(["bash", "-lc", joined])
        else:
            argv.extend(["Cli", "-p", "15", "-c", joined])
        return argv
    if node.kind == "linux":
        argv.append("bash")
    else:
        argv.append("Cli")
    return argv


def run_ssh(
    target: str,
    *,
    runtime: str | None = None,
    command: list[str] | None = None,
    exec_fn=os.execvp,
) -> int:
    """Exec into the node (replaces the process on success)."""
    node = resolve_node(target, runtime=runtime)
    argv = build_exec_argv(node, command=command)
    try:
        exec_fn(argv[0], argv)
    except OSError as exc:
        raise RuntimeError(f"failed to exec {argv[0]}: {exc}") from exc
    return 0  # unreachable when exec succeeds
