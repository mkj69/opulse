"""Exports publish complete directory trees and retain the previous tree on writer errors."""

import json

import pytest

from opulse.worlds import showcase, showcase_tasks, showcase_tasks_action
from opulse.worlds._atomic_export import staged_export


def _assert_no_staging(parent):
    assert not list(parent.glob(".*.tmp-*"))
    assert not list(parent.glob(".*.old-*"))


@pytest.mark.parametrize("fail", [True, False])
def test_world_export_replaces_complete_tree(tmp_path, monkeypatch, fail):
    folder = tmp_path / "clock"
    (folder / "steps" / "old").mkdir(parents=True)
    (folder / "steps" / "old" / "0.json").write_text("old steps")
    (folder / "tasks" / "keep.json").parent.mkdir()
    (folder / "tasks" / "keep.json").write_text("keep tasks")
    (tmp_path / "clock.json").write_text("old browser")

    def writer(spec, out_path, seed, root, steps_dir):
        steps_dir.mkdir(parents=True)
        (steps_dir / "0.json").write_text("new steps")
        if fail:
            raise RuntimeError("writer stopped")
        out_path.write_text("intermediate")
        return {"world": "clock", "metrics": {"_prints": set()}}

    monkeypatch.setattr(showcase, "export_spec", writer)
    if fail:
        with pytest.raises(RuntimeError, match="writer stopped"):
            showcase.export_world("clock", tmp_path, seeds=1)
        assert (folder / "steps" / "old" / "0.json").read_text() == "old steps"
        assert (tmp_path / "clock.json").read_text() == "old browser"
    else:
        showcase.export_world("clock", tmp_path, seeds=1)
        assert (folder / "steps" / str(showcase.world_spec("clock").seed) / "0.json").read_text() == "new steps"
        assert not (folder / "steps" / "old").exists()
        assert json.loads((tmp_path / "clock.json").read_text())["seeds"][0]["file"] == "clock.json"
    assert (folder / "tasks" / "keep.json").read_text() == "keep tasks"
    _assert_no_staging(tmp_path)


@pytest.mark.parametrize("fail", [True, False])
def test_tasks_export_replaces_complete_tree(tmp_path, monkeypatch, fail):
    folder = tmp_path / "action" / "tasks"
    folder.mkdir(parents=True)
    (folder / "old.json").write_text("old tasks")
    sidecar = folder.parent / "tasks.json"
    sidecar.write_text("old index")

    def writer(directory, output):
        (output / "new.json").write_text("new tasks")
        if fail:
            raise RuntimeError("writer stopped")
        return {"world": "action"}

    monkeypatch.setattr(showcase_tasks_action, "export_action_tasks", writer)
    if fail:
        with pytest.raises(RuntimeError, match="writer stopped"):
            showcase_tasks.export_tasks("action", tmp_path)
        assert (folder / "old.json").read_text() == "old tasks"
        assert sidecar.read_text() == "old index"
    else:
        showcase_tasks.export_tasks("action", tmp_path)
        assert (folder / "new.json").read_text() == "new tasks"
        assert not (folder / "old.json").exists()
        assert json.loads(sidecar.read_text())["world"] == "action"
    _assert_no_staging(folder.parent)


def test_single_spec_keeps_old_steps_when_json_writer_fails(tmp_path, monkeypatch):
    spec = showcase.world_spec("clock")
    steps = tmp_path / "clock" / "steps" / str(spec.seed)
    steps.mkdir(parents=True)
    (steps / "old.json").write_text("old steps")
    sidecar = tmp_path / "clock.json"
    sidecar.write_text("old browser")

    def fail_write(path, data):
        raise RuntimeError("json writer stopped")

    monkeypatch.setattr(showcase, "_write", fail_write)
    with pytest.raises(RuntimeError, match="json writer stopped"):
        showcase.export_spec(spec, sidecar)
    assert (steps / "old.json").read_text() == "old steps"
    assert sidecar.read_text() == "old browser"
    _assert_no_staging(steps.parent)


def test_sidecar_publish_failure_restores_directory(tmp_path, monkeypatch):
    folder = tmp_path / "steps"
    folder.mkdir()
    (folder / "old.json").write_text("old")
    sidecar = tmp_path / "world.json"
    sidecar.write_text("old index")
    original_replace = type(sidecar).replace

    def fail_replace(path, target):
        if target == sidecar:
            raise OSError("publish stopped")
        return original_replace(path, target)

    monkeypatch.setattr(type(sidecar), "replace", fail_replace)
    with pytest.raises(OSError, match="publish stopped"):
        with staged_export(folder, sidecar) as (staged, staged_json):
            (staged / "new.json").write_text("new")
            staged_json.write_text("new index")
    assert (folder / "old.json").read_text() == "old"
    assert not (folder / "new.json").exists()
    assert sidecar.read_text() == "old index"
    _assert_no_staging(tmp_path)
