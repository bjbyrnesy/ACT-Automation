# Leaf-pair EVPN AA multi-homing

**Status:** deferred  
**Origin:** `docs/superpowers/specs/2026-11-20-acta-extend-add-site-design.md`

## Problem

PR #14 supports `mlag-peer` vs `evpn-aa` for **borders** and **backbone** only.
Leaf MLAG pairs still always get peer links. Operators who run ESI/AA MH on
leaf pairs must shut peers by hand after emit.

## Proposal

- Optional `leaf_redundancy=mlag-peer|evpn-aa` (default `mlag-peer`).
- When `evpn-aa`, omit leaf peer links for pairs sized N≥2; keep port
  reservations stable.
- Align create prompts and extend site fabric with that flag.

## Acceptance

- [ ] Capacity header field + create/extend prompts
- [ ] No leaf peer links when `evpn-aa`
- [ ] Existing mlag-peer topologies unchanged by default
- [ ] Tests for emit and extend
