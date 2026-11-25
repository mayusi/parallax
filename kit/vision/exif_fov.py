"""exif_fov.py — the horizontal field of view a photo was taken with, from its EXIF (35 mm equivalent focal length):
camera fitting then has one unknown less (a lens is the hardest thing to read from a silhouette).

    python kit/vision/exif_fov.py <photo>   -> {"fov": degrees | null, "f35": mm | null}
"""

import json
import math
import sys

from PIL import Image


def fov_of(path):
    try:
        img = Image.open(path)
        exif = img.getexif()
        sub = exif.get_ifd(0x8769) if hasattr(exif, "get_ifd") else {}
        f35 = sub.get(41989) or exif.get(41989)  # FocalLengthIn35mmFilm
        if not f35:
            return None, None
        w, h = img.size
        long_side = 36.0 if w >= h else 24.0  # the frame's horizontal extent on 35 mm film
        return round(math.degrees(2 * math.atan(long_side / (2 * float(f35)))), 2), float(f35)
    except Exception:  # noqa: BLE001 — no EXIF is an answer (null), never a crash
        return None, None


if __name__ == "__main__":
    fov, f35 = fov_of(sys.argv[1])
    print(json.dumps({"schema": 1, "status": "pass", "summary": f"exif: fov {fov} deg" if fov else "exif: no lens recorded",
                      "next_action": "none", "fov": fov, "f35": f35}))
