# Host data-plane net Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Opt-in per-attach host data-plane IPv4 (default `192.168.2.0/24`, gw `192.168.2.1`) with eth1 or LACP `bond0`, lab settings defaults, clab exec/bind bootstrap, and `/root/HOST-NET.md`.

**Architecture:** Pure helpers in `acta/clab/host_net.py` allocate addresses and render bootstrap + docs. Attach/CLI/API/UI pass `host_net` flags; `sync_host_into_clab` / `linux_jumphost_node` persist labels and emit binds+exec. Switch Po/VLAN stay in CloudVision.

**Tech Stack:** Python ≥3.15, `ipaddress`, containerlab YAML, FastAPI, React/Vite UI, pytest.

**Spec:** `docs/superpowers/specs/2026-11-24-host-dataplane-net-design.md`

## Global Constraints

- Enablement is **opt-in** (`host_net` / `--host-net`); default attach unchanged.
- Defaults: subnet `192.168.2.0/24`, gateway `192.168.2.1`.
- Single-homed → IP+gw on **`eth1`**; dual-homed (2+ data links) → LACP **`bond0`** (802.3ad) with `eth1`/`eth2` slaves.
- **No** switch Port-Channel / VLAN / SVI generation from ACT.
- Clab linux hosts only (not ACT `generic` VM networking).
- Persist assignment on clab node labels: `acta.host-net`, `acta.host-ip`, `acta.host-subnet`, `acta.host-gateway`, `acta.host-iface`.
- Format black; lint ruff; UI `npm run build` green.
- Work on branch `feat/host-dataplane-net` (create from current tip if needed).

## File map

| File | Responsibility |
|------|----------------|
| `acta/clab/host_net.py` | Defaults, validation, allocation, bootstrap/md/env render, label helpers, claimed-IP scan |
| `acta/clab/support.py` | Extend `linux_jumphost_node` for host-net labels/exec/binds |
| `acta/attach.py` | Thread host_net opts through attach/sync; write host-net files; detach cleanup |
| `acta/cli.py` | `--host-net`, `--host-ip`, `--host-subnet`, `--host-gateway` |
| `acta/config.py` | `HOST_NET_SUBNET`, `HOST_NET_GATEWAY` in `CONFIG_KEYS` |
| `acta/web/settings_api.py` | Allowlist + expose host-net settings |
| `acta/web/routes_ops.py` | `AttachBody` fields |
| `acta/web/ops.py` | Pass fields into `run_attach` |
| `ui/src/pages/SettingsPage.tsx` | Subnet/gateway fields |
| `ui/src/pages/AttachPage.tsx` | Checkbox + advanced IP/subnet/gw |
| `ui/src/api/client.ts` | Attach payload types |
| `tests/test_host_net.py` | Allocation + render unit tests |
| `tests/test_attach_show.py` | Attach with `--host-net` integration |
| `tests/test_web_settings.py` | Settings round-trip |
| `README.md` | Short attach `--host-net` note |

---

### Task 1: `host_net` allocation + validation helpers

**Files:**
- Create: `acta/clab/host_net.py`
- Create: `tests/test_host_net.py`

**Interfaces:**
- Produces:
  - `DEFAULT_HOST_NET_SUBNET = "192.168.2.0/24"`
  - `DEFAULT_HOST_NET_GATEWAY = "192.168.2.1"`
  - `LABEL_ENABLED = "acta.host-net"` (value `"true"`)
  - `LABEL_IP = "acta.host-ip"`, `LABEL_SUBNET = "acta.host-subnet"`, `LABEL_GATEWAY = "acta.host-gateway"`, `LABEL_IFACE = "acta.host-iface"`
  - `dataclass HostNetPlan(ip: str, subnet: str, gateway: str, iface: str, dual_homed: bool)`
  - `def resolve_host_net(*, enabled: bool, host_ip: str | None, host_subnet: str | None, host_gateway: str | None, config: dict[str, str] | None, claimed: set[str], dual_homed: bool) -> HostNetPlan | None`
  - `def claimed_ips_from_clab(lab: dict) -> set[str]`
  - `def next_host_ip(subnet: str, gateway: str, claimed: set[str]) -> str`
  - `def validate_host_net(subnet: str, gateway: str, host_ip: str | None) -> None`  # raises ValueError

- [ ] **Step 1: Write failing tests**

```python
# tests/test_host_net.py
from __future__ import annotations

import pytest

from acta.clab import host_net as hn


def test_next_host_ip_skips_network_gateway_broadcast_and_claimed():
    claimed = {"192.168.2.2", "192.168.2.3"}
    assert hn.next_host_ip("192.168.2.0/24", "192.168.2.1", claimed) == "192.168.2.4"


def test_validate_rejects_gateway_outside_subnet():
    with pytest.raises(ValueError, match="gateway"):
        hn.validate_host_net("192.168.2.0/24", "10.0.0.1", None)


def test_validate_rejects_host_ip_equal_gateway():
    with pytest.raises(ValueError, match="gateway"):
        hn.validate_host_net("192.168.2.0/24", "192.168.2.1", "192.168.2.1")


def test_resolve_disabled_returns_none():
    assert (
        hn.resolve_host_net(
            enabled=False,
            host_ip=None,
            host_subnet=None,
            host_gateway=None,
            config={},
            claimed=set(),
            dual_homed=False,
        )
        is None
    )


def test_resolve_auto_allocates_and_picks_iface():
    plan = hn.resolve_host_net(
        enabled=True,
        host_ip=None,
        host_subnet=None,
        host_gateway=None,
        config={},
        claimed=set(),
        dual_homed=True,
    )
    assert plan is not None
    assert plan.ip == "192.168.2.2"
    assert plan.subnet == "192.168.2.0/24"
    assert plan.gateway == "192.168.2.1"
    assert plan.iface == "bond0"
    assert plan.dual_homed is True


def test_claimed_ips_from_clab_labels():
    lab = {
        "topology": {
            "nodes": {
                "h1": {
                    "kind": "linux",
                    "labels": {
                        "acta.host-net": "true",
                        "acta.host-ip": "192.168.2.2",
                    },
                },
                "leaf1": {"kind": "ceos"},
            }
        }
    }
    assert hn.claimed_ips_from_clab(lab) == {"192.168.2.2"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_host_net.py -q --tb=short`  
Expected: FAIL (module missing)

- [ ] **Step 3: Implement `acta/clab/host_net.py`**

```python
"""Opt-in host data-plane addressing helpers (attach --host-net)."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass

DEFAULT_HOST_NET_SUBNET = "192.168.2.0/24"
DEFAULT_HOST_NET_GATEWAY = "192.168.2.1"

LABEL_ENABLED = "acta.host-net"
LABEL_IP = "acta.host-ip"
LABEL_SUBNET = "acta.host-subnet"
LABEL_GATEWAY = "acta.host-gateway"
LABEL_IFACE = "acta.host-iface"


@dataclass(frozen=True)
class HostNetPlan:
    ip: str
    subnet: str
    gateway: str
    iface: str
    dual_homed: bool

    @property
    def prefixlen(self) -> int:
        return ipaddress.ip_network(self.subnet, strict=False).prefixlen


def validate_host_net(subnet: str, gateway: str, host_ip: str | None) -> None:
    network = ipaddress.ip_network(subnet, strict=False)
    if network.version != 4:
        raise ValueError("host net subnet must be IPv4")
    gw = ipaddress.ip_address(gateway)
    if gw not in network:
        raise ValueError(f"gateway {gateway} is not in subnet {subnet}")
    if gw in (network.network_address, network.broadcast_address):
        raise ValueError("gateway cannot be network or broadcast address")
    if host_ip is None:
        return
    addr = ipaddress.ip_address(host_ip)
    if addr not in network:
        raise ValueError(f"host IP {host_ip} is not in subnet {subnet}")
    if addr in (network.network_address, network.broadcast_address):
        raise ValueError("host IP cannot be network or broadcast address")
    if addr == gw:
        raise ValueError("host IP cannot equal gateway")


def next_host_ip(subnet: str, gateway: str, claimed: set[str]) -> str:
    validate_host_net(subnet, gateway, None)
    network = ipaddress.ip_network(subnet, strict=False)
    gw = ipaddress.ip_address(gateway)
    taken = {ipaddress.ip_address(x) for x in claimed}
    for candidate in network.hosts():
        if candidate == gw or candidate in taken:
            continue
        return str(candidate)
    raise ValueError(f"no free host addresses left in {subnet}")


def claimed_ips_from_clab(lab: dict) -> set[str]:
    nodes = ((lab.get("topology") or {}).get("nodes")) or {}
    out: set[str] = set()
    if not isinstance(nodes, dict):
        return out
    for node in nodes.values():
        if not isinstance(node, dict):
            continue
        labels = node.get("labels") or {}
        if not isinstance(labels, dict):
            continue
        if str(labels.get(LABEL_ENABLED, "")).lower() not in {"1", "true", "yes"}:
            continue
        ip = str(labels.get(LABEL_IP, "")).strip()
        if ip:
            out.add(ip.split("/", 1)[0])
    return out


def resolve_host_net(
    *,
    enabled: bool,
    host_ip: str | None,
    host_subnet: str | None,
    host_gateway: str | None,
    config: dict[str, str] | None,
    claimed: set[str],
    dual_homed: bool,
) -> HostNetPlan | None:
    if not enabled:
        return None
    cfg = config or {}
    subnet = (host_subnet or cfg.get("HOST_NET_SUBNET") or DEFAULT_HOST_NET_SUBNET).strip()
    gateway = (
        host_gateway or cfg.get("HOST_NET_GATEWAY") or DEFAULT_HOST_NET_GATEWAY
    ).strip()
    explicit = host_ip.strip() if host_ip else None
    validate_host_net(subnet, gateway, explicit)
    if explicit:
        if explicit in claimed:
            raise ValueError(f"host IP {explicit} already in use")
        ip = explicit
    else:
        ip = next_host_ip(subnet, gateway, claimed)
    iface = "bond0" if dual_homed else "eth1"
    return HostNetPlan(
        ip=ip, subnet=subnet, gateway=gateway, iface=iface, dual_homed=dual_homed
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_host_net.py -q --tb=short`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add acta/clab/host_net.py tests/test_host_net.py
git commit -m "feat(host-net): add allocation and validation helpers"
```

---

### Task 2: Bootstrap script + HOST-NET.md / .env renderers

**Files:**
- Modify: `acta/clab/host_net.py`
- Modify: `tests/test_host_net.py`

**Interfaces:**
- Consumes: `HostNetPlan`
- Produces:
  - `def render_bootstrap(plan: HostNetPlan) -> str`  # `/bin/sh` idempotent
  - `def render_host_net_md(plan: HostNetPlan, *, host: str) -> str`
  - `def render_host_net_env(plan: HostNetPlan) -> str`
  - `def host_net_labels(plan: HostNetPlan) -> dict[str, str]`
  - `def write_host_net_files(dir: Path, host: str, plan: HostNetPlan) -> tuple[Path, Path, Path]`  
    writes `bootstrap.sh`, `HOST-NET.md`, `HOST-NET.env` under `dir/host/`

- [ ] **Step 1: Write failing render tests**

```python
def test_render_bootstrap_single_uses_eth1():
    plan = hn.HostNetPlan(
        ip="192.168.2.10",
        subnet="192.168.2.0/24",
        gateway="192.168.2.1",
        iface="eth1",
        dual_homed=False,
    )
    script = hn.render_bootstrap(plan)
    assert "eth1" in script
    assert "192.168.2.10/24" in script
    assert "bond0" not in script


def test_render_bootstrap_dual_creates_lacp_bond():
    plan = hn.HostNetPlan(
        ip="192.168.2.11",
        subnet="192.168.2.0/24",
        gateway="192.168.2.1",
        iface="bond0",
        dual_homed=True,
    )
    script = hn.render_bootstrap(plan)
    assert "mode 802.3ad" in script or "mode=802.3ad" in script
    assert "eth1" in script and "eth2" in script
    assert "bond0" in script
    assert "192.168.2.11/24" in script


def test_render_md_mentions_mcast_and_cloudvision():
    plan = hn.HostNetPlan(
        ip="192.168.2.10",
        subnet="192.168.2.0/24",
        gateway="192.168.2.1",
        iface="eth1",
        dual_homed=False,
    )
    md = hn.render_host_net_md(plan, host="host1")
    assert "mcast-send" in md
    assert "CloudVision" in md
    assert "192.168.2.10" in md
```

- [ ] **Step 2: Run tests — expect FAIL (functions missing)**

Run: `uv run --extra dev pytest tests/test_host_net.py -q --tb=line`

- [ ] **Step 3: Implement renderers**

Bootstrap requirements (implement exactly these behaviors):

- `#!/bin/sh` + `set -eu`
- Wait briefly for `eth1` to exist (loop `ip link show eth1`).
- Single: `ip link set eth1 up`; `ip addr replace ${ip}/${prefix} dev eth1`; `ip route replace default via ${gw} dev eth1`.
- Dual: create bond if missing (`ip link add bond0 type bond mode 802.3ad miimon 100`); set `eth1`/`eth2` down, master bond0, up; `ip addr replace` + default via on `bond0`.
- Idempotent: use `replace`, tolerate existing bond.
- Copy env/md already bound; script may `cp` from `/etc/acta-host-net/` if binds use that path — prefer writing md/env via binds to `/root/` directly so script only does networking.

`host_net_labels(plan)`:

```python
{
  LABEL_ENABLED: "true",
  LABEL_IP: plan.ip,
  LABEL_SUBNET: plan.subnet,
  LABEL_GATEWAY: plan.gateway,
  LABEL_IFACE: plan.iface,
}
```

`HOST-NET.md` must include: current IP/iface/subnet/gw; mgmt vs data-plane note; how to change IP; LACP+CloudVision for dual; tools list including `ping`, `traceroute`, `curl`, `dig`, `lldpcli`, `mcast-send`, `mcast-receive`, `mcast-status`.

- [ ] **Step 4: Run tests — expect PASS**

Run: `uv run --extra dev pytest tests/test_host_net.py -q --tb=short`

- [ ] **Step 5: Commit**

```bash
git add acta/clab/host_net.py tests/test_host_net.py
git commit -m "feat(host-net): render bootstrap script and HOST-NET docs"
```

---

### Task 3: Wire `linux_jumphost_node` + file layout helper

**Files:**
- Modify: `acta/clab/support.py` (`linux_jumphost_node`)
- Modify: `acta/clab/host_net.py` (add `host_net_artifact_dir`)
- Modify: `tests/test_host_net.py` and/or `tests/test_clab.py` jumphost test

**Interfaces:**
- Consumes: `HostNetPlan`, label helpers
- Produces: `linux_jumphost_node(..., host_net: HostNetPlan | None = None, host_net_dir: Path | None = None) -> dict`
  - When `host_net` set: merge labels; `exec` = `["lldpd", "sh /etc/acta-host-net/bootstrap.sh"]` (keep lldpd first); `binds` include:
    - `{host_net_dir}/bootstrap.sh:/etc/acta-host-net/bootstrap.sh:ro`
    - `{host_net_dir}/HOST-NET.md:/root/HOST-NET.md:ro`
    - `{host_net_dir}/HOST-NET.env:/root/HOST-NET.env:ro`
- Produces: `def host_net_artifact_dir(clab_path: Path, host: str) -> Path`  
  → `clab_path.parent / f"{clab_path.name.removesuffix('.yml').removesuffix('.yaml')}.host-net" / host`  
  (normalize so `foo.clab.yml` → `foo.clab.host-net/host`)

Prefer exact: for `demo.clab.yml` use `demo.host-net/<host>/` via  
`clab_path.with_suffix("").with_suffix("").name` carefully — implement:

```python
def host_net_artifact_dir(clab_path: Path, host: str) -> Path:
    name = clab_path.name
    for suffix in (".clab.yml", ".clab.yaml", ".yml", ".yaml"):
        if name.endswith(suffix):
            stem = name[: -len(suffix)]
            break
    else:
        stem = clab_path.stem
    return clab_path.parent / f"{stem}.host-net" / host
```

- [ ] **Step 1: Failing test for node shape**

```python
def test_linux_jumphost_node_includes_host_net_binds(tmp_path):
    from acta.clab.support import linux_jumphost_node
    from acta.clab.host_net import HostNetPlan, write_host_net_files, host_net_artifact_dir

    clab = tmp_path / "lab.clab.yml"
    clab.write_text("name: lab\n")
    plan = HostNetPlan("192.168.2.5", "192.168.2.0/24", "192.168.2.1", "eth1", False)
    d = host_net_artifact_dir(clab, "h1")
    write_host_net_files(d, plan)
    node = linux_jumphost_node("img:tag", mgmt_ipv4="172.100.100.10", host_net=plan, host_net_dir=d)
    assert node["labels"]["acta.host-ip"] == "192.168.2.5"
    assert any("bootstrap.sh" in b for b in node["binds"])
    assert "lldpd" in node["exec"]
    assert any("bootstrap.sh" in e for e in node["exec"])
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement `write_host_net_files`, extend `linux_jumphost_node`**

Keep backward compatible: omit `host_net` → unchanged node (`exec: [lldpd]` only, no binds/labels).

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add acta/clab/support.py acta/clab/host_net.py tests/test_host_net.py
git commit -m "feat(host-net): extend linux jumphost node with binds and exec"
```

---

### Task 4: Settings keys (`HOST_NET_SUBNET` / `HOST_NET_GATEWAY`)

**Files:**
- Modify: `acta/config.py` — append to `CONFIG_KEYS`
- Modify: `acta/web/settings_api.py` — add to `_EXACT_KEYS` and `get_settings` defaults
- Modify: `tests/test_web_settings.py`
- Modify: `ui/src/pages/SettingsPage.tsx` — two text fields under clab section

**Interfaces:**
- Produces: settings GET/PATCH round-trip for both keys; empty → UI may show placeholder defaults without writing until save

- [ ] **Step 1: Failing settings test**

```python
def test_host_net_settings_round_trip(tmp_path: Path):
    from acta.web.settings_api import get_settings, patch_settings

    patched = patch_settings(
        tmp_path,
        {"HOST_NET_SUBNET": "192.168.2.0/24", "HOST_NET_GATEWAY": "192.168.2.1"},
    )
    assert patched["HOST_NET_SUBNET"] == "192.168.2.0/24"
    assert patched["HOST_NET_GATEWAY"] == "192.168.2.1"
    assert get_settings(tmp_path)["HOST_NET_GATEWAY"] == "192.168.2.1"
```

- [ ] **Step 2: Run — expect FAIL (key not allowlisted or missing)**

- [ ] **Step 3: Add keys to `CONFIG_KEYS` + `_EXACT_KEYS` + `get_settings` output; Settings UI fields**

- [ ] **Step 4: Run `tests/test_web_settings.py` — PASS; `npm run build` in `ui/` — PASS**

- [ ] **Step 5: Commit**

```bash
git add acta/config.py acta/web/settings_api.py tests/test_web_settings.py ui/src/pages/SettingsPage.tsx
git commit -m "feat(settings): add HOST_NET_SUBNET and HOST_NET_GATEWAY"
```

---

### Task 5: Attach plumbing (library + CLI)

**Files:**
- Modify: `acta/attach.py` — `run_attach`, `attach_host_act`, `attach_host_clab`, `sync_host_into_clab`
- Modify: `acta/cli.py` — flags; pass through `run_attach(...)`
- Modify: `tests/test_attach_show.py`

**Interfaces:**
- Extend signatures with:
  - `host_net: bool = False`
  - `host_ip: str | None = None`
  - `host_subnet: str | None = None`
  - `host_gateway: str | None = None`
- `sync_host_into_clab(..., host_net_plan: HostNetPlan | None = None)`  
  When plan set: `write_host_net_files`, pass into `linux_jumphost_node`.  
  When plan None: strip host-net labels/binds if re-syncing without net (or leave prior — **prefer**: only set when plan provided; detach removes artifacts).
- Dual-homed for iface selection: `len(endpoints) >= 2` (or existing `dual_homed and two links`).
- Detach: delete `host_net_artifact_dir` for that host if present.

CLI:

```python
attach.add_argument("--host-net", action="store_true", help="Assign data-plane IP (see HOST_NET_*)")
attach.add_argument("--host-ip", default=None, help="Optional IPv4; else auto from subnet")
attach.add_argument("--host-subnet", default=None, help="Override lab HOST_NET_SUBNET")
attach.add_argument("--host-gateway", default=None, help="Override lab HOST_NET_GATEWAY")
```

- [ ] **Step 1: Failing attach integration test**

Use existing temp ACT+clab fixtures in `tests/test_attach_show.py`. Pattern:

```python
def test_attach_host_net_writes_clab_labels_and_artifacts(tmp_path, ...):
    # create minimal ACT+sibling clab with one mlag pair or --to leaf
    # run_attach(..., host_net=True)
    # load sibling clab yaml
    # assert labels acta.host-ip present
    # assert artifact bootstrap.sh exists
```

Also assert without `host_net=True` there are no `acta.host-net` labels.

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Thread parameters; in `sync_host_into_clab` after building links:**

```python
claimed = claimed_ips_from_clab(data)
# exclude this host's old IP from claimed when re-attach
plan = resolve_host_net(...)  # called from attach_host_* with dual_homed=(len(links)>=2)
if plan:
    d = host_net_artifact_dir(clab_path, host)
    write_host_net_files(d, plan)
    nodes[host] = linux_jumphost_node(image, mgmt_ipv4=mgmt_ip, host_net=plan, host_net_dir=d)
else:
    nodes[host] = linux_jumphost_node(image, mgmt_ipv4=mgmt_ip)
```

Call `resolve_host_net` once in `attach_host_act` after links known; pass plan into sync.

- [ ] **Step 4: Run attach tests — PASS**

- [ ] **Step 5: Commit**

```bash
git add acta/attach.py acta/cli.py tests/test_attach_show.py
git commit -m "feat(attach): opt-in --host-net data-plane addressing"
```

---

### Task 6: Web API + Attach UI

**Files:**
- Modify: `acta/web/routes_ops.py` — `AttachBody`
- Modify: `acta/web/ops.py` — `op_attach` kwargs
- Modify: `ui/src/api/client.ts` — `attachTopology` body
- Modify: `ui/src/pages/AttachPage.tsx` — checkbox + optional fields
- Test: extend `tests/test_web_ops.py` or attach API test if present

**Interfaces:**
- `AttachBody`: `host_net: bool | None = None`, `host_ip: str | None = None`, `host_subnet: str | None = None`, `host_gateway: str | None = None`
- UI: checkbox “Data-plane IP”; when checked show IP / subnet / gateway inputs (placeholders from settings fetch)

- [ ] **Step 1: Failing API test** — POST `/api/attach` with `host_net: true` on a temp topo (mirror existing attach web test patterns)

- [ ] **Step 2: Implement body + ops pass-through + UI**

- [ ] **Step 3: `uv run --extra dev --extra ui pytest tests/test_web_ops.py -q` and `npm run build`**

- [ ] **Step 4: Commit**

```bash
git add acta/web/routes_ops.py acta/web/ops.py ui/src/api/client.ts ui/src/pages/AttachPage.tsx tests/test_web_ops.py
git commit -m "feat(webui): attach host-net checkbox and settings fields"
```

---

### Task 7: README + export + final verification

**Files:**
- Modify: `README.md` — attach section note for `--host-net` and CloudVision Po/VLAN
- Modify: `acta/clab/__init__.py` — export public helpers if other modules import from package root (optional; prefer `from acta.clab.host_net import ...`)

- [ ] **Step 1: Document in README near attach examples**

```text
# Opt-in data-plane IP (default 192.168.2.0/24, gw .1); dual-homed → LACP bond0
acta attach host host1 TOPO.yml --mlag-pair 1 --host-net
# Configure matching MLAG Port-Channel + VLAN/SVI in CloudVision
```

- [ ] **Step 2: Full test sweep**

Run:

```bash
uv run --extra dev --extra ui pytest tests/test_host_net.py tests/test_attach_show.py tests/test_web_settings.py tests/test_web_ops.py tests/test_clab.py -q --tb=short
cd ui && npm run build
```

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add README.md acta/clab/__init__.py
git commit -m "docs: document attach --host-net and CloudVision expectations"
```

---

## Spec coverage (self-review)

| Spec item | Task |
|-----------|------|
| Opt-in enablement | 5, 6 |
| Defaults 192.168.2.0/24 + .1 | 1, 4 |
| Lab settings + per-attach override | 4, 5, 6 |
| Auto allocate / explicit IP | 1, 5 |
| eth1 vs LACP bond0 | 1, 2, 5 |
| No switch Po from ACT | 2 (docs), 7 (README) |
| Clab exec/bind bootstrap | 2, 3, 5 |
| `/root/HOST-NET.md` + tools/mcast | 2 |
| Detach frees artifacts | 5 |
| Tests allocation + script + plumbing | 1, 2, 5, 6, 7 |

No intentional TBDs. Label keys and function names are consistent across tasks (`acta.host-ip`, `HostNetPlan`, `resolve_host_net`, `linux_jumphost_node(..., host_net=)`).
