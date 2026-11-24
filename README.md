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

Examples assume an activated venv (see [Install](#install) — or
`bash scripts/install-deps.sh`). Use `acta …` or `python acta.py …`.

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

Everything you need lives in this section. Later chapters only point here.

### One-shot installer (simplest)

From the repo root on **macOS** or **Linux** (Windows: use WSL2, then the same):

```bash
bash scripts/install-deps.sh
```

That installs missing host tools (**uv**, **Node.js**, **Graphviz**), ensures
Python 3.15+ via uv, runs `uv sync --extra dev`, and builds the Web UI SPA into
`acta/web/static/`.

Useful flags:

```bash
bash scripts/install-deps.sh --with-clab   # also Podman + containerlab install hint
bash scripts/install-deps.sh --hooks       # pre-commit install --install-hooks
bash scripts/install-deps.sh --ui-only     # leaner: uv sync --extra ui
bash scripts/install-deps.sh --no-graphviz # skip dot (live Web UI diagram does not need it)
bash scripts/install-deps.sh --help
```

Then:

```bash
source .venv/bin/activate
bash scripts/serve-ui.sh                   # http://127.0.0.1:8765/
```

Homebrew is required on macOS for Node/Graphviz/Podman packages. The script will
not install Homebrew itself — see https://brew.sh if `brew` is missing.

Prefer the step-by-step sections below when you want full control.

### Dependency matrix

| Dependency | Version | Required for | Notes |
| --- | --- | --- | --- |
| **Python** | **3.15+** | CLI, tests, Web API | Runtime for `acta` |
| **uv** | current | Install / venv / lockfile | Prefer over pip |
| **Node.js + npm** | **20+** | Web UI SPA build (`scripts/build-ui.sh`, Vite) | Not provided by `uv`; see [Rebuild the SPA](#rebuild-the-spa-build-uish) |
| **Graphviz** (`dot`) | any recent | Optional PNG from `acta show` | Not needed for the live CV diagram in the Web UI |
| **Podman** (or Docker) | recent | `clab deploy` / `ssh` / onboard exec | Default runtime is Podman |
| **containerlab** | recent | Clab deploy path | On the lab host (`CLAB_HOST` may be remote) |
| **pre-commit** | via `dev` extra | Optional local hooks | Gitleaks, Black, Ruff |

Python packages (PyYAML, httpx, rich; FastAPI/uvicorn for Web UI) come from
`uv sync` — you do **not** install those by hand.

Never commit `.config` or `.env`.

### 1. Python 3.15+

```bash
python3 --version   # must be 3.15 or newer
```

| Platform | Install |
| --- | --- |
| macOS | `brew install python@3.15` (or newer formula) |
| Fedora | `sudo dnf install python3.15` |
| Debian/Ubuntu | Use deadsnakes or a 3.15+ distro package |
| Windows | [python.org](https://www.python.org/downloads/) installer; enable “Add to PATH” |

### 2. uv

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# macOS alternative
brew install uv

# Windows
winget install astral-sh.uv
# or: irm https://astral.sh/uv/install.ps1 | iex
```

Confirm: `uv --version`.

### 3. Node.js 20+ (Web UI)

`uv sync --extra ui` installs only the **Python** API (FastAPI / uvicorn). Building
or hot-reloading the React SPA needs **Node.js 20+** with `npm` on `PATH`.

```bash
# macOS (Homebrew)
brew install node

# Fedora / RHEL
sudo dnf install nodejs

# Debian / Ubuntu — use Node 20+ (distro package or NodeSource)
# https://github.com/nodesource/distributions
sudo apt-get install -y nodejs npm   # only if that package is Node 20+

# Version managers (any OS)
# fnm: https://github.com/Schniz/fnm
# nvm: https://github.com/nvm-sh/nvm
```

```bash
node -v   # v20.x or newer
npm -v
```

`scripts/build-ui.sh` tries `brew install node` on macOS when `npm` is missing and
Homebrew is present; otherwise it prints the same hints and exits.

### 4. Graphviz (optional PNGs)

Only for Graphviz PNG export from `acta show` / older diagram paths. The Web UI
topology pane does **not** require `dot`.

```bash
# macOS
brew install graphviz

# Fedora
sudo dnf install graphviz

# Debian / Ubuntu
sudo apt-get install -y graphviz

# Windows
winget install graphviz
# then ensure Graphviz `bin` is on PATH
```

Confirm: `dot -V`.

### 5. Podman / Docker + containerlab (clab path)

Needed to deploy and exec into containerlab labs. Default CLI runtime is **Podman**.

| Platform | Notes |
| --- | --- |
| macOS | Install [Podman](https://podman.io/) (often `brew install podman`) and start a Podman machine. `acta ssh` works via the runtime; raw `ssh admin@172.100…` usually needs extra routing. |
| Linux | `podman` or `docker` from the distro; install [containerlab](https://containerlab.dev/install/) on the host that runs labs. |
| Windows | Prefer **WSL2** or a remote Linux lab host (`CLAB_HOST` / Settings). |

Confirm (on the lab host): `podman version` or `docker version`, and `containerlab version`.

### 6. Project venv (Python deps)

From the repo root:

```bash
cd ACT-Automation

# Day-to-day CLI + tests + Web API stubs in CI
uv sync --extra dev

# Leaner: CLI + Web API only (enough for acta serve after SPA build)
# uv sync --extra ui

source .venv/bin/activate           # macOS / Linux / WSL
# .venv\Scripts\activate            # Windows
```

After activate, `acta` is on `PATH` (or use `python acta.py` / `uv run acta …`).

Optional hooks (after `uv sync --extra dev`):

```bash
pre-commit install --install-hooks
```

### Quick verify

```bash
python3 --version    # ≥ 3.15 (or: uv run python --version)
uv --version
node -v && npm -v    # ≥ 20, if you use the Web UI
dot -V               # optional
podman version       # or docker — if you use clab
acta --help          # after uv sync + activate
```

Or re-run the installer anytime; it skips tools that are already present:

```bash
bash scripts/install-deps.sh
```

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

## Web UI

Localhost ops console for Create / Labs / Extend / Attach / jobs / Settings, with a
live **CV-style topology diagram** (zoom, loupe, host rails). Binds
**127.0.0.1:8765** only and opens a browser. Clab host may be local or remote via
Settings / `CLAB_HOST`. No SSH-in-UI.

**Prerequisites:** [Install](#install) — at minimum Python 3.15+, uv, and Node.js 20+
(`npm`). Graphviz is not required for the live diagram. Easiest path:
`bash scripts/install-deps.sh` then the command below.

### Run it (preferred)

From the repo root:

```bash
bash scripts/serve-ui.sh
```

That syncs the `ui` extra, builds the SPA into `acta/web/static/`, and runs
`acta serve`. Open **http://127.0.0.1:8765/** (the script also tries to open a
browser). Stop with Ctrl-C.

Flags pass through to `acta serve`:

```bash
bash scripts/serve-ui.sh --no-open              # do not open a browser
bash scripts/serve-ui.sh --port 9000            # alternate port
bash scripts/serve-ui.sh --root /path/to/labs   # override labs directory
```

Topology YAML lives under **`labs/`** (gitignored local working copy). The Web UI
defaults to `--root labs`. Tracked samples are in **`examples/`** — copy one in
before opening the UI:

```bash
mkdir -p labs
cp examples/campus-l2ls.yml labs/
bash scripts/serve-ui.sh --no-open
```

### Run it step by step

Keep each `uv …` invocation on **one** line (a break after `uv` runs bare `uv` help):

```bash
uv sync --extra ui
bash scripts/build-ui.sh
uv run acta serve            # or: .venv/bin/acta serve
# aliases: acta ui
```

You should see:

```text
ACTA Web UI listening on http://127.0.0.1:8765/
Labs root: …
Press Ctrl-C to stop.
INFO:     Uvicorn running on http://127.0.0.1:8765 …
```

### Rebuild the SPA (`build-ui.sh`)

Whenever `ui/` changes (or after a fresh clone without built assets), from the
repo root:

```bash
bash scripts/build-ui.sh
```

This runs `npm ci` + `npm run build` in `ui/`, then copies `ui/dist/` into
`acta/web/static/` for `acta serve`. Those files are **generated** (gitignored);
never commit hashed `index-*.js` / CSS under `static/assets/`. A successful run
ends with:

```text
✓ built in …ms
UI built → …/ACT-Automation/acta/web/static/index.html
Serve with: bash scripts/serve-ui.sh   (or: uv run acta serve)
```

Harmless npm noise you can ignore if that final line appears: funding messages,
“New major version of npm available”, and (on older checkouts) an
`install-scripts` / `fsevents` allowScripts notice. The repo’s `ui/package.json`
already approves `fsevents@2.3.3` for npm 11+ script policy.

`scripts/install-deps.sh` and `scripts/serve-ui.sh` both call `build-ui.sh` for
you; use it alone when you only need to refresh static assets.

### Frontend dev (hot reload)

API still comes from `acta serve`; Vite proxies `/api` → `:8765`.

```bash
# Terminal 1 — API + built static (or API only after a prior build)
bash scripts/serve-ui.sh --no-open

# Terminal 2 — Vite on :5173
cd ui && npm ci && npm run dev
```

Then use the Vite URL printed in the terminal (typically http://127.0.0.1:5173/).

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

- Deploy / destroy / redeploy use `--runtime` / `CLAB_RUNTIME` when set;
  otherwise auto-detect on the lab host (podman if available, else docker).
  Web UI Deploy + Settings expose the same choice.
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

`.config` keys (CLI wins): `CLAB_NAME`, `CLAB_IMAGE`, `CLAB_HOST`, `CLAB_RUNTIME`
(`docker`|`podman`; when unset, deploy/destroy/redeploy auto-detect),
`CLAB_HOST_IMAGE`, `CLAB_FROM_ACT`, `CLAB_MGMT_*`, `CLAB_DNS`, `CLAB_NTP`,
`CLAB_DISABLEAAA`, `CVAAS_HOST`, `CVAAS_TOKEN`, …

cEOS is not on Docker Hub. Load an Arista archive on the lab host with Web UI
**Images → Upload & load**, or `docker load` / `podman load`. An optional
registry (Settings `CLAB_REGISTRY`) is only for copying that image to other
lab hosts. `CLAB_REGISTRY` must be `host[:port][/path]`; short names (including
namespaced ones like `acta/ceos:1`) are prefixed with it, while refs whose first
segment has a `.` or `:` (e.g. `other.io:5000/ceos:1`) are used as-is.

**Podman store vs `sudo containerlab`:** rootless and rootful podman have
separate image stores. If deploy runs `sudo -n containerlab` as a non-root user,
images must be in root's store. The Images page therefore uses `sudo -n podman`
for list/load/tag/push/pull when the runtime is podman, the lab-host user is
not root, and passwordless sudo works. If it does not, the page and job logs
show a `WARNING:` and the operation proceeds rootless; load manually with
`sudo podman load -i <archive>` on the host. The linux jumphost image is separate: `scripts/build-host-image.sh`
(default `CLAB_HOST_IMAGE=localhost/acta-host-multitool:v0.10.0-mcast0.2.3`).

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

Install commands for every dependency are centralized under [Install](#install).
Short platform reminders:

### macOS

- Use Homebrew for uv, Node, Graphviz, and Podman where possible.
- Containerlab labs need a **Podman machine**. `acta ssh` works via the runtime;
  raw `ssh admin@172.100…` usually does not without extra routing.

### Windows

- Install Python 3.15+ and uv (see Install). Prefer **WSL2** or a remote Linux
  lab host for containerlab (`CLAB_HOST` / Settings).
- If you want Graphviz PNGs, install Graphviz and put its `bin` on `PATH`.

### Linux

- Distro packages for Python 3.15+, Node 20+, Graphviz, Podman/Docker, and
  [containerlab](https://containerlab.dev/install/) on the lab host.

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

1. Clone; run `bash scripts/install-deps.sh` (or follow [Install](#install)
   step-by-step). Optional: `bash scripts/install-deps.sh --hooks`.
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
