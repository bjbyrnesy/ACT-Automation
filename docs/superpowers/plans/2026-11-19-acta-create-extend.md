# ACTA Create + Extend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `acta.py` with `create` and `extend` so fabrics reserve spare width and grow on unused ports without changing existing link endpoints.

**Architecture:** Python package `acta/` behind `acta.py`. Shared `Capacity` + `PortPlan` drive create emit and extend append. Topology is parse/emit of ACT YAML with a `# capacity:` header. Soft max uses reserved blocks; past soft max uses next free Ethernet ≤16; L2 spines hard-capped at 2.

**Tech Stack:** Python ≥3.15, uv, PyYAML, pytest, black, ruff.

**Spec:** `docs/superpowers/specs/2026-11-19-acta-python-cli-design.md`

**Follow-on plans (same branch, after this plan):**
- `docs/superpowers/plans/2026-11-19-acta-upload-onboard.md` — `upload` + ACT `onboard`
- `docs/superpowers/plans/2026-11-19-acta-clab-cutover.md` — `clab` move, README, delete `.sh` / `clab.py`

## Global Constraints

- Python `requires-python >=3.15`; manage env with `uv` only (`uv sync`, `uv run …`).
- Format with black; lint with ruff; type hints on new code.
- Existing link endpoints never change on extend.
- Soft `max_*` for planned layout; hard cap **16** Ethernet ports per switch.
- L2 fabrics: spines hard-capped at **2**.
- L3LS planned spines default/ceiling prompt **4** (soft overrun still allowed until port hard cap).
- Capacity persisted in YAML `# capacity:` comments; extend fails without a parseable header.
- No shell shims; do not delete `.sh` until the cutover plan completes.
- Secrets stay in `.config` / `.env`, never in code.
- Work on branch `feature/topology-spare-width-extend`; ACT/clab host remains **trogdor** (no clab02).

## File map (this plan)

| File | Responsibility |
|------|----------------|
| `pyproject.toml` / `uv.lock` | Project metadata, deps, tool config |
| `acta.py` | CLI entry |
| `acta/__init__.py` | Package version marker |
| `acta/cli.py` | Argparse: create, extend (+ stubs OK for upload/onboard/clab) |
| `acta/config.py` | Load/save `.config` |
| `acta/prompt.py` | Interactive prompts |
| `acta/capacity.py` | Parse/emit capacity header; soft/hard limits |
| `acta/portplan.py` | Reserved offsets + next-free ≤16 |
| `acta/topology.py` | ACT YAML model: nodes, links, used ports, write |
| `acta/create.py` | Interactive create + emit |
| `acta/extend.py` | Append spine/leaf/pair/mleaf |
| `acta/diagram.py` | Optional graphviz PNG (minimal in this plan) |
| `tests/test_capacity.py` | Header + limits |
| `tests/test_portplan.py` | Offsets + next-free |
| `tests/test_topology.py` | Parse/used ports |
| `tests/test_create.py` | Emit + header |
| `tests/test_extend.py` | Append + endpoint freeze |
| `tests/test_cli_help.py` | `--help` shape |

---

### Task 1: uv project + CLI stub + help

**Files:**
- Create: `pyproject.toml`
- Create: `acta.py`
- Create: `acta/__init__.py`
- Create: `acta/cli.py`
- Create: `tests/test_cli_help.py`
- Modify: `.gitignore` (add `.venv/` if missing)

**Interfaces:**
- Consumes: nothing
- Produces: `acta.cli.main(argv: list[str] | None = None) -> int`; entry `acta.py` calls `sys.exit(main())`

- [ ] **Step 1: Write the failing help test**

```python
# tests/test_cli_help.py
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_acta_help_lists_core_commands():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "acta.py"), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    out = proc.stdout
    for name in ("create", "extend", "upload", "onboard", "clab"):
        assert name in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli_help.py::test_acta_help_lists_core_commands -v`  
(If uv/project missing, `uv run` fails — that counts as fail.)  
Expected: FAIL (no `acta.py` / no project)

- [ ] **Step 3: Add `pyproject.toml`**

```toml
[project]
name = "acta"
version = "0.1.0"
description = "ACT Automation CLI"
readme = "README.md"
requires-python = ">=3.15"
dependencies = [
  "pyyaml>=6.0",
  "httpx>=0.28",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.0",
  "ruff>=0.9",
  "black>=25.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.ruff]
line-length = 88
target-version = "py315"

[tool.black]
line-length = 88
target-version = ["py315"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["acta"]
```

- [ ] **Step 4: Sync env**

Run: `uv sync --extra dev`  
Expected: `uv.lock` created; `.venv` ready

- [ ] **Step 5: Implement stub CLI**

```python
# acta/__init__.py
__version__ = "0.1.0"
```

```python
# acta/cli.py
from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="acta.py",
        description=(
            "ACT Automation — create, extend, upload, and onboard fabric labs "
            "(ACT + containerlab). Capacity reserved at create time; extend only "
            "uses unused ports (existing endpoints stay fixed)."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser(
        "create",
        help=(
            "Interactive ACT topology create (pinned serials/MACs, "
            "spare spine/leaf/mleaf capacity)"
        ),
    )
    sub.add_parser("extend", help="Grow an existing topology on unused ports")
    sub.add_parser(
        "upload",
        help="Upload topology YAML to ACT; optional lab create/deploy",
    )
    sub.add_parser(
        "onboard",
        help="Onboard a Running ACT lab to CVaaS (TerminAttr over SSH)",
    )
    clab = sub.add_parser(
        "clab",
        help="Containerlab: generate, deploy, onboard cEOS labs",
    )
    clab_sub = clab.add_subparsers(dest="clab_command", required=True)
    clab_sub.add_parser("generate", help="Convert ACT topology YAML to containerlab")
    clab_sub.add_parser("deploy", help="Deploy a .clab.yml locally or via --host")
    clab_sub.add_parser("onboard", help="Onboard cEOS containers to CVaaS")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    print(f"ERROR: command {args.command!r} not implemented yet", flush=True)
    return 2
```

```python
#!/usr/bin/env python3
"""ACT Automation CLI entrypoint."""
from __future__ import annotations

import sys

from acta.cli import main

if __name__ == "__main__":
    sys.exit(main())
```

Ensure `.gitignore` contains `.venv/` and `uv.lock` is committed.

- [ ] **Step 6: Run help test**

Run: `uv run pytest tests/test_cli_help.py::test_acta_help_lists_core_commands -v`  
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock acta.py acta/__init__.py acta/cli.py tests/test_cli_help.py .gitignore
git commit -m "feat(acta): add uv project and CLI stub"
```

---

### Task 2: Capacity header parse/emit + limits

**Files:**
- Create: `acta/capacity.py`
- Create: `tests/test_capacity.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `HARD_PORT_MAX: int = 16`
  - `@dataclass Capacity` with `fabric_mode: str | None`, `max_spines: int`, `max_leaves: int`, `max_mleafs_per_pair: int`, `spines: int`, `leaves: int`
  - `parse_capacity_header(text: str) -> Capacity`
  - `format_capacity_header(cap: Capacity) -> str`
  - `validate_create_capacity(cap: Capacity) -> None` raises `ValueError`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_capacity.py
import pytest

from acta.capacity import (
    HARD_PORT_MAX,
    Capacity,
    format_capacity_header,
    parse_capacity_header,
    validate_create_capacity,
)


def test_hard_port_max_is_16():
    assert HARD_PORT_MAX == 16


def test_round_trip_header():
    cap = Capacity(
        fabric_mode="l3ls",
        max_spines=4,
        max_leaves=8,
        max_mleafs_per_pair=2,
        spines=2,
        leaves=4,
    )
    text = format_capacity_header(cap)
    assert "max_spines=4" in text
    got = parse_capacity_header(text)
    assert got == cap


def test_parse_missing_header_raises():
    with pytest.raises(ValueError, match="capacity"):
        parse_capacity_header("nodes:\n")


def test_validate_rejects_max_leaves_below_current():
    cap = Capacity(
        fabric_mode=None,
        max_spines=2,
        max_leaves=2,
        max_mleafs_per_pair=0,
        spines=2,
        leaves=4,
    )
    with pytest.raises(ValueError, match="max_leaves"):
        validate_create_capacity(cap)


def test_validate_l2_rejects_spines_above_2():
    cap = Capacity(
        fabric_mode="l2",
        max_spines=3,
        max_leaves=4,
        max_mleafs_per_pair=0,
        spines=2,
        leaves=4,
    )
    with pytest.raises(ValueError, match="L2"):
        validate_create_capacity(cap)
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `uv run pytest tests/test_capacity.py -v`  
Expected: FAIL import error

- [ ] **Step 3: Implement `acta/capacity.py`**

```python
from __future__ import annotations

import re
from dataclasses import dataclass

HARD_PORT_MAX = 16

_HEADER_RE = re.compile(
    r"^#\s*capacity:\s*(?P<body>.+)$",
    re.MULTILINE,
)


@dataclass(frozen=True)
class Capacity:
    fabric_mode: str | None
    max_spines: int
    max_leaves: int
    max_mleafs_per_pair: int
    spines: int
    leaves: int


def _parse_body(body: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in body.split():
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        out[key] = value
    return out


def parse_capacity_header(text: str) -> Capacity:
    matches = list(_HEADER_RE.finditer(text))
    if not matches:
        raise ValueError("missing # capacity: header")
    merged: dict[str, str] = {}
    for match in matches:
        merged.update(_parse_body(match.group("body")))
    required = (
        "max_spines",
        "max_leaves",
        "max_mleafs_per_pair",
        "spines",
        "leaves",
    )
    missing = [k for k in required if k not in merged]
    if missing:
        raise ValueError(f"capacity header missing keys: {', '.join(missing)}")
    mode = merged.get("fabric_mode")
    if mode in ("", "none"):
        mode = None
    return Capacity(
        fabric_mode=mode,
        max_spines=int(merged["max_spines"]),
        max_leaves=int(merged["max_leaves"]),
        max_mleafs_per_pair=int(merged["max_mleafs_per_pair"]),
        spines=int(merged["spines"]),
        leaves=int(merged["leaves"]),
    )


def format_capacity_header(cap: Capacity) -> str:
    mode = cap.fabric_mode or "none"
    line1 = (
        f"# capacity: fabric_mode={mode} max_spines={cap.max_spines} "
        f"max_leaves={cap.max_leaves} max_mleafs_per_pair={cap.max_mleafs_per_pair}"
    )
    line2 = f"# capacity: spines={cap.spines} leaves={cap.leaves}"
    return f"{line1}\n{line2}\n"


def validate_create_capacity(cap: Capacity) -> None:
    if cap.max_leaves < cap.leaves:
        raise ValueError("max_leaves must be >= current leaves")
    if cap.max_spines < cap.spines:
        raise ValueError("max_spines must be >= current spines")
    if cap.fabric_mode == "l2" and cap.max_spines > 2:
        raise ValueError("L2 fabric max_spines hard-capped at 2")
    if cap.fabric_mode == "l2" and cap.spines > 2:
        raise ValueError("L2 fabric spines hard-capped at 2")
    if cap.max_spines > HARD_PORT_MAX or cap.max_leaves > HARD_PORT_MAX:
        raise ValueError(f"planned width cannot exceed {HARD_PORT_MAX} ports")
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `uv run pytest tests/test_capacity.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add acta/capacity.py tests/test_capacity.py
git commit -m "feat(acta): add capacity header parse and limits"
```

---

### Task 3: PortPlan reserved offsets + next-free

**Files:**
- Create: `acta/portplan.py`
- Create: `tests/test_portplan.py`

**Interfaces:**
- Consumes: `Capacity`, `HARD_PORT_MAX` from `acta.capacity`
- Produces:
  - `@dataclass PortPlan` with helpers:
    - `spine_to_leaf_port(leaf_index: int) -> int`  # on spine
    - `leaf_to_spine_port(spine_index: int) -> int`  # on leaf
    - `leaf_mlag_ports() -> tuple[int, int]`
    - `leaf_mleaf_port(mleaf_slot: int) -> int`  # 1-based slot
    - `spine_mlag_ports() -> tuple[int, int]`
    - `next_free_port(used: set[int], prefer: int | None = None) -> int`  
      Prefer `prefer` if free and ≤16; else smallest free in 1..16; else raise

**Port rules (locked):**
- Spine Eth `L` ↔ leaf `L` for leaf index L (reserved through `max_leaves`).
- Leaf Eth `S` ↔ spine `S` for spine index S (reserved through `max_spines`).
- Leaf MLAG peer ports: `max_spines+1`, `max_spines+2`.
- Member-leaf uplink on leaf: `max_spines+2+m` for slot `m` (1..max_mleafs_per_pair).
- Spine MLAG peer ports: `max_leaves+1`, `max_leaves+2`.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_portplan.py
import pytest

from acta.capacity import Capacity
from acta.portplan import PortPlan


def _cap(**kwargs) -> Capacity:
    base = dict(
        fabric_mode="l3ls",
        max_spines=4,
        max_leaves=8,
        max_mleafs_per_pair=2,
        spines=2,
        leaves=4,
    )
    base.update(kwargs)
    return Capacity(**base)


def test_mesh_ports_use_indices():
    plan = PortPlan(_cap())
    assert plan.spine_to_leaf_port(3) == 3
    assert plan.leaf_to_spine_port(2) == 2


def test_service_ports_sit_after_reserved_blocks():
    plan = PortPlan(_cap(max_spines=4, max_leaves=8))
    assert plan.leaf_mlag_ports() == (5, 6)
    assert plan.leaf_mleaf_port(1) == 7
    assert plan.leaf_mleaf_port(2) == 8
    assert plan.spine_mlag_ports() == (9, 10)


def test_next_free_prefers_planned_then_scans():
    plan = PortPlan(_cap())
    assert plan.next_free_port({1, 2, 3}, prefer=4) == 4
    assert plan.next_free_port({1, 2, 3, 4}, prefer=4) == 5


def test_next_free_raises_at_hard_cap():
    plan = PortPlan(_cap())
    used = set(range(1, 17))
    with pytest.raises(ValueError, match="16"):
        plan.next_free_port(used)
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `uv run pytest tests/test_portplan.py -v`  
Expected: FAIL import error

- [ ] **Step 3: Implement `acta/portplan.py`**

```python
from __future__ import annotations

from dataclasses import dataclass

from acta.capacity import HARD_PORT_MAX, Capacity


@dataclass(frozen=True)
class PortPlan:
    capacity: Capacity

    def spine_to_leaf_port(self, leaf_index: int) -> int:
        return leaf_index

    def leaf_to_spine_port(self, spine_index: int) -> int:
        return spine_index

    def leaf_mlag_ports(self) -> tuple[int, int]:
        base = self.capacity.max_spines
        return (base + 1, base + 2)

    def leaf_mleaf_port(self, mleaf_slot: int) -> int:
        if mleaf_slot < 1:
            raise ValueError("mleaf_slot must be >= 1")
        return self.capacity.max_spines + 2 + mleaf_slot

    def spine_mlag_ports(self) -> tuple[int, int]:
        base = self.capacity.max_leaves
        return (base + 1, base + 2)

    def next_free_port(self, used: set[int], prefer: int | None = None) -> int:
        if prefer is not None and 1 <= prefer <= HARD_PORT_MAX and prefer not in used:
            return prefer
        for port in range(1, HARD_PORT_MAX + 1):
            if port not in used:
                return port
        raise ValueError(f"no free Ethernet ports left (hard max {HARD_PORT_MAX})")
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `uv run pytest tests/test_portplan.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add acta/portplan.py tests/test_portplan.py
git commit -m "feat(acta): add PortPlan reserved offsets and next-free"
```

---

### Task 4: Topology model — parse links, used ports, write

**Files:**
- Create: `acta/topology.py`
- Create: `tests/test_topology.py`

**Interfaces:**
- Consumes: `parse_capacity_header`, `format_capacity_header`, `Capacity`
- Produces:
  - `@dataclass Connection` with `a_node: str`, `a_port: int`, `b_node: str`, `b_port: int`
  - `@dataclass TopologyDoc` with `raw_prefix: str`, `capacity: Capacity`, `nodes: dict`, `connections: list[Connection]`, `raw_suffix` handling as needed
  - `load_topology(path: Path) -> TopologyDoc`
  - `used_ports(doc: TopologyDoc, node: str) -> set[int]`
  - `connection_endpoints(doc: TopologyDoc) -> set[tuple[str, int]]`
  - `write_topology(path: Path, doc: TopologyDoc) -> None`  
    Preserve non-capacity body structure enough for tests; emit capacity header at top after optional title comments.

ACT link line shape today:
`  - connection: [name:EthernetN, name:EthernetM]`

Keep parse robust with a regex on those lines. Node blocks remain YAML-loadable: for v1, store full file text, splice capacity header, and append new node/link text blocks on extend (surgical string/YAML hybrid is OK if tests lock behavior).

**Recommended approach for reliability:** parse whole file with PyYAML after stripping `connection` custom form into a normalized structure **or** regex-extract connections + capacity and keep node YAML section. Prefer:

1. Read text.
2. Parse capacity.
3. Regex-find all `connection:` endpoints into `Connection` list.
4. On write for extend tests: rewrite file from a structured emit for nodes+links once create exists; for this task, implement `parse_connections(text) -> list[Connection]` and `used_ports` first.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_topology.py
from pathlib import Path

from acta.topology import parse_connections, used_ports_from_connections

SAMPLE = """
# capacity: fabric_mode=none max_spines=4 max_leaves=8 max_mleafs_per_pair=0
# capacity: spines=2 leaves=2
links:
  - connection: [demo-spine1:Ethernet1, demo-leaf1:Ethernet1]
  - connection: [demo-spine1:Ethernet2, demo-leaf2:Ethernet1]
  - connection: [demo-spine2:Ethernet1, demo-leaf1:Ethernet2]
"""


def test_parse_connections():
    conns = parse_connections(SAMPLE)
    assert len(conns) == 3
    assert (conns[0].a_node, conns[0].a_port) == ("demo-spine1", 1)


def test_used_ports():
    conns = parse_connections(SAMPLE)
    assert used_ports_from_connections(conns, "demo-spine1") == {1, 2}
    assert used_ports_from_connections(conns, "demo-leaf1") == {1, 2}
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `uv run pytest tests/test_topology.py -v`  
Expected: FAIL

- [ ] **Step 3: Implement parse helpers in `acta/topology.py`**

```python
from __future__ import annotations

import re
from dataclasses import dataclass

_CONN_RE = re.compile(
    r"connection:\s*\[(?P<a_node>[^:]+):Ethernet(?P<a_port>\d+),\s*"
    r"(?P<b_node>[^:]+):Ethernet(?P<b_port>\d+)\]"
)


@dataclass(frozen=True)
class Connection:
    a_node: str
    a_port: int
    b_node: str
    b_port: int


def parse_connections(text: str) -> list[Connection]:
    out: list[Connection] = []
    for match in _CONN_RE.finditer(text):
        out.append(
            Connection(
                a_node=match.group("a_node").strip(),
                a_port=int(match.group("a_port")),
                b_node=match.group("b_node").strip(),
                b_port=int(match.group("b_port")),
            )
        )
    return out


def used_ports_from_connections(conns: list[Connection], node: str) -> set[int]:
    used: set[int] = set()
    for conn in conns:
        if conn.a_node == node:
            used.add(conn.a_port)
        if conn.b_node == node:
            used.add(conn.b_port)
    return used
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `uv run pytest tests/test_topology.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add acta/topology.py tests/test_topology.py
git commit -m "feat(acta): parse ACT connection endpoints and used ports"
```

---

### Task 5: Create — single-DC emit with capacity header

**Files:**
- Create: `acta/create.py`
- Create: `acta/mac.py` (deterministic MAC helper)
- Modify: `acta/topology.py` (emit helpers)
- Modify: `acta/cli.py` (wire `create` non-interactive test path)
- Create: `tests/test_create.py`

**Interfaces:**
- Consumes: `Capacity`, `PortPlan`, `format_capacity_header`
- Produces:
  - `@dataclass FabricSpec` — hostname_prefix, serial_prefix, eos_version, capacity, mlag_pairs: bool, spine_mlag: bool, member_leaf_pairs: list[int], member_leaves_per_pair: int, dc_count: int = 1
  - `generate_mac(serial_prefix: str, hostname: str) -> str` (Arista OUI `00:1c:73` + sha256 like `generate.sh`)
  - `emit_act_yaml(spec: FabricSpec) -> str`
  - CLI: `acta.py create --spec-json PATH` for tests (hidden/internal OK) **or** `create_from_spec(spec) -> str` called directly in unit tests without full prompts

**Emit rules (single-DC, MLAG on):**
- Nodes: `spine1..spines`, `leaf1..leaves`, optional mleafs.
- Mesh links for every current spine×leaf using PortPlan mesh ports.
- Leaf MLAG on odd/even pairs using `leaf_mlag_ports()`.
- mleaf dual-home using `leaf_mleaf_port(slot)`.
- Do **not** create links on unused reserved ports.

Port from `generate.sh` for MAC:

```bash
hash=$(printf '%s' "${SERIAL_PREFIX}-$1" | shasum -a 256 | cut -c1-6)
printf '00:1c:73:%s:%s:%s' ...
```

Python equivalent with `hashlib.sha256`.

- [ ] **Step 1: Write failing create test**

```python
# tests/test_create.py
from acta.capacity import Capacity
from acta.create import FabricSpec, emit_act_yaml
from acta.topology import parse_connections


def test_emit_includes_capacity_and_mesh_without_spare_links():
    spec = FabricSpec(
        hostname_prefix="demo",
        serial_prefix="demo",
        eos_version="4.35.4M",
        capacity=Capacity(
            fabric_mode=None,
            max_spines=4,
            max_leaves=8,
            max_mleafs_per_pair=2,
            spines=2,
            leaves=2,
        ),
        mlag_pairs=True,
        spine_mlag=False,
        member_leaf_pairs=[],
        member_leaves_per_pair=0,
    )
    text = emit_act_yaml(spec)
    assert "max_spines=4" in text
    assert "demo-spine1:" in text
    conns = parse_connections(text)
    # 2 spines * 2 leaves = 4 mesh + 2 MLAG peer links = 6
    assert len(conns) == 6
    # reserved leaf3 on spine must not appear
    assert not any(c.a_port == 3 or c.b_port == 3 for c in conns if "spine" in c.a_node)
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `uv run pytest tests/test_create.py::test_emit_includes_capacity_and_mesh_without_spare_links -v`  
Expected: FAIL

- [ ] **Step 3: Implement `mac.py` + `emit_act_yaml`**

Implement `FabricSpec` and `emit_act_yaml` mirroring single-DC node/IP/link patterns from `generate.sh` (IPs: spines `.11+`, leaves `.21+`, mleafs `.131+`; `veos.version`; `ztp: false`; serial/MAC fields). Put capacity header immediately under the file title comment block.

Keep multi-DC out of this task (Task 8).

- [ ] **Step 4: Run test — expect PASS**

Run: `uv run pytest tests/test_create.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add acta/mac.py acta/create.py acta/topology.py tests/test_create.py
git commit -m "feat(acta): emit single-DC ACT YAML with spare capacity"
```

---

### Task 6: Create — interactive prompts + capacity banner + CLI wire-up

**Files:**
- Create: `acta/prompt.py`
- Create: `acta/config.py`
- Modify: `acta/create.py` (interactive `run_create`)
- Modify: `acta/cli.py`

**Interfaces:**
- `load_config(path: Path) -> dict[str, str]`
- `save_config(path: Path, data: dict[str, str]) -> None` (mode 0o600)
- `prompt_value(label: str, default: str | None = None, secret: bool = False) -> str`
- `run_create(project_dir: Path) -> Path` returns written topology path

**Prompt additions after size (exact intent):**
- Explain briefly, then ask `max_spines` / `max_leaves` / `max_mleafs_per_pair`.
- Banner must mention `acta.py extend` examples (`--add leaf`, `--add spine`, `--add mleaf --pair N`).
- L2: force `max_spines=2` when fabric_mode is l2 (multi-DC path in Task 8); single-DC treat as no fabric_mode / non-l2 unless later specified.

Also persist new keys in `.config`: `MAX_SPINES`, `MAX_LEAVES`, `MAX_MLEAFS_PER_PAIR`.

- [ ] **Step 1: Write failing unit test for banner text helper**

```python
# tests/test_create.py (add)
from acta.create import capacity_banner


def test_capacity_banner_mentions_extend_commands():
    text = capacity_banner()
    assert "acta.py extend" in text
    assert "--add leaf" in text
    assert "--add mleaf" in text
```

- [ ] **Step 2: Run — expect FAIL**

Run: `uv run pytest tests/test_create.py::test_capacity_banner_mentions_extend_commands -v`  
Expected: FAIL

- [ ] **Step 3: Implement banner + config/prompt + wire `create`**

`capacity_banner()` returns a short multi-line string. `run_create` can remain partially stubbed for non-TTY tests; CLI `create` calls `run_create`. For interactive fields, port logic from `generate.sh` prompts; defaults: spines 2, leaves 4, max_spines 4, max_leaves max(leaves, 8) or user entry, max_mleafs_per_pair max(current, 2).

- [ ] **Step 4: Manual smoke (optional in agent run)**

Run: `uv run python acta.py create -h`  
Expected: help for create (add create parser args if any)

- [ ] **Step 5: Commit**

```bash
git add acta/prompt.py acta/config.py acta/create.py acta/cli.py tests/test_create.py
git commit -m "feat(acta): interactive create prompts and capacity banner"
```

---

### Task 7: Extend — add leaf (endpoint freeze)

**Files:**
- Create: `acta/extend.py`
- Modify: `acta/cli.py`
- Create: `tests/test_extend.py`

**Interfaces:**
- `extend_topology(path: Path, add: str, *, site: str | None = None, pair: int | None = None, count: int = 1, out: Path | None = None, new: bool = False) -> Path`
- Leaf add: next leaf index; for each current spine `s`, link `spine{s}:Ethernet{leaf}` ↔ `leaf{leaf}:Ethernet{s}` using planned ports if free; else `next_free_port` with warning callback/list.

- [ ] **Step 1: Write failing extend tests**

```python
# tests/test_extend.py
from pathlib import Path

from acta.capacity import Capacity
from acta.create import FabricSpec, emit_act_yaml
from acta.extend import extend_topology
from acta.topology import parse_connections


def _write_base(tmp_path: Path) -> Path:
    spec = FabricSpec(
        hostname_prefix="demo",
        serial_prefix="demo",
        eos_version="4.35.4M",
        capacity=Capacity(
            fabric_mode=None,
            max_spines=4,
            max_leaves=8,
            max_mleafs_per_pair=2,
            spines=2,
            leaves=2,
        ),
        mlag_pairs=True,
        spine_mlag=False,
        member_leaf_pairs=[],
        member_leaves_per_pair=0,
    )
    path = tmp_path / "topology-demo.yml"
    path.write_text(emit_act_yaml(spec))
    return path


def test_add_leaf_preserves_existing_endpoints(tmp_path: Path):
    path = _write_base(tmp_path)
    before = {
        (c.a_node, c.a_port, c.b_node, c.b_port)
        for c in parse_connections(path.read_text())
    }
    extend_topology(path, add="leaf")
    after_conns = parse_connections(path.read_text())
    after = {(c.a_node, c.a_port, c.b_node, c.b_port) for c in after_conns}
    assert before <= after
    assert any("leaf3" in f"{a}{b}" for a, _, b, _ in after - before)
```

- [ ] **Step 2: Run — expect FAIL**

Run: `uv run pytest tests/test_extend.py::test_add_leaf_preserves_existing_endpoints -v`  
Expected: FAIL

- [ ] **Step 3: Implement leaf extend**

Load text; parse capacity + connections; compute next leaf index from node names / capacity.leaves; append node YAML + mesh links; bump `leaves` in header via `format_capacity_header`; write atomically (`tmp` replace).

- [ ] **Step 4: Run — expect PASS**

Run: `uv run pytest tests/test_extend.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add acta/extend.py acta/cli.py tests/test_extend.py
git commit -m "feat(acta): extend topology with add leaf"
```

---

### Task 8: Extend — spine, pair, mleaf + soft-max warn + hard-16 + L2 cap

**Files:**
- Modify: `acta/extend.py`
- Modify: `tests/test_extend.py`

**Interfaces:** same `extend_topology`; add behaviors:
- `add=spine`: reject if `fabric_mode=="l2"` and spines≥2; else mesh to all current leaves
- `add=pair`: add two leaves + MLAG peer links between them
- `add=mleaf`: require `pair`; use next mleaf slot under that pair
- Soft overrun: when planned prefer port busy or past max count, use `next_free_port` and collect warnings returned or printed
- Hard fail when next-free raises

- [ ] **Step 1: Write failing tests**

```python
import pytest

from acta.capacity import Capacity
from acta.create import FabricSpec, emit_act_yaml
from acta.extend import extend_topology


def test_l2_rejects_third_spine(tmp_path: Path):
    spec = FabricSpec(
        hostname_prefix="demo",
        serial_prefix="demo",
        eos_version="4.35.4M",
        capacity=Capacity(
            fabric_mode="l2",
            max_spines=2,
            max_leaves=8,
            max_mleafs_per_pair=0,
            spines=2,
            leaves=2,
        ),
        mlag_pairs=True,
        spine_mlag=False,
        member_leaf_pairs=[],
        member_leaves_per_pair=0,
        dc_count=2,
    )
    path = tmp_path / "topo.yml"
    path.write_text(emit_act_yaml(spec))
    with pytest.raises(ValueError, match="L2"):
        extend_topology(path, add="spine", site="A")


def test_mleaf_requires_pair(tmp_path: Path):
    path = _write_base(tmp_path)
    with pytest.raises(ValueError, match="pair"):
        extend_topology(path, add="mleaf")


def test_hard_cap_fails_when_no_free_ports(tmp_path: Path):
    from acta.portplan import PortPlan
    from acta.capacity import Capacity

    plan = PortPlan(
        Capacity(
            fabric_mode=None,
            max_spines=4,
            max_leaves=8,
            max_mleafs_per_pair=0,
            spines=2,
            leaves=2,
        )
    )
    with pytest.raises(ValueError, match="16"):
        plan.next_free_port(set(range(1, 17)))
```

- [ ] **Step 2: Run — expect FAIL**

Run: `uv run pytest tests/test_extend.py -v`  
Expected: new tests FAIL

- [ ] **Step 3: Implement remaining add modes + warnings**

- [ ] **Step 4: Run full unit suite for acta pieces**

Run: `uv run pytest tests/test_capacity.py tests/test_portplan.py tests/test_topology.py tests/test_create.py tests/test_extend.py tests/test_cli_help.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add acta/extend.py tests/test_extend.py
git commit -m "feat(acta): extend spine pair mleaf with soft-max and hard-16"
```

---

### Task 9: Multi-DC create parity (l2/l3ls) enough for extend --site

**Files:**
- Modify: `acta/create.py`
- Modify: `acta/extend.py`
- Modify: `tests/test_create.py`, `tests/test_extend.py`

**Interfaces:**
- `FabricSpec.dc_count: int`, `fabric_mode: str | None` already on Capacity
- Naming: `{prefix}-{site}-spineN` etc.; bb nodes for multi-DC
- Port rules for bb/border: place **after** reserved spine/leaf service blocks (document constants in `PortPlan`: e.g. spine bb ports start at `max_leaves+3` for l2). Match intent of `generate.sh` multi-DC section without sliding when leaves grow inside max.

- [ ] **Step 1: Failing test — two-site l3ls emit has borders + capacity**

```python
def test_multi_dc_l3ls_emit_has_border_and_bb():
    spec = FabricSpec(
        hostname_prefix="demo",
        serial_prefix="demo",
        eos_version="4.35.4M",
        capacity=Capacity(
            fabric_mode="l3ls",
            max_spines=4,
            max_leaves=8,
            max_mleafs_per_pair=0,
            spines=2,
            leaves=2,
        ),
        mlag_pairs=True,
        spine_mlag=False,
        member_leaf_pairs=[],
        member_leaves_per_pair=0,
        dc_count=2,
    )
    text = emit_act_yaml(spec)
    assert "demo-A-border1:" in text
    assert "demo-bb1:" in text
```

- [ ] **Step 2: Implement multi-DC emit + extend `--site`**

Extend leaf/spine/mleaf scoped to site letter. Prompt path tested via passing `site="B"`.

- [ ] **Step 3: pytest PASS**

- [ ] **Step 4: Commit**

```bash
git add acta/create.py acta/extend.py acta/portplan.py tests/test_create.py tests/test_extend.py
git commit -m "feat(acta): multi-DC create and site-scoped extend"
```

---

### Task 10: Diagram hook + README note for Plan 1 users

**Files:**
- Create: `acta/diagram.py`
- Modify: `acta/create.py`, `acta/extend.py` (call best-effort PNG)
- Modify: `README.md` — short “Preview: acta create/extend (uv)” section pointing at this plan; full cutover docs wait for Plan 3

**Interfaces:**
- `write_png(dot_source: str, png_path: Path) -> bool` returns False if graphviz missing

- [ ] **Step 1: Implement best-effort diagram (skip if `dot` missing)**
- [ ] **Step 2: `uv run ruff check acta tests` and `uv run black acta tests`**
- [ ] **Step 3: Full pytest for new tests + existing `tests/test_clab.py` still on old `clab.py`**

Run: `uv run pytest -v`  
Expected: PASS (clab tests unchanged)

- [ ] **Step 4: Commit**

```bash
git add acta/diagram.py acta/create.py acta/extend.py README.md
git commit -m "feat(acta): optional PNG diagrams and preview README notes"
```

---

## Plan 1 self-review

**Spec coverage (create/extend slice):**
- Spare width prompts + banner → Task 6
- Capacity header → Task 2, 5
- Port reservation + next-free + hard 16 → Task 3, 8
- Extend leaf/spine/pair/mleaf + site → Tasks 7–9
- Endpoint freeze → Task 7
- L2 spine cap → Task 8
- Soft max overrun → Task 8
- uv / 3.15 → Task 1
- upload/onboard/clab delete → deferred to follow-on plans (called out in header)

**Placeholders:** None remaining; Task 8 fixtures use `emit_act_yaml` / `PortPlan` directly.

**Type consistency:** `Capacity`, `PortPlan`, `FabricSpec`, `extend_topology(...)` names reused throughout.
