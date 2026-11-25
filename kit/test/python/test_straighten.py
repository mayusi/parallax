"""kit trace --straighten: a profile photographed by a camera turned away from it (a real perspective: K R K^-1 for a
camera yawing about its vertical axis — NOT the straightening's own model) must trace back to its true shape. Shapes
are compared bbox-fitted, as the silhouette check compares them (straightening is right up to a stretch along the
length, which the bbox fit removes)."""

import os
import sys
import unittest

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "blender"))
import trace as T  # noqa: E402  (kit/blender/trace.py: system python, no bpy)

W, H = 1400, 700
PROFILE = [(250, 300), (1150, 300), (1150, 340), (720, 340), (720, 420), (640, 420), (640, 345),  # barrel, receiver
           (560, 345), (520, 470), (470, 470), (500, 345), (350, 345), (330, 400), (250, 400)]  # grip, stock


def true_mask():
    im = Image.new("L", (W, H), 0)
    ImageDraw.Draw(im).polygon(PROFILE, fill=255)
    return np.asarray(im) > 127


def yaw_homography(deg, f=900.0):
    """a pinhole camera turned `deg` about its vertical axis (the plane seen head-on before), then re-framed so the
    whole object stays in the picture (a photographer keeps the subject in frame) -> (3x3, canvas size)"""
    k = np.array([[f, 0, W / 2], [0, f, H / 2], [0, 0, 1]])
    t = np.radians(deg)
    r = np.array([[np.cos(t), 0, np.sin(t)], [0, 1, 0], [-np.sin(t), 0, np.cos(t)]])
    h = k @ r @ np.linalg.inv(k)
    pts = np.c_[np.array(PROFILE, float), np.ones(len(PROFILE))] @ h.T
    pts = pts[:, :2] / pts[:, 2:]
    lo, hi = pts.min(0) - 60, pts.max(0) + 60
    shift = np.array([[1, 0, -lo[0]], [0, 1, -lo[1]], [0, 0, 1]])
    return shift @ h, (int(hi[0] - lo[0]), int(hi[1] - lo[1]))


def camera_yaw(mask, deg, f=900.0):
    h, size = yaw_homography(deg, f)
    return T._warp_mask(mask, h, size)


def fit(mask, size=(600, 200)):
    ys, xs = np.nonzero(mask)
    crop = Image.fromarray((mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1] * 255).astype(np.uint8))
    return np.asarray(crop.resize(size, Image.NEAREST)) > 127


def iou(a, b):
    a, b = fit(a), fit(b)
    return float((a & b).sum() / max(1, (a | b).sum()))


class TestStraighten(unittest.TestCase):
    def test_yawed_camera_traces_back(self):
        truth = true_mask()
        for deg in (30, 40):
            seen = camera_yaw(truth, deg)
            before = iou(seen, truth)
            self.assertTrue(T._perspective(seen)["suspect"], f"{deg} deg: the perspective check should flag it")
            hv = T.straighten_homography(seen)
            self.assertIsNotNone(hv, f"{deg} deg: no straightening found")
            h, size, _vp = hv
            fixed = T._warp_mask(seen, h, size)
            after = iou(fixed, truth)
            self.assertGreaterEqual(after, 0.95, f"{deg} deg: straightened IoU {after:.3f} (was {before:.3f})")
            self.assertGreater(after, before, f"{deg} deg: straightening made it worse ({before:.3f} -> {after:.3f})")
            self.assertFalse(T._perspective(fixed)["suspect"], f"{deg} deg: still converging after straightening")

    def test_the_lines_frame_is_cut_like_the_straightened_trace(self):
        """the lines / perceptual checks re-cut the photo from the trace's record: with --straighten they must apply the
        same warp (kept in the trace), or the photo frame stays converging while the trace is straight"""
        import tempfile

        import socket  # noqa: PLC0415

        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "vision"))
        # importing the vision code installs its offline guard (no socket may connect, by design): this test only
        # cuts a photo, so the guard is put back off for the rest of the suite (the worker test talks to 127.0.0.1)
        saved = [(socket.socket, k, getattr(socket.socket, k)) for k in ("connect", "connect_ex", "sendto")] + [
            (socket, k, getattr(socket, k)) for k in ("create_connection", "getaddrinfo")]
        try:
            import lines as L  # noqa: E402,PLC0415
        finally:
            for owner, k, v in saved:
                setattr(owner, k, v)

        seen = camera_yaw(true_mask(), 35)
        h, size, _vp = T.straighten_homography(seen)
        traced = fit(T._warp_mask(seen, h, size))
        with tempfile.TemporaryDirectory() as d:
            photo = os.path.join(d, "yawed.png")
            Image.fromarray(np.where(seen[..., None], 60, 245).repeat(3, axis=2).astype(np.uint8)).save(photo)
            info = {"photo": photo, "box": None, "rotate": 0, "bg": "light", "threshold": 28.0,
                    "straighten": {"homography": np.asarray(h, float).ravel().tolist(), "size": list(size)}}
            _rgb, with_warp = L.photo_frame(info)
            _rgb, without = L.photo_frame(dict(info, straighten=None))
        self.assertGreaterEqual(iou(fit(with_warp), traced), 0.95)
        self.assertLess(iou(fit(without), traced), iou(fit(with_warp), traced))

    def test_square_on_picture_left_alone(self):
        """a true side view has nothing to undo: no transform (or one that changes nothing)"""
        truth = true_mask()
        hv = T.straighten_homography(truth)
        if hv is not None:
            h, size, _vp = hv
            self.assertGreaterEqual(iou(T._warp_mask(truth, h, size), truth), 0.98)


if __name__ == "__main__":
    unittest.main()
