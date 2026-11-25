"""clips.py — two small made clips for the dailies' proof (kit selftest + kit/test/python/test_vfx_dailies.py): a
"scene" whose fire is there in ONE frame, drawn on twos, and stays until the clip ends; and "ours", which grows over
a few frames, freezes four, and goes. Every number the read should give is known from how the frames are made:

    the scene (24 a second)   8 dark frames, then a fire disc at full size at once, a new drawing every 2 frames
                              (it flickers between two sizes), 16 frames, and the clip ends while it is lit
    ours (30 a second)        10 dark frames; a disc of radius 15, 30, 45, then 60; two more drawings near full
                              size; ONE drawing held four frames (a hit-stop); six drawings shrinking; 10 dark frames
    blank (30 a second)       40 dark frames: a recording that shows nothing

The fire is orange with a white-hot middle on a blue-grey night: in the hue band 5-55 the kit measures for fire.
"""

import subprocess

import numpy as np

W, H = 320, 180
HUE = (5.0, 55.0)
YY, XX = np.mgrid[0:H, 0:W]


def frame(radius=0):
    f = np.zeros((H, W, 3), dtype=np.uint8)
    f[:] = (38, 50, 68)
    if radius:
        f[(XX - 160) ** 2 + (YY - 90) ** 2 <= radius * radius] = (240, 130, 30)
        f[(XX - 160) ** 2 + (YY - 90) ** 2 <= (radius // 3) ** 2] = (255, 250, 240)
    return f


def scene_frames():
    out = [frame() for _ in range(8)]
    for k in range(8):
        out += [frame(60 - 3 * (k % 2))] * 2
    return np.stack(out)


def our_frames():
    out = [frame() for _ in range(10)]
    out += [frame(15), frame(30), frame(45), frame(60), frame(54), frame(60)]
    out += [frame(56)] * 4
    out += [frame(r) for r in (50, 40, 30, 20, 12, 6)]
    out += [frame() for _ in range(10)]
    return np.stack(out)


def blank_frames():
    return np.stack([frame() for _ in range(40)])


def write(path, frames, fps):
    """frames (N, H, W, 3) -> an mp4 at `fps` (near-lossless, so a held drawing stays one drawing)"""
    n, h, w, _ = frames.shape
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps),
                    "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "8", "-pix_fmt", "yuv420p", path],
                   input=frames.tobytes(), check=True, timeout=300)
    return path
