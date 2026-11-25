"""test_world_paint_roles.py - A LAND MAY HOLD MORE THAN TEN PAINTED ROLES (LIMITATIONS_FIXES_V3.md stage E.1).
The painter wrote one decimal digit a cell, so rivers.py refused a land that already had ten roles ("no room for
river") and an eleventh role written by str() took two characters and shifted every cell after it. Now a role is ONE
CHARACTER a cell, chr(48 + role) - "0".."9" exactly as before (old lands read the same, byte for byte), then ":" ";"
"<" ... "~" (79 roles). Held here: the codec both ways, rivers.py on a land of 12 roles (it adds the 13th, keeps the
others where they were), the web viewer's packing. The Luau readers (environment.luau, World.roleAt, the runtime,
the snow lock) are held in kit/test/spec/worldpaint.spec.luau."""
import importlib.util
import json
import os
import sys
import tempfile
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
WORLD = os.path.join(HERE, "..", "..", "world")
sys.path.insert(0, WORLD)


def load(name):
    spec = importlib.util.spec_from_file_location(f"kit_world_{name}_paintroles", os.path.join(WORLD, f"{name}.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


T = load("terrain")
R = load("rivers")
W = load("web")

TWELVE = ["meadow", "lush", "dirt", "mud", "rock", "cliff", "snow", "sand", "scree", "moss", "gravel", "ash"]


def valley(n=48):
    x = np.arange(n)[:, None]
    z = np.arange(n)[None, :]
    return (np.abs(x - n // 2) * 2.0 + (n - z) * 0.5).astype(float)


class Codec(unittest.TestCase):
    def test_the_first_ten_roles_are_the_old_digits(self):
        a = np.arange(10).repeat(3)
        self.assertEqual(T.paint_encode(a), "".join(map(str, a.tolist())))  # (what terrain.py wrote before)

    def test_every_role_round_trips_in_one_character(self):
        a = np.arange(T.PAINT_MAX)
        s = T.paint_encode(a)
        self.assertEqual(len(s), T.PAINT_MAX)
        self.assertGreaterEqual(T.PAINT_MAX, 64)
        self.assertEqual(T.paint_decode(s).tolist(), a.tolist())
        self.assertEqual(T.paint_decode(s[:12], (3, 4)).shape, (3, 4))
        self.assertEqual(s[10:13], ":;<")
        json.loads(json.dumps({"paint": s}))  # (every character survives the heightmap's JSON)

    def test_a_role_out_of_range_is_refused(self):
        with self.assertRaises(ValueError):
            T.paint_encode(np.array([T.PAINT_MAX]))
        with self.assertRaises(ValueError):
            T.paint_encode(np.array([-1]))
        with self.assertRaises(ValueError):
            T.paint_decode("01/")  # ("/" is 47: under "0")


class RiversOnTwelveRoles(unittest.TestCase):
    def test_rivers_adds_the_thirteenth_and_keeps_the_rest(self):
        h = valley()
        nx, nz = h.shape
        rng = np.random.default_rng(7)
        before = rng.integers(0, len(TWELVE), size=(nx, nz))
        before[before == TWELVE.index("cliff")] = 0  # (rivers never paints a cliff: keep the test about the code)
        hm = {"nx": nx, "nz": nz, "step": 4.0, "heights": h.ravel().tolist(), "roles": list(TWELVE),
              "paint": T.paint_encode(before)}
        fd, path = tempfile.mkstemp(suffix=".hm.json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(hm, fh)
        self.assertEqual(R.main([path, "--share", "0.03", "--out", path + ".png"]), 0)
        out = json.load(open(path, encoding="utf-8"))
        self.assertEqual(out["roles"], TWELVE + ["river"])
        self.assertEqual(len(out["paint"]), nx * nz)  # (one character a cell: nothing shifted)
        after = T.paint_decode(out["paint"], (nx, nz))
        river = after == 12
        self.assertGreater(int(river.sum()), 8)
        self.assertTrue(np.array_equal(after[~river], before[~river]))  # every other cell kept its own role
        self.assertTrue(set(out["paint"]) >= {"<"})  # ("<" = 60 = role 12, the river)
        # run again: idempotent (the old river handed back, the new one painted the same)
        self.assertEqual(R.main([path, "--share", "0.03", "--out", path + ".png"]), 0)
        again = json.load(open(path, encoding="utf-8"))
        self.assertEqual(again["roles"], out["roles"])
        self.assertEqual(again["paint"], out["paint"])


class WebViewer(unittest.TestCase):
    def test_the_page_packs_every_role(self):
        mats = W.TERRAIN_MATS
        palette = [mats[i % len(mats)] for i in range(13)]
        roles = T.paint_encode(np.array([0, 9, 10, 12]))
        packed = W.pack_splat({"roles": roles, "palette": palette, "nx": 2, "nz": 2, "x0": 0, "z0": 0, "w": 1, "d": 1})
        import base64

        raw = list(base64.b64decode(packed["data"]))
        self.assertEqual(raw, [mats.index(palette[i]) for i in (0, 9, 10, 12)])


if __name__ == "__main__":
    unittest.main()
