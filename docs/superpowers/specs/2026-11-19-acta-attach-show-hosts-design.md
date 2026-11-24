# Attach hosts + show topology

**Date:** 2026-11-19  
**Status:** implemented

## Summary

After the switch fabric exists, operators attach jumphosts with top-level
`acta.py attach` and inspect MLAG pairs with `acta.py show`. ACT emits
`node_type: generic`; containerlab maps the same hostname to `kind: linux`
(pinned `ghcr.io/srl-labs/network-multitool`) with `exec: [lldpd]` so LLDP is
on by default.

## Orthogonal axes

| Axis | Values | Controls |
|------|--------|----------|
| Use case | `datacenter` \| `campus` | Host attach allow-list |
| Fabric mode | `l3ls` \| `l2ls` (legacy `l2` normalized) | Topology shape |

**Attach policy:** DC → leaf/mleaf/border; Campus → those + spine (intentional
for small L2LS deployments that burn spine access ports); never bb.

## Commands

```text
acta.py show TOPOLOGY
acta.py attach host NAME TOPOLOGY --to SWITCH[:EthernetN]
acta.py attach host NAME TOPOLOGY --mlag-pair N --et K
acta.py attach host NAME TOPOLOGY --mlag-pair N --single-homed --mlag-side a
acta.py attach host NAME TOPOLOGY --mleaf N
acta.py detach host NAME TOPOLOGY
```

`--mlag-pair` defaults to dual-homed (both leaves). `--single-homed` plus
optional `--mlag-side a|b` attaches to one leaf of the pair.

`show` numbers MLAG pairs (`--mlag-pair`) and member-leaves (`--mleaf`) in
the same discovery order attach uses.

Platform (ACT vs clab) is inferred from the topology file. Attaching to ACT
YAML syncs a sibling `*.clab.yml` when present.
