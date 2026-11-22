"""Tests for the local labs file facade."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from acta.web.errors import WebError
from acta.web.labs import (
    delete_topology,
    get_lab,
    lab_id_from_filename,
    list_labs,
    list_topologies,
    read_topology,
    write_topology,
)


def test_list_topologies_filters_yaml_and_marks_clab_siblings(tmp_path: Path) -> None:
    act = tmp_path / "fabric.yml"
    act.write_text("nodes:\n  leaf1: {}\n", encoding="utf-8")
    (tmp_path / "fabric.clab.yaml").write_text("nodes: {}\n", encoding="utf-8")
    (tmp_path / "other.yaml").write_text("nodes: {}\n", encoding="utf-8")
    (tmp_path / "notes.yml").write_text("title: notes\n", encoding="utf-8")
    (tmp_path / "ignored.txt").write_text("nodes: {}\n", encoding="utf-8")

    listed = list_topologies(tmp_path)

    assert [entry["name"] for entry in listed] == ["fabric.yml", "other.yaml"]
    assert listed[0] == {
        "name": "fabric.yml",
        "path": str(act),
        "lab_id": "fabric",
        "mtime": act.stat().st_mtime,
        "has_clab_sibling": True,
    }
    assert listed[1]["has_clab_sibling"] is False


def test_write_then_read_uses_basename_and_preserves_text(tmp_path: Path) -> None:
    yaml_text = "nodes:\n  leaf1: {}\n"

    path = write_topology(tmp_path, yaml_text, stem="fabric")

    assert path.name == f"fabric-{date.today().isoformat()}.yml"
    assert path.parent == tmp_path
    assert read_topology(tmp_path, path.name) == {
        "yaml_text": yaml_text,
        "path": str(path),
        "name": path.name,
        "lab_id": "fabric",
    }
    assert [entry["name"] for entry in list_topologies(tmp_path)] == [path.name]


def test_write_uses_unique_suffix_without_overwrite(tmp_path: Path) -> None:
    first = write_topology(tmp_path, "nodes: {first: {}}\n")
    second = write_topology(tmp_path, "nodes: {second: {}}\n")
    third = write_topology(tmp_path, "nodes: {third: {}}\n")

    assert second.name == first.stem + "-2.yml"
    assert third.name == first.stem + "-3.yml"
    assert first.read_text(encoding="utf-8") == "nodes: {first: {}}\n"


@pytest.mark.parametrize(
    "name", ["../outside.yml", "/tmp/outside.yml", "..\\outside.yml"]
)
def test_read_rejects_path_traversal(tmp_path: Path, name: str) -> None:
    with pytest.raises(WebError) as raised:
        read_topology(tmp_path, name)

    assert raised.value.status_code == 400


def test_read_rejects_symlink_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "labs"
    root.mkdir()
    outside = tmp_path / "outside.yml"
    outside.write_text("nodes: {}\n", encoding="utf-8")
    (root / "escape.yml").symlink_to(outside)

    with pytest.raises(WebError) as raised:
        read_topology(root, "escape.yml")

    assert raised.value.status_code == 400


def test_read_missing_returns_404(tmp_path: Path) -> None:
    with pytest.raises(WebError) as raised:
        read_topology(tmp_path, "missing.yml")

    assert raised.value.status_code == 404


@pytest.mark.parametrize("stem", ["", "../escape", "a/b", "a\\b"])
def test_write_rejects_unsafe_stem(tmp_path: Path, stem: str) -> None:
    with pytest.raises(WebError) as raised:
        write_topology(tmp_path, "nodes: {}\n", stem=stem)

    assert raised.value.status_code == 400


@pytest.mark.parametrize(
    ("name", "lab_id"),
    [
        ("fabric.yml", "fabric"),
        ("fabric-2026-11-21.yml", "fabric"),
        ("fabric-2026-11-21-2.yml", "fabric"),
        ("topology-blz3-2026-11-20.yml", "topology-blz3"),
    ],
)
def test_lab_id_from_filename(name: str, lab_id: str) -> None:
    assert lab_id_from_filename(name) == lab_id


def test_list_labs_groups_versions(tmp_path: Path) -> None:
    import os

    first = write_topology(tmp_path, "nodes:\n  a: {}\n", stem="blz")
    older = tmp_path / "blz-2020-01-01.yml"
    older.write_text("nodes:\n  b: {}\n", encoding="utf-8")
    os.utime(older, (1_000_000, 1_000_000))
    os.utime(first, (2_000_000, 2_000_000))

    labs = list_labs(tmp_path)
    assert len(labs) == 1
    assert labs[0]["id"] == "blz"
    assert labs[0]["version_count"] == 2
    assert labs[0]["latest"]["name"] == first.name
    assert get_lab(tmp_path, "blz")["id"] == "blz"


def test_delete_topology_removes_file(tmp_path: Path) -> None:
    path = write_topology(tmp_path, "nodes:\n  a: {}\n", stem="blz")
    delete_topology(tmp_path, path.name)
    assert not path.exists()
    assert list_labs(tmp_path) == []
