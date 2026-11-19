from pathlib import Path

import pytest

from acta import cli
from acta.capacity import Capacity
from acta.create import FabricSpec, emit_act_yaml


def _write(tmp_path: Path, dc_count: int = 1) -> Path:
    spec = FabricSpec(
        hostname_prefix="demo",
        serial_prefix="demo",
        eos_version="4.35.4M",
        capacity=Capacity("l3ls" if dc_count > 1 else None, 4, 8, 2, 2, 2),
        mlag_pairs=True,
        spine_mlag=False,
        member_leaf_pairs=[],
        member_leaves_per_pair=0,
        dc_count=dc_count,
    )
    path = tmp_path / "topology-demo.yml"
    path.write_text(emit_act_yaml(spec))
    return path


def _interactive(monkeypatch: pytest.MonkeyPatch, answers: list[str]) -> list[str]:
    asked: list[str] = []
    responses = iter(answers)

    def fake_prompt(label: str, default: str | None = None) -> str:
        asked.append(label)
        return next(responses)

    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(cli, "prompt_value", fake_prompt)
    return asked


def test_extend_add_is_optional_in_parser():
    assert cli.build_parser().parse_args(["extend", "t.yml"]).add is None


def test_extend_without_add_errors_when_not_a_tty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False)
    assert cli.main(["extend", str(_write(tmp_path))]) == 2
    assert "--add is required" in capsys.readouterr().err


def test_extend_prompts_for_add_when_tty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    path = _write(tmp_path)
    asked = _interactive(monkeypatch, ["bogus", "LEAF"])

    assert cli.main(["extend", str(path)]) == 0

    assert len(asked) == 2 and asked[0].startswith("What to add")
    assert "demo-leaf3:" in path.read_text()
    assert "Enter one of" in capsys.readouterr().err


def test_multi_dc_extend_prompts_for_site_when_tty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    path = _write(tmp_path, dc_count=2)
    asked = _interactive(monkeypatch, ["b"])

    assert cli.main(["extend", str(path), "--add", "leaf"]) == 0

    assert asked == ["Site (A/B)"]
    assert "demo-B-leaf3:" in path.read_text()
    assert "demo-A-leaf3:" not in path.read_text()


def test_multi_dc_extend_without_site_errors_when_not_a_tty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False)
    path = _write(tmp_path, dc_count=2)
    assert cli.main(["extend", str(path), "--add", "leaf"]) == 2
    assert "requires --site" in capsys.readouterr().err


def test_single_dc_extend_does_not_prompt_for_site(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    asked = _interactive(monkeypatch, [])
    assert cli.main(["extend", str(_write(tmp_path)), "--add", "leaf"]) == 0
    assert asked == []


def test_extend_output_is_clean_and_lists_warnings_and_free_slots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False)
    path = _write(tmp_path)

    assert cli.main(["extend", str(path), "--add", "leaf", "--count", "7"]) == 0

    captured = capsys.readouterr()
    assert f"Wrote {path}" in captured.out
    assert "Added: demo-leaf3," in captured.out
    assert "Remaining planned slots:" in captured.out
    assert "Warning: leaf9 exceeds planned soft capacity" in captured.err
    assert ".py:" not in captured.err and "UserWarning" not in captured.err


def test_extend_out_refuses_existing_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False)
    path = _write(tmp_path)
    target = tmp_path / "taken.yml"
    target.write_text("original\n")
    before = path.read_text()

    code = cli.main(["extend", str(path), "--add", "leaf", "--out", str(target)])

    assert code == 2
    assert "already exists" in capsys.readouterr().err
    assert target.read_text() == "original\n"
    assert path.read_text() == before


def test_extend_new_prints_dated_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False)
    path = _write(tmp_path)

    assert cli.main(["extend", str(path), "--add", "leaf", "--new"]) == 0

    out = capsys.readouterr().out
    assert f"Wrote {tmp_path / 'topology-demo-'}" in out
