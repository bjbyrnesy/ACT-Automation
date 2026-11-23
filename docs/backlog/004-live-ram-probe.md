# Live RAM probe for site-add messaging

**Status:** deferred  
**Origin:** `docs/superpowers/specs/2026-11-20-acta-extend-add-site-design.md`

## Problem

Site-add prints a **static** baseline→EVPN RAM range (~1.8× cEOS count ×
1.5–1.75). Lab hosts vary; a live sample from trogdor (or `--host`) would make
the “>24 cEOS confirm” threshold more honest.

## Proposal

- Optional probe: sum RSS of running cEOS containers (Podman/Docker), derive
  GiB/node, feed `ram_range_message`.
- Fall back to the static rule when no lab is running or probe fails.
- Keep messaging a **range**, not a single number.

## Acceptance

- [ ] Probe works local and remote (`CLAB_HOST`)
- [ ] Fallback when empty/unavailable
- [ ] Wired into `extend --add site` messaging
- [ ] Docs note the measurement assumptions (quiet lab, image version)
