# Fabric mode (L2 campus vs L3LS) Implementation Plan

> **For agentic workers:** implement task-by-task. Steps use checkbox syntax.

**Goal:** Multi-site topologies choose fabric mode. `l2` = no border leaves, backbone dual-homes to spines. `l3ls` = keep current border↔spine↔bb.

**Files:** `generate.sh`, `_common.sh`, `README.md`, this plan.

## Tasks

- [x] Prompt + cache `FABRIC_MODE` when `DC_COUNT > 1` (`l2` / `l3ls`, default `l3ls`)
- [x] Detect mode when reloading an existing topology (borders ⇒ `l3ls`, else `l2`)
- [x] Multi-DC emit: skip borders + border links in `l2`; `spine`↔`bb` instead
- [x] Spine MLAG ports stay `LEAF_COUNT+3/+4` (bb uses `+1/+2` in `l2`)
- [x] DOT diagram matches emit
- [x] Confirm banner + README mention mode
- [ ] Commit with prior `clab.py` work on branch `clab`
