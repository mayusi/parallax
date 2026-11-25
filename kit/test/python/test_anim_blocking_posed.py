"""kit/anim/blocking.py - a HAND-POSED file (<Name>.pose.json) blocked and locked (2026-11-14; the owner's order: every
method enforced in use): its key poses are shown from the clip the owner's rig poses from the file, his yes is to the
sheet made from the file as it was, and a posed move made after the rule is not built without it. The rig's part
(Blender) is one test, skipped where the kit's Blender or the rig is not there; the rest uses a strike clip as the
clip "the rig posed"."""
import copy
import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import blocking as B        # noqa: E402
import strike as S          # noqa: E402

LOVED = os.path.join(ROOT, "kit", "selftest", "anim", "faults", "loved", "Katana1Kesa.move.json")
DAY = "2026-11-14"
NAME = "PosedProbe"
BLENDER = os.environ.get("KIT_BLENDER") or os.environ.get("BLENDER") or "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"
RIG = os.path.join(ROOT, "assets", "rigs", "R6_IK.blend")


def setup(tmp_path, frames=(0, 12, 26, 51)):
    """a posed file keyed at `frames` and the clip "the rig posed from it" (a loved cut stands in)"""
    with open(LOVED, encoding="utf-8") as fh:
        clip = S.generate(json.load(fh))[0]
    cp, pp = tmp_path / "posed.clip.json", tmp_path / f"{NAME}.pose.json"
    pose = {"name": NAME, "fps": 60, "keys": [{"f": f, "body": {"turn": 5 * i}, "note": "a remark"} for i, f in enumerate(frames)]}
    pp.write_text(json.dumps(pose), encoding="utf-8")
    rigged(str(cp), str(pp), clip)
    return str(cp), str(pp), str(tmp_path / "anims"), str(tmp_path / "out")


def rigged(cp, pp, clip=None):
    """mark the clip as what the rig posed from the file as it is now (kit/anim/pose_r6.py writes this source)"""
    import hashlib
    if clip is None:
        clip = json.load(open(cp, encoding="utf-8"))
    clip["source"] = {"kind": "pose", "file": pp, "sha256": hashlib.sha256(open(pp, "rb").read()).hexdigest()}
    json.dump(clip, open(cp, "w", encoding="utf-8"))


def test_a_posed_files_keys_are_its_poses(tmp_path):
    cp, pp, anims, out = setup(tmp_path)
    m = B.make(NAME, out, anims, clip_path=cp, pose=pp, today=DAY)
    assert m["source"] == "pose" and [p["frame"] for p in m["poses"]] == [0, 12, 26, 51]
    assert m["made_from"] == [pp.replace(os.sep, "/")] and all(p.get("key") for p in m["poses"])   # the FILE, not the scratch clip
    keys = B.posed_keys(pp, 60)
    assert [k["t"] for k in keys] == [0.0, 0.2, round(26 / 60, 6), 0.85] and "f" not in keys[0]
    timed = json.load(open(pp))
    timed["keys"][1] = {"t": 0.25, "body": {"turn": 5}}
    json.dump(timed, open(pp, "w"))
    assert B.posed_keys(pp, 60)[1]["t"] == 0.25               # a key may give seconds
    timed["keys"][1] = {"f": 30, "t": 0.1}                    # both: the frame wins, as the rig reads it
    json.dump(timed, open(pp, "w"))
    assert [k["t"] for k in B.posed_keys(pp, 60)][2] == 0.5


@pytest.mark.parametrize("bad", [{"name": "x"}, {"keys": []}, {"keys": [{"body": {}}]}, {"keys": ["k"]}, {"keys": [{"f": True}]}])
def test_a_posed_file_without_timed_keys_is_refused(tmp_path, bad):
    cp, pp, anims, out = setup(tmp_path)
    json.dump(bad, open(pp, "w"))
    rigged(cp, pp)
    with pytest.raises(ValueError, match="no keyed poses|has no frame"):
        B.make(NAME, out, anims, clip_path=cp, pose=pp, today=DAY)


def yes(tmp_path):
    cp, pp, anims, out = setup(tmp_path)
    m = B.make(NAME, out, anims, clip_path=cp, pose=pp, today=DAY)
    rec = B.approve(B.load_record(anims, NAME), "yes, those poses", m["poses"], by="owner", today=DAY, source=m["source"],
                    made_from_sha256=m["made_from_sha256"], pose_sha256=m["pose_sha256"])
    B.save_record(anims, NAME, rec)
    return cp, pp, anims, out


def held(anims, pp):
    r = B.lock([(NAME, "pose", pp, None)], anims)
    return r["held"].get(NAME), r["free"].get(NAME)


def test_a_posed_move_is_held_until_his_yes_and_again_when_the_file_changes(tmp_path):
    cp, pp, anims, out = setup(tmp_path)
    assert "has not been shown its key poses" in held(anims, pp)[0]
    cp, pp, anims, out = yes(tmp_path)
    why, free = held(anims, pp)
    assert why is None and free.startswith("approved by the owner")
    spec = json.load(open(pp))
    spec["keys"][2]["body"]["turn"] = 40                      # one key changed after his yes
    json.dump(spec, open(pp, "w"))
    assert "the file changed since" in held(anims, pp)[0]
    os.remove(pp)                                             # ... and a file that is gone is no file he said yes to
    assert held(anims, pp)[0]


def test_a_yes_given_on_another_kind_of_blocking_does_not_free_a_posed_file(tmp_path):
    cp, pp, anims, out = setup(tmp_path)
    m = B.make(NAME, out, anims, clip_path=cp, today=DAY)     # a blocking of a clip, not of the posed file
    rec = B.approve(B.load_record(anims, NAME), "yes", m["poses"], by="owner", today=DAY, source=m["source"],
                    made_from_sha256=m["made_from_sha256"])
    B.save_record(anims, NAME, rec)
    assert "was not given on a blocking of this posed file" in held(anims, pp)[0]
    typed = {"approved": {"by": "owner", "words": "x", "source": "pose", "pose_sha256": B.pose_hash(pp)},
             "notes": [], "history": []}
    B.save_record(anims, NAME, typed)                         # a record typed by hand: no poses he saw
    assert "holds no poses" in held(anims, pp)[0]
    one = [{"frame": 0, "id": "made-up"}]                     # ... or one invented pose under its own id
    typed["approved"].update(poses=one, id=B.blocking_id(one))
    B.save_record(anims, NAME, typed)
    assert "are not this file's keys" in held(anims, pp)[0]


def test_posed_files_made_before_the_rule_are_never_asked(tmp_path):
    cp, pp, anims, out = setup(tmp_path)
    os.makedirs(anims)
    for f in ("Old.pose.json", "_private.pose.json", "Other.move.json"):
        open(os.path.join(anims, f), "w").write("{}")
    path, names = B.freeze_posed(anims, today=DAY)
    assert names == ["Old"] and B.posed_before(anims) == {"Old"} and B.before_rule(anims) == set()
    other = B.lock([("Old", "move", str(tmp_path / "gone.move.json"), None)], anims)      # the posed list excuses posed files only
    assert "Old" in other["held"]
    r = B.lock([("Old", "pose", str(tmp_path / "gone.pose.json"), None), (NAME, "pose", pp, None)], anims)
    assert "made before the rule" in r["free"]["Old"] and NAME in r["held"]
    with pytest.raises(ValueError, match="frozen once"):
        B.freeze_posed(anims)
    open(path, "w").write("{not json")
    with pytest.raises(ValueError, match="never delete it"):
        B.lock([(NAME, "pose", pp, None)], anims)


def run_cli(*args):
    r = subprocess.run([sys.executable, os.path.join(ROOT, "kit", "anim", "blocking.py"), *args], capture_output=True,
                       text=True, encoding="utf-8", cwd=ROOT)
    return r.returncode, json.loads(r.stdout.strip().splitlines()[-1])


def test_the_whole_round_as_commands(tmp_path):
    cp, pp, anims, out = setup(tmp_path)
    where = ["--out", out, "--anims", anims]
    code, v = run_cli("lock", f"{NAME}=pose={pp}", "--anims", anims)
    assert code == 1 and v["next_action"].startswith(f"lune run kit anim block {NAME} --sheet ")
    code, m = run_cli("make", NAME, "--clip", cp, "--pose", pp, *where)
    assert code == 0 and "4 key pose(s) held" in m["summary"]
    assert run_cli("approve", NAME, "yes", "--by", "owner", "--id", m["id"], *where)[0] == 0
    assert run_cli("lock", f"{NAME}=pose={pp}", "--anims", anims)[0] == 0
    code, v = run_cli("freeze", "--posed", "--anims", anims)
    assert code == 0 and "hand-posed file(s) made before the rule" in v["summary"]


@pytest.mark.skipif(not (os.path.isfile(BLENDER) and os.path.isfile(RIG)), reason="the kit's Blender or the owner's rig is not here")
def test_the_owners_rig_poses_the_kits_template_and_its_keys_are_blocked(tmp_path):
    with open(os.path.join(ROOT, "kit", "templates", "anim.pose.json"), encoding="utf-8") as fh:
        text = fh.read().replace("__NAME__", NAME)
    pp, cp = tmp_path / f"{NAME}.pose.json", tmp_path / "posed.clip.json"
    pp.write_text(text, encoding="utf-8")
    r = subprocess.run([BLENDER, "-b", RIG, "--disable-autoexec", "--python-exit-code", "2", "-P",
                        os.path.join(ROOT, "kit", "anim", "pose_r6.py"), "--", str(pp), "--out", str(cp)],
                       capture_output=True, text=True, cwd=ROOT, timeout=240)
    assert r.returncode == 0 and cp.exists(), r.stdout[-400:]
    m = B.make(NAME, str(tmp_path / "out"), str(tmp_path / "anims"), clip_path=str(cp), pose=str(pp), today=DAY)
    keyed = [round(float(k["f"])) for k in json.loads(text)["keys"]]
    assert m["source"] == "pose" and [p["frame"] for p in m["poses"]] == keyed and len(keyed) >= 3


# ---- what the stage's review found (2026-11-14) ----
def test_his_yes_survives_a_checkout_that_rewrites_line_endings(tmp_path):
    cp, pp, anims, out = yes(tmp_path)
    text = json.dumps(json.load(open(pp)), indent=1)
    open(pp, "w", newline="").write(text.replace("\n", "\r\n"))          # the same content, other bytes
    assert held(anims, pp)[0] is None


def test_the_clip_must_be_what_the_rig_posed_from_this_very_file(tmp_path):
    cp, pp, anims, out = setup(tmp_path)
    clip = json.load(open(cp))
    clip["source"] = {"kind": "move", "file": "some.move.json"}             # another clip altogether
    json.dump(clip, open(cp, "w"))
    with pytest.raises(ValueError, match="is not what the owner's rig posed from"):
        B.make(NAME, out, anims, clip_path=cp, pose=pp, today=DAY)
    rigged(cp, pp)
    spec = json.load(open(pp))
    spec["keys"][1]["body"]["turn"] = 77                                    # the file changed after the rig posed it
    json.dump(spec, open(pp, "w"))
    with pytest.raises(ValueError, match="is not what the owner's rig posed from"):
        B.make(NAME, out, anims, clip_path=cp, pose=pp, today=DAY)
    rigged(cp, pp)
    with pytest.raises(ValueError, match="no --move with --pose"):
        B.make(NAME, out, anims, clip_path=cp, pose=pp, move_path=pp, today=DAY)
