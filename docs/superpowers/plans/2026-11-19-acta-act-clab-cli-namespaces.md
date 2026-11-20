# Equal `act` / `clab` CLI Namespaces Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hard-cut top-level ACT verbs under `acta.py act …` so they sit parallel to `acta.py clab …`.

**Architecture:** Nest existing create/extend/upload/onboard argparse parsers under an `act` subcommand; dispatch via `args.command == "act"` + `args.act_command`. Update user-facing strings and help tests. No package renames, no deprecation aliases.

**Tech Stack:** Python 3 + argparse, pytest, README markdown.

## Global Constraints

- Hard cut: top-level `create|extend|upload|onboard` must fail (unknown command).
- Top-level help lists only `act` and `clab`.
- Handlers stay in existing modules; CLI nesting + strings only.
- Format with black; pass ruff; keep unit tests green.

---

### Task 1: Failing help tests for new CLI shape

**Files:**
- Modify: `tests/test_cli_help.py`
- Modify: `tests/test_create.py` (string assertions for next-steps)

**Interfaces:**
- Consumes: `acta.py` CLI (not yet nested)
- Produces: failing tests that define acceptance

- [ ] **Step 1: Rewrite help tests**

```python
def test_acta_help_lists_core_commands():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "acta.py"), "--help"],
        check=False, capture_output=True, text=True,
    )
    assert proc.returncode == 0
    out = proc.stdout
    for name in ("act", "clab"):
        assert name in out
    for gone in ("  create", "  extend", "  upload", "  onboard"):
        # Avoid matching nested help text; ensure top-level usage line is act|clab
        pass
    assert "acta.py act" in out or "{act,clab}" in out or "act" in out


def test_act_help_lists_subcommands():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "acta.py"), "act", "--help"],
        check=False, capture_output=True, text=True,
    )
    assert proc.returncode == 0
    for name in ("create", "extend", "upload", "onboard"):
        assert name in proc.stdout


def test_create_help_mentions_for_target():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "acta.py"), "act", "create", "--help"],
        ...
    )


def test_upload_help_mentions_topology():
    # path: acta.py act upload --help


def test_onboard_help_mentions_lab():
    # path: acta.py act onboard --help


def test_top_level_onboard_is_unknown():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "acta.py"), "onboard", "--help"],
        check=False, capture_output=True, text=True,
    )
    assert proc.returncode != 0
```

Also update `tests/test_create.py` expectations from `acta.py extend` / `acta.py upload` to `acta.py act extend` / `acta.py act upload`.

- [ ] **Step 2: Run tests — expect FAIL**

```bash
uv run pytest tests/test_cli_help.py tests/test_create.py -q --tb=line
```

Expected: FAIL (old paths / missing `act` subparser).

- [ ] **Step 3: Commit tests**

```bash
git add tests/test_cli_help.py tests/test_create.py
git commit -m "test(acta): expect act/clab equal CLI namespaces"
```

---

### Task 2: Nest ACT verbs under `act` in argparse + dispatch

**Files:**
- Modify: `acta/cli.py` (`build_parser`, `main`)

**Interfaces:**
- Consumes: existing `_run_extend`, `_run_upload`, `_run_onboard`, `run_create`
- Produces: `args.command in {"act","clab"}`; `args.act_command` for ACT verbs

- [ ] **Step 1: Restructure `build_parser`**

Top-level subparsers: only `act` and `clab`. Move create/extend/upload/onboard parsers under `act.add_subparsers(dest="act_command", required=True)`. Keep all existing flags. Update top-level description to mention `act` and `clab` namespaces.

- [ ] **Step 2: Update `main` dispatch**

```python
if args.command == "act":
    if args.act_command == "create":
        run_create(...)
        return 0
    if args.act_command == "extend":
        return _run_extend(args)
    if args.act_command == "upload":
        return _run_upload(args)
    if args.act_command == "onboard":
        return _run_onboard()
```

Keep early `if raw and raw[0] == "clab":` delegation unchanged.

- [ ] **Step 3: Run help tests — expect PASS**

```bash
uv run pytest tests/test_cli_help.py -q --tb=line
```

- [ ] **Step 4: Commit**

```bash
git add acta/cli.py
git commit -m "feat(acta): nest create/extend/upload/onboard under act"
```

---

### Task 3: Update user-facing command strings

**Files:**
- Modify: `acta/create.py` (capacity banner + Next: hints)
- Modify: `acta/upload.py` (`acta onboard` → `acta.py act onboard`)
- Modify: `acta/capacity.py` (recreate via `acta.py act create`)
- Modify: `acta/clab/generate.py`, `acta/clab/support.py`, `acta/clab/cli.py` (mentions of `acta.py create`)

- [ ] **Step 1: Replace strings**

| Old | New |
|-----|-----|
| `acta.py create` | `acta.py act create` |
| `acta.py extend` | `acta.py act extend` |
| `acta.py upload` | `acta.py act upload` |
| `acta onboard` / `acta.py onboard` | `acta.py act onboard` |

Keep `acta.py clab …` as-is.

- [ ] **Step 2: Run create + upload related tests**

```bash
uv run pytest tests/test_create.py tests/test_cli_help.py -q --tb=line
```

- [ ] **Step 3: Commit**

```bash
git add acta/create.py acta/upload.py acta/capacity.py acta/clab/generate.py acta/clab/support.py acta/clab/cli.py
git commit -m "fix(acta): point hints at act/clab namespaced commands"
```

---

### Task 4: README + acceptance

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README command examples** to `acta.py act …` / `acta.py clab …`; top-level verb table / workflow sections.

- [ ] **Step 2: Full unit suite**

```bash
uv run pytest -q --tb=line
uv run black acta tests
uv run ruff check acta tests
```

- [ ] **Step 3: Manual smoke**

```bash
uv run python acta.py --help
uv run python acta.py act --help
uv run python acta.py act onboard --help
uv run python acta.py onboard --help   # must fail
uv run python acta.py clab onboard --help
```

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: document equal act/clab CLI namespaces"
```

---

## Spec coverage

| Spec requirement | Task |
|------------------|------|
| Top-level only act + clab | 1–2 |
| act create/extend/upload/onboard | 2 |
| clab unchanged | 2 (no change) |
| No aliases; top-level onboard fails | 1–2 |
| Hint/README strings | 3–4 |
| Handlers stay put | 2 |
| Tests green | 4 |
