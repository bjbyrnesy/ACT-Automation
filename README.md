# ACT + CVaaS Onboarding Helper 🤖

An automated **CVaaS onboarding tool** & **ACT lab creator** for EOS devices running in Arista Cloud Test (ACT). Point it at **your running lab** and every switch shows up in CVaaS Inventory ~1 minute later. *Code authored by Claude.*

## Why Does this exist? 🤷‍♂️

Using ACT with CVaaS can be painful for a few reasons: 

1. If you need to change a *single link* or add/remove a node, the entire lab must be **destroyed and recreated**. 
2. Automating a VM that has ZTP configuration & connectivity necessary to tie EOS devices to CVaaS must be re-deployed every time a topology change is made. Painful.

This script aims to solve those problems by assigning a **static MAC** & **serial** to every device (`generate.sh` script) and by automatically discovering, SSH-ing into and pasting the onboarding token into every EOS device to simplify new/existing devices showing up in CVaaS. 

## When should I use it? ⏱️

Do you need a **long-lived ACT environment** to demo or test? Do you need a **quick topology** to demo something live? Do you just want to **test** a specific EOS version quickly? Do you want to practice the **Campus Fabric** or **L3LS/EVPN Studios**?

> Then YES, this is for you!!  🫵

This is *not* a tool to build any possible iteration of a network topology in ACT. It has intentional limits that coorelate with the **Campus Fabric** & **L3LS Studios**. 

## Quickstart 🏎️
> [!NOTE]
> This has been built & tested on a Mac, if running on a PC, follow the steps below.

### Preview: acta create/extend (uv)

The Python CLI preview can create a topology with reserved growth capacity and
extend it later without moving existing link endpoints. The existing `.sh`
workflows below remain supported while the rest of the CLI is migrated.

```bash
uv sync --extra dev
uv run acta.py create
uv run acta.py extend topology-demo-2026-11-19.yml --add leaf
uv run acta.py extend topology-demo-2026-11-19.yml --add mleaf --pair 1
```

If Graphviz `dot` is available, create and extend also write or refresh the PNG
beside the topology YAML. Run `uv run acta.py extend --help` for all growth
options, including multi-site `--site` selection.

## MacOS Users 🍎
If you don't have Brew installed, check this URL https://brew.sh/. 

On your laptop:
- `jq`, `yq`. Install with:
  ```bash
  brew install jq yq
  ```
- (Optional) `graphviz` — if installed, `generate.sh` also emits a PNG
  diagram to upload with your topology file in ACT alongside the YAML:
  ```bash
  brew install graphviz
  ```

### PC Users 🪟

Install the following tools and set your terminal to Git Bash in order for this to work:

1. Install `graphviz` in Powershell and add it to your path
   1. `winget install -e --id Graphviz.Graphviz`
   2. `export PATH=$PATH:"/c/Program Files/Graphviz/bin"`
2. Install `jq`
   1. `winget install jqlang.jq`
3. Install `yq` (used by `act_topology.sh` to convert YAML → JSON for the ACT API)
   1. `winget install MikeFarah.yq`
4. Open VS Code, in the terminal panel, click the down arrow (v) next to the + (plus) icon in the top right.
5. Select **Git Bash** from the dropdown menu.
6. Once the new terminal loads continue below. 

### Create a new simple ACT Topology

1. Download or clone the repo to your laptop
2. Open a terminal and move to that directory
3. Run the `./generate.sh` script
4. Answer the prompts to build a simple topology you can use in ACT
5. Upload the generated topology with `./act_topology.sh <topology-file>`
6. Choose whether `act_topology.sh` should create and deploy the lab, or do it
   later in the ACT UI

```bash
./generate.sh
#   Serial prefix (e.g. bsmith): rclark
#   Hostname prefix [rclark]:
#   Number of datacenters/campuses (1-4) [1]:
#   Number of spines [2]:
#   Number of leaves [4]:
#   Pair leaves into MLAG pairs (y/n) [n]:
#   EOS version [4.35.4M]:
#   Continue? [y/N] y
#   Wrote topology-rclark-2026-09-15.yml
#   Wrote topology-rclark-2026-09-15.png
```

Upload the generated YAML to the ACT account associated with your API key:

```bash
./act_topology.sh topology-rclark-2026-09-15.yml
#   ACT tenant [ce]:
#   ACT API key: ****  (36 chars)
#   Topology name [topology-rclark-2026-09-15.yml]:
#   Uploading topology 'topology-rclark-2026-09-15.yml' to ce.act.arista.com...
#   topology creation: completed.
#   Created ACT topology 'topology-rclark-2026-09-15.yml'.
#   Create and deploy a lab from this topology? [y/N] y
#   Lab name [topology-rclark-2026-09-15-lab]:
#   lab creation: completed.
#   lab deployment: completed.
#   Deployed lab 'topology-rclark-2026-09-15-lab'.
```

### Build a containerlab lab

The containerlab workflow uses the same topology choices and links as the ACT
generator. First run `./generate.sh`, then convert its generated ACT YAML:

```bash
./generate.sh
./clab.py generate topology-rclark-2026-09-15.yml --name rclark-lab --image ceos:4.35.4M
# Optional: choose a different management subnet when generating:
# ./clab.py generate topology-rclark-2026-09-15.yml --name rclark-lab --image ceos:4.35.4M --mgmt-subnet 10.40.0.0/23
./clab.py deploy rclark-lab.clab.yml
./clab.py onboard rclark-lab.clab.yml --endpoint apiserver.arista.io
```

Run the last two commands on the Linux lab host, or add `--host user@lab-host`
to run them over SSH. The initiating machine needs Python 3 and Mike Farah
`yq` v4. The Linux host needs containerlab, Docker or Podman, and the specified
cEOS image already loaded in the selected runtime or accessible to it. Remote access uses your SSH configuration
and noninteractive authentication; the host must allow passwordless `sudo` for
containerlab and access to the runtime or passwordless `sudo` for it.
Use `--runtime docker` (the deployment default) or `--runtime podman` for
deployment. Onboarding automatically finds the lab in accessible Docker and
rootless or rootful Podman stores; use `--runtime` to restrict the search.
Deploy the topology before onboarding it.
Containerlab's default management network must have DNS and outbound access to
the selected CVaaS endpoint on TCP 443.
Newly generated cEOS nodes use the `MGMT` management VRF; onboarding directs
TerminAttr through that VRF. Existing topology files must be regenerated to
include the setting. Containerlab runs a post-deployment EOS command to configure
ensure `vrf instance MGMT`, then save DNS/NTP as `ip name-server vrf MGMT …`
and `ntp server vrf MGMT …`. Defaults come from `CLAB_DNS` / `CLAB_NTP` in
`.config`, or `--name-servers` / `--ntp-servers` on the CLI. Onboard repeats
those VRF-scoped DNS/NTP lines when the node has `CLAB_MGMT_VRF`. Regenerate
and redeploy existing labs to apply generate-time changes.

Generated topologies include a `<topology>.annotations.json` file for the
Containerlab VS Code Topology Viewer, with explicit `core` and site groups.
Member leaves are centered under their connected leaf pairs. Deployment copies
this file to the lab host alongside the topology. Existing local and host-side
annotations are preserved; to regenerate a layout, first back up and move aside
the existing annotation files on both the generating machine and lab host.

Container names are `clab-<lab-name>-<node>`. Keep `--name` short. A leading
`clab-` on ACT hostnames is stripped during conversion so you get
`clab-campus-A-mleaf1` instead of `clab-2site-campus-clab-A-mleaf1`.
When ACT nodes already include the lab prefix (`blz-B-leaf2`), the container
node key is shortened (`B-leaf2`) but EOS/CVaaS hostname keeps the full ACT
name (`blz-B-leaf2`) via generate exec and onboard.

`clab.py` reads optional defaults from `.config` in the current directory (same
file as the shell scripts). CLI flags override. Useful keys: `CLAB_NAME`,
`CLAB_IMAGE` (or `EOS_VERSION` → `ceos:$EOS_VERSION`), `CLAB_HOST`,
`CLAB_MGMT_SUBNET`, `CLAB_MGMT_NETWORK`, `CLAB_MGMT_GATEWAY`,
`CLAB_MGMT_RANGE`, `CLAB_MGMT_BRIDGE`, `CLAB_MGMT_MTU`, `CLAB_DNS` (space-separated IPs),
`CLAB_NTP` (space-separated IPs), `CLAB_DISABLEAAA` (`y`/`n` — adds
`-disableaaa` to the initial TerminAttr onboarding exec), `CVAAS_HOST`,
`CVAAS_TOKEN`. Containerlab onboarding uses a valid cached enrollment token and
prompts if it is missing, expired, or invalid. A newly entered token is used
for that run and is not written to `.config`.

Generated labs use `172.100.100.0/22` on containerlab's default management
network unless `--mgmt-subnet` is provided. Nodes receive sequential static
management addresses in topology order, skipping the gateway. Set an optional
allocation range, gateway, bridge, and MTU using the arguments below; for example:

```bash
./clab.py generate topology-rclark-2026-09-15.yml --name dc-demo --image ceos:4.35.3F \
  --mgmt-subnet 172.16.16.0/23 --mgmt-gateway 172.16.17.254 \
  --mgmt-range 172.16.17.0/24 --mgmt-bridge mgmt-br0 --mgmt-mtu 1500
```

Generated YAML uses `et` links with `INTFTYPE: et`. Beside it, the generator
creates `configs/base-config.eos` and per-node `configs/SN/*.eos` identity files;
keep them with the topology. The base configuration follows containerlab's cEOS
template and uses its default `admin` / `admin` login; change it before deploying
to a shared network. Deployment copies the required files to the lab host and
refuses to overwrite conflicting files. Existing local startup configuration and
serial files are preserved, and conflicting serial identities stop generation.
Use separate output directories for labs with differently configured nodes.

Static addresses may change when topology node order changes. Reserve the chosen
addresses on the management network and avoid overlap with other labs. If the
subnet already belongs to another Docker network, select that network
with `--mgmt-network` when generating. For an existing generated file, select
it for deployment without editing the file:

```bash
./clab.py deploy --host user@lab-host --mgmt-network mgmt rclark-lab.clab.yml
```

The named network must have the configured subnet. Specify its actual gateway
with `--mgmt-gateway` if it differs from the subnet’s first usable address, which
the generator reserves by default. This option changes the copy
of the topology stored on the host, not the local file; use it on each deployment.
Containerlab's other management network requirements still apply.

If SSH reports `Permission denied` reading `/etc/ssh/ssh_config.d/clab-<lab>.conf`,
check the file and its parent directories with `namei -l` on the lab host. If
the lab's system SSH config is not readable, an administrator can make that
config readable (replace the lab name):

```bash
sudo chmod 644 /etc/ssh/ssh_config.d/clab-rclark-lab.conf
```

This fixes an existing file; it does not change permissions on SSH private keys.

Deployment saves the topology on the host at
`~/.act-automation/clab/<lab-name>/topology.clab.yml`. To destroy the lab, run
`sudo containerlab destroy --runtime docker -t ~/.act-automation/clab/<lab-name>/topology.clab.yml` (replace `docker` with `podman` if selected)
on that host. Destroying the lab is separate from decommissioning its CVaaS
devices. Re-run conversion with the same source identities and lab name to
retain the same intended cEOS serials; changing the ACT serial prefix changes
them. The generated serials are separate from ACT serials. The workflow sets
`CEOS_SERIAL_NUMBER` and binds a per-node `ceos-config` with a deterministic
serial and system MAC. Verify the identity before and after redeployment on
your host before relying on CVaaS identity continuity; older generated labs may
have used a different system MAC. Avoid running multiple labs with the same source
serials simultaneously.

Onboarding supports generated containerlab files and prompts for a token if no
valid cached token is available. It submits the TerminAttr configuration to each cEOS container and reports
individual failures; check CVaaS Inventory to confirm registration. Retry after
nodes finish booting if they are not yet ready. As with the ACT workflow, a
copy of the enrollment token is placed on each device for TerminAttr.

#### Containerlab command arguments

Use `./clab.py --help` or `./clab.py <command> --help` for help.

**Generate:** `./clab.py generate SOURCE --name NAME --image IMAGE [options]`

| Argument | Description |
| --- | --- |
| `SOURCE` | Required ACT topology YAML produced by `generate.sh`. |
| `--name NAME` | Required containerlab name: lowercase letters, numbers, and hyphens, starting with a letter or number; maximum 63 characters. |
| `--image IMAGE` | Required cEOS image name and tag available on the lab host. |
| `--output FILE` | Output path; defaults to `<name>.clab.yml` in the current directory. |
| `--mgmt-subnet CIDR` | IPv4 management subnet; defaults to `172.100.100.0/22`. |
| `--mgmt-gateway IP` | Gateway within the management subnet; defaults to containerlab’s gateway selection. |
| `--mgmt-range CIDR` | Subnet used to assign node addresses; must be within the management subnet. |
| `--mgmt-bridge NAME` | Management bridge interface name. |
| `--mgmt-mtu NUMBER` | Management network MTU. |
| `--mgmt-network NAME` | Docker management network name; defaults to containerlab's `clab` network. |
| `--name-servers IP [IP ...]` | IPv4 DNS servers in `MGMT`; default `CLAB_DNS` or `8.8.8.8 1.1.1.1`. |
| `--ntp-servers IP [IP ...]` | IPv4 NTP servers in `MGMT`; default `CLAB_NTP` (omit if unset). |
| `-h`, `--help` | Show command help. |

**Deploy:** `./clab.py deploy TOPOLOGY [options]`

| Argument | Description |
| --- | --- |
| `TOPOLOGY` | Required generated containerlab topology file. |
| `--host HOST` | SSH alias or `user@host` for the Linux lab host; omit to deploy locally. |
| `--mgmt-network NAME` | Override the management network for this deployment; the local topology file is not changed. |
| `--runtime docker\|podman` | Container runtime for deployment; defaults to Docker. |
| `-h`, `--help` | Show command help. |

**Onboard:** `./clab.py onboard TOPOLOGY [options]`

| Argument | Description |
| --- | --- |
| `TOPOLOGY` | Required generated containerlab topology file. |
| `--host HOST` | SSH alias or `user@host` for the Linux lab host; omit to onboard local containers. |
| `--endpoint HOSTNAME` | CVaaS API hostname, such as `apiserver.arista.io`; prompts if omitted. |
| `--runtime docker\|podman` | Restrict runtime discovery; defaults to automatic detection. |
| `--disableaaa` / `--no-disableaaa` | Pass `-disableaaa` on the initial TerminAttr exec; default from `CLAB_DISABLEAAA`. |
| `-h`, `--help` | Show command help. |

For example, to onboard a lab on a remote host:

```bash
./clab.py onboard rclark-lab.clab.yml --host user@lab-host --endpoint apiserver.arista.io
```

### Once you created a lab (or you have one running) already

1. Collect an ACT API key from the ACT UI
   * Click your **Username** in the top right > **My Profile** > **API Key**
2. Collect an onboarding token from CVaaS
   * **Devices** > **Device Registration** > **Generate a Token**
3. Run the `./onboard.sh` script locally in a terminal
4. Follow the prompts 

```bash
./onboard.sh
#   ACT tenant [ce]:
#   ACT username (e.g. firstname.lastname): ryan.clark
#   ACT API key: ****  (36 chars)
#   CVaaS enrollment token: ****  (944 chars)
#   ...
#   Lab: rclark-campus-lab
#   EOS password: from local act-campus-topo-no-cvp_rclark.yml
#   Will paste TerminAttr config to 55 vEOS device(s):
#     ...
#   Continue? [y/N] y
#   Pre-flight: checking CVaaS reachability from each device...
#     ...
#   Pasting TerminAttr snippet to each switch...
#     ...
```

`onboard.sh` reads the EOS password out of the topology's `veos:` block
(checking your local file first, then the ACT API, then falling back to
`cvp123!`).

## How this works ⚙️

Three scripts, run in order:

| Step | Script | What it does |
| ---- | ------ | ------------ |
| 1 *(optional)* | `./generate.sh` | Interactively generates a topology YAML with **pinned `serial_number` + `system_mac_address`** on every node. Skip this step if you already have a topology — `onboard.sh` works with any vEOS topology, not just generated ones.  |
| 2 | `./act_topology.sh` | Uploads a generated topology to ACT via the REST API. Optionally creates and deploys a lab from it. |
| 3 | `./onboard.sh` | Finds your Running lab via the ACT API and SSH-pastes the TerminAttr onboarding snippet to every vEOS switch. Auto-detects the EOS password from the topology's `veos:` block, so it works with topologies you authored elsewhere. |

When prompted, choose whether to create and deploy the lab immediately. If you
decline, you can deploy the generated topology later in the ACT UI.

No DHCP server. No ZTP. No bootstrap.py. No dedicated ztp-server node.

## Files 🗂️

| File | Purpose |
| ---- | ------- |
| `onboard.sh`  | Lists your Running labs and onboards every vEOS switch to CVaaS. |
| `generate.sh` | *(optional)* Interactive topology generator with pinned serials + MACs. Multi-site asks fabric mode: `l3ls` (border leaves) or `l2` (backbone on spines). |
| `act_topology.sh` | Uploads a topology YAML to ACT and optionally creates + deploys a lab. Shares cached ACT credentials with `onboard.sh`. |
| `clab.py` | Converts generated ACT topologies to containerlab and deploys or onboards cEOS labs locally or over SSH. |
| `_common.sh`  | Shared helpers (prompt/cache/tool-check). Sourced by the scripts; don't run directly. |
| `topology-<prefix>-<YYYY-MM-DD>.yml` | Topology produced by `generate.sh`. Filename must be unique across the ACT tenant — `generate.sh` enforces the convention. |
| `.config`     | Auto-generated cache of your answers (ACT/CVaaS + optional `CLAB_*`). **gitignored.** Delete to re-prompt. |


## Redeploying

When you want to change the topology:

1. Edit the topology — for `generate.sh`-produced ones, re-run it and
   change spine/leaf counts as needed (the new file has today's date in
   its name, so it won't overwrite your previous labs). For
   hand-authored topologies, edit in place.
2. Run `./act_topology.sh <topology-file>` and accept the deployment prompt, or
   deploy it later in the ACT UI.
3. Run `./onboard.sh` and pick the new lab from the list.

If the topology has pinned `serial_number` + `system_mac_address` on
every node (either via `generate.sh` or because you added them
manually), CVaaS will recognize the devices as the same ones from
before — state / dashboards / studios / labels carry over.

## Cleaning up CVaaS 🧹
Be respectul to others and clean up any orphaned VM's you have built and aim to retire. CVaaS actually has a nice bulk decommission feature. 

1. Click **Devices** > **Device Registration**
2. Click the **Decommission and Replace Devices** tab at the top
3. Click the **Hostname** chip and type in the hostname string you used
4. Click select all and click the **Decommission** button
   
![alt text](<cvaas-cleanup.gif>)

## Sharing this with someone else 🎁

1. Clone the repo.
2. Run `./onboard.sh` against any Running lab — they enter their own ACT
   and CVaaS creds when prompted. Works on labs they authored anywhere.
3. *(Optional)* Run `./generate.sh` if they want pinned-identity
   topologies of their own. It forces them to enter their own serial
   prefix (the `(e.g. bsmith)` hint means it's never cached or shared).

No edits to either script needed.

## Why TerminAttr token-secure auth instead of the bootstrap.py flow

CVaaS supports two onboarding paths:

- **`bootstrap.py`**: an Arista-provided Python script that does a
  multi-step enrollment dance (token → device cert exchange → device-specific
  bootstrap → registration). Requires the device to be reachable to a
  bootstrap-script host during ZTP.
- **TerminAttr `token-secure` auth**: TerminAttr does the same enrollment
  internally on first connect, using just the enrollment token in a file.
  No ZTP, no DHCP, no HTTP server, no per-device bootstrap host — you just
  give the daemon a token and a CVaaS endpoint and it figures it out.

For an ACT lab where you have SSH access to every device the moment it
boots, the second path is dramatically simpler.

## Note on Upgrading

Without the setting below, you cannot upgrade EOS nodes in ACT through CloudVision. This setting is baked into every yaml template to allow you to demo upgrades via. CVaaS.

```
settings:
   legacy_eos_versioning: false
```

## v2 / TODO

- Topology diagram upload via the ACT REST API (the `diagram_path` field
  expects a server-side path; investigating with the ACT team).
- Auto-generate the topology file from AVD configs (see
  [emilarista/act_topgen](https://github.com/emilarista/act_topgen)).
- Parallelize the auto-paste ssh loop (currently serial — fine for ~6
  switches, slow for larger topologies).
