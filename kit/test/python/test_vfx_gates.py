"""The VFX recording gate (kit/vfx/player/player.js summarize) on synthetic curves via kit/vfx/gates_test.cjs, and the
creative director's taste rules (kit/vfx/director.py) on synthetic EXPANDED presets: each rule must FIRE on the failure
it was learned from and HOLD on its fix (a rule that cannot fire is worse than none - echo-dish once could not)."""
import importlib.util
import json
import os
import shutil
import subprocess
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
spec = importlib.util.spec_from_file_location("director", os.path.join(ROOT, "kit", "vfx", "director.py"))
director = importlib.util.module_from_spec(spec)
spec.loader.exec_module(director)


def rule(rid):
    return next(r for r in json.load(open(os.path.join(ROOT, director.RULES), encoding="utf-8"))["rules"] if r["id"] == rid)


def fires(rid, preset):
    r = rule(rid)
    return bool(director.LINTS[r["type"]](preset, r))


def booth(ground="Slate", sky="night", dist=30):
    return {"ground": ground, "sky": sky, "viewDefs": {"hero": {"pos": [0, 0, dist], "look": [0, 0, 0]}}}


class Gates(unittest.TestCase):
    @unittest.skipIf(shutil.which("node") is None, "node is not installed")
    def test_recording_gate_verdicts(self):
        r = subprocess.run(["node", os.path.join(ROOT, "kit", "vfx", "gates_test.cjs")], capture_output=True, text=True)
        out = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(out["status"], "pass", out["failed"])
        self.assertGreaterEqual(out["ran"], 7)


class TasteRules(unittest.TestCase):
    def test_echo_dish_reads_the_expanded_copies(self):
        ring = {"kind": "mesh", "shape": "arc", "material": "Neon"}
        three = {"layers": [dict(ring, name="r")] + [dict(ring, name=f"r_echo{k}") for k in (1, 2, 3)]}
        one = {"layers": [dict(ring, name="r"), dict(ring, name="r_echo1")]}
        self.assertTrue(fires("echo-dish", three))
        self.assertFalse(fires("echo-dish", one))

    def test_semantic_frames_erase_mesh_layers(self):
        # the player's semantic frame pass drops every mesh layer from the energy pass: a flame column alone at the
        # hit draws nothing unless the frames turn semantic off (firewhirl r1-r2)
        col = {"kind": "mesh", "name": "column", "shape": "flame", "material": "Neon", "at": 0.5, "life": 2.0, "scale": [1, 1, 1]}
        frame = {"kind": "impact", "style": "frame", "name": "f", "at": 1.7, "life": 0.07, "draw": {"star": 0, "wedge": 0}}
        base = {"hitstop": [{"at": 1.7}]}
        self.assertTrue(fires("frames-need-shapes", dict(base, layers=[col, frame])))
        off = dict(frame, draw={"star": 0, "wedge": 0, "semantic": False})
        self.assertFalse(fires("frames-need-shapes", dict(base, layers=[col, off])))
        # (review 2026-10-24) what the player still draws under semantic frames: an aimed tube as a wedge, a lit Block as ink
        tube = {"kind": "mesh", "name": "beam", "shape": "tube", "aim": [0, 0, 9], "material": "Neon", "at": 0.5, "life": 2.0, "scale": [1, 1, 1]}
        self.assertFalse(fires("frames-need-shapes", dict(base, layers=[tube, dict(frame, draw={"star": 0})])))  # wedge defaults on
        self.assertTrue(fires("frames-need-shapes", dict(base, layers=[tube, frame])))  # wedge 0: no wedge, erased
        block = {"kind": "mesh", "name": "slab", "shape": "Block", "material": "SmoothPlastic", "at": 0.5, "life": 2.0, "scale": [2, 2, 2]}
        self.assertFalse(fires("frames-need-shapes", dict(base, layers=[block, frame])))
        # (review 2026-10-25) a layer kept out of the frames (frames: false) is not something they can draw
        rubble = {"kind": "debris", "name": "rubble", "at": 0.5, "life": 2.0, "count": 20}
        self.assertFalse(fires("frames-need-shapes", dict(base, layers=[rubble, frame])))
        self.assertTrue(fires("frames-need-shapes", dict(base, layers=[dict(rubble, frames=False), frame])))

    def test_rim_pearls_reads_the_rim_shell(self):
        shell = {"kind": "mesh", "material": "ForceField", "name": "bead_rim", "scale": [0.6, 0.6, 0.6]}
        self.assertTrue(fires("rim-pearls", {"layers": [dict(shell, transparency=0.35)]}))
        self.assertFalse(fires("rim-pearls", {"layers": [dict(shell, transparency=0.78)]}))
        self.assertFalse(fires("rim-pearls", {"layers": [dict(shell, transparency=0.35, scale=[4, 4, 4])]}))  # a big shell

    def test_ground_plate_only_full_flat_rings(self):
        ring = {"kind": "mesh", "shape": "arc", "name": "crest", "params": {"radius": 2, "width": 0.42, "arc": 360}, "scale": [13, 5, 13]}
        self.assertTrue(fires("ground-plate", {"booth": booth(dist=34), "layers": [ring]}))
        thread = {"kind": "mesh", "shape": "arc", "name": "thread", "params": {"radius": 60, "width": 0.3, "arc": 20, "vertical": 1}}
        self.assertFalse(fires("ground-plate", {"booth": booth(dist=14), "layers": [thread]}))  # a chord in the air (seam)

    def test_untextured_neon_is_a_share_or_a_volume(self):
        mesh = lambda n, shape, tex=None: {"kind": "mesh", "name": n, "shape": shape, "material": "Neon", **({"texture": tex} if tex else {})}
        accents = {"layers": [mesh("r1", "ring")] + [mesh(f"t{k}", "flame", "fire") for k in range(12)]}  # starblade-like
        self.assertFalse(fires("untextured-neon-mesh", accents))
        self.assertTrue(fires("untextured-neon-mesh", {"layers": [mesh("core", "sphere")] + [mesh(f"t{k}", "flame", "fire") for k in range(12)]}))

    def test_puffs_rule_is_cel_smoke_only(self):
        cel = {"kind": "sprite", "name": "column", "texture": "gpu_smoke_cel", "count": 3, "size": [[0, 5], [1, 13]]}
        lit = dict(cel, texture="gpu_smoke", name="steam")
        self.assertTrue(fires("few-giant-puffs", {"layers": [cel]}))
        self.assertFalse(fires("few-giant-puffs", {"layers": [lit]}))  # lit simulated smoke is a whole volume (nuke_v4)

    def test_frames_need_shapes(self):
        frame = {"kind": "impact", "style": "frame", "name": "f", "at": 1.0, "life": 0.06}
        dust = {"kind": "sprite", "name": "dust", "at": 0, "lifetime": [0.5, 1], "for": 3, "size": 0.35, "lightEmission": 1}
        spikes = {"kind": "mesh", "name": "spikes", "material": "Glass", "at": 1.0, "life": 1, "scale": [[0, [1, 0.02, 1]], [0.1, [1, 1, 1]], [1, [1, 1, 1]]]}
        empty = {"hitstop": [{"at": 1.0}], "layers": [frame, dust, spikes]}  # hoarfrost round 4: specks + flat Glass
        self.assertTrue(fires("frames-need-shapes", empty))
        shards = {"kind": "debris", "name": "shards", "at": 1.0, "count": 30}
        self.assertFalse(fires("frames-need-shapes", dict(empty, layers=[frame, dust, spikes, shards])))

    def test_cut_frames_need_an_arc_drawn_at_the_hit(self):
        frame = {"kind": "impact", "style": "frame", "name": "cut", "at": 2.4, "life": 0.07, "draw": {"slash": 2.2, "split": 1}}
        gust = {"kind": "mesh", "shape": "arc", "name": "gust", "at": 2.4, "life": 0.42, "sweep": {"head": [[0, 0], [0.2, 1], [1, 1]]}}
        p = {"hitstop": [{"at": 2.4}], "layers": [frame, gust]}
        self.assertTrue(fires("cut-frames-need-arc", p))  # sandfall round 1: from zero length
        gust2 = dict(gust, sweep={"head": [[0, 0.35], [0.15, 1], [1, 1]]})
        self.assertFalse(fires("cut-frames-need-arc", dict(p, layers=[frame, gust2])))

    def test_hero_distance_survives_path_only_views(self):
        p = {"booth": {"viewDefs": {"cine": {"path": [{"t": 0}]}, "side": {"pos": [0, 0, 20], "look": [0, 0, 0]}}}}
        self.assertAlmostEqual(director.hero_distance(p), 20.0)
        self.assertEqual(director.hero_distance({"booth": {}}), 30.0)


if __name__ == "__main__":
    unittest.main()


class FinishGate(unittest.TestCase):
    def test_frames_count_catches_a_sheet_taken_as_one_frame(self):
        import importlib.util as iu
        sp = iu.spec_from_file_location("vfx_fxfinish", os.path.join(ROOT, "kit", "vfx", "fxfinish.py"))
        fx = iu.module_from_spec(sp)
        sp.loader.exec_module(fx)
        from PIL import Image
        img = Image.new("RGBA", (1024, 1024), (255, 255, 255, 255))
        def ok(n, want):
            return next(c for c in fx.check(img, (4, 4), 0.0, 0.5, n, False, want=want) if c["name"] == "frames_count")["ok"]
        self.assertFalse(ok(1, 16))  # bloom_grow / kanada_flare before the import slice fix
        self.assertTrue(ok(16, 16))
        self.assertFalse(any(c["name"] == "frames_count" for c in fx.check(img, (1, 1), 0.0, 1.0, 1, False)))  # a still


class CraftChecks(unittest.TestCase):
    """the owner's round-1 verdicts as critique-sheet warnings (2026-10-25): each fires on its failure, holds on its fix"""

    def test_speck_frames_warn_and_close_ups_do_not(self):
        speck = {"views": {"hero": {"frames": [{"t": 1, "sf": 0.1}] * 5}}}
        close = {"views": {"hero": {"frames": [{"t": 1, "sf": 0.7}] * 5}}}
        self.assertTrue(any("speck" in c for c in director.craft_checks({"layers": []}, speck)))
        self.assertFalse(director.craft_checks({"layers": []}, close))

    def test_generic_puff_cards_and_ground_sliced_cards(self):
        puffs = {"layers": [{"kind": "sprite", "name": "steam", "count": 27, "lit": {"top": "gpu_smoke"}}]}
        self.assertTrue(any("cotton" in c for c in director.craft_checks(puffs, {})))
        card = {"kind": "sprite", "name": "steam", "count": 1, "texture": "x_gpu", "flipbook": {"layout": "8x8"},
                "orientation": "FacingCameraWorldUp", "size": 26}
        sliced = {"layers": [dict(card, point=[0, 12.6, 0])]}
        seated = {"layers": [dict(card, point=[0, 13.3, 0])]}
        self.assertTrue(any("slices" in c for c in director.craft_checks(sliced, {})))
        self.assertFalse(director.craft_checks(seated, {}))

    def test_plain_plastic_meshes_warn_unless_textured_or_mirrors(self):
        clay = {"layers": [{"kind": "mesh", "name": "crown", "material": "SmoothPlastic"}]}
        mirror = {"layers": [{"kind": "mesh", "name": "crown", "material": "SmoothPlastic", "reflectance": 0.6}]}
        self.assertTrue(any("clay" in c for c in director.craft_checks(clay, {})))
        self.assertFalse(director.craft_checks(mirror, {}))

    def test_reframed_impact_frames_warn_unless_drawn_from_the_live_shot(self):
        f = {"kind": "impact", "style": "frame", "name": "frame_0_ink"}
        self.assertTrue(any("re-framed" in c for c in director.craft_checks({"layers": [dict(f, camera="subject")]}, {})))
        self.assertTrue(any("re-framed" in c for c in director.craft_checks({"layers": [f]}, {})))  # no camera: the player's close-up
        self.assertFalse(director.craft_checks({"layers": [dict(f, camera="none")]}, {}))

    def test_border_faded_texture_on_a_closed_shape_warns_seam(self):
        specs = {"faded": {"post": {}}, "wrapped": {"wrap": True, "post": {}}, "tiled": {"post": {"border": 0}}}.get
        ring = {"kind": "mesh", "name": "deck", "shape": "ring", "material": "Neon"}
        self.assertTrue(any("seam" in c for c in director.craft_checks({"layers": [dict(ring, texture="faded")]}, {}, specs)))
        self.assertFalse(director.craft_checks({"layers": [dict(ring, texture="wrapped")]}, {}, specs))
        self.assertFalse(director.craft_checks({"layers": [dict(ring, texture="tiled")]}, {}, specs))
        arc = dict(ring, shape="arc", texture="faded")  # an open strip: its ends never meet
        self.assertFalse(director.craft_checks({"layers": [arc]}, {}, specs))
        circle = dict(ring, shape="disc", texture="faded", params={"planar": 1})  # projected flat: no seam to close
        self.assertFalse(director.craft_checks({"layers": [circle]}, {}, specs))
        shapeless = {"kind": "mesh", "name": "halo", "texture": "faded"}  # no shape: the player draws a ring
        self.assertTrue(any("seam" in c for c in director.craft_checks({"layers": [shapeless]}, {}, specs)))
        nulled = {"nulled": {"post": {"border": None}}}.get  # an explicit null border must not crash the check
        self.assertTrue(any("seam" in c for c in director.craft_checks({"layers": [dict(ring, texture="nulled")]}, {}, nulled)))
