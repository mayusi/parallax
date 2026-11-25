"""The photogrammetry tool's own readers (kit/tools/photoscan.py; his D-R02): COLMAP's text model and a PLY header."""

import math
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "tools"))
import photoscan as P  # noqa: E402


def write(folder, name, text):
    with open(os.path.join(folder, name), "w", encoding="utf-8") as fh:
        fh.write(text)


class Model(unittest.TestCase):
    def test_a_camera_is_placed_where_its_pose_says_and_its_up_is_the_image_up(self):
        with tempfile.TemporaryDirectory() as d:
            # one camera turned 90 degrees about the world's x, 2 units back along its own axis; and a level one
            q = math.sqrt(0.5)
            write(d, "images.txt", "# header\n"
                  f"1 {q} {q} 0 0 0 0 2 1 tilted.jpg\n\n"
                  "2 1 0 0 0 0 0 5 1 level.jpg\n\n")
            write(d, "points3D.txt", "# header\n1 0 0 0 255 255 255 0.5 1 0\n2 1 1 1 255 255 255 1.5 1 1\n")
            m = P.read_model(d)
        level = next(c for c in m["cameras"] if c["image"] == "level.jpg")
        self.assertEqual([round(x, 6) for x in level["centre"]], [0, 0, -5])
        self.assertEqual([round(x, 6) for x in level["up"]], [0, -1, 0])     # (COLMAP's image y points DOWN)
        tilted = next(c for c in m["cameras"] if c["image"] == "tilted.jpg")
        self.assertAlmostEqual(sum(x * x for x in tilted["up"]), 1.0)
        self.assertEqual((m["points"], m["error"]), (2, 1.0))


class Ply(unittest.TestCase):
    def test_the_vertex_count_is_read_from_the_header_and_an_empty_file_is_none(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.ply")
            with open(p, "wb") as fh:
                fh.write(b"ply\nformat binary_little_endian 1.0\nelement vertex 1234\nproperty float x\n"
                         b"end_header\n" + b"\0" * 64)
            self.assertEqual(P.ply_vertices(p), 1234)
            with open(p, "wb") as fh:
                fh.write(b"ply\nformat binary_little_endian 1.0\nelement vertex 0\nend_header\n")
            self.assertEqual(P.ply_vertices(p), 0)
            self.assertEqual(P.ply_vertices(os.path.join(d, "none.ply")), 0)


class Photos(unittest.TestCase):
    def test_a_portrait_photo_is_turned_upright_by_its_own_flag(self):
        from PIL import Image  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as d:
            src, dst = os.path.join(d, "in"), os.path.join(d, "out")
            os.makedirs(src)
            for i in range(3):   # stored 400 x 300 on its side, with the phone's "turn 90" flag (orientation 6)
                im = Image.new("RGB", (400, 300), (i * 40, 0, 0))
                exif = im.getexif()
                exif[0x0112] = 6
                im.save(os.path.join(src, f"p{i} a.jpg"), exif=exif)
            names = P.prepare(src, dst)
            self.assertEqual(len(names), 3)
            with Image.open(os.path.join(dst, names[0])) as up:
                self.assertEqual(up.size, (300, 400))

    def test_photos_of_different_sizes_are_refused_by_name(self):
        from PIL import Image  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "in")
            os.makedirs(src)
            for i in range(3):
                Image.new("RGB", (400, 300)).save(os.path.join(src, f"a{i}.jpg"))
            Image.new("RGB", (300, 300)).save(os.path.join(src, "odd.jpg"))
            with self.assertRaises(ValueError) as e:
                P.prepare(src, os.path.join(d, "out"))
            self.assertIn("odd.jpg (300 x 300)", str(e.exception))

    def test_a_folder_it_did_not_make_is_never_deleted(self):
        with tempfile.TemporaryDirectory() as d:
            work = os.path.join(d, "mine")
            os.makedirs(work)
            write(work, "keep.txt", "the owner's")
            with self.assertRaises((ValueError, RuntimeError)):
                P.scan(os.path.join(d, "photos_none"), "x", work=work) if os.path.isfile(P.COLMAP) else \
                    (_ for _ in ()).throw(ValueError("no COLMAP here"))
            self.assertTrue(os.path.isfile(os.path.join(work, "keep.txt")))

    def test_a_stopped_clear_keeps_the_mark_and_the_next_one_finishes(self):
        # (2026-11-18: rmtree took the mark first, a file another run held stopped it, and every later run refused
        #  the folder - the photoscan and delight tests red until someone deleted it by hand)
        with tempfile.TemporaryDirectory() as d:
            work = os.path.join(d, "work")
            os.makedirs(os.path.join(work, "dense"))
            write(work, P.MARK, "")
            write(work, "a.json", "{}")
            write(os.path.join(work, "dense"), "fused.ply", "x")
            real = P.os.remove

            def held(path):
                if path.endswith("a.json"):
                    raise PermissionError(13, "in use by another run", path)
                return real(path)

            P.os.remove = held
            try:
                with self.assertRaises(PermissionError):
                    P.clear_work(work)
            finally:
                P.os.remove = real
            self.assertTrue(os.path.isfile(os.path.join(work, P.MARK)))
            P.clear_work(work)
            self.assertEqual(os.listdir(work), [P.MARK])


class Level(unittest.TestCase):
    def cams(self, degrees, tilt=0.0):
        out = []
        for a in degrees:
            r = math.radians(a)
            out.append({"centre": [2 * math.cos(r), 2 * math.sin(r), 0.0], "up": [math.sin(tilt), 0.0, -math.cos(tilt)]})
        return out

    def test_a_full_level_ring_agrees_and_leaves_no_wide_gap(self):
        lv = P.levelling(self.cams(range(0, 360, 30)))
        self.assertGreater(lv["agreement"], 0.99)
        self.assertAlmostEqual(lv["gap"], 30.0, places=3)

    def test_a_half_orbit_leaves_a_wide_gap(self):
        self.assertGreater(P.levelling(self.cams(range(0, 181, 30)))["gap"], P.ORBIT_GAP)

    def test_cameras_on_their_sides_round_a_ring_do_not_agree(self):
        side = [{"centre": [2 * math.cos(math.radians(a)), 2 * math.sin(math.radians(a)), 0.0],
                 "up": [-math.sin(math.radians(a)), math.cos(math.radians(a)), 0.0]} for a in range(0, 360, 30)]
        self.assertLess(P.levelling(side)["agreement"], P.UP_BAR)


class Names(unittest.TestCase):
    def test_a_photo_name_with_spaces_is_read_whole(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "images.txt", "# h\n1 1 0 0 0 0 0 5 1 photo 005 left.jpg\n\n")
            write(d, "points3D.txt", "# h\n")
            self.assertEqual(P.read_model(d)["cameras"][0]["image"], "photo 005 left.jpg")
            self.assertEqual(P._image_rows(d)[0][4], "photo 005 left.jpg")


class Bars(unittest.TestCase):
    def test_the_outline_bars_sit_between_what_was_measured(self):
        self.assertTrue(0.88 < P.OUTLINE_BAR < 0.99)       # (a doubled scan 0.88, a good one 0.99)
        self.assertTrue(0.79 < P.OUTLINE_WORST < 0.98)     # (the doubled scan's worst photo 0.79)
        self.assertEqual(P.TRIMS[0], 7)                    # (COLMAP's own 10 emptied the urn's surface)


if __name__ == "__main__":
    unittest.main()
