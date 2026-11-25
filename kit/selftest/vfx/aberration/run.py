#!/usr/bin/env python3
"""The self-test of CHROMATIC ABERRATION baked into a texture (kit/vfx/fxfinish.py `post.aberration`; the VFX methods
audit, stage 12).

    python kit/selftest/vfx/aberration/run.py good   a made white disc, four frames growing, packed by the real packer
                                                     with "aberration" (radial): in the sheet red reaches past the
                                                     disc's rim and blue stops short of it (a red fringe outside, a
                                                     yellow one inside), the middle of the disc is still white, the
                                                     bigger disc has the wider fringe, and the packer's own checks pass
    python kit/selftest/vfx/aberration/run.py faint  the same disc with an amount that parts the colours by half
                                                     a pixel: the packer must refuse it, saying "under a pixel"
                                                     (exit 1), and write no sheet

What each part does when it is wrong is proven in kit/test/python/test_vfx_aberration.py. Everything is written to a
folder of this run's own under build/selftest/, removed at the end. Nothing here shows a sheet in Roblox.
"""
import os
import shutil
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "edges"))
import run as edges_run  # noqa: E402  (its `pack`: the real packer on made frames)

N = edges_run.N
PASS = edges_run.PASS
RADII = [22, 30, 38, 46]


def disc(radius):
    yy, xx = np.mgrid[0:N, 0:N]
    a = (np.hypot(xx - N / 2 + 0.5, yy - N / 2 + 0.5) < radius).astype(np.float32)
    return np.dstack([a, a, a, a])


def fringe(cell):
    """how many pixels of the cell's middle row are red or yellow (red there, blue not)"""
    row = cell[N // 2]
    return int(((row[:, 0] > 0.6) & (row[:, 2] < 0.4) & (row[:, 3] > 0.5)).sum())


def main(argv):
    case = argv[0] if argv else "good"
    root = os.path.join("build", "selftest", f"vfx_aberration_{case}_{os.getpid()}")
    try:
        frames = [disc(r) for r in RADII]
        if case == "faint":
            code, said, sheet = edges_run.pack(root, "made_faint", frames, dict(PASS, aberration={"amount": 0.004}))
            if code == 0 or sheet is not None:
                return edges_run.say("pass", "aberration faint: an amount that parts the colours by under a pixel was packed", "kit/vfx/fxfinish.py aberration_block")
            return edges_run.say("fail", "aberration faint: " + str(said.get("summary", ""))[:300], str(said.get("next_action", ""))[:200])
        code, said, sheet = edges_run.pack(root, "made_split", frames, dict(PASS, aberration={"amount": 0.04}))
        if code != 0 or sheet is None:
            return edges_run.say("fail", "aberration good: the packer refused the made disc: " + str(said.get("summary", ""))[:240], "kit/vfx/fxfinish.py")
        problems = []
        first, last = sheet[:N, :N], sheet[N:, N:]  # radius 22 and radius 46
        out_x = N // 2 - 46 - 2  # two pixels outside the big disc's rim
        if not (last[N // 2, out_x, 0] > 0.9 and last[N // 2, out_x, 1] < 0.1 and last[N // 2, out_x, 2] < 0.1 and last[N // 2, out_x, 3] > 0.9):
            problems.append("no red fringe outside the disc's rim")
        in_x = N // 2 - 46 + 2
        if not (last[N // 2, in_x, 0] > 0.9 and last[N // 2, in_x, 1] > 0.9 and last[N // 2, in_x, 2] < 0.1):
            problems.append("blue does not stop short of the rim (no yellow just inside it)")
        if not (last[N // 2, N // 2, :3] > 0.98).all() or not (first[N // 2, N // 2, :3] > 0.98).all():
            problems.append("the middle of the disc is no longer white")
        if fringe(last) <= fringe(first) + 2:
            problems.append(f"the bigger disc's fringe is not the wider ({fringe(first)} px at radius 22, {fringe(last)} px at radius 46)")
        if last[4, 4, 3] > 0.01:
            problems.append("something drawn far outside the disc")
        if problems:
            return edges_run.say("fail", "aberration good: " + "; ".join(problems), "kit/vfx/fxfinish.py apply_aberration")
        return edges_run.say("pass", f"aberration good: a made white disc packed with aberration has red past its rim and blue short of it, a white middle, "
                             f"and a fringe that widens with the disc ({fringe(first)} px at radius 22, {fringe(last)} px at radius 46)", "none")
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
