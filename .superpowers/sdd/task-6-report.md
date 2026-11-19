Status: Complete — interactive prompts, secure config cache, capacity banner, topology writing, and CLI create wire-up implemented.
Commits: 47d0ca0 feat(acta): interactive create prompts and capacity banner
Tests: 64 passed; banner TDD red/green confirmed; create help, config mode/round-trip, and interactive write smoke passed.
Checks: Black and Ruff pass for acta plus the changed test; git diff check passes.
Concerns: Repository-wide Black/Ruff still report pre-existing drift in clab.py and tests/test_clab.py; no Task 6 files are affected.
Report: /Users/corey/code/ACT-Automation/.superpowers/sdd/task-6-report.md

Review fix evidence (2026-11-19):
- Capacity prompts clamp cached defaults to their valid range and re-prompt entries outside it.
- Maximum spine/leaf counts cannot be lower than current counts or exceed the 16-port cap.
- Member leaves per selected pair cannot exceed the chosen maximum.
- `save_config` mode 0o600 and MAX_SPINES/MAX_LEAVES/MAX_MLEAFS_PER_PAIR round-trip are covered with `tmp_path`.
- `uv run pytest tests/test_create.py tests/test_config.py -v`: 9 passed.
- Black and Ruff passed for `acta/create.py`, `tests/test_create.py`, and `tests/test_config.py`.

Reserved port-budget fix evidence (2026-11-19):
- Shared create-capacity validation reserves leaf spine-facing, MLAG peer, and
  member-leaf slots within Ethernet16, plus spine MLAG slots for two-spine plans.
- Interactive create retries all capacity limits when the shared validator rejects
  their reserved port budget, preventing emit-only failures.
- `max_spines=16` with `max_mleafs_per_pair=1` is covered as a rejected plan.
- `uv run pytest tests/test_capacity.py tests/test_create.py tests/test_portplan.py -q`:
  18 passed.
- Black and Ruff passed for all changed Python files.
