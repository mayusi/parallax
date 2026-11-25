"""kit/gen/views_rig.py: the kit's views as Pixal3D cameras — the main view lands on Pixal3D's canonical front camera,
every view projects a Roblox point where Pixal3D's own projection puts it, the exported GLB comes back in Roblox
space, and the extents fitted from the pictures' aspect ratios are the object's."""

import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "gen"))
import views_rig as R  # noqa: E402

RES = 512


def pixal3d_project(p_world, c2w, fov_deg, res):
    """Pixal3D's project_points_to_image_batch for one camera (its pixel x / y, before its half-pixel offset)"""
    pc = (np.linalg.inv(c2w) @ np.append(p_world, 1.0))[:3]
    f = 16.0 / math.tan(math.radians(fov_deg) / 2) * res / 32.0
    return np.array([f * pc[0] / -pc[2] + res / 2, -f * pc[1] / -pc[2] + res / 2])


def grid_to_world(raw):
    """Pixal3D's ProjGrid: a voxel-grid point (x, y, z) sits at (x, -z, y) in its world"""
    return np.array([raw[0], -raw[2], raw[1]])


def ovoxel_glb(raw):
    """o_voxel's GLB export: (x, y, z) -> (x, z, -y)"""
    return np.array([raw[0], raw[2], -raw[1]])


class TestViewsRig(unittest.TestCase):
    def test_the_main_view_is_pixal3d_canonical_front_camera(self):
        for main in R.MAIN_PREFERENCE:
            for fov in (R.ORTHO_FOV, R.PERSPECTIVE_FOV):
                d = R.distance(fov)
                front = np.array([[1, 0, 0, 0], [0, 0, -1, -d], [0, 1, 0, 0], [0, 0, 0, 1.0]])
                self.assertTrue(np.allclose(R.c2w(main, main, fov), front), (main, fov))

    def test_pixal3d_example_rig_is_the_perspective_rig(self):
        self.assertAlmostEqual(R.distance(R.PERSPECTIVE_FOV), 3.1192, places=3)

    def test_every_view_projects_like_pixal3d(self):
        rng = np.random.default_rng(0)
        pts = rng.uniform(-0.5, 0.5, (20, 3))
        for main in R.MAIN_PREFERENCE:
            rot = R.world_rotation(main)
            for view in R.ORDER:
                for fov in (R.ORTHO_FOV, R.PERSPECTIVE_FOV):
                    ours = R.project(pts, view, fov, RES)[:, :2]
                    theirs = np.array([pixal3d_project(rot @ p, R.c2w(view, main, fov), fov, RES) for p in pts])
                    self.assertLess(np.abs(ours - theirs).max(), 1e-6, (main, view, fov))

    def test_the_exported_glb_comes_back_in_roblox_space(self):
        rng = np.random.default_rng(1)
        for main in R.MAIN_PREFERENCE:
            rot, back = R.world_rotation(main), R.glb_to_roblox(main)
            for p in rng.uniform(-0.5, 0.5, (10, 3)):
                world = rot @ p
                raw = np.array([world[0], world[2], -world[1]])  # the grid point at that world position
                self.assertTrue(np.allclose(grid_to_world(raw), world))
                self.assertTrue(np.allclose((back @ np.append(ovoxel_glb(raw), 1.0))[:3], p), main)
            self.assertAlmostEqual(np.linalg.det(back[:3, :3]), 1.0)

    def test_main_front_is_pixal3d_own_turn(self):
        rot = np.array([[-1, 0, 0, 0], [0, 0, -1, 0], [0, -1, 0, 0], [0, 0, 0, 1.0]])
        self.assertTrue(np.allclose(R.glb_to_roblox("front"), rot))

    def test_the_kit_picture_conventions(self):
        c = RES / 2
        front_pt, right_pt, top_pt = np.array([0, 0, -0.4]), np.array([0.4, 0, 0]), np.array([0, 0.4, 0])
        side = R.project(np.stack([front_pt, top_pt]), "side", R.ORTHO_FOV, RES)
        self.assertGreater(side[0, 0], c)  # side: the model's front on the right
        self.assertLess(side[1, 1], c)  # up is up
        front = R.project(right_pt[None], "front", R.ORTHO_FOV, RES)
        self.assertLess(front[0, 0], c)  # front: the model's right (+X) on the picture's left
        top = R.project(np.stack([front_pt, right_pt]), "top", R.ORTHO_FOV, RES)
        self.assertLess(top[0, 1], c)  # top: the front at the top of the picture
        self.assertGreater(top[1, 0], c)  # +X on the right
        back = R.project(right_pt[None], "back", R.ORTHO_FOV, RES)
        self.assertGreater(back[0, 0], c)

    def test_extents_from_aspect_ratios(self):
        ext = np.array([0.3, 0.5, 1.0])
        sizes = {"side": (ext[2] * 700, ext[1] * 700), "front": (ext[0] * 90, ext[1] * 90),
                 "top": (ext[0] * 333, ext[2] * 333)}
        got, off = R.fit_extents(sizes)
        self.assertTrue(np.allclose(got, ext))
        self.assertTrue(all(abs(v) < 1e-6 for v in off.values()))

    def test_disagreeing_views_are_reported(self):
        got, off = R.fit_extents({"side": (100, 50), "front": (30, 50), "back": (36, 50)})
        self.assertGreater(abs(off["back"]), 5)
        self.assertAlmostEqual(got.max(), 1.0)

    def test_views_that_miss_an_axis_are_refused(self):
        with self.assertRaises(ValueError):
            R.fit_extents({"front": (30, 50), "back": (30, 50)})
        with self.assertRaises(ValueError):
            R.choose_main({"top": "t.png"})

    def test_framed_picture_has_the_fitted_size(self):
        ext = np.array([0.3, 0.5, 1.0])
        k = R.frame_scale("side", (400, 200), ext, RES)
        s = (RES / 2) / R.HALF
        self.assertAlmostEqual(400 * k, ext[2] * s, places=6)
        self.assertAlmostEqual(200 * k, ext[1] * s, places=6)

    def test_transforms_put_the_main_view_first(self):
        t = R.transforms({"side": "s.png", "top": "t.png", "front": "f.png"}, "front", R.ORTHO_FOV)
        self.assertEqual([f["name"] for f in t["frames"]], ["front", "side", "top"])
        self.assertAlmostEqual(t["camera_angle_x"], math.radians(R.ORTHO_FOV))


if __name__ == "__main__":
    unittest.main()
