"""kit vfx cost counts what the engine must hold: a fracture's pieces and a swarm's stones are runtime meshes of their
own, and a swarm in an authored field pays for every element (three review leftovers of the VFX methods audit: stages
5, 11 and 14 - none of them was in the cost line)."""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "vfx"))
import cost  # noqa: E402


def effects(tmp_path, pieces=14, elements=3):
    for folder, name, data in (("fractures", "slab", {"schema": 1, "pieces": [{"k": i} for i in range(pieces)]}),
                               ("fields", "whirl", {"schema": 1, "elements": [{"kind": "wind"}] * elements})):
        os.makedirs(tmp_path / folder, exist_ok=True)
        json.dump(data, open(tmp_path / folder / f"{name}.json", "w"))
    return str(tmp_path)


def test_a_fractures_pieces_are_meshes_while_their_layer_lasts(tmp_path):
    preset = {"duration": 3, "layers": [
        {"kind": "mesh", "at": 0, "life": 3, "shape": "ring"},
        {"kind": "debris", "at": 1, "life": 1, "pieces": "slab"}]}
    c = cost.cost(preset, effects(tmp_path))
    assert c["piece_meshes"] == 14 and c["stone_meshes"] == 0
    assert c["built_meshes_peak"] == 15          # the ring and the 14 pieces: all built when the effect is set up
    assert c["meshes_peak"] == 1 and c["missing"] == []


def test_stones_are_meshes_and_plain_swarm_parts_are_not(tmp_path):
    preset = {"duration": 2, "layers": [
        {"kind": "swarm", "at": 0, "life": 2, "shape": "Rock", "count": 24},
        {"kind": "swarm", "at": 0, "life": 2, "count": 80}]}
    c = cost.cost(preset, effects(tmp_path))
    assert c["stone_meshes"] == 24 and c["built_meshes_peak"] == 24 and c["swarm_parts"] == 104


def test_pieces_and_stones_are_held_for_the_whole_effect(tmp_path):
    """the review of this change: the game builds them when the effect is set up and gives them back when it is
    over - two layers whose lives never overlap are still held together (a Studio play client held 127 for starblade)"""
    preset = {"duration": 4, "layers": [
        {"kind": "debris", "at": 0, "life": 1, "pieces": "slab"},
        {"kind": "swarm", "at": 2, "life": 1, "shape": "Rock", "count": 30}]}
    assert cost.cost(preset, effects(tmp_path))["built_meshes_peak"] == 44


def test_a_mesh_layer_is_held_from_the_start_until_its_own_life_is_over(tmp_path):
    preset = {"duration": 6, "layers": [
        {"kind": "mesh", "at": 0, "life": 1, "shape": "ring"},
        {"kind": "mesh", "at": 4, "life": 1, "shape": "ring"}]}
    c = cost.cost(preset, effects(tmp_path))
    assert c["meshes_peak"] == 1 and c["built_meshes_peak"] == 2     # one SHOWN at a time, two built at the start


def test_a_ribbon_and_a_draped_mark_are_one_mesh_each_and_stones_are_forty_at_most(tmp_path):
    preset = {"duration": 2, "layers": [
        {"kind": "trail", "at": 0, "life": 1, "mesh": True}, {"kind": "trail", "at": 0, "life": 1},
        {"kind": "decal", "at": 0, "life": 1, "wrap": True}, {"kind": "decal", "at": 0, "life": 1},
        {"kind": "swarm", "at": 0, "life": 1, "shape": "Rock", "count": 150}]}
    assert cost.cost(preset, effects(tmp_path))["built_meshes_peak"] == 42


def test_a_field_costs_every_element_for_every_part(tmp_path):
    plain = {"duration": 2, "layers": [{"kind": "swarm", "at": 0, "life": 2, "count": 100}]}
    field = {"duration": 2, "layers": [{"kind": "swarm", "at": 0, "life": 2, "count": 100, "field": {"name": "whirl"}}]}
    folder = effects(tmp_path, elements=4)
    a, b = cost.cost(plain, folder), cost.cost(field, folder)
    assert a["field_ms_per_frame"] == 0
    assert b["field_ms_per_frame"] == round(100 * 4 * cost.US_PER_FIELD_ELEMENT / 1000, 3)
    assert b["luau_ms_per_frame"] > a["luau_ms_per_frame"]


def test_a_kept_file_that_is_not_there_is_said_not_counted_as_nothing(tmp_path):
    preset = {"duration": 2, "layers": [
        {"kind": "debris", "at": 0, "life": 1, "pieces": "gone"},
        {"kind": "swarm", "at": 0, "life": 1, "count": 10, "field": {"name": "gone"}}]}
    c = cost.cost(preset, effects(tmp_path))
    assert c["piece_meshes"] == 0 and sorted(c["missing"]) == ["field gone", "fracture plan gone"]


def test_a_preset_with_none_of_them_costs_what_it_did(tmp_path):
    preset = {"duration": 2, "layers": [{"kind": "mesh", "at": 0, "life": 1, "shape": "ring"},
                                        {"kind": "sprite", "at": 0, "count": 20, "lifetime": 1}]}
    c = cost.cost(preset, effects(tmp_path))
    assert (c["meshes_peak"], c["built_meshes_peak"], c["peak_particles"], c["piece_meshes"], c["stone_meshes"]) == (1, 1, 20, 0, 0)


def test_thrown_rocks_are_meshes_too(tmp_path):
    """found on starblade: the cost line said 25 meshes at once, a Studio play client held 127 (four rock layers)"""
    preset = {"duration": 3, "layers": [
        {"kind": "mesh", "at": 0, "life": 3, "shape": "ring"},
        {"kind": "debris", "at": 0, "life": 3, "shape": "rock", "count": 90},      # (the layer throws 40 at most)
        {"kind": "debris", "at": 1, "life": 1, "count": 12}]}                       # (plain blocks: no mesh)
    c = cost.cost(preset, effects(tmp_path))
    assert c["stone_meshes"] == 40 and c["piece_meshes"] == 0 and c["built_meshes_peak"] == 41


RUN_LUAU = """local fs = require("@lune/fs")
local serde = require("@lune/serde")
local process = require("@lune/process")
local B = require("../../../src/kit/VfxBudget")
local sets = serde.decode("json", fs.readFile(process.args[1]))
local out = {}
local pieces = sets.__pieces
sets.__pieces = nil
for name, layers in sets do
	out[name] = B.builds(layers, function(plan)
		return pieces[plan]
	end)
end
print(serde.encode("json", out))
"""


def test_the_games_count_of_built_meshes_is_the_cost_lines(tmp_path):
    """one rule in two places: src/kit/VfxBudget.luau `builds` (what Vfx.coldPlays counts by) and `built_meshes` here,
    run against each other on every version 3 preset of the kit and on made layers of every kind that builds"""
    import glob
    import shutil
    import subprocess
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    made = [{"kind": "mesh"}, {"kind": "debris", "shape": "rock", "count": 90}, {"kind": "debris", "shape": "rock"},
            {"kind": "debris", "count": 12}, {"kind": "swarm", "shape": "Rock", "count": 150}, {"kind": "swarm", "shape": "Rock"},
            {"kind": "swarm", "count": 80}, {"kind": "trail", "mesh": True}, {"kind": "trail"}, {"kind": "decal", "wrap": True},
            {"kind": "decal", "wrap": 6}, {"kind": "decal"}, {"kind": "sprite", "count": 20},
            {"kind": "debris", "shape": "rock", "count": 0}, {"kind": "swarm", "shape": "Rock", "count": 0},
            {"kind": "debris", "pieces": "slab"}, {"kind": "debris", "pieces": "gone"}]
    os.makedirs(tmp_path / "fractures")
    json.dump({"pieces": [{"k": i} for i in range(14)]}, open(tmp_path / "fractures" / "slab.json", "w"))
    sets = {"made": made}
    # the project's effects and the kit's own starters (kit/starter/vfx holds version 3 presets too)
    for folder in (("assets", "effects"), ("kit", "starter", "vfx")):
        for path in sorted(glob.glob(os.path.join(root, *folder, "*.json"))):
            try:
                p = json.load(open(path, encoding="utf-8"))
            except ValueError:
                continue
            if isinstance(p, dict) and p.get("version") == 3 and isinstance(p.get("layers"), list):
                sets[f"{folder[-1]}/{os.path.basename(path)}"] = p["layers"]
    work = os.path.join(root, "build", "selftest", f"vfx_builds_{os.getpid()}")
    os.makedirs(work, exist_ok=True)
    try:
        json.dump(dict(sets, __pieces={"slab": 14}), open(os.path.join(work, "sets.json"), "w"))
        open(os.path.join(work, "run.luau"), "w", newline="\n").write(RUN_LUAU)
        got = subprocess.run([shutil.which("lune") or "lune", "run", os.path.join(work, "run.luau"), os.path.join(work, "sets.json")],
                             capture_output=True, text=True, timeout=120, cwd=root)
        assert got.returncode == 0, got.stderr[-400:]
        game = json.loads(got.stdout.strip().splitlines()[-1])
    finally:
        shutil.rmtree(work, ignore_errors=True)
    # every version 3 preset found is checked, however few - the kit's own starters always among them (the author's repo
    # also floors its library at 50+, which only the author's own library meets)
    assert sum(1 for name in sets if name.startswith("vfx/")) >= 2
    # and every version 3 preset of the project is among them (counted a second way: a glob that finds nothing cannot
    # pass for "a project with no effects")
    fx, mine = os.path.join(root, "assets", "effects"), set()
    for f in os.listdir(fx) if os.path.isdir(fx) else []:
        try:
            p = json.load(open(os.path.join(fx, f), encoding="utf-8")) if f.endswith(".json") else None
        except ValueError:
            continue
        if isinstance(p, dict) and p.get("version") == 3 and isinstance(p.get("layers"), list):
            mine.add(f"effects/{f}")
    assert {name for name in sets if name.startswith("effects/")} == mine
    for name, layers in sets.items():
        missing = []
        ours = sum((1 if el.get("kind") == "mesh" else cost.built_meshes(el, str(tmp_path), missing)) for el in layers if isinstance(el, dict))
        assert game[name] == ours, (name, game[name], ours)
    # mesh, rocks 40 + 6, stones 40 + 40, ribbon, two draped marks, rocks of count 0, stones of count 0 (one), 14 pieces
    assert game["made"] == 1 + 40 + 6 + 40 + 40 + 1 + 1 + 1 + 0 + 1 + 14


def seq_file(tmp_path, name, cols, rows, strips=None):
    d = tmp_path / "seq"  # (effects() is tmp_path itself)
    d.mkdir(parents=True, exist_ok=True)
    body = {"cols": cols, "rows": rows, "frames": [[0.0] * ((cols + 1) * (rows + 1) * 3)]}
    if strips:
        body["strips"] = strips
    (d / f"{name}.json").write_text(json.dumps(body))


def seq_layer(name, at=0.0, life=1.0):
    return {"kind": "mesh", "shape": "seq", "params": {"seq": name}, "at": at, "life": life}


def test_a_mesh_sequence_counts_its_triangles_both_faces(tmp_path):
    # the V3 doc, VFX stage E.2: a baked burst <= 800 triangles, the ones at once <= 3 x 800 together
    seq_file(tmp_path, "crown", 32, 8)           # 256 squares x 4 (two triangles, both faces) = 1024
    seq_file(tmp_path, "hair", 2, 10, strips=5)  # 20 squares x 5 strips x 4 = 400
    c = cost.cost({"duration": 2, "layers": [seq_layer("crown"), seq_layer("hair", at=1.5, life=0.5)]}, effects(tmp_path))
    assert c["seq_tris_most"] == 1024
    assert c["seq_peak"] == 1 and c["seq_tris_peak"] == 1024     # never both at once
    assert c["missing"] == []


def test_many_small_sequences_at_once_are_held_to_the_total(tmp_path):
    seq_file(tmp_path, "band", 10, 5)            # 200 triangles each
    small = {"duration": 1, "layers": [seq_layer("band") for _ in range(11)]}
    c = cost.cost(small, effects(tmp_path))
    assert (c["seq_peak"], c["seq_tris_peak"]) == (11, 2200)   # under 2400 together: within the budget
    c = cost.cost({"duration": 1, "layers": [seq_layer("band") for _ in range(13)]}, effects(tmp_path))
    assert c["seq_tris_peak"] == 2600                           # over it
    c = cost.cost({"duration": 1, "layers": [seq_layer("gone")]}, effects(tmp_path))
    assert c["missing"] == ["seq/gone.json"]
