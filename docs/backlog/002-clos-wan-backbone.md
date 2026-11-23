# Clos / mesh WAN backbone beyond hub

**Status:** deferred  
**Origin:** `docs/superpowers/specs/2026-11-20-acta-extend-add-site-design.md`

## Problem

Site-extend ships a **hub** backbone (`backbone_mode=hub`, shared `bb1..N`).
Real multi-site labs often want per-site border/WAN pairs into a Clos or mesh
instead of a single hub.

## Proposal

- Extend capacity header with `backbone_mode=clos` (or similar).
- Emit per-site WAN edge + Clos spines (or mesh) without renumbering existing
  hub labs unless explicitly migrated.
- Keep hub path as the default; Clos is opt-in at create / promote.

## Acceptance

- [ ] Design note / plan before coding
- [ ] Create + extend emit Clos topology
- [ ] PortPlan reservations so adds do not slide endpoints
- [ ] Tests for hub→Clos non-goal (no silent rewrite) and Clos create smoke
