"""madeproject.py — a small made project for the style sheet's proof (kit selftest + kit/test/python/
test_vfx_stylesheet.py): one effect "fx" built from the set "fire", its chart with two beats on our clock (0-0.5 s,
0.5 s to the end), a "scene" clip and "our" recording made by kit/selftest/vfx/dailies/clips.py. The tool is run
from inside it (its paths are relative to the project it stands in)."""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dailies"))
import clips  # noqa: E402


BEATS = """# the made scene, beat by beat

| Beat | Scene time | On screen |
|---|---|---|
| 0 the hit | 0.2-0.5 s | a flame arc, there in one frame |
| 1 the going | 0.5-0.9 s | the arc thins and goes |
"""


def project(root, ours, name="fx", set_name="fire", booth=None):
    """write the project into `root`; ours: the frames of our recording (clips.our_frames() / clips.blank_frames()).
    name / set_name: the effect and its set (the review page's fixture gives them names of its run's own, because the
    page reads recordings and sheets in the project's build folder). booth: where our recording goes (default: the
    made project's own build/vfx/booth) -> the recording's path."""
    effects = os.path.join(root, "assets", "effects")
    measured = os.path.join(effects, "refs_measured")
    booth = booth or os.path.join(root, "build", "vfx", "booth")
    os.makedirs(measured, exist_ok=True)
    os.makedirs(booth, exist_ok=True)
    scene = clips.write(os.path.join(root, "scene.mp4"), clips.scene_frames(), 24)
    recording = clips.write(os.path.join(booth, f"{name}_play_hero.mp4"), ours, 30)
    json.dump({"version": 3, "duration": 1.2, "scene": {"set": set_name}, "booth": {"views": ["hero"]}, "layers": []},
              open(os.path.join(effects, f"{name}.json"), "w"))
    json.dump({"set": set_name, "clip": scene.replace(os.sep, "/"), "clip_fps": 24.0, "cuts": []},
              open(os.path.join(measured, f"{set_name}.breakdown.json"), "w"))
    json.dump({"schema": 1, "duration": 1.2, "beats": [
        {"beat": "0 the hit", "scene": [0.2, 0.9], "t": 0.0, "len": 0.5, "hold": 0.0, "key": True},
        {"beat": "1 the going", "scene": [0.2, 0.9], "t": 0.5, "len": 0.7, "hold": 0.0, "key": False}]},
        open(os.path.join(measured, f"{set_name}.chart.json"), "w"))
    json.dump({"hue": [5.0, 55.0]}, open(os.path.join(measured, f"{set_name}_scene.json"), "w"))
    # the beat sheet the chart is drawn from (kit vfx chart): the same two beats, at their scene times
    open(os.path.join(measured, f"{set_name}.beats.md"), "w", encoding="utf-8", newline="\n").write(BEATS)
    return recording
