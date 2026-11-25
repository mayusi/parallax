"""kit/vfx/legacy.py (kit vfx migrate; the V3 doc, VFX stage A.1): the four legacy preset keys found and fixed - a
sprite's spreadAngle -> spread, a fov layer's fov -> delta, a shake's frequency dropped, a big opaque ground card
standing up (FacingCameraWorldUp) - by the validator's own rules; the report writes nothing, --apply rewrites only the
named presets (key order and the file's layout kept, run twice = the same), and a piece the owner judged is refused
without his words."""

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "vfx"))
import legacy  # noqa: E402


def card(**kw):
    el = {"name": "wall", "kind": "sprite", "point": [0, 0, 0], "size": [[0, 20], [1, 80]]}
    el.update(kw)
    return el


class Rules(unittest.TestCase):
    def test_each_key_is_found_with_its_fix(self):
        p = {"version": 3, "layers": [
            {"kind": "sprite", "spreadAngle": [20, 20]},
            {"kind": "sprite", "spreadAngle": [5, 5], "spread": [30, 30]},
            {"kind": "fov", "fov": [[0, 0], [1, 6]]},
            {"kind": "shake", "frequency": 9},
            card(),
        ]}
        got = [(h["path"], h["fix"]) for h in legacy.hits(p)]
        self.assertEqual(got, [
            ("layers[1].spreadAngle", "rename to spread"),
            ("layers[2].spreadAngle", "drop (spread is set)"),
            ("layers[3].fov", "rename to delta"),
            ("layers[4].frequency", "drop"),
            ("layers[5].orientation", 'set "FacingCameraWorldUp"'),
        ])

    def test_keys_the_validator_does_not_warn_on_are_not_touched(self):
        # spreadAngle on a non-sprite, frequency on a non-shake, fov on a non-fov layer: the validator says nothing
        p = {"layers": [{"kind": "mesh", "spreadAngle": 3}, {"kind": "light", "frequency": 2},
                        {"kind": "camera", "fov": 70}]}
        self.assertEqual(legacy.hits(p), [])

    def test_the_card_rule_is_the_validators(self):
        self.assertTrue(legacy.big_ground_card(card(), None))
        self.assertTrue(legacy.big_ground_card(card(size=40), None))
        self.assertFalse(legacy.big_ground_card(card(size=39), None))                  # under 40 studs
        self.assertFalse(legacy.big_ground_card(card(point=[0, 50, 0]), None))         # bottom off the floor
        self.assertTrue(legacy.big_ground_card(card(point=[0, 41, 0]), None))          # 41 - 80 / 2 = 1: on it
        self.assertFalse(legacy.big_ground_card(card(lightEmission=0.5), None))        # bright, additive
        self.assertFalse(legacy.big_ground_card(card(orientation="FacingCameraWorldUp"), None))
        self.assertTrue(legacy.big_ground_card(card(orientation="FacingCamera"), None))
        self.assertTrue(legacy.big_ground_card(card(point="g"), {"g": [0, 0, 0]}))     # a named point
        self.assertFalse(legacy.big_ground_card(card(point="@blade"), {}))            # an attachment: unknown

    def test_migrated_renames_in_place_and_keeps_the_rest(self):
        p = {"layers": [{"name": "a", "kind": "sprite", "spreadAngle": [9, 9], "count": 4},
                        {"name": "b", "kind": "fov", "fov": [[0, 1]], "life": 1},
                        {"name": "c", "kind": "shake", "frequency": 3, "amplitude": 1},
                        card(color="gold")]}
        before = json.dumps(p)
        m = legacy.migrated(p)
        self.assertEqual(json.dumps(p), before)  # the original untouched
        self.assertEqual(list(m["layers"][0]), ["name", "kind", "spread", "count"])
        self.assertEqual(m["layers"][0]["spread"], [9, 9])
        self.assertEqual(list(m["layers"][1]), ["name", "kind", "delta", "life"])
        self.assertNotIn("frequency", m["layers"][2])
        self.assertEqual(m["layers"][3]["orientation"], "FacingCameraWorldUp")
        self.assertEqual(legacy.hits(m), [])


class InPlace(unittest.TestCase):
    """the rewrite changes the keys it fixes and nothing else in the file"""

    def test_a_one_line_layer_keeps_its_line(self):
        text = ('{\n  "version": 3,\n  "layers": [\n'
                '    { "name": "a", "kind": "sprite", "spreadAngle": [9, 9], "count": 4 },\n'
                '    { "name": "b", "kind": "shake", "amplitude": 1, "frequency": 3 },\n'
                '    { "name": "c", "kind": "fov", "fov": [[0, 1]] }\n  ]\n}\n')
        self.assertEqual(legacy.rewrite(text), (
            '{\n  "version": 3,\n  "layers": [\n'
            '    { "name": "a", "kind": "sprite", "spread": [9, 9], "count": 4 },\n'
            '    { "name": "b", "kind": "shake", "amplitude": 1 },\n'
            '    { "name": "c", "kind": "fov", "delta": [[0, 1]] }\n  ]\n}\n'))

    def test_drops_first_middle_last_and_an_insert_beside_a_drop(self):
        lines = [
            '{"kind": "shake", "frequency": 3, "amplitude": 1}',                   # first
            '{"amplitude": 1, "kind": "shake", "frequency": 3, "life": 1}',        # middle
            '{"kind": "sprite", "point": [0,0,0], "size": 90, "spread": 1, "spreadAngle": 2}',  # last + an insert
            '{"frequency": 3, "kind": "shake"}',
        ]
        text = '{"layers": [' + ", ".join(lines) + "]}"
        got = json.loads(legacy.rewrite(text))
        self.assertEqual(got, legacy.migrated(json.loads(text)))
        self.assertEqual(got["layers"][2], {"kind": "sprite", "point": [0, 0, 0], "size": 90, "spread": 1,
                                            "orientation": "FacingCameraWorldUp"})
        # an escaped quote in a string before a key does not confuse it
        t2 = '{"about": "a \\"quoted\\" word, \\\\", "layers": [{"kind": "fov", "fov": 1}]}'
        self.assertEqual(json.loads(legacy.rewrite(t2))["layers"][0], {"kind": "fov", "delta": 1})

    def test_every_real_preset_rewrites_to_its_migration(self):
        # in memory only: the project's own presets as they are, each rewritten and parsed back (rewrite raises if
        # its text does not parse to migrated(preset)); a preset with nothing to fix comes back byte for byte.
        # The corpus is every preset as it is AND every earlier version the VFX library keeps byte for byte
        # (library/vfx/effects/<name>/versions/): the owner's D3 (2026-11-22) migrated 60 presets in place, so their
        # pre-migration texts - the shapes this rewrite must handle - live on only there
        top = os.path.join(HERE, "..", "..", "..")
        root = os.path.join(top, "assets", "effects")
        names = sorted(os.listdir(root)) if os.path.isdir(root) else []
        paths = [os.path.join(root, f) for f in names if f.endswith(".json") and not f.startswith("_")]
        lib = os.path.join(top, "library", "vfx", "effects")
        for name in sorted(os.listdir(lib)) if os.path.isdir(lib) else []:
            vd = os.path.join(lib, name, "versions")
            if os.path.isdir(vd):
                paths += [os.path.join(vd, f) for f in sorted(os.listdir(vd)) if f.endswith(".json")]
        if not paths:
            # (the folder alone is no corpus: assets/effects/refs_measured/ holds the kit's measured effect norms, which
            # install seeds into every project)
            self.skipTest("no effect presets here (the author's assets/effects/ library is not shipped with the kit)")
        for f in paths:
            with open(f, encoding="utf-8", newline="") as fh:
                text = fh.read()
            out = legacy.rewrite(text)
            if legacy.hits(json.loads(text)):
                self.assertEqual(legacy.hits(json.loads(out)), [], f)
                self.assertLess(abs(len(out) - len(text)), 40 * len(legacy.hits(json.loads(text))) + 1, f)
            else:
                self.assertEqual(out, text, f)
        # (the author's repo also floors the corpus - over 100 texts, over 70 of them migrated - which only the
        # author's own library meets: a project's presets are each checked above, however few)


class Command(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.fx = os.path.join(self.tmp, "assets", "effects")
        os.makedirs(self.fx)
        self.old = os.getcwd()
        os.chdir(self.tmp)
        # one judged piece (a verdict note in the vault, as kit verdict writes it)
        vd = os.path.join("kit", "knowledge", "vault", "vfx", "verdicts")
        os.makedirs(vd)
        open(os.path.join(vd, "judged-piece--2026-10-22.md"), "w").write("x")
        self.preset = {"version": 3, "layers": [{"name": "s", "kind": "sprite", "spreadAngle": [1, 2]}]}
        for n in ("plain_piece", "judged_piece"):
            with open(os.path.join(self.fx, f"{n}.json"), "w", encoding="utf-8", newline="") as f:
                f.write(json.dumps(self.preset, indent=4).replace("\n", "\r\n") + "\r\n")
        with open(os.path.join(self.fx, "clean.json"), "w") as f:
            json.dump({"version": 3, "layers": []}, f)

    def tearDown(self):
        os.chdir(self.old)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_cli(self, *argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = legacy.main(["--effects", self.fx, *argv])
        return code, json.loads(buf.getvalue().strip().splitlines()[-1])

    def raw(self, n):
        return open(os.path.join(self.fx, f"{n}.json"), "rb").read()

    def test_the_report_writes_nothing_and_names_the_judged(self):
        before = self.raw("plain_piece")
        code, out = self.run_cli()
        self.assertEqual(code, 0)
        self.assertEqual(out["status"], "warn")
        rows = {r["name"]: r for r in out["presets"]}
        self.assertEqual(set(rows), {"plain_piece", "judged_piece"})
        self.assertTrue(rows["judged_piece"]["judged"])
        self.assertFalse(rows["plain_piece"]["judged"])
        self.assertEqual(self.raw("plain_piece"), before)

    def test_apply_needs_names(self):
        code, out = self.run_cli("--apply")
        self.assertEqual(code, 1)
        self.assertIn("name the presets", out["summary"])

    def test_apply_rewrites_keeping_the_layout_and_is_idempotent(self):
        code, out = self.run_cli("--apply", "plain_piece")
        self.assertEqual((code, out["status"]), (0, "ok"))
        text = self.raw("plain_piece").decode("utf-8")
        self.assertIn("\r\n", text)                           # the file's own newlines
        self.assertTrue(text.endswith("\r\n"))
        self.assertIn('\r\n    "version"', text)              # its own indent
        self.assertEqual(json.loads(text)["layers"][0]["spread"], [1, 2])
        once = self.raw("plain_piece")
        code, out = self.run_cli("--apply", "plain_piece")    # nothing left to fix: the same bytes
        self.assertEqual(code, 0)
        self.assertEqual(self.raw("plain_piece"), once)

    def test_a_judged_piece_needs_the_owners_words(self):
        before = self.raw("judged_piece")
        code, out = self.run_cli("--apply", "judged_piece")
        self.assertEqual(code, 1)
        self.assertIn("refused 1", out["summary"])
        self.assertEqual(self.raw("judged_piece"), before)
        code, out = self.run_cli("--apply", "judged_piece", "--judged", "   ")  # blank words are no words
        self.assertEqual(code, 1)
        code, out = self.run_cli("--apply", "judged_piece", "--judged", "yes, switch the cones on")
        self.assertEqual(code, 0)
        self.assertNotEqual(self.raw("judged_piece"), before)

    def test_an_unknown_name_fails(self):
        code, out = self.run_cli("--apply", "no_such")
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
