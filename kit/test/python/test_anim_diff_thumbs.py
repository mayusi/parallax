"""kit/anim/diff.py + thumbs.py (AAA gaps v2 A5 / A1): a clip against itself differs by nothing, against an edited
copy by the edit; the thumbnail sheet renders a cell per key with the blade in it"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import diff as D      # noqa: E402
import strike as S    # noqa: E402
import thumbs as T    # noqa: E402

KEY = {"grip": [0.4, -0.4, -1.6], "dir": [0.2, 0.7, -0.7], "pos": [0, -0.6, 0], "right": [0.55, 0, 1.0],
       "left": [-0.57, 0, -0.7], "ease": "InOut"}
MOVE = {"name": "DiffProbe", "kind": "strike", "fps": 60, "rig": "R6", "arm_slide": 2.4, "leg_slide": 1.3,
        "sword": {"length": 3.6, "grip": 0.5, "kind": "katana"},
        "keys": [dict(KEY, t=0.0, yaw=0), dict(KEY, t=0.2, yaw=20, grip=[0.9, 0.6, -0.6], dir=[0.3, 0.6, 0.75]),
                 dict(KEY, t=0.4, yaw=-20, grip=[-0.3, -0.6, -2.0], dir=[-0.5, -0.3, -0.8])]}


def test_diff_zero_against_itself_and_sees_an_edit():
    a = S.generate(json.loads(json.dumps(MOVE)))[0]
    rows, shift, _ = D.compare(a, a)
    assert all(r["max_deg"] < 0.05 for r in rows.values()) and shift == 0
    m = json.loads(json.dumps(MOVE))
    m["keys"][1]["yaw"] = 45
    b = S.generate(m)[0]
    rows, _, _ = D.compare(a, b)
    assert rows["Torso"]["max_deg"] > 10


def test_thumbs_sheet_has_the_blade():
    a = S.generate(json.loads(json.dumps(MOVE)))[0]
    corners = T.blade(a, 10)
    assert corners is not None and corners.shape == (8, 3)
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "animations"))
        json.dump(a, open(os.path.join(d, "animations", "DiffProbe.clip.json"), "w"))
        mp = os.path.join(d, "DiffProbe.move.json")
        json.dump(MOVE, open(mp, "w"))
        os.environ["KIT_BUILD"] = d
        try:
            T.main(["DiffProbe", "--move", mp])
        finally:
            os.environ.pop("KIT_BUILD", None)
        assert os.path.getsize(os.path.join(d, "animations", "DiffProbe.thumbs.png")) > 1000
