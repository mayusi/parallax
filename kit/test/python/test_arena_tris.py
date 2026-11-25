"""kit/tools/arena_tris.py sums the integration arena's triangles offline (V4 §13.8: the 1.5M budget is not readable
from Luau): world primitives + placed W3 meshes from their manifests, the hero's mesh groups, the R6 bodies; a mesh
the build lacks is reported, never counted as zero."""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "tools"))
import arena_tris  # noqa: E402


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def _fixture(root, mesh_tris=1000, hero=(300, 200)):
    _write(os.path.join(root, "build", "worlds", "W.json"), {"parts": [
        {"class": "Part", "shape": "Block"},
        {"class": "WedgePart", "shape": "WedgePart"},
        {"class": "Part", "mesh": "m1"},
        {"class": "Part", "mesh": "m1"},
    ]})
    if mesh_tris is not None:
        _write(os.path.join(root, "build", "worldmeshes", "m1.mesh.json"), {"tris": mesh_tris})
    _write(os.path.join(root, "build", "models", "H.manifest.json"),
           {"groups": {"a": {"tris": hero[0]}, "b": {"tris": hero[1]}}})


def test_sums_world_meshes_hero_and_bodies(tmp_path):
    _fixture(str(tmp_path))
    out = arena_tris.count(str(tmp_path), "W", "H", bodies=2)
    assert out["parts"]["world"] == 12 + 8 + 2 * 1000  # a placed mesh counts once per placement
    assert out["parts"]["hero"] == 500
    assert out["parts"]["bodies"] == 2 * arena_tris.R6_BODY_ESTIMATE
    assert out["total"] == 2020 + 500 + 2 * arena_tris.R6_BODY_ESTIMATE
    assert out["status"] == "pass"


def test_over_budget_fails(tmp_path):
    _fixture(str(tmp_path), mesh_tris=900_000)
    out = arena_tris.count(str(tmp_path), "W", "H", bodies=0)
    assert out["status"] == "fail" and out["total"] > arena_tris.BUDGET
    assert ">" in out["summary"]


def test_missing_mesh_is_reported_not_zero(tmp_path):
    _fixture(str(tmp_path), mesh_tris=None)
    out = arena_tris.count(str(tmp_path), "W", "H", bodies=0)
    assert out["status"] == "fail"
    assert "world mesh m1" in out["summary"]


def test_cli_prints_one_json_line(tmp_path, capsys):
    _fixture(str(tmp_path))
    code = arena_tris.main(["--root", str(tmp_path), "--world", "W", "--hero", "H", "--bodies", "0"])
    line = capsys.readouterr().out.strip()
    assert code == 0 and json.loads(line)["status"] == "pass"
