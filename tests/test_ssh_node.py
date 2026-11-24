"""Tests for acta.py ssh (podman/docker exec into lab nodes)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from acta.ssh_node import (
    ResolvedNode,
    build_exec_argv,
    detect_kind,
    resolve_container_name,
    resolve_node,
    run_ssh,
)

ROOT = Path(__file__).resolve().parents[1]


def test_resolve_container_name_exact_and_unique_fragment():
    running = ["blz2-A-leaf1", "blz2-A-leaf2", "blz2-host1", "blz2-host2"]
    assert resolve_container_name("blz2-host1", running) == "blz2-host1"
    assert resolve_container_name("host1", running) == "blz2-host1"
    assert resolve_container_name("A-leaf2", running) == "blz2-A-leaf2"


def test_resolve_container_name_ambiguous():
    running = ["blz2-host1", "demo-host1"]
    with pytest.raises(LookupError, match="ambiguous"):
        resolve_container_name("host1", running)


def test_build_exec_argv_linux_and_ceos():
    host = ResolvedNode(container="blz2-host1", kind="linux", runtime="podman")
    switch = ResolvedNode(
        container="blz2-A-leaf1", kind="arista_ceos", runtime="podman"
    )
    assert build_exec_argv(host, tty=True) == [
        "podman",
        "exec",
        "-it",
        "blz2-host1",
        "bash",
    ]
    assert build_exec_argv(switch, tty=False) == [
        "podman",
        "exec",
        "-i",
        "blz2-A-leaf1",
        "Cli",
    ]
    assert build_exec_argv(switch, command=["show", "hostname"], tty=False) == [
        "podman",
        "exec",
        "-i",
        "blz2-A-leaf1",
        "Cli",
        "-p",
        "15",
        "-c",
        "show hostname",
    ]


def test_run_ssh_execs_resolved_argv(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "acta.ssh_node.resolve_node",
        lambda target, runtime=None: ResolvedNode(
            container="blz2-host1", kind="linux", runtime="podman"
        ),
    )
    monkeypatch.setattr("acta.ssh_node.sys.stdin.isatty", lambda: False)
    monkeypatch.setattr("acta.ssh_node.sys.stdout.isatty", lambda: False)
    seen: list[list[str]] = []

    def fake_exec(file: str, args: list[str]) -> None:
        seen.append(list(args))

    run_ssh("host1", exec_fn=fake_exec)
    assert seen == [["podman", "exec", "-i", "blz2-host1", "bash"]]


def test_cli_ssh_help():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "acta.py"), "ssh", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "podman" in proc.stdout
    assert "node" in proc.stdout


def test_resolve_node_uses_runtime_ps(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "acta.ssh_node.list_running_containers",
        lambda runtime: ["blz2-A-leaf1", "blz2-host1"],
    )
    monkeypatch.setattr("acta.ssh_node.detect_kind", lambda runtime, container: "linux")
    node = resolve_node("host1", runtime="podman")
    assert node.container == "blz2-host1"
    assert node.kind == "linux"
    assert node.runtime == "podman"


def test_resolve_node_falls_through_empty_podman_to_docker(
    monkeypatch: pytest.MonkeyPatch,
):
    """Docker-only labs: podman is on PATH but has no containers."""

    def fake_which(name: str) -> str | None:
        return f"/usr/bin/{name}" if name in {"podman", "docker"} else None

    def fake_ps(runtime: str) -> list[str]:
        if runtime == "podman":
            return []
        return ["campus-spine1", "campus-leaf1"]

    monkeypatch.setattr("acta.ssh_node.shutil.which", fake_which)
    monkeypatch.setattr("acta.ssh_node.list_running_containers", fake_ps)
    monkeypatch.setattr(
        "acta.ssh_node.detect_kind", lambda runtime, container: "arista_ceos"
    )
    node = resolve_node("campus-spine1")
    assert node.runtime == "docker"
    assert node.container == "campus-spine1"


def test_detect_kind_ignores_go_template_no_value(monkeypatch: pytest.MonkeyPatch):
    def fake_run(argv, **kwargs):
        class Result:
            returncode = 0
            stdout = "<no value>|ghcr.io/srl-labs/network-multitool:v0.10.0\n"
            stderr = ""

        return Result()

    monkeypatch.setattr("acta.ssh_node.subprocess.run", fake_run)
    assert detect_kind("podman", "blz2-host1") == "linux"


def test_detect_kind_inspect_failure_raises(monkeypatch: pytest.MonkeyPatch):
    def fake_run(argv, **kwargs):
        class Result:
            returncode = 1
            stdout = ""
            stderr = "no such container"

        return Result()

    monkeypatch.setattr("acta.ssh_node.subprocess.run", fake_run)
    with pytest.raises(RuntimeError, match="inspect failed"):
        detect_kind("podman", "missing")


def test_cli_ssh_runtime_after_node_is_not_eaten():
    from acta.cli import build_parser

    args = build_parser().parse_args(["ssh", "host1", "--runtime", "docker"])
    assert args.node == "host1"
    assert args.runtime == "docker"
    assert args.remote_command == []
