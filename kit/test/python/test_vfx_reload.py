"""the player's hot reload reads a preset's kept files again (two review leftovers of the VFX methods audit, stages 5
and 11: a fracture plan cut again, or a field edited, stayed the old one until `kit vfx play` was run again)."""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "vfx"))
import capture  # noqa: E402

PRESET = {"layers": [
    {"kind": "debris", "pieces": "slab"},
    {"kind": "swarm", "field": {"name": "whirl"}},
    {"kind": "swarm", "cloud": {"name": "star"}},
    {"kind": "mesh", "pieces": "not_a_debris_layer"},
    {"kind": "debris", "count": 6}]}


def put(root, folder, name, data):
    os.makedirs(root / folder, exist_ok=True)
    json.dump(data, open(root / folder / f"{name}.json", "w"))


def made(root):
    put(root, "fractures", "slab", {"pieces": [1, 2, 3]})
    put(root, "fields", "whirl", {"elements": [{"kind": "wind"}]})
    put(root, "points", "star", {"points": [[i, 0, 0] for i in range(12)]})


def test_every_kept_file_a_layer_names_is_read(tmp_path):
    made(tmp_path)
    got, bad = capture.kept_files(PRESET, str(tmp_path))
    assert bad == []
    assert list(got["fractures"]) == ["slab"] and list(got["fields"]) == ["whirl"] and list(got["points"]) == ["star"]


def test_a_plan_cut_again_is_the_new_one(tmp_path):
    made(tmp_path)
    put(tmp_path, "fractures", "slab", {"pieces": [1, 2, 3, 4, 5]})
    assert len(capture.kept_files(PRESET, str(tmp_path))[0]["fractures"]["slab"]["pieces"]) == 5


def test_a_file_that_is_not_what_it_should_be_is_left_out_and_said(tmp_path):
    made(tmp_path)
    put(tmp_path, "fields", "whirl", {"elements": []})
    put(tmp_path, "points", "star", {"points": [[0, 0, "x"]] * 12})
    os.remove(tmp_path / "fractures" / "slab.json")
    got, bad = capture.kept_files(PRESET, str(tmp_path))
    assert got == {"fractures": {}, "fields": {}, "points": {}}
    assert len(bad) == 3 and any("cannot be read" in b for b in bad)


def test_a_name_that_is_no_name_is_never_a_path(tmp_path):
    made(tmp_path)
    preset = {"layers": [{"kind": "debris", "pieces": "../slab"}, {"kind": "swarm", "field": {"name": 7}}]}
    assert capture.kept_files(preset, str(tmp_path)) == ({"fractures": {}, "fields": {}, "points": {}}, [])
