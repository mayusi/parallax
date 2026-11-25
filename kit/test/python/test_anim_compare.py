"""kit/anim/compare.py - the reference beside the result (AAA plan #6): footage frames at the dossier's phase moments
beside our clip's look frames"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import compare as CP    # noqa: E402


def test_frames_from_a_video_and_a_look(tmp_path, monkeypatch):
    import cv2
    from PIL import Image
    vid = str(tmp_path / "v.mp4")
    w = cv2.VideoWriter(vid, cv2.VideoWriter_fourcc(*"mp4v"), 10, (64, 48))
    for i in range(20):
        w.write(np.full((48, 64, 3), i * 10, np.uint8))
    w.release()
    f = CP.footage_frame(vid, 1.0, h=96)
    assert f is not None and f.shape[0] == 96
    look = tmp_path / "Probe.r6.look"
    look.mkdir()
    for i in range(10):
        Image.new("RGB", (40, 30), (i * 20, 0, 0)).save(look / f"three-quarter_{i + 1:04d}.png")
    monkeypatch.setattr(CP, "BUILD", str(tmp_path))
    im = CP.ours_frame("Probe", 0.1, "three-quarter", 60, h=60)     # 0.1 s = 6 frames in -> the 7th png
    assert im.height == 60 and im.getpixel((0, 0))[0] == 120
