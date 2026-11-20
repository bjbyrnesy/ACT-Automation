# ACT / containerlab equal CLI namespaces

**Date:** 2026-11-19  
**Status:** approved (design); pending implementation  
**Branch:** `feature/topology-spare-width-extend`

## Problem

`acta.py onboard` targets ACT vEOS labs, while containerlab onboarding is
`acta.py clab onboard`. That asymmetry caused users with a running clab lab to
invoke the wrong command and hit “No Running labs found.”

## Decision

Hard-cut the top-level CLI into two equal platform namespaces. No deprecation
aliases for the old top-level verbs.

```text
acta.py act  {create,extend,upload,onboard}
acta.py clab {generate,deploy,onboard}
```

Top-level `create`, `extend`, `upload`, and `onboard` are removed.

## Command map

| New | Replaces | Notes |
|-----|----------|--------|
| `acta.py act create` | `acta.py create` | Keep `--for act\|clab\|both`, `--name`, `--image` |
| `acta.py act extend` | `acta.py extend` | Same flags (`--add`, `--site`, `--pair`, `--count`, `--out`, `--new`) |
| `acta.py act upload` | `acta.py upload` | Same flags |
| `acta.py act onboard` | `acta.py onboard` | ACT API + SSH TerminAttr; no topology positional |
| `acta.py clab generate\|deploy\|onboard` | unchanged | Already nested |

## Behavior

- Handlers stay in existing modules (`acta/create.py`, `acta/extend.py`,
  `acta/upload.py`, `acta/onboard_act.py`, `acta/clab/*`). This change is
  argparse nesting and user-facing strings only.
- `act create --for clab|both` remains valid (create already emits clab labs).
- Next-step / hint strings that print bare `acta.py create|extend|upload|onboard`
  must be updated to the `act …` forms (and clab hints stay under `clab …`).

## Out of scope

- Deprecation shims for old top-level commands
- Renaming Python packages or moving `onboard_act.py`
- Changing ACT/CVaaS/containerlab runtime behavior beyond CLI paths

## Acceptance

- `uv run python acta.py --help` lists only `act` and `clab` (plus `-h`)
- `uv run python acta.py act --help` lists create, extend, upload, onboard
- `uv run python acta.py act onboard --help` and `… clab onboard --help` both work
- `uv run python acta.py onboard` fails as unknown command
- Help / create / upload / README strings use the new paths
- Existing unit tests updated; suite green
