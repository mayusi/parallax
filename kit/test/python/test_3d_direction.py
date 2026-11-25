"""kit/direction.py --lane 3d (the owner, 2026-10-25: "work on originality ... a creative director and creative
direction in the pipeline"): a 3D direction doc needs a concept SHEET per direction and Axes naming shape, material
and mood; three directions that differ on fewer than 2 axes are one direction; a complete doc is READY, a picked one
PICKED; a new doc's template carries the 3D axes and .png sheets"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
DIRECTION = os.path.join(ROOT, "kit", "direction.py")

DOC = """# Probe — direction

## Intent
{intent}

## The one idea
A duelling pistol grown from a clockwork music box, wound before each shot.

## References
- Music box (photography) — take: the comb and drum — leave: the toy scale
- Flintlock duelling pistol (museum) — take: the lock plate — leave: the wood grain
- Art nouveau jewellery (painting) — take: the whiplash curve — leave: the flowers
- Bloodborne (game) — take: the trick mechanism — leave: the gothic grime
- Pocket watch (photography) — take: the crown and case — leave: the chain
- Steamboat Willie (film) — take: the rhythm of the crank — leave: the cartoon

## Pillars
- every moving part is visible
- one whiplash curve runs grip to muzzle
- brass and lacquer only

## Bans
- no glowing lines
- no skulls
- no tactical rails

## Directions
### A — Courtly
Feeling: refined. Risk: too delicate.
Axes: maker=house of strings; era=1890s; shape=round; material=brass; mood=elegant
Sheet: direction/Probe_A.png

### B — Workshop
Feeling: honest. Risk: plain.
Axes: maker=tinker guild; era=1850s; shape=square; material=iron; mood=sturdy
Sheet: direction/Probe_B.png

### C — Carnival
Feeling: playful. Risk: toy-like.
Axes: maker=fair masters; era=1920s; shape=blade; material=lacquer; mood=mischief
Sheet: direction/Probe_C.png

## Pick
{pick}
""".format(intent=" ".join(["the holder feels a ritual of winding before the shot and pride in a crafted object"] * 3),
           pick="{pick}")


def run(*args):
    r = subprocess.run([sys.executable, DIRECTION, *args], capture_output=True, text=True)
    return r.returncode, json.loads(r.stdout.strip().splitlines()[-1])


def make(tmp, text):
    os.makedirs(os.path.join(tmp, "direction"), exist_ok=True)
    for k in "ABC":
        open(os.path.join(tmp, "direction", f"Probe_{k}.png"), "wb").write(b"png")
    path = os.path.join(tmp, "direction", "Probe.md")
    open(path, "w", encoding="utf-8").write(text)
    return path


def test_ready_and_picked():
    with tempfile.TemporaryDirectory() as tmp:
        code, out = run("check", make(tmp, DOC.replace("{pick}", "pending")), "--lane", "3d")
        assert (code, out["direction"]) == (0, "ready"), out
        assert "concept sheets" in out["next_action"]
        code, out = run("check", make(tmp, DOC.replace("{pick}", 'picked: A by owner — "the courtly one"')), "--lane", "3d")
        assert out["direction"] == "picked", out


def test_axes_must_name_shape_material_mood():
    with tempfile.TemporaryDirectory() as tmp:
        bad = DOC.replace("{pick}", "pending").replace("material=brass; ", "")
        code, out = run("check", make(tmp, bad), "--lane", "3d")
        assert code == 1 and any("shape, material, mood" in p for p in out["problems"]), out


def test_one_idea_in_three_grades_is_refused():
    with tempfile.TemporaryDirectory() as tmp:
        same = DOC.replace("{pick}", "pending")
        same = same.replace("maker=tinker guild; era=1850s; shape=square; material=iron; mood=sturdy",
                            "maker=house of strings; era=1890s; shape=round; material=brass; mood=sturdy")
        code, out = run("check", make(tmp, same), "--lane", "3d")
        assert code == 1 and any("differ on" in p for p in out["problems"]), out


def test_new_template_has_3d_axes_and_sheets():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "direction", "Gun.md")
        code, out = run("new", path, "--lane", "3d", "--name", "Gun")
        text = open(path, encoding="utf-8").read()
        assert code == 0 and "maker=...; era=...; shape=...; material=...; mood=..." in text
        assert "Sheet: direction/Gun_A.png" in text and "concept sheets" in text
