"""kit/anim/proc_dossier.direction_missing (the owner's order 2026-10-24: creative direction before anything original):
a dossier that names a direction needs that doc at least READY; older dossiers that name none pass"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import proc_dossier as DS  # noqa: E402

DIRECTION = os.path.join(ROOT, "kit", "direction.py")

READY = """# Probe — direction

## Intent
{intent}

## The one idea
One cut that is drawn, struck and sheathed before the target falls.

## References
- Film A (film) — take: the stillness — leave: the blood
- Film B (film) — take: the draw — leave: the music
- Painting C (painting) — take: the line — leave: the colour
- Game D (game) — take: the hit-stop — leave: the UI
- Photo E (photography) — take: the stance — leave: the setting
- Kata F (martial art) — take: the timing — leave: the bow

## Pillars
- stillness
- one line
- the sheath

## Bans
- spinning
- flailing arms
- a wind-up

## Directions
### A — Still
Feeling: calm. Risk: too slow.
Axes: rhythm=held; read=low; effort=sustained; mood=calm
Frame: direction/Probe_A.png

### B — Flash
Feeling: sudden. Risk: unreadable.
Axes: rhythm=one beat; read=high; effort=sudden; mood=sharp
Frame: direction/Probe_B.png

### C — Ritual
Feeling: weight. Risk: long.
Axes: rhythm=two beats; read=wide; effort=bound; mood=heavy
Frame: direction/Probe_C.png

## Pick
pending
""".format(intent=" ".join(["the player feels the silence before a single decisive cut and then the release"] * 4))


def test_older_dossiers_without_a_direction_pass():
    assert DS.direction_missing({"name": "old"}) == []


def test_a_todo_or_missing_direction_is_refused(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert DS.direction_missing({"direction": "TODO: decide"})
    assert "does not exist" in DS.direction_missing({"direction": "Probe"})[0]


def test_a_ready_direction_passes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    d = tmp_path / "assets" / "animations" / "direction"
    d.mkdir(parents=True)
    for k in "ABC":
        (d / f"Probe_{k}.png").write_bytes(b"png")
    (d / "Probe.md").write_text(READY, encoding="utf-8")
    assert DS.direction_missing({"direction": "Probe"}) == []
    (d / "Probe_C.png").unlink()                              # a frame missing -> back to draft
    assert "draft" in DS.direction_missing({"direction": "Probe"})[0]


def test_direction_frames_pick_the_first_middle_and_last_key():
    """kit anim direction --frames: each option's frame shows its first key, the moment and its last key"""
    sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
    import direction_frames as DF
    assert DF.key_frames({"keys": [{"f": 0}, {"f": 14}, {"f": 30}]}) == [1, 15, 31]
    assert DF.key_frames({"keys": [{"f": 0}, {"f": 8}, {"f": 16}, {"f": 24}]}) == [1, 17, 25]
    assert DF.key_frames({"keys": [{"f": 0}, {"f": 12}]}) == [1, 13, 13]


def test_a_new_anim_doc_names_the_anim_axes_and_png_frames(tmp_path):
    import subprocess
    p = tmp_path / "Probe.md"
    r = subprocess.run([sys.executable, "-I", DIRECTION, "new", str(p), "--lane", "anim"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    text = p.read_text(encoding="utf-8")
    assert "Axes: rhythm=...; read=...; effort=...; mood=..." in text
    assert "direction/Probe_A.png" in text and ".ogg" not in text
