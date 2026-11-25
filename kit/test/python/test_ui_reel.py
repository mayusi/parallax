"""kit ui reel: keyframes interpolate (numbers eased, colours in RGB, text and booleans stepped)"""
import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("kit_ui_reel", os.path.join(HERE, "..", "..", "ui", "reel.py"))
reel = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(reel)


class TestReel(unittest.TestCase):
    def test_numbers_interpolate_and_hold_outside_the_keys(self):
        tr = {"keys": [[0, 0.82], [1, 0.54]], "ease": "linear"}
        self.assertAlmostEqual(reel.value_at(tr, 0.5), 0.68)
        self.assertEqual(reel.value_at(tr, -1), 0.82)
        self.assertEqual(reel.value_at(tr, 5), 0.54)

    def test_a_size_key_in_pixels_is_refused(self):
        model = {"Children": [{"Name": "Hud", "Children": [{"Name": "Clip", "Properties": {}}]}]}
        bad = reel.check_tracks([{"node": "Hud.Clip", "prop": "size_x", "keys": [[0, 0], [0.6, 694]]}], model)
        self.assertEqual(len(bad), 1)
        self.assertIn("PIXELS", bad[0])
        self.assertEqual(reel.check_tracks([{"node": "Hud.Clip", "prop": "size_x", "keys": [[0, 0], [0.6, 0.913]]}], model), [])
        bad = reel.check_tracks([{"node": "Hud.Clip", "prop": "size_x", "keys": [[0, "50%"]]}], model)  # (crashed before)
        self.assertEqual(len(bad), 1)

    def test_newer_art_is_synced_before_a_reel_paints(self):
        import tempfile
        import time as _t
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = os.path.join(tmp, "src", "witch"), os.path.join(tmp, "dst", "witch")
            os.makedirs(src)
            os.makedirs(dst)
            from PIL import Image
            for name in ("old.png", "new.png", "resized.png"):
                Image.new("RGBA", (8, 8), (10, 10, 10, 255)).save(os.path.join(dst, name))
            _t.sleep(0.05)
            Image.new("RGBA", (8, 8), (10, 10, 10, 255)).save(os.path.join(src, "old.png"))
            os.utime(os.path.join(src, "old.png"), (0, 0))                              # older than its built copy: left alone
            Image.new("RGBA", (8, 8), (200, 0, 0, 255)).save(os.path.join(src, "new.png"))      # newer: copied
            Image.new("RGBA", (16, 16), (0, 200, 0, 255)).save(os.path.join(src, "resized.png"))  # newer but resized: kit ui's job
            n = reel.sync_art(os.path.join(tmp, "src"), os.path.join(tmp, "dst"))
            self.assertEqual(n, 1)
            self.assertEqual(Image.open(os.path.join(dst, "new.png")).getpixel((0, 0))[0], 200)
            self.assertEqual(Image.open(os.path.join(dst, "resized.png")).size, (8, 8))

    def test_the_motion_critic(self):
        lin = [{"node": "Hud.A", "prop": "dx", "ease": "linear", "keys": [[0, -400], [0.3, 0]]}]
        self.assertTrue(any("LINEAR" in n["note"] for n in reel.critique(lin, 2.0, 24)))
        eased = [{"node": "Hud.A", "prop": "dx", "ease": "out", "keys": [[0, -400], [0.3, 0]]}]
        self.assertEqual(reel.critique(eased, 2.0, 24), [])                          # eased, quick, then still: clean
        slow = [{"node": "Hud.A", "prop": "dy", "ease": "out", "keys": [[0, 300], [0.2, 200], [0.5, 100], [0.75, 40], [1.0, 0]]}]
        self.assertTrue(any("settle" in n["note"] for n in reel.critique(slow, 3.0, 24)))
        drift = [{"node": "Hud.A", "prop": "scale", "ease": "out", "keys": [[0, 0.5], [0.3, 1.0], [3.0, 1.05]]}]
        self.assertFalse(any("settle" in n["note"] for n in reel.critique(drift, 3.5, 24)))   # (a slow drift is ambient)
        together = [{"node": f"Hud.R{i}", "prop": "dx", "ease": "out", "keys": [[0, 900], [0.3, 0]]} for i in range(3)]
        self.assertTrue(any("stagger" in n["note"] for n in reel.critique(together, 2.0, 24)))
        punch = [{"node": f"Hud.P{i}", "prop": "scale", "ease": "out", "keys": [[0, 1], [0.5, 1], [0.55, 1.3], [0.7, 1]]} for i in range(4)]
        self.assertFalse(any("stagger" in n["note"] for n in reel.critique(punch, 2.0, 24)))   # (a shared hit punch is on purpose)
        flat = [{"node": "Hud.Hero", "prop": "scale", "ease": "out", "keys": [[0, 0.5], [0.3, 1.0]]}]
        self.assertTrue(any("overshoot" in n["note"] for n in reel.critique(flat, 2.0, 24, ["Hud.Hero"])))
        sway = [{"node": "Stage.Fig0", "prop": "dx", "ease": "inout", "keys": [[0, 18], [2.0, -18], [4.0, 18]]}]
        self.assertEqual(reel.critique(sway, 4.0, 24), [])                             # an ambient sway is life, not a slow entrance
        tail = [{"node": "Hud.A", "prop": "dx", "ease": "out", "keys": [[0, -600], [0.2, -300], [1.4, 0]]}]
        self.assertTrue(any("settle" in n["note"] for n in reel.critique(tail, 3.0, 24)))   # a big slow tail IS the entrance
        blink = [{"node": "Hud.A", "prop": "dx", "ease": "out", "keys": [[0, -400], [0.3, 0]]},
                 {"node": "Hud.Press", "prop": "alpha", "ease": "step", "keys": [[0, 0], [1.0, 1], [1.6, 0.2], [2.0, 1], [2.6, 0.2]]}]
        self.assertFalse(any("READ" in n["note"] for n in reel.critique(blink, 2.8, 24)))   # a blink is not an entrance
        backed = [{"node": "Boon1.Dia", "prop": "scale", "ease": "back", "keys": [[0, 0.2], [0.4, 1.0]]}]
        self.assertFalse(any("overshoot" in n["note"] for n in reel.critique(backed, 2.0, 24, ["Boon1.Dia"])))   # 'back' overshoots
        hero = [{"node": "Boon1.Dia", "prop": "scale", "ease": "out", "keys": [[0, 0.2], [0.4, 1.0]]}]
        self.assertTrue(any("overshoot" in n["note"] for n in reel.critique(hero, 2.0, 24, ["Boon1.Dia"])))
        tach = [{"node": "Dial.Needle", "prop": "rotation", "ease": "inout", "keys": [[0, 190], [0.9, 356], [1.0, 275], [1.9, 356], [2.0, 284], [2.6, 342], [4.5, 380]]},
                {"node": "Dial.Clip", "prop": "size_x", "ease": "linear", "keys": [[0, 0.7], [2.6, 0.7], [4.5, 0.1]]}]
        self.assertEqual(reel.critique(tach, 4.6, 24), [])   # a gameplay gauge and a draining meter: nothing to say
        late = [{"node": "Hud.A", "prop": "dx", "ease": "out", "keys": [[0, -400], [1.9, 0]]}]
        self.assertTrue(any("READ" in n["note"] for n in reel.critique(late, 2.0, 24)))

    def test_text_and_booleans_step(self):
        self.assertEqual(reel.value_at({"keys": [[0, "82"], [1, "54"]]}, 0.99), "82")
        self.assertEqual(reel.value_at({"keys": [[0, "82"], [1, "54"]]}, 1.0), "54")
        self.assertEqual(reel.value_at({"keys": [[0, False], [1, True]]}, 0.5), False)

    def test_colours_interpolate_in_rgb_even_before_the_first_key(self):
        tr = {"keys": [[1, "#000000"], [2, "#ffffff"]]}
        self.assertEqual(reel.value_at(tr, 0), [0.0, 0.0, 0.0])
        mid = reel.value_at(tr, 1.5)
        self.assertAlmostEqual(mid[0], 0.5, places=2)

    def test_art_swaps_the_picture_a_node_shows(self):
        inst = {"Properties": {}}
        reel.apply_model(inst, "art", "witch/witch_dash_2")
        self.assertEqual(inst["Properties"]["Attributes"]["Attributes"]["KitArt"]["String"], "witch/witch_dash_2")
        tr = {"keys": [[0, "witch/a"], [0.3, "witch/b"]], "ease": "step"}
        self.assertEqual(reel.value_at(tr, 0.29), "witch/a")
        self.assertEqual(reel.value_at(tr, 0.31), "witch/b")

    def test_easing_ends(self):
        for k in ("linear", "in", "out", "inout"):
            self.assertAlmostEqual(reel.ease(k, 0), 0)
            self.assertAlmostEqual(reel.ease(k, 1), 1)


    def test_the_critic_is_not_fooled_by_beats_drifts_jolts_or_key_counts(self):
        say = lambda tracks, dur=3.0: [n["note"] for n in reel.critique(tracks, dur, 24)]
        # beats: a flare that leaves its rest and comes back on every beat is not one long entrance
        self.assertEqual(say([{"node": "H.Flare", "prop": "scale", "ease": "out", "keys": [[0, 0.4], [0.85, 0.4], [1.1, 1.3], [1.4, 0.4], [1.65, 1.3], [1.95, 0.4], [2.2, 1.3], [2.5, 0.4]]}]), [])
        # a 3% push-in over the whole reel is a camera drift (1.03 - 1.0 is not exactly 0.03 in floats)
        self.assertEqual(say([{"node": "S.Fig", "prop": "scale", "ease": "inout", "keys": [[0, 1.0], [4.0, 1.03]]}], 4.0), [])
        # a slide that arrives in 0.18 s, creeps 2% while held, then leaves: arrived at 0.88 s, not 'settles in 0.9 s'
        self.assertEqual(say([{"node": "H.Tape", "prop": "dx", "ease": "out", "keys": [[0, -1600], [0.7, -1600], [0.88, 0], [1.45, 30], [1.6, 1800]]}], 3.6), [])
        # a hit jolt (two flips inside 0.15 s) may be linear
        self.assertEqual(say([{"node": "Health", "prop": "dy", "ease": "linear", "keys": [[0, 0], [0.7, 0], [0.73, 6], [0.76, -5], [0.8, 0], [3.0, 0]]}]), [])
        # an entrance with a spring settle and an exit key is NOT gameplay, however many keys: still told it is linear
        spring = [{"node": "P", "prop": "dx", "ease": "linear", "keys": [[0, -600], [0.15, 20], [0.22, -8], [0.28, 0], [2.4, 0], [2.7, 600]]}]
        self.assertTrue(any("LINEAR" in n for n in say(spring)))
        # a late spring entrance still gets the READ note
        late = [{"node": "P", "prop": "dx", "ease": "out", "keys": [[0, -600], [2.5, -600], [2.6, 20], [2.7, -8], [2.8, 4], [2.9, 0]]}]
        self.assertTrue(any("READ" in n for n in say(late)))
        # a bar that wipes IN is an entrance (only a DRAIN is the game's timing)
        wipe = [{"node": "Bar", "prop": "size_x", "ease": "linear", "keys": [[2.7, 0], [2.95, 1]]}]
        self.assertTrue(any("LINEAR" in n for n in say(wipe)) and any("READ" in n for n in say(wipe)))
        # a damage number that floats up until it is hidden floats AWAY: no 'takes 0.90 s to settle'
        pop = [{"node": "H.Pop", "prop": "dy", "ease": "out", "keys": [[0, 0], [0.7, 0], [1.6, -70], [1.99, -70], [2.0, 0]]},
               {"node": "H.Pop", "prop": "visible", "ease": "step", "keys": [[0, False], [0.7, True], [1.6, False]]}]
        self.assertEqual(say(pop), [])
        # keys out of order are read in time order
        self.assertEqual(reel.nums({"keys": [[1, 5], [0, 0], [0.5, "x"]]}), [[0, 0], [1, 5]])

    def test_reel_macros_expand_to_plain_tracks(self):
        tr = reel.expand_macros([
            {"macro": "flipbook", "node": "Card.Flip", "frames": "s/spin_f{k}", "count": 4, "from": 2.0, "to": 2.4, "reverse": True},
            {"macro": "cycle", "node": "Grain", "frames": ["g/a", "g/b"], "fps": 10},
            {"macro": "weave", "node": "Film", "amp": [2, 3], "fps": 10, "seed": 1},
            {"node": "X", "prop": "alpha", "keys": [[0, 0], [1, 1]]}], 1.0)
        flip = tr[0]
        self.assertEqual(flip["keys"][0], [0, "s/spin_f3"])                       # holds the first frame before it plays
        self.assertEqual([k[1] for k in flip["keys"][1:]], ["s/spin_f3", "s/spin_f2", "s/spin_f1", "s/spin_f0"])
        self.assertEqual([k[0] for k in flip["keys"][1:]], [2.0, 2.1, 2.2, 2.3])
        self.assertEqual([k[1] for k in tr[1]["keys"]][:4], ["g/a", "g/b", "g/a", "g/b"])
        self.assertEqual(len(tr[1]["keys"]), 11)
        dx, dy = tr[2], tr[3]
        self.assertEqual((dx["prop"], dy["prop"]), ("dx", "dy"))
        self.assertTrue(all(abs(k[1]) <= 2 for k in dx["keys"]) and all(abs(k[1]) <= 3 for k in dy["keys"]))
        self.assertEqual(tr[4]["node"], "X")                                      # a plain track passes through
        self.assertEqual(reel.critique(tr, 1.0, 24), [])                           # (steps: nothing for the critic)

    def test_a_number_node_shows_text_by_swapping_its_cells(self):
        node = {"Properties": {"Attributes": {"Attributes": {"Kit_Digits": {"String": "neon/spd"}}}},
                "Children": [{"Name": f"C{i}", "Properties": {}} for i in (1, 2, 3)]}
        self.assertTrue(reel.set_number(node, "9:5"))
        arts = [c["Properties"].get("Attributes", {}).get("Attributes", {}).get("KitArt", {}).get("String") for c in node["Children"]]
        self.assertEqual(arts, ["neon/spd_9", "neon/spd_u58", "neon/spd_5"])
        reel.set_number(node, "7")
        self.assertEqual([c["Properties"]["Visible"] for c in node["Children"]], [True, False, False])
        self.assertFalse(reel.set_number({"Properties": {}}, "5"))           # (a label is the hook's, not a number)
        centred = {"Properties": {"Attributes": {"Attributes": {"Kit_Digits": {"String": "d"}, "Kit_DigitCell": {"Float64": 40},
                                                               "Kit_DigitAlign": {"String": "center"}}}},
                   "Children": [{"Name": f"C{i}", "Properties": {}} for i in (1, 2, 3)]}
        reel.set_number(centred, "82")                                       # (two digits re-centre, like Ui.number)
        self.assertEqual(centred["Children"][0]["Properties"]["Position"], {"UDim2": [[0.5, -40.0], [0, 0]]})

    def test_runtime_fx_become_tracks_like_ui_fx(self):
        enc = "shimmer:alpha=0.5,angle=20,delay=0,period=2,width=0.1;split:alpha=0.5,dur=0.1,every=1,px=5"
        node = {"Name": "N", "ClassName": "ImageLabel", "Properties": {"Attributes": {"Attributes": {"Kit_Fx": {"String": enc}}}},
                "Children": [{"Name": "Fx_Shimmer", "ClassName": "ImageLabel", "Properties": {},
                              "Children": [{"Name": "Band", "ClassName": "UIGradient", "Properties": {}}]},
                             {"Name": "Fx_SplitA", "ClassName": "ImageLabel", "Properties": {}},
                             {"Name": "Fx_SplitB", "ClassName": "ImageLabel", "Properties": {}},
                             {"Name": "Fx_SplitC", "ClassName": "ImageLabel", "Properties": {}}]}
        base = {"Children": [{"Name": "Hud", "Children": [node]}]}
        tr = reel.fx_tracks(base, 4.0)
        self.assertEqual(tr, reel.fx_tracks(base, 4.0))                     # (seeded: the same film every time)
        sweep = next(t for t in tr if t["node"] == "Hud.N.Fx_Shimmer" and t["prop"] == "grad_offset")
        self.assertEqual(reel.value_at(sweep, 0.0), -1.0)                    # (the band waits off the piece)
        self.assertAlmostEqual(reel.value_at(sweep, 0.9), 1.0)               # (swept by 0.45 of a period)
        self.assertEqual(reel.check_tracks(tr, base), [])
        m, _ = reel.frame_state(base, tr, 1.0)
        band = m["Children"][0]["Children"][0]["Children"][0]["Children"][0]
        self.assertIn("Offset", band["Properties"])                          # (grad_offset writes the gradient)
        given = [{"node": "Hud.N.Fx_Shimmer", "prop": "grad_offset", "keys": [[0, 0]]}]
        self.assertFalse(any(t["prop"] == "grad_offset" for t in reel.fx_tracks(base, 4.0, given)))  # (the script wins)

    def test_a_burst_flies_the_same_every_time_and_draws_over_the_frame(self):
        from PIL import Image
        p = {"count": "8", "life": "0.5", "speed": "400,800", "spread": "360", "angle": "-90", "gravity": "900",
             "size": "10,20", "spin": "180", "colors": "#ff0000,#00ff00", "fade": "1", "shrink": "1"}
        self.assertEqual(reel.burst_parts(p, 3), reel.burst_parts(p, 3))      # (seeded)
        self.assertEqual(len(reel.burst_parts(p, 3)), 8)
        self.assertIn(reel.burst_parts(p, 3)[0]["col"], [(255, 0, 0), (0, 255, 0)])   # (0..255, not 0..1)
        im = Image.new("RGBA", (400, 400), (0, 0, 0, 255))
        out = reel.burst_frame(im.copy(), 0.1, [(0.0, (200, 200), "pop", 1)], {"pop": p})
        self.assertNotEqual(out.tobytes(), im.tobytes())                     # (sparks in flight at 0.1 s)
        gone = reel.burst_frame(im.copy(), 0.9, [(0.0, (200, 200), "pop", 1)], {"pop": p})
        self.assertEqual(gone.tobytes(), im.tobytes())                       # (none after their life)

if __name__ == "__main__":
    unittest.main()
