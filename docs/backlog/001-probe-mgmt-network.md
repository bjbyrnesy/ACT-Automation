# `acta probe network` / mgmt network discovery

**Status:** deferred  
**Origin:** deploy/show mgmt-bridge vs network confusion (pre–PR #11/#9)

## Problem

Operators confuse Docker/Podman **network name** (`--mgmt-network`) with a
**CIDR** (`--mgmt-subnet`) or Linux **bridge** (`--mgmt-bridge`). False
“mgmt network already exists” detection and opaque `source` / NAT behavior make
lab bring-up painful.

## Proposal

Add a read-only helper, e.g. `acta probe network` (or `acta clab probe`), that:

- Lists runtime networks (Podman/Docker) with names, drivers, subnets, and
  whether a clab lab is attached.
- Distinguishes bridge device name vs network name vs subnet.
- Prints a short hint for the correct `--mgmt-*` flags (no writes).

## Acceptance

- [ ] Non-interactive output suitable for scripts and humans
- [ ] Works for local and `--host` remote clab hosts
- [ ] Docs in README next to deploy mgmt flags
- [ ] No topology mutation
