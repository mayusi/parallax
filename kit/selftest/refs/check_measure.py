"""check_measure.py — kit refs measure's orientation, on an X-long wedge (kit/selftest/refs/wedge_x.obj: 4 m long,
0.2 m tall at its back rising to 1.0 m at its front): the sections must run back -> front (u = 0 short, u = 1 tall) and
the side silhouette must show the front on the RIGHT, as every kit view does. A mirrored side (seen from +Y: +X on the
left) traced the length backwards while the sections ran forwards. Never "fix" this check or its wedge.

    python kit/selftest/refs/check_measure.py <measure.json>
"""

import json
import os
import sys

import numpy as np
from PIL import Image

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))


def main(argv):
    m = json.load(open(argv[0], encoding="utf-8"))
    st = m["stations"]
    rises = st[-1]["ry_mm"] > st[0]["ry_mm"] * 2
    im = np.asarray(Image.open(os.path.join(REPO, m["masks"]["side"])).convert("L")) > 127
    ys, xs = np.nonzero(im)
    w = xs.max() - xs.min()
    left = float(im[:, xs.min(): xs.min() + w // 10].sum(axis=0).mean())
    right = float(im[:, xs.max() - w // 10: xs.max()].sum(axis=0).mean())
    ok = rises and right > left * 2
    said = (f"sections {st[0]['ry_mm']:.0f} -> {st[-1]['ry_mm']:.0f} mm tall back to front; side silhouette "
            f"{left:.0f} px at its left end, {right:.0f} px at its right")
    print(json.dumps({"schema": 1, "status": "pass" if ok else "fail",
                      "summary": ("measure keeps the front on the right: " if ok else "MIRRORED or reversed: ") + said,
                      "next_action": "none" if ok else "fix kit/refs/measure.py's side camera (the front must show on the right)"}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
