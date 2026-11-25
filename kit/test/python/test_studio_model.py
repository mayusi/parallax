"""A built model in ROBLOX STUDIO with no upload (kit/tools/studio_model.py): the pure parts here - the shot's framing,
the watcher of model_shot.luau's on-screen steps (fed made pictures), the model's mask and the Blender twin's
comparison - and a REAL pack of the fade fixture through Blender: every group written centred (a MeshPart made from
an EditableMesh keeps its vertices where they are given; measured 2026-11-18), in Roblox's axes (its box is the
manifest's center and size_studs), UVs from the image's top, the maps raw RGBA, the scripts filled in. The Studio side
(the engine's own picture) is run by a session through the Studio tools; it cannot run here."""

import json
import math
import os
import subprocess
import sys
import unittest

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "tools"))
sys.path.insert(0, os.path.join(ROOT, "kit", "world"))
import cad_check  # noqa: E402
import studio_model as sm  # noqa: E402
import studio_shots  # noqa: E402

BLENDER = cad_check.blender()
OUT = os.path.join("build", "_test_studio_model")

WIN, VIEW = (900, 600), (100, 80, 800, 480)   # a window and the 3D view inside it (700 x 400)


def window(fill=None, scene=None):
    """a made picture of the Studio window: grey chrome, the 3D view covered by a signal colour or showing `scene`"""
    img = Image.new("RGB", WIN, (40, 40, 40))
    if fill:
        img.paste(Image.new("RGB", (VIEW[2] - VIEW[0], VIEW[3] - VIEW[1]), fill), VIEW[:2])
    elif scene:
        img.paste(scene, VIEW[:2])
    return img


def scene(with_model=True, shade=150):
    img = Image.new("RGB", (VIEW[2] - VIEW[0], VIEW[3] - VIEW[1]), (90, 160, 200))
    if with_model:
        ImageDraw.Draw(img).rectangle((300, 150, 399, 249), fill=(shade, shade, shade))
    return img


class Framing(unittest.TestCase):
    def test_the_whole_model_in_the_height_seen_from_its_front(self):
        eye, target = sm.framing([{"center": [0, 1, 0], "size": [2, 2, 2]}], fov=30)
        self.assertEqual(target, [0, 1, 0])
        far = math.dist(eye, target)
        self.assertAlmostEqual(far, math.sqrt(3) / math.sin(math.radians(15)) * sm.SHOT_ROOM, places=2)
        self.assertLess(eye[2], 0)                          # (Roblox's front is -Z)
        self.assertGreater(eye[1], target[1])               # (a little above)

    def test_several_groups_are_framed_as_one(self):
        _, target = sm.framing([{"center": [-1, 0, 0], "size": [1, 1, 1]}, {"center": [3, 0, 0], "size": [1, 1, 1]}])
        self.assertEqual(target, [1, 0, 0])


class WatchTheSteps(unittest.TestCase):
    def run_walk(self, frames):
        w = sm.Watch(studio_shots.flash_box, studio_shots.differ)
        states = [w.feed(f) for f in frames]
        return w, states

    def test_the_view_the_model_and_what_is_behind_it(self):
        m, b = window(scene=scene(True)), window(scene=scene(False))
        frames = [window(scene=scene(True))] + [window(sm.SIGNALS["start"])] * 2 + [m] * 3 \
            + [window(sm.SIGNALS["behind"])] * 2 + [b] * 3 + [window(sm.SIGNALS["end"])]
        w, states = self.run_walk(frames)
        self.assertEqual(states[0], "start")                # (nothing taken before the walk starts)
        self.assertEqual(w.state, "done")
        self.assertEqual(w.box, VIEW)
        self.assertEqual(w.views["model"].size, (700, 400))
        mask = sm.model_mask(w.views["model"], w.views["behind"])
        self.assertEqual(mask.getbbox(), (300, 150, 400, 250))

    def test_a_signal_never_becomes_a_view(self):
        # (the hold was too short: CYAN came before two reads of the model agreed - lost, not a cyan "model")
        frames = [window(sm.SIGNALS["start"]), window(scene=scene(True)), window(sm.SIGNALS["behind"]),
                  window(sm.SIGNALS["behind"])]
        w, _ = self.run_walk(frames)
        self.assertEqual(w.state, "lost")
        self.assertNotIn("model", w.views)

    def test_the_end_signal_is_never_taken_for_what_is_behind(self):
        frames = [window(sm.SIGNALS["start"]), window(scene=scene(True)), window(scene=scene(True)),
                  window(sm.SIGNALS["behind"]), window(sm.SIGNALS["end"]), window(sm.SIGNALS["end"])]
        w, _ = self.run_walk(frames)
        self.assertEqual(w.state, "lost")
        self.assertNotIn("behind", w.views)


class Compare(unittest.TestCase):
    def test_the_same_place_half_as_bright(self):
        studio = scene(True, shade=160)
        mask = sm.model_mask(studio, scene(False))
        twin = Image.new("RGBA", studio.size, (0, 0, 0, 0))
        ImageDraw.Draw(twin).rectangle((300, 150, 399, 249), fill=(80, 80, 80, 255))
        c = sm.compare(studio, mask, twin)
        self.assertEqual(c["iou"], 1.0)
        self.assertAlmostEqual(c["lum_ratio"], 0.5, places=2)

    def test_a_twin_standing_elsewhere_is_seen(self):
        studio = scene(True)
        mask = sm.model_mask(studio, scene(False))
        twin = Image.new("RGBA", studio.size, (0, 0, 0, 0))
        ImageDraw.Draw(twin).rectangle((350, 150, 449, 249), fill=(150, 150, 150, 255))
        self.assertLess(sm.compare(studio, mask, twin)["iou"], sm.IOU_BAR)


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class PackTheFadeFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        env = dict(os.environ, KIT_GAME="none", KIT_BUILD=OUT)
        cls.build = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                                    os.path.join(ROOT, "kit", "selftest", "blender", "build_fade.py"), "--",
                                    "--no-preview"], cwd=ROOT, capture_output=True, text=True, timeout=1800, env=env,
                                   encoding="utf-8", errors="replace")
        r = subprocess.run([sys.executable, os.path.join(ROOT, "kit", "tools", "studio_model.py"), "pack",
                            "_selftest_fade", "--build", OUT, "--port", "8799", "--at", "0,50,0"], cwd=ROOT,
                           capture_output=True, text=True, timeout=1800, encoding="utf-8", errors="replace")
        cls.code, cls.out = r.returncode, json.loads(r.stdout.strip().splitlines()[-1])
        cls.dir = os.path.join(ROOT, OUT, "studio", "_selftest_fade")
        with open(os.path.join(ROOT, OUT, "models", "_selftest_fade.manifest.json"), encoding="utf-8") as fh:
            cls.manifest = json.load(fh)

    def test_it_packs(self):
        self.assertEqual(self.build.returncode, 0, (self.build.stderr or self.build.stdout)[-800:])
        self.assertEqual((self.code, self.out["status"]), (0, "pass"), self.out["summary"])

    def test_every_group_is_centred_and_its_box_is_the_manifests(self):
        for group, entry in self.manifest["groups"].items():
            with open(os.path.join(self.dir, f"mesh_{group}.json"), encoding="utf-8") as fh:
                m = json.load(fh)
            for i in range(3):
                lo, hi = min(v[i] for v in m["verts"]), max(v[i] for v in m["verts"])
                self.assertAlmostEqual(lo + hi, 0.0, places=4, msg=(group, i))          # (centred)
                self.assertAlmostEqual(hi - lo, entry["size_studs"][i], delta=2e-3, msg=(group, i))
                mid = (m["bounds"][0][i] + m["bounds"][1][i]) / 2
                self.assertAlmostEqual(mid, entry["center"][i], delta=2e-3, msg=(group, i))   # (Roblox's axes)

    def test_the_uvs_count_from_the_images_top(self):
        # (the pane fades from clear at its FOOT to solid at its top: the map's alpha, read where the top vertices'
        #  UVs point, must be the solid end)
        from PIL import Image as PILImage  # noqa: PLC0415

        with open(os.path.join(self.dir, "mesh_pane.json"), encoding="utf-8") as fh:
            m = json.load(fh)
        model = json.load(open(os.path.join(self.dir, "model.json"), encoding="utf-8"))
        pane = next(g for g in model["groups"] if g["group"] == "pane")
        w, h = pane["maps"]["ColorMap"]["size"]
        raw = open(os.path.join(self.dir, pane["maps"]["ColorMap"]["file"]), "rb").read()
        self.assertEqual(len(raw), w * h * 4)
        img = PILImage.frombytes("RGBA", (w, h), raw)
        top, foot = [], []
        for t in m["tris"]:
            for k in range(3):
                y = m["verts"][t[k]][1]
                u, v = m["uvs"][t[3 + k]]
                a = img.getpixel((min(w - 1, int(u * w)), min(h - 1, int(v * h))))[3]
                (top if y > 1.4 else foot if y < -1.4 else []).append(a)
        self.assertGreater(min(top), 200, top)
        self.assertLess(max(foot), 60, foot)

    def test_the_written_normals_face_the_way_the_triangles_wind(self):
        # (review 2026-11-18: a mirror in the axes keeps every box and centre but turns the winding inside out)
        for group in self.manifest["groups"]:
            with open(os.path.join(self.dir, f"mesh_{group}.json"), encoding="utf-8") as fh:
                m = json.load(fh)
            for t in m["tris"]:
                a, b, c = (m["verts"][t[k]] for k in range(3))
                e1 = [b[i] - a[i] for i in range(3)]
                e2 = [c[i] - a[i] for i in range(3)]
                n = [e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0]]
                written = m["normals"][t[6]]
                self.assertGreater(sum(x * y for x, y in zip(n, written)), 0, (group, t))

    def test_the_twin_sees_the_post_where_the_camera_puts_it(self):
        # the twin's camera, offline: the fade fixture is NOT symmetric (the stone post at x = -1.25, the pane to its
        # +X side); a camera from its front (-Z) has Roblox's right along -X, so the post stands on the picture's
        # RIGHT. A mirrored twin draws the half-clear pane there instead (review 2026-11-18)
        model = json.load(open(os.path.join(self.dir, "model.json"), encoding="utf-8"))
        eye, target = sm.framing(model["groups"], 30.0)
        w, h = 480, 320
        f = [t - e for t, e in zip(target, eye)]
        k = math.sqrt(sum(x * x for x in f))
        f = [x / k for x in f]
        r = [f[1] * 0 - f[2] * 1, f[2] * 0 - f[0] * 0, f[0] * 1 - f[1] * 0]       # (look x world up)
        k = math.sqrt(sum(x * x for x in r))
        r = [x / k for x in r]
        u = [r[1] * f[2] - r[2] * f[1], r[2] * f[0] - r[0] * f[2], r[0] * f[1] - r[1] * f[0]]
        look = {"Brightness": 2, "Ambient": [70, 70, 70], "OutdoorAmbient": [128, 128, 128], "SunDirection": [-0.5, 0.8, -0.3],
                "camera": {"space": "model", "position": eye, "look": f, "up": u, "fov": 30.0, "viewport": [w, h]}}
        lj = os.path.join(ROOT, OUT, "twin_look.json")
        with open(lj, "w", encoding="utf-8") as fh:
            json.dump(look, fh)
        png = os.path.join(ROOT, OUT, "twin_test.png")
        r_ = subprocess.run([BLENDER, "-b", os.path.join(ROOT, OUT, "models", "_selftest_fade.blend"), "--factory-startup",
                             "--python-exit-code", "2", "-P", os.path.join(ROOT, "kit", "blender", "studio_twin.py"), "--",
                             os.path.join(ROOT, OUT, "models", "_selftest_fade.manifest.json"), lj, png], cwd=ROOT,
                            capture_output=True, text=True, timeout=900, encoding="utf-8", errors="replace")
        self.assertEqual(r_.returncode, 0, (r_.stderr or r_.stdout)[-800:])
        img = Image.open(png).convert("RGBA")

        def pixel(p):
            d = [p[i] - eye[i] for i in range(3)]
            z = sum(a * b for a, b in zip(d, f))
            t = math.tan(math.radians(15))
            x = sum(a * b for a, b in zip(d, r)) / z / t
            y = sum(a * b for a, b in zip(d, u)) / z / t
            return round(w / 2 + x * h / 2), round(h / 2 - y * h / 2)

        post = pixel((-1.25, 2.4, -0.5))
        self.assertGreater(post[0], w / 2, post)                          # (Roblox's -X: the picture's right)
        self.assertGreater(img.getpixel(post)[3], 230, post)              # (the solid post, not the fading pane)
        self.assertLess(img.getpixel(pixel((-2.2, 1.5, 0.0)))[3], 20)       # (beside the post: nothing)

    def test_a_folder_it_did_not_write_is_never_emptied(self):
        keep = os.path.join(ROOT, OUT, "not_mine")
        os.makedirs(keep, exist_ok=True)
        with open(os.path.join(keep, "precious.txt"), "w", encoding="utf-8") as fh:
            fh.write("x")
        r = subprocess.run([sys.executable, os.path.join(ROOT, "kit", "tools", "studio_model.py"), "pack",
                            "_selftest_fade", "--build", OUT, "--out", keep], cwd=ROOT, capture_output=True, text=True,
                           timeout=600, encoding="utf-8", errors="replace")
        self.assertNotEqual(r.returncode, 0)
        self.assertTrue(os.path.isfile(os.path.join(keep, "precious.txt")))

    def test_the_game_s_alpha_rule_and_the_scripts(self):
        model = json.load(open(os.path.join(self.dir, "model.json"), encoding="utf-8"))
        pane = next(g for g in model["groups"] if g["group"] == "pane")
        self.assertEqual((pane["alpha_mode"], pane["alpha_soft"]), ("Transparency", True))
        for f in ("load.luau", "shot.luau", "cost.luau"):
            src = open(os.path.join(self.dir, f), encoding="utf-8").read()
            self.assertNotIn("{{", src, f)
        self.assertIn('local BASE = "http://127.0.0.1:8799"', open(os.path.join(self.dir, "load.luau"),
                                                                     encoding="utf-8").read())


if __name__ == "__main__":
    unittest.main()
