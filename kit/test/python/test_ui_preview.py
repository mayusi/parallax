"""kit/ui/preview.py motion: the plan the frame strips draw from is the one the runtime plays — a container's
stagger spaces only the children that enter, in sibling order; delays add; the eases are bounded; every enter
kind has a state at the start and the end."""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "ui"))

# loaded under its own name: other kit tests import their own `preview` modules (kit/anim, kit/vfx) in this process
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("kit_ui_preview", os.path.join(HERE, "..", "..", "ui", "preview.py"))
preview = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(preview)


def attrs(**kw):
    out = {}
    for k, v in kw.items():
        out[k] = {"Float64": v} if isinstance(v, (int, float)) else {"String": v}
    return {"Attributes": out}


def frame(name, children=None, **kw):
    return {"ClassName": "Frame", "Name": name, "Properties": {"Attributes": attrs(**kw)} if kw else {}, "Children": children or []}


class TestMotionPlan(unittest.TestCase):
    def test_stagger_spaces_entering_children_in_sibling_order(self):
        model = {"ClassName": "ScreenGui", "Children": [frame("Root", [
            frame("Menu", [
                frame("A", Motion_enter="fade", Motion_enter_delay=0.5, Motion_enter_duration=1.0),
                frame("Static"),  # no enter: takes no stagger slot
                frame("B", Motion_enter="rise", Motion_enter_delay=0.5, Motion_enter_duration=1.0),
                frame("C", Motion_enter="pop", Motion_enter_duration=0.4),
            ], Motion_stagger=0.1),
        ])]}
        plan = preview.motion_plan(model)
        self.assertEqual(set(plan), {"Root.Menu.A", "Root.Menu.B", "Root.Menu.C"})
        self.assertAlmostEqual(plan["Root.Menu.A"][1], 0.5)
        self.assertAlmostEqual(plan["Root.Menu.B"][1], 0.6)
        self.assertAlmostEqual(plan["Root.Menu.C"][1], 0.2)
        self.assertEqual(plan["Root.Menu.C"][0], "pop")
        self.assertEqual(plan["Root.Menu.C"][3], "quad")  # the default ease

    def test_eases_are_bounded_and_end_at_one(self):
        for kind in ("quad", "sine", "back", "expo", "linear", "elastic"):
            self.assertAlmostEqual(preview.ease(kind, 0), 0, places=6, msg=kind)
            self.assertAlmostEqual(preview.ease(kind, 1), 1, places=6, msg=kind)
            self.assertGreaterEqual(preview.ease(kind, 0.5), 0, kind)

    def test_every_enter_kind_hides_at_start_and_shows_at_end(self):
        for kind in ("fade", "rise", "drop", "sweep", "pop", "slam", "swell", "wipe", "typewriter"):
            start = preview.enter_state(kind, 0.0, "HELLO")
            end = preview.enter_state(kind, 1.0, "HELLO")
            if kind == "wipe":
                self.assertEqual(start["wipe"], 0)
                self.assertEqual(end["wipe"], 1)
            elif kind == "typewriter":
                self.assertEqual(start["text"], "")
                self.assertEqual(end["text"], "HELLO")
            else:
                self.assertLessEqual(start.get("alpha", 1), 0.01, kind)
                self.assertAlmostEqual(end.get("alpha", 1), 1, places=6, msg=kind)
                self.assertAlmostEqual(end.get("scale", 1), 1 if kind != "swell" else 1.04, places=6, msg=kind)

    def test_viewport_scale_reads_the_screen_attribute(self):
        model = {"ClassName": "ScreenGui", "Properties": {"Attributes": attrs(Kit_Scale_phone=0.72)}, "Children": []}
        self.assertAlmostEqual(preview.viewport_scale(model, "phone"), 0.72)
        self.assertAlmostEqual(preview.viewport_scale(model, "desktop"), 1.0)

    def test_at_overrides_reflow_the_phone_view_only(self):
        root = frame("Root", [
            {"ClassName": "Frame", "Name": "Card", "Properties": {"BackgroundColor3": {"Color3": [1, 0, 0]},
             "Size": {"UDim2": [[0, 400], [0, 200]]}, "Position": {"UDim2": [[0, 0], [0, 0]]},
             "Attributes": {"Attributes": {"Kit_At_phone": {"String": "Size=1,0,0,100|Position=0,0,1,-100|Visible=true"},
                                           "Kit_At_tablet": {"String": "Visible=false"}}}}}])
        root["Properties"] = {"Size": {"UDim2": [[1, 0], [1, 0]]}, "BackgroundTransparency": 1}
        model = {"ClassName": "ScreenGui", "Children": [root]}
        self.assertEqual(preview.parse_at("Size=1,0,0,100|TextSize=18|Visible=false|Anchor=0.5,1"),
                         {"Size": {"UDim2": [[1, 0], [0, 100]]}, "TextSize": 18.0, "Visible": False, "AnchorPoint": {"Vector2": [0.5, 1.0]}})
        phone = preview.with_at(model, "phone")["Children"][0]["Children"][0]["Properties"]
        self.assertEqual(phone["Size"], {"UDim2": [[1, 0], [0, 100]]})
        desktop = preview.with_at(model, "desktop")["Children"][0]["Children"][0]["Properties"]
        self.assertEqual(desktop["Size"], {"UDim2": [[0, 400], [0, 200]]})
        self.assertIs(preview.with_at(model, "tablet")["Children"][0]["Children"][0]["Properties"]["Visible"], False)
        im, _ = preview.draw_viewport(model, 844, 390, "phone")
        px = im.convert("RGB").getpixel
        self.assertGreater(px((600, 380))[0], 200)  # the card hugs the bottom edge on the phone...
        self.assertLess(px((600, 50))[0], 200)  # ...and no longer sits at the top

    def test_a_scaled_viewport_draws_at_the_viewport_size_and_insets_keep_their_box(self):
        from PIL import Image
        for insets in ("DeviceSafeInsets", "CoreUISafeInsets", "TopbarSafeInsets", "None"):
            model = {"ClassName": "ScreenGui", "Properties": {"Attributes": attrs(Kit_Scale_phone=0.6, Kit_Insets=insets)},
                     "Children": [{"ClassName": "Frame", "Name": "Root", "Properties": {"BackgroundColor3": {"Color3": [1, 0, 0]},
                                                                                        "Size": {"UDim2": [[1, 0], [1, 0]]}}}]}
            im, checks = preview.draw_viewport(model, 844, 390, "phone")
            self.assertIsInstance(im, Image.Image)
            self.assertEqual(im.size, (844, 390), insets)
            self.assertEqual(checks, [])
            # the red root fills the box its insets allow: under the top bar for Core, beside the buttons for Topbar
            px = im.convert("RGB").getpixel
            if insets == "CoreUISafeInsets":
                self.assertNotEqual(px((400, 10))[0] > 200, True)  # the top band is the backdrop, not the root
                self.assertGreater(px((400, 200))[0], 200)
            elif insets == "TopbarSafeInsets":
                self.assertGreater(px((422, 20))[0], 200)  # inside the strip beside the buttons
                self.assertLess(px((422, 300))[0], 200)  # below the strip: backdrop
            else:
                self.assertGreater(px((400, 200))[0], 200)


class TestWorldAndPlates(unittest.TestCase):
    def test_the_identity_world_picks_the_backdrop_over_the_bg_token(self):
        # a candy-bright game with a navy scrim token still previews over a sunny world
        model = {"ClassName": "ScreenGui", "Properties": {"Attributes": attrs(Kit_bg="#0f1b36", Kit_World="a sunny toy world")},
                 "Children": []}
        im, _ = preview.draw_screen(model, 400, 200)
        r, g, b = im.convert("RGB").getpixel((200, 20))
        self.assertGreater(b, 180)  # sky, not a dark night
        self.assertGreater(g, 150)
        dark = {"ClassName": "ScreenGui", "Properties": {"Attributes": attrs(Kit_bg="#0f1b36")}, "Children": []}
        im2, _ = preview.draw_screen(dark, 400, 200)
        self.assertLess(sum(im2.convert("RGB").getpixel((200, 20))), 200)

    def test_a_plate_backed_imagebutton_draws_no_placeholder_box(self):
        # Image "" = the plate child is the look; an unknown asset id still gets the labelled placeholder
        def button(image):
            return {"ClassName": "ScreenGui", "Properties": {"Attributes": attrs()},
                    "Children": [{"ClassName": "ImageButton", "Name": "B",
                                  "Properties": {"Image": image, "BackgroundTransparency": 1,
                                                 "Size": {"UDim2": [[0, 100], [0, 100]]}, "Position": {"UDim2": [[0, 50], [0, 50]]}}}]}
        plain, _ = preview.draw_screen(button(""), 300, 200)
        placeholder, _ = preview.draw_screen(button("rbxassetid://1"), 300, 200)
        backdrop, _ = preview.draw_screen({"ClassName": "ScreenGui", "Properties": {"Attributes": attrs()}, "Children": []}, 300, 200)
        # the diagonal of the placeholder cross crosses the centre of the box
        self.assertEqual(plain.convert("RGB").getpixel((100, 100)), backdrop.convert("RGB").getpixel((100, 100)))
        self.assertNotEqual(placeholder.convert("RGB").getpixel((100, 100)), backdrop.convert("RGB").getpixel((100, 100)))

    def test_an_empty_grounded_panel_is_flagged_on_desktop_only(self):
        def screen(child_w, child_h=40):
            return {"ClassName": "ScreenGui", "Properties": {"Attributes": attrs()},
                    "Children": [{"ClassName": "Frame", "Name": "Card",
                                  "Properties": {"BackgroundColor3": {"Color3": [1, 1, 1]}, "BackgroundTransparency": 0,
                                                 "Size": {"UDim2": [[0, 800], [0, 600]]}, "Position": {"UDim2": [[0, 100], [0, 100]]}},
                                  "Children": [{"ClassName": "TextLabel", "Name": "T",
                                                "Properties": {"Text": "x", "TextSize": 20, "Size": {"UDim2": [[0, child_w], [0, child_h]]},
                                                               "Position": {"UDim2": [[0, 10], [0, 10]]}, "BackgroundTransparency": 1}}]}]}
        _, checks = preview.draw_screen(screen(100), 1920, 1080)
        self.assertTrue(any(c[0] == "empty_panel" and c[1] == "Card" for c in checks), checks)
        _, full = preview.draw_screen(screen(780, 560), 1920, 1080)
        self.assertFalse(any(c[0] == "empty_panel" for c in full), full)
        _, phone = preview.draw_screen(screen(100), 844, 390)
        self.assertFalse(any(c[0] == "empty_panel" for c in phone), phone)
        # a full-screen frame is a scrim, never "empty"
        scrim = screen(100)
        scrim["Children"][0]["Properties"]["Size"] = {"UDim2": [[1, 0], [1, 0]]}
        scrim["Children"][0]["Properties"]["Position"] = {"UDim2": [[0, 0], [0, 0]]}
        _, sc = preview.draw_screen(scrim, 1920, 1080)
        self.assertFalse(any(c[0] == "empty_panel" for c in sc), sc)

    def test_phone_text_under_11px_drawn_is_flagged_on_the_phone_view_only(self):
        model = {"ClassName": "ScreenGui", "Properties": {"Attributes": attrs(Kit_Scale_phone=0.5)},
                 "Children": [{"ClassName": "TextLabel", "Name": "Hint",
                               "Properties": {"Text": "tap", "TextSize": 16, "Size": {"UDim2": [[0, 200], [0, 40]]},
                                              "Position": {"UDim2": [[0, 100], [0, 100]]}, "BackgroundTransparency": 1}}]}
        _, phone = preview.draw_viewport(model, 844, 390, "phone")
        self.assertTrue(any(c[0] == "phone_text" and c[1] == "Hint" for c in phone), phone)
        _, desk = preview.draw_viewport(model, 1920, 1080, "desktop")
        self.assertFalse(any(c[0] == "phone_text" for c in desk), desk)

    def test_the_identity_world_picture_is_the_backdrop_when_present(self):
        from PIL import Image
        import tempfile
        art = tempfile.mkdtemp()
        os.makedirs(os.path.join(art, "toy"))
        Image.new("RGB", (64, 32), (250, 20, 20)).save(os.path.join(art, "toy", "world.png"))
        old = preview.ART_DIR
        preview.ART_DIR = art
        preview._art_cache.clear()
        try:
            model = {"ClassName": "ScreenGui", "Properties": {"Attributes": attrs(Kit_Identity="toy")}, "Children": []}
            im, _ = preview.draw_screen(model, 200, 100)
            self.assertGreater(im.convert("RGB").getpixel((100, 50))[0], 200)  # the red picture, cover-fitted
        finally:
            preview.ART_DIR = old
            preview._art_cache.clear()

    def test_siblings_paint_by_zindex_like_the_engine(self):
        lay = preview.Layout(1920, 1080)
        root = {"ClassName": "Frame", "Name": "Hud", "Properties": {}}
        soul = {"ClassName": "Frame", "Name": "Soul", "Properties": {"ZIndex": 3, "LayoutOrder": 1}}
        vessel = {"ClassName": "ImageLabel", "Name": "Vessel", "Properties": {"ZIndex": 2, "LayoutOrder": 2}}
        child = {"ClassName": "ImageLabel", "Name": "Glint", "Properties": {"ZIndex": 1, "LayoutOrder": 1}}
        for inst, path in ((root, "Hud"), (soul, "Hud.Soul"), (vessel, "Hud.Vessel"), (child, "Hud.Vessel.Glint")):
            lay.order.append((inst, (0, 0, 10, 10), None, path))
        painted = [e[3] for e in lay.paint_order()]
        self.assertEqual(painted, ["Hud", "Hud.Vessel", "Hud.Vessel.Glint", "Hud.Soul"])   # z 3 over z 2; a child rides its parent

    def test_bounce_enter_starts_small_and_lands_at_full_size(self):
        self.assertLess(preview.enter_state("bounce", 0, "x")["scale"], 0.7)
        self.assertEqual(preview.enter_state("bounce", 1, "x")["scale"], 1)


    def test_a_squeeze_is_text_colliding_only_on_the_smaller_screen(self):
        desk = {"A": (0.1, 0.1, 0.2, 0.1, True), "B": (0.5, 0.1, 0.2, 0.1, True), "Bg": (0.0, 0.0, 0.9, 0.9, False),
                "Emblem": (0.1, 0.1, 0.05, 0.05, False)}
        phone = {"A": (0.1, 0.1, 0.4, 0.2, True), "B": (0.3, 0.1, 0.4, 0.2, True), "Bg": (0.0, 0.0, 0.9, 0.9, False),
                 "Emblem": (0.1, 0.1, 0.1, 0.1, False)}
        out = preview.squeezed(desk, phone, "phone")
        self.assertEqual([(c[1], c[2].split(" ")[2]) for c in out], [("A", "B")])   # A/B collide only on the phone
        # (the backdrop under text is designed; the emblem overlaps A on desktop too)

class TestStates(unittest.TestCase):
    def test_a_plate_button_state_reaches_its_plate_and_label(self):
        att = lambda v: {"String": v}  # noqa: E731
        btn = {"Name": "Buy", "ClassName": "TextButton", "Properties": {"Text": "", "Attributes": {"Attributes": {
            "Kit_States": att("hover,locked"), "Kit_S_locked": att("imageColor=#808080;text=LOCKED;art=sim/pill_panel")}}},
            "Children": [{"Name": "Plate", "ClassName": "ImageLabel", "Properties": {}},
                         {"Name": "Label", "ClassName": "TextLabel", "Properties": {"Text": "R$ 49"}}]}
        model = {"Children": [{"Name": "Shop", "Children": [btn]}]}
        self.assertEqual(preview.stated_nodes(model), [("Shop.Buy", ["hover", "locked"])])
        preview.apply_state(btn, "locked")
        plate, label = btn["Children"]
        self.assertEqual(label["Properties"]["Text"], "LOCKED")                 # (the words are the Label's)
        self.assertAlmostEqual(plate["Properties"]["ImageColor3"]["Color3"][0], 128 / 255)  # (the picture is the Plate's)
        self.assertEqual(plate["Properties"]["Attributes"]["Attributes"]["KitArt"]["String"], "sim/pill_panel")
        self.assertNotIn("ImageColor3", btn["Properties"])


class TestPaths(unittest.TestCase):
    def test_a_path_is_sampled_cut_and_drawn_like_ui_path(self):
        pts = preview.path_points("0,0;0.5,1;1,0", smooth=True)
        self.assertEqual(len(pts), 2 * 12 + 1)                                 # (12 samples a segment, like Ui.path)
        self.assertEqual(pts[0], (0.0, 0.0))
        self.assertEqual(pts[-1], (1.0, 0.0))
        half = preview.path_cut([(0, 0), (10, 0)], 0.5)
        self.assertEqual(half[-1], (5.0, 0.0))
        im, m = preview.path_layer("0,0.5;1,0.5", 100, 20, 4, "#ff0000", False, False, 0.5)
        a = im.getchannel("A")
        self.assertGreater(a.getpixel((m + 25, m + 10)), 200)                 # (drawn on the first half...)
        self.assertEqual(a.getpixel((m + 90, m + 10)), 0)                     # (...not yet on the second)


class TestAccessibility(unittest.TestCase):
    def test_busy_ground_contrast_is_the_worst_tenth_not_the_average(self):
        from PIL import Image, ImageDraw
        calm = Image.new("RGBA", (200, 60), (20, 20, 20, 255))
        layer = Image.new("RGBA", (200, 60), (0, 0, 0, 0))
        self.assertIsNone(preview.busy_contrast(calm, layer, (0, 0, 200, 60), (255, 255, 255)))   # (calm: the gate's job)
        busy = calm.copy()
        ImageDraw.Draw(busy).rectangle([0, 0, 60, 60], fill=(235, 235, 235, 255))              # (a bright cloud behind)
        worst = preview.busy_contrast(busy, layer, (0, 0, 200, 60), (255, 255, 255))
        self.assertLess(worst, 1.5)                                                               # (white on the cloud)

    def test_colour_blind_simulation_merges_red_and_green(self):
        from PIL import Image
        im = Image.new("RGB", (2, 1))
        im.putpixel((0, 0), (200, 40, 40))
        im.putpixel((1, 0), (60, 140, 40))
        d = preview.simulate_cvd(im, "deuteranopia")
        a, b = d.getpixel((0, 0)), d.getpixel((1, 0))
        self.assertLess(sum(abs(x - y) for x, y in zip(a, b)), 80)                                # (close for a deuteranope)
        t = preview.simulate_cvd(im, "tritanopia")
        self.assertEqual(t.size, (2, 1))


if __name__ == "__main__":
    unittest.main()
