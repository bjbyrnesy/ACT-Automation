# ACT Automation (`acta.py`)

One Python CLI for **Arista Cloud Test (ACT)** and **containerlab** labs, plus
day-2 helpers to **show** the fabric, **attach** jumphosts, **ssh** into nodes,
and onboard switches to **CVaaS**.

```text
acta.py act  {create,extend,upload,onboard}              # ACT / vEOS
acta.py clab {create,generate,deploy,destroy,redeploy,onboard,show}
acta.py show | attach | ssh                              # day-2 (both platforms)
acta.py serve | ui                                       # local Web UI (127.0.0.1)
```

Examples assume an activated venv (see [Install](#install)). Use `acta …` or
`python acta.py …`.

## Why this exists

Growing or rewiring an ACT lab usually means destroy/recreate, and tying devices
to CVaaS without ZTP is tedious. `acta.py`:

1. Builds topologies with **pinned serial + system MAC** and **spare port capacity**
   so extend does not renumber existing links.
2. Uploads / deploys on ACT, or generates and deploys the same fabric on containerlab
   (`prefix: ""` so container names match ACT hostnames).
3. Pastes TerminAttr (`token-secure`) onto **switches only** (vEOS / cEOS) — never
   linux/generic jumphosts.

Intentional scope: Campus Fabric and L3LS / EVPN Studios shapes — not every possible
topology.

## Install

Needs **Python 3.15+**.

### Install uv

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# or: brew install uv
# Windows: winget install astral-sh.uv
#   or: irm https://astral.sh/uv/install.ps1 | iex
```

### Install dependencies and activate the venv

```bash
cd ACT-Automation
uv sync --extra dev                 # creates .venv and installs deps + acta
source .venv/bin/activate           # macOS / Linux / WSL
# .venv\Scripts\activate            # Windows
```

After activate, `acta` is on `PATH` (or use `python acta.py`). Optional:
`pre-commit install --install-hooks`. Graphviz `dot` is optional for PNG diagrams
(`brew install graphviz`). Never commit `.config` or `.env`.

## Quickstart

```bash
# ACT path
python acta.py act create
python acta.py act upload topology-….yml
python acta.py act onboard

# containerlab path (interactive create under clab — equal noun)
python acta.py clab create --name mylab --image ceos:4.35.4M
# or both outputs: acta act create --for both --name mylab --image ceos:4.35.4M
python acta.py clab deploy mylab.clab.yml          # or --from-act …
python acta.py clab onboard mylab.clab.yml --endpoint apiserver.arista.io

# Day-2
acta show topology-….yml
acta attach host jump1 topology-….yml --mlag-pair 1 --et 11
acta ssh jump1
acta ssh A-leaf1 -- show hostname
acta clab redeploy mylab.clab.yml        # after attach/extend
```

### Web UI (local)

Localhost ops console (Create → Graphviz preview → Write, Labs/Show, Extend,
Attach, Clab/ACT jobs, Settings). Binds **127.0.0.1:8765** and opens a browser.
Clab host may be local or remote via Settings / `CLAB_HOST`. No SSH-in-UI.
Graphviz `dot` required for PNG preview.

```bash
uv sync --extra ui --extra dev
# first time / after ui/ changes:
bash scripts/build-ui.sh
acta serve                 # alias: acta ui
# optional: acta serve --no-open --root /path/to/labs
```

Dev (Vite hot reload, API still via `acta serve`):

```bash
# Terminal 1
acta serve --no-open
# Terminal 2
cd ui && npm ci && npm run dev   # proxies /api → :8765
```

---

## CLI map

| Command | Purpose |
| --- | --- |
| `serve` / `ui` | Local Web UI on 127.0.0.1 (opens browser) |
| `act create` | Interactive fabric + capacity header; `--for act\|clab\|both` |
| `act extend` | Add leaf / mleaf / site / … on unused ports only |
| `act upload` | Push YAML to ACT; optional lab create/deploy |
| `act onboard` | Running ACT lab → CVaaS (SSH + TerminAttr on **vEOS** only) |
| `clab create` | Same interactive create; defaults to clab (`--for clab\|both`). Still writes an ACT YAML sibling as the fabric source for extend/generate |
| `clab generate` | ACT YAML → project `.clab.yml` + configs / annotations |
| `clab deploy` | Deploy under `~/.act-automation/clab/<name>/` (local or `--host`) |
| `clab destroy` | Tear down a deployed lab (does not regenerate sibling YAML) |
| `clab redeploy` | Destroy if present, then deploy |
| `clab onboard` | Running cEOS containers → CVaaS (**arista_ceos** only; skips linux hosts) |
| `show` | MLAG / mleaf / host tables, SSH probes, Graphviz PNG |
| `attach host` | Add generic/linux jumphost after the fabric exists |
| `ssh` | `podman`/`docker exec` into a host (`bash`) or switch (`Cli`) |

---

## ACT workflow

### Create

```bash
python acta.py act create
python acta.py act create --for both --name mylab --image ceos:4.35.4M
```

Prompts cover serial/hostname prefix, site count (1–8) with **named site tokens**,
spines/leaves, MLAG, member-leaves, use case (`datacenter`|`campus`), fabric mode
(`l3ls`|`l2ls`), backbone/border redundancy (`mlag-peer` default or `evpn-aa`), and
**planned capacity** (`max_spines`, `max_leaves`, `max_mleafs_per_pair`). Capacity is
stored in `# capacity:` header comments so later extend can use reserved Ethernet
blocks.

| `--for` | Output |
| --- | --- |
| `act` (default) | ACT topology YAML only |
| `clab` | Generate sibling `.clab.yml` (and configs) for containerlab |
| `both` | ACT YAML + containerlab lab |

Default comes from `CREATE_FOR` in `.config` when set.

### Extend

```bash
python acta.py act extend topology-….yml --add leaf
python acta.py act extend topology-….yml --add mleaf --pair 1
# Add (or promote into) a named site — always writes a new dated YAML
python acta.py act extend topology-….yml --add site --name aus
python acta.py act extend topology-….yml --add site --first-site aus --name dfw
```

- **Soft max:** capacity header. Past soft max → warning; still ≤ Ethernet16.
- **Hard stop:** 16 Ethernet ports per switch.
- **L2LS spines:** hard-capped at 2.
- Existing `node:EthernetN` endpoints never move. Bad/missing capacity header → fail;
  recreate with `act create`.
- **`--add site`:** promotes a single-site lab to a named first site + backbone hub
  when needed, then can add another site. L3LS attaches borders↔bb; L2LS attaches
  spines↔bb. Default redundancy is `mlag-peer`; `evpn-aa` skips peer links. Prints a
  baseline→EVPN RAM range and ACT upload next steps; confirm (or `--force`) when
  projected cEOS exceed ~24. Serial/MAC preserved on promote unless
  `--rekey-identity`.

### Upload + onboard

```bash
python acta.py act upload topology-….yml
python acta.py act onboard
```

Need an ACT API key (UI → profile) and a CVaaS enrollment token
(Devices → Device Registration). Onboard picks a Running lab, resolves EOS creds
from the topology `veos:` block (else `cvpadmin` / `cvp123!`), and pastes TerminAttr
to **vEOS devices only**.

---

## Containerlab workflow

Lab work for this project runs on a host with **Podman** (preferred) or Docker and
containerlab. On macOS, deploy into a **Podman machine**; `acta.py` can invoke
containerlab via `podman machine ssh` when needed.

```bash
python acta.py clab generate topology-….yml --name mylab --image ceos:4.35.4M
python acta.py clab deploy mylab.clab.yml
# or:  clab deploy --from-act topology-….yml
python acta.py clab onboard mylab.clab.yml --endpoint apiserver.arista.io
```

After topology edits (`attach` / `extend`):

```bash
python acta.py clab destroy mylab.clab.yml
python acta.py clab deploy mylab.clab.yml
# same as:
python acta.py clab redeploy mylab.clab.yml
```

### Naming and identity

- Generated labs use `prefix: ""` → container name **equals** the ACT hostname
  (`blz2-A-spine1`), not `clab-<lab>-…`.
- Deploy stores the lab at `~/.act-automation/clab/<lab-name>/topology.clab.yml`.
- cEOS gets deterministic serial / system MAC via `CEOS_SERIAL_NUMBER` and
  per-node `ceos-config`. Destroying the lab ≠ decommissioning CVaaS devices.

### Runtime and host

- Deploy / destroy / redeploy default to `--runtime podman` (`docker` optional).
- `--host user@lab-host` runs those steps over SSH (passwordless sudo for
  containerlab / runtime as documented for your host).
- Onboard auto-discovers docker / rootless / rootful podman unless `--runtime` is set.
- **Onboard skips `kind: linux` jumphosts** — only `arista_ceos` gets TerminAttr.

### Management network

Defaults: subnet `172.100.100.0/22`, sequential static `mgmt-ipv4`, DNS/NTP in VRF
`MGMT` (`CLAB_DNS` / `CLAB_NTP` or `--name-servers` / `--ntp-servers`). Useful
generate flags: `--mgmt-subnet`, `--mgmt-gateway`, `--mgmt-range`, `--mgmt-bridge`,
`--mgmt-mtu`, `--mgmt-network`. Deploy can override `--mgmt-network` /
`--mgmt-bridge` on the host copy only.

`--mgmt-network` is the Docker/Podman **network name** (default `clab`).
`--mgmt-bridge` is the Linux **bridge interface** name (`mgmt.bridge`, ≤15 chars).
Bridge settings apply when the network is **created**; if a network already
exists, destroy it first (or use a new `--mgmt-network` name) for Docker to
pick up a new bridge.

`.config` keys (CLI wins): `CLAB_NAME`, `CLAB_IMAGE`, `CLAB_HOST`, `CLAB_HOST_IMAGE`,
`CLAB_FROM_ACT`, `CLAB_MGMT_*`, `CLAB_DNS`, `CLAB_NTP`, `CLAB_DISABLEAAA`,
`CVAAS_HOST`, `CVAAS_TOKEN`, …

Full flag lists: `python acta.py clab <command> --help`.

---

## Day-2: show, attach, ssh

### `show`

```bash
python acta.py show topology-….yml
python acta.py show topology-….yml --plain --no-ssh
# Remote clab (Docker/Podman on another host) — also: acta.py clab show …
python acta.py show topology-….clab.yml --host user@lab-host --runtime docker
```

Prints node counts, **numbered MLAG pairs** (`--mlag-pair`), **member-leaves**
(`--mleaf`), attached hosts, and SSH-reachable mgmt IPs (`admin@…` switches,
`root@…` multitool hosts). Accepts ACT YAML or `.clab.yml`. Writes / refreshes
a Graphviz PNG; inline in Kitty / Ghostty / WezTerm / iTerm2 when supported
(`--image` / `--plain`).

With `--host`, TCP/22 probes and `containerlab inspect` run on that lab host
(where the mgmt bridge is routed). On macOS without `--host`, show falls back
to `podman machine ssh` when local probes miss. Prefer `acta.py ssh` (exec)
over host-routed SSH for a shell.

### `attach host`

Create builds the **switch fabric first**. Attach jumphosts afterward:

```bash
python acta.py attach host jump1 topology-….yml --to leaf1
python acta.py attach host jump2 topology-….yml --mlag-pair 1 --et 11
python acta.py attach host jump3 topology-….yml --mleaf 1
```

- ACT → `node_type: generic` (default ubuntu / `ansible`/`ansible`).
- Sibling `*.clab.yml` (when present) → `kind: linux` multitool image with
  **mcast-tools** preinstalled (`mcast-send` / `mcast-receive` / `mcast-status`),
  `lldpd` on, static `mgmt-ipv4`, no `cmd:` override (keeps dropbear SSH alive).
  Build once on the clab host: `scripts/build-host-image.sh` (default
  `CLAB_HOST_IMAGE=localhost/acta-host-multitool:v0.10.0-mcast0.2.3`).
- Dual-homed / MLAG without `--et` picks one Ethernet free on **both** peers.
- Use case policy: datacenter → no spines; campus → spines allowed (warning).

Then `clab redeploy` (or destroy+deploy) so the running lab picks up new hosts.

### `ssh`

```bash
python acta.py ssh blz2-host1              # bash
python acta.py ssh A-leaf1                 # EOS Cli
python acta.py ssh host1 -- uname -a
python acta.py ssh leaf1 --runtime docker -- show hostname
```

Uses `podman` or `docker exec` (not mgmt-network SSH). Unique name fragments are
enough when unambiguous. Default shells: linux → `bash`, cEOS → `Cli`.

Default logins (mgmt SSH, when reachable): cEOS `admin`/`admin`; multitool often
`root` (image default). ACT generic VMs use the topology `generic:` user
(default `ansible`/`ansible`).

---

## Platform notes

### macOS

- Graphviz: `brew install graphviz`
- Containerlab labs: Podman machine. `acta.py ssh` works from the Mac via the
  runtime; raw `ssh admin@172.100…` usually does not without extra routing.

### Windows

1. Python 3.15+ and uv.
2. Optional Graphviz + PATH to its `bin`.
3. Prefer WSL2 / a Linux lab host for containerlab.

---

## How the pieces fit

| Path | Flow |
| --- | --- |
| ACT | `act create` → `act upload` → (UI or upload deploy) → `act onboard` |
| Clab | `act create` [`--for clab\|both`] → `clab deploy` → `clab onboard` |
| Grow | `act extend` / `attach` → upload or `clab redeploy` → onboard again if needed |

No DHCP, ZTP, or `bootstrap.py`. CVaaS enrollment uses TerminAttr **token-secure**
auth (token file + endpoint), which fits labs where every switch is SSH-reachable
at boot.

Pinned serials/MACs let CVaaS treat rebuilds as the same devices (studios / labels
carry over) when you keep the same identities.

### Repo layout

| Path | Role |
| --- | --- |
| `acta.py` | CLI entry (`act`, `clab`, `show`, `attach`, `ssh`) |
| `acta/` | Implementation package |
| `pyproject.toml` / `uv.lock` | Python ≥3.15 project |
| `.pre-commit-config.yaml` | Local gitleaks + Black/Ruff |
| `.github/workflows/` | CI + security Actions |
| `topology-<prefix>-<date>.yml` | Create output (gitignored pattern) |
| `.config` | Local answers / tokens (**gitignored**) |

---

## CVaaS cleanup

Decommission labs you are done with (Devices → Device Registration →
Decommission and Replace). Prefer bulk decommission by hostname prefix.

![CVaaS cleanup](<cvaas-cleanup.gif>)

## Sharing

1. Clone; `uv sync --extra dev` (+ optional `pre-commit install`).
2. Use your own ACT / CVaaS credentials when prompted — never share `.config`.
3. Optional: `act create` with **your** serial prefix (not cached for others).

## Upgrading EOS via CloudVision

Topologies set `legacy_eos_versioning: false` so CVaaS can drive EOS upgrades in ACT.

## CI & security

**Local:** pre-commit (Gitleaks on commit; full scan on push; block `.config`/`.env`;
Black/Ruff).

**GitHub Actions:** same pre-commit suite + pytest; Gitleaks, zizmor, Trivy;
Dependabot for Actions/pip. CodeQL / native Secret scanning need a repo
**owner** and are not run in CI; collaborators are covered by pre-commit + Gitleaks.

## TODO

- Topology diagram upload via ACT REST (`diagram_path` server-side path).
- Optional AVD → topology generation
  ([emilarista/act_topgen](https://github.com/emilarista/act_topgen)).
- Parallelize ACT onboard SSH loop for large labs.
