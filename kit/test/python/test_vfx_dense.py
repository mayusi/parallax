"""kit/vfx/dense.py: a beat's timing read frame by frame (kit vfx breakdown --dense, kit vfx dailies). Frames are
made here: a bright disc on a dark picture that grows drawing by drawing, holds, and fades - the way an anime hit is
timed - so every number the read gives is known beforehand."""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "vfx"))
import dense as D  # noqa: E402

H, W, BG = 90, 160, 40
YY, XX = np.mgrid[0:H, 0:W]


def frame(radius=0, value=230, cx=80, cy=45):
    f = np.full((H, W, 3), BG, dtype=np.uint8)
    if radius:
        f[(XX - cx) ** 2 + (YY - cy) ** 2 <= radius * radius] = value
    return f


def hit(per_drawing):
    """6 quiet frames; a disc growing 6 -> 12 -> 18 -> 24, each drawing held `per_drawing` frames; the last drawing
    fading 230 -> 60 over 8 frames; 8 quiet frames"""
    frames = [frame() for _ in range(6)]
    for r in (6, 12, 18, 24):
        frames += [frame(r) for _ in range(per_drawing)]
    for k in range(8):
        frames.append(frame(24, int(round(230 - 21.25 * (k + 1)))))
    frames += [frame() for _ in range(8)]
    return np.stack(frames)


class TestCurves(unittest.TestCase):
    def test_cover_is_the_share_of_the_screen_lit_over_the_quiet_picture(self):
        c = D.curves(hit(2))
        self.assertEqual(float(c["cover"][0]), 0.0)                        # quiet: nothing covered
        disc = float(((XX - 80) ** 2 + (YY - 45) ** 2 <= 24 * 24).sum()) / (H * W)
        self.assertAlmostEqual(float(c["cover"][12]), disc, places=6)      # the big drawing: its own area
        self.assertAlmostEqual(float(c["bright"][12]), (230 - BG) / 255.0, places=3)
        self.assertLess(float(c["bright"][18]), float(c["bright"][12]))    # fading: dimmer, the same shape
        self.assertAlmostEqual(float(c["cover"][18]), disc, places=6)

    def test_change_is_zero_on_a_held_drawing_and_large_on_a_new_one(self):
        c = D.curves(hit(2))
        self.assertEqual(float(c["change"][9]), 0.0)                       # 12 held a second frame
        self.assertAlmostEqual(float(c["change"][10]), 1.0 - (12.0 / 18.0) ** 2, delta=0.03)   # 12 -> 18
        self.assertEqual(float(c["change"][16]), 0.0)                      # fading: the same drawing

    def test_one_dark_flicker_does_not_set_the_quiet_picture(self):
        frames = hit(2)
        frames[3] = 0                                                       # one black frame in the lead
        c = D.curves(frames)
        self.assertEqual(float(c["cover"][1]), 0.0)                        # the picture itself is still "quiet"


class TestTiming(unittest.TestCase):
    def test_a_hit_drawn_on_twos_arrives_stays_and_goes(self):
        t = D.timing(D.curves(hit(2)), 24)
        self.assertEqual(t["hit"], 12)                                      # the frame most of its light is there: the big drawing
        self.assertEqual(t["arrive"], 4)                                    # two drawings of two frames before it
        self.assertEqual(t["stay"], 4)                                      # two frames at full, two still over 70 %
        self.assertEqual(t["go"], 5)                                        # ... then down to a fifth
        self.assertEqual((t["freeze"], t["frozen"]), (4, 4))                # one drawing all the while it stays: longer than twos
        self.assertEqual((t["on"], D.on_what(t["on"])), (2, "on twos"))
        self.assertEqual(t["holds"][:2], [2, 2])
        self.assertEqual((t["cut_in"], t["stay_cut"], t["cut_away"], t["steady"]), (False, False, False, False))
        self.assertEqual(t["seconds"], {"hit": 0.5, "arrive": 0.167, "stay": 0.167, "go": 0.208, "freeze": 0.167,
                                        "frozen": 0.167, "span": round(13 / 24.0, 3)})
        self.assertIn("arrives over 4 frame(s) = 0.17 s; stays 4 frame(s) = 0.17 s at most of its light; "
                      "goes in 5 frame(s) = 0.21 s; a freeze of 4 frame(s) = 0.17 s; drawn on twos", D.describe(t))

    def test_the_same_hit_on_ones_and_on_threes(self):
        self.assertEqual(D.timing(D.curves(hit(1)), 24)["on"], 1)
        self.assertEqual(D.timing(D.curves(hit(3)), 24)["on"], 3)
        self.assertEqual(D.on_what(3), "on threes")

    def test_a_film_on_twos_uploaded_at_30_a_second_is_still_on_twos(self):
        film = hit(2)                                                       # 24 a second, every drawing two frames
        shown = film[(np.arange(int(len(film) * 30 / 24)) * 24 / 30).astype(int)]   # each 4th frame shown twice
        t = D.timing(D.curves(shown), 30)
        self.assertIn(3, t["holds"])                                        # 2 and 3 frame holds at 30 a second ...
        self.assertEqual(t["on"], 2)                                        # ... are one drawing every two film frames
        self.assertEqual(D.timing(D.curves(hit(1)), 60)["on"], 1)           # every frame new at 60: "on ones", never 0

    def test_the_uploads_own_doubled_frame_is_not_a_freeze(self):
        # a film on ONES at 30 a second: every fourth drawing is shown twice by the upload itself
        film = np.stack([frame() for _ in range(4)] + [frame(24, 200, cx=60 + 2 * k) for k in range(16)] +
                        [frame() for _ in range(4)])
        shown = film[(np.arange(int(len(film) * 30 / 24)) * 24 / 30).astype(int)]
        t = D.timing(D.curves(shown), 30)
        self.assertEqual((t["on"], t["freeze"], t["frozen"]), (1, 2, 0))    # a run of 2 is the rhythm's own at 30
        self.assertIn("no freeze", D.describe(t))
        stopped = np.concatenate([shown[:12], np.repeat(shown[12:13], 4, axis=0), shown[13:]])   # a real hit-stop:
        t = D.timing(D.curves(stopped), 30)                                 # one drawing on screen four frames
        self.assertEqual((t["freeze"], t["frozen"]), (4, 4))
        self.assertIn("a freeze of", D.describe(t))

    def test_a_drawing_frozen_four_frames_at_the_hit_is_read_as_a_freeze_of_four(self):
        frames = [frame() for _ in range(5)] + [frame(10)] + [frame(24) for _ in range(4)] + \
                 [frame(20, 150), frame(14, 110)] + [frame() for _ in range(6)]
        t = D.timing(D.curves(np.stack(frames)), 24)
        self.assertEqual((t["hit"], t["arrive"], t["stay"], t["go"], t["freeze"]), (6, 1, 4, 1, 4))
        self.assertEqual(t["seconds"]["freeze"], 0.167)

    def test_light_that_is_there_in_one_frame_snaps_in(self):
        frames = [frame() for _ in range(5)] + [frame(24), frame(23), frame(24)] + [frame() for _ in range(5)]
        t = D.timing(D.curves(np.stack(frames)), 24)
        self.assertEqual((t["hit"], t["arrive"], t["stay"], t["go"], t["freeze"]), (5, 0, 3, 0, 1))
        self.assertFalse(t["cut_in"])                                       # nothing lit the frame before: not a cut
        self.assertIn("arrives in one frame (nothing lit the frame before)", D.describe(t))
        self.assertIn("no freeze", D.describe(t))

    def test_the_hit_is_where_the_light_arrives_not_the_brightest_frame_of_a_long_stay(self):
        # the FlameArc arc, 2026-11-12: there in one frame, then creeping brighter for most of a second; the
        # brightest frame is near the shot's end, and that is not where an eye puts the hit
        frames = [frame() for _ in range(4)] + [frame(24, 200 + 2 * k) for k in range(15)] + [frame() for _ in range(4)]
        t = D.timing(D.curves(np.stack(frames)), 24)
        self.assertEqual((t["hit"], t["brightest"], t["arrive"], t["stay"]), (4, 18, 0, 15))

    def test_a_shot_that_opens_on_it_or_ends_while_it_is_lit_says_so(self):
        whole = hit(2)
        opened = D.timing(D.curves(whole[12:]), 24)                         # the cut lands on the big drawing
        self.assertTrue(opened["cut_in"])
        self.assertEqual(opened["arrive"], 0)
        self.assertIn("the shot opens on it already lit (no arrival to read)", D.describe(opened))
        left = D.timing(D.curves(whole[:14]), 24)                           # ... or leaves while it is at full light
        self.assertTrue(left["stay_cut"] and left["cut_away"])
        self.assertIn("the shot ends while it is still there", D.describe(left))

    def test_a_window_that_never_lights_up_has_no_timing_and_says_why(self):
        c = D.curves(np.stack([frame() for _ in range(12)]))
        self.assertIsNone(D.timing(c, 24))
        self.assertIn("nothing lit up", D.verdict(c, None))
        self.assertEqual(D.describe(None), "nothing lit up")

    def test_lit_and_changing_on_every_frame_is_named_not_read_as_a_beat(self):
        frames = np.stack([frame(10, cx=12 + 9 * i) for i in range(16)])   # a light sliding across: a moving camera
        c = D.curves(frames)
        t = D.timing(c, 24)
        self.assertEqual(t["span"], [0, 15])
        self.assertIn("moving camera", D.verdict(c, t))
        self.assertEqual(D.verdict(D.curves(hit(2)), D.timing(D.curves(hit(2)), 24)), "")   # a clean beat: nothing to say


def scene_frame(radius=0, patch=True):
    """a blue-grey night picture with an orange lamp always on screen (scenery in the effect's hue band) and, when
    `radius`, an orange fire disc with a white-hot middle: what a real scene's frame holds"""
    f = np.zeros((H, W, 3), dtype=np.uint8)
    f[:] = (40, 52, 70)
    if patch:
        f[4:16, 4:24] = (230, 120, 40)
    if radius:
        f[(XX - 80) ** 2 + (YY - 45) ** 2 <= radius * radius] = (240, 130, 30)
        f[(XX - 80) ** 2 + (YY - 45) ** 2 <= (radius // 3) ** 2] = (255, 250, 240)
    return f


class TestByColour(unittest.TestCase):
    HUE = (5.0, 55.0)

    def beat(self):
        frames = [scene_frame() for _ in range(6)]
        for r in (6, 12, 18, 24):
            frames += [scene_frame(r), scene_frame(r)]
        frames += [scene_frame(r) for r in (18, 14, 10, 6, 3)] + [scene_frame() for _ in range(8)]
        return np.stack(frames)

    def test_the_effect_is_what_the_key_read_calls_it_orange_or_white_hot_never_the_night(self):
        c = D.curves(self.beat(), hue=self.HUE)
        lamp = 12 * 20 / float(H * W)
        self.assertAlmostEqual(float(c["cover"][0]), lamp, places=6)       # the lamp alone: in the band, not the beat
        disc = float(((XX - 80) ** 2 + (YY - 45) ** 2 <= 24 * 24).sum()) / (H * W)
        self.assertAlmostEqual(float(c["cover"][12]), lamp + disc, places=6)   # fire and its white-hot middle
        self.assertEqual(float(D.curves(self.beat(), hue=(200.0, 260.0))["cover"][0]), 0.0)   # a blue band: nothing lit

    def test_scenery_in_the_band_is_the_windows_floor_not_the_beat(self):
        t = D.timing(D.curves(self.beat(), hue=self.HUE), 24)
        self.assertEqual((t["hit"], t["arrive"], t["stay"], t["go"], t["freeze"], t["on"]), (12, 4, 2, 2, 2, 2))
        self.assertGreater(t["base"], 0.0)                                  # the lamp is there, and is taken off
        self.assertEqual((t["cut_in"], t["stay_cut"], t["cut_away"], t["steady"]), (False, False, False, False))

    def test_a_window_lit_at_one_level_throughout_has_no_beat_shape(self):
        c = D.curves(np.stack([scene_frame(18) for _ in range(12)]), hue=self.HUE)
        t = D.timing(c, 24)
        self.assertTrue(t["steady"])
        self.assertIn("steady level", D.verdict(c, t))


def made(energy, change):
    """curves written out by hand: `energy` light a frame (one drawing's cover, at full brightness), `change` 1 where
    a new drawing starts"""
    return {"cover": np.array(energy, dtype=float), "bright": np.ones(len(energy)), "change": np.array(change, dtype=float)}


class TestWholeDrawings(unittest.TestCase):
    """a review's findings, 2026-11-12: a drawing the lit span cut in two was counted as a short hold"""

    def test_a_film_on_threes_seen_through_a_short_lit_span_is_not_called_ones(self):
        # drawings start at frames 0, 3, 6, 9; only frames 2..6 are lit: one frame of the first drawing, the whole
        # second, one frame of the third
        t = D.timing(made([0, 0, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0], [0, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0]), 24)
        self.assertEqual(t["holds"], [1, 3, 1])
        self.assertIsNone(t["on"])                                          # ONE whole drawing is not a rhythm
        self.assertEqual(t["frozen"], 0)                                    # ... and three frames may just be threes
        self.assertIn("3 drawing(s) in it", D.describe(t))

    def test_two_whole_drawings_are_a_rhythm(self):
        # lit from frame 3 to 11: three whole drawings of three frames, a new one starting where the light ends
        t = D.timing(made([0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0], [0, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0]), 24)
        self.assertEqual((t["holds"], t["on"], t["frozen"]), ([3, 3, 3], 3, 0))

    def test_a_freeze_the_window_ends_on_is_at_least_that_long(self):
        # three new drawings, then the third stays to the window's last frame
        scene = D.timing(made([0, 0, 1, 1, 1, 1, 1, 1, 1, 1], [0, 0, 1, 1, 1, 0, 0, 0, 0, 0]), 24)
        self.assertEqual((scene["frozen"], scene["frozen_open"], scene["stay_cut"]), (6, True, True))
        # ours: the same, frozen four frames, then gone
        ours = D.timing(made([0, 0, 1, 1, 1, 1, 1, 1, 0, 0], [0, 0, 1, 1, 1, 0, 0, 0, 1, 0]), 24)
        self.assertEqual((ours["frozen"], ours["frozen_open"]), (4, False))
        self.assertIn("a freeze while it stays: the scene at least 0.25 s (6 of its frames), ours 0.17 s (4 of its frames)",
                      D.compare(scene, ours))
        self.assertIn("a freeze of at least 6 frame(s)", D.describe(scene))
        # an EARLIER, longer freeze and then a drawing still held when the window ends: that last one may have gone
        # on past the earlier one's length, so the freeze is "at least" whenever the window ends while it stays
        earlier = D.timing(made([0, 0] + [1] * 10, [0, 0, 1, 1, 0, 0, 0, 0, 1, 0, 0, 0]), 24)
        self.assertEqual((earlier["frozen"], earlier["frozen_open"]), (5, True))
        # no freeze seen before the cut is "none in what the shot shows", and it tells the two apart only when ours
        # froze within a stay no longer than the scene's seen one
        cut = D.timing(made([0, 0] + [1] * 8, [0, 0, 1, 1, 1, 1, 1, 1, 1, 1]), 24)
        self.assertEqual((cut["frozen"], cut["frozen_open"], cut["seconds"]["stay"]), (0, True, 0.333))
        self.assertIn("no freeze in what the shot shows", D.describe(cut))
        self.assertIn("a freeze while it stays: the scene none in the 0.33 s its shot shows, ours 0.17 s (4 of its frames)",
                      D.compare(cut, ours))
        # ours frozen LONGER than what the cut let us see of the scene's: nothing can be claimed
        longer = D.timing(made([0, 0] + [1] * 12 + [0, 0], [0, 0, 1, 1, 1] + [0] * 9 + [1, 0]), 24)
        self.assertEqual((longer["frozen"], longer["frozen_open"]), (10, False))
        self.assertFalse(any(s.startswith("a freeze") for s in D.compare(scene, longer)))

    def test_a_freeze_the_window_opens_on_is_at_least_that_long_too(self):
        # a third review, 2026-11-12: only the window's END made a freeze "at least". A window that OPENS on a held
        # drawing saw only the rest of that hold
        curves = made([1] * 6 + [0] * 4, [0, 0, 0, 0, 0, 1, 1, 0, 0, 0])
        opens = D.timing(curves, 24)
        self.assertEqual((opens["cut_in"], opens["frozen"], opens["frozen_open"], opens["stay_cut"]), (True, 5, True, False))
        self.assertIn("opens on it already lit", D.describe(opens))
        self.assertIn("a freeze of at least 5 frame(s)", D.describe(opens))
        # a scene's whole freeze of six frames beside it: ours may have been frozen longer than the five seen, so
        # "ours 0.21 s" is not claimed against the scene's 0.25 s
        whole = D.timing(made([0, 0] + [1] * 8 + [0, 0], [0, 0, 1, 0, 0, 0, 0, 0, 1, 1, 1, 0]), 24)
        self.assertEqual((whole["frozen"], whole["frozen_open"]), (6, False))
        self.assertFalse(any(s.startswith("a freeze") for s in D.compare(whole, opens)))
        # the frame before the window is KNOWN to be dark (our own recording): the light arrives in one frame there,
        # the drawing started with it, and its freeze is whole
        dark = D.timing(curves, 24, before=0.0)
        self.assertEqual((dark["cut_in"], dark["arrive"], dark["frozen"], dark["frozen_open"]), (False, 0, 5, False))
        self.assertIn("arrives in one frame", D.describe(dark))
        self.assertIn("a freeze of 5 frame(s)", D.describe(dark))
        # ... and known to be LIT: as a cut
        lit = D.timing(curves, 24, before=1.0)
        self.assertEqual((lit["cut_in"], lit["frozen_open"]), (True, True))

    def test_the_floor_is_one_rule_whatever_is_known_of_the_frame_before(self):
        # the real numbers of the FlameArc animatic's clash (2026-11-12): two frames of a small drawing, the hit drawing
        # for three, whole, a hair smaller, whole, going. The two small frames are taken for "what is lit through the
        # window": the light "arrives in one frame", and the line it is called arrived at sits high (0.82 of its peak)
        light = [0.203, 0.203, 0.561, 0.561, 0.561, 0.656, 0.580, 0.656, 0.397, 0.397]
        curves = made(light, [1, 0, 1, 0, 0, 1, 1, 1, 1, 0])
        blind = D.timing(curves, 30)
        self.assertEqual((blind["hit"], blind["arrive"]), (2, 0))
        self.assertGreater(blind["base"], 0.25)
        line = (blind["base"] + D.MOST * (blind["peak"] - blind["base"])) / blind["peak"]
        self.assertTrue(0.80 < line < 0.85)             # (why the animatic's light is WHOLE on its hit drawing)
        # knowing the frame before was dark does NOT lower the floor. It was tried (and taken out the same day): a
        # glow that starts WITH the stretch then counts as the beat arriving - a snap on it read as a third of a
        # second - and a scene's shot and our own stretch were read by two rules
        self.assertEqual(D.timing(curves, 30, before=0.0)["base"], blind["base"])
        self.assertEqual(D.timing(curves, 30, before=0.9)["base"], blind["base"])
        glow = made([0.3] * 10 + [1.0] * 6 + [0.3] * 14, [1] + [0] * 9 + [1] + [0] * 5 + [1] + [0] * 13)
        for before in (None, 0.0):
            snap = D.timing(glow, 30, before=before)
            self.assertEqual((snap["hit"], snap["arrive"], snap["go"]), (10, 0, 0), before)     # the snap, in one frame

    def test_our_own_stretch_knows_the_frame_before_it(self):
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "vfx"))
        import denseclip as DC
        # beat A: dark, then one drawing there at once and held five frames, a new one, gone
        energy = [0] * 10 + [1] * 6 + [0] * 10
        change = [0] * 10 + [1, 0, 0, 0, 0, 1] + [1] + [0] * 9
        shot = {"fps": 30.0, "from": 0.0, "frames": len(energy), "curves": made(energy, change)}
        a = DC.within(shot, 10 / 30, 22 / 30)["timing"]
        self.assertEqual((a["cut_in"], a["arrive"], a["frozen"], a["frozen_open"]), (False, 0, 5, False))
        # beat B's stretch opens while beat A's drawing is still held: what is seen of that hold is "at least"
        energy = [0] * 10 + [1] * 20 + [0] * 10
        change = [0] * 10 + [1] + [0] * 14 + [1] + [0] * 4 + [1] + [0] * 9
        shot = {"fps": 30.0, "from": 0.0, "frames": len(energy), "curves": made(energy, change)}
        b = DC.within(shot, 20 / 30, 34 / 30)["timing"]
        self.assertEqual((b["cut_in"], b["frozen"], b["frozen_open"], b["stay_cut"]), (True, 5, True, False))


class TestCompare(unittest.TestCase):
    def test_a_curve_read_at_another_frame_rate_keeps_its_holds(self):
        np.testing.assert_array_equal(D.resample([0, 1, 2, 3], 24, 48), [0, 0, 1, 1, 2, 2, 3, 3])
        np.testing.assert_array_equal(D.resample([5, 7], 60, 30, count=1), [5])

    def test_the_differences_are_said_in_seconds_and_in_drawings(self):
        scene = D.timing(D.curves(hit(2)), 24)
        ours = D.timing(D.curves(hit(1)), 60)                               # every frame new, at 60 a second
        self.assertEqual(D.compare(scene, ours), [
            "it arrives: the scene over 0.17 s, ours over 0.03 s",
            "it stays: the scene 0.17 s, ours 0.05 s",
            "it goes: the scene in 0.21 s, ours in 0.08 s",
            "a freeze while it stays: the scene 0.17 s (4 of its frames), ours has none",
            "the scene is drawn on twos, ours on ones"])
        snap = D.timing(D.curves(np.stack([frame() for _ in range(5)] + [frame(24), frame(23), frame(24), frame(23)] +
                                          [frame(20, 150)] + [frame() for _ in range(5)])), 24)
        self.assertEqual(D.compare(snap, scene)[0], "it arrives: the scene in one frame, ours over 0.17 s")
        self.assertEqual(D.compare(scene, scene), [])                       # the same timing: nothing to say
        self.assertEqual(D.compare(scene, None), ["one of the two never lights up: nothing to compare"])

    def test_what_a_cut_hid_is_not_compared_or_is_at_least(self):
        scene = D.timing(D.curves(hit(2)), 24)
        cut = D.timing(D.curves(hit(2)[12:]), 24)                           # a scene that cuts in on the lit effect
        self.assertEqual(D.compare(cut, scene)[0], "it arrives: the scene's shot opens on it already lit, ours takes 0.17 s")
        self.assertIsNone(cut["on"])                                        # one held drawing is not a rhythm ...
        self.assertIn("1 drawing(s) in it, the longest on screen 9 frame(s)", D.describe(cut))
        self.assertFalse(any("drawn" in s for s in D.compare(cut, scene)))  # ... so none is compared
        long = D.timing(D.curves(np.stack([frame() for _ in range(4)] + [frame(24 - k % 2) for k in range(12)])), 24)
        self.assertTrue(long["stay_cut"])                                   # twelve frames lit, then the shot ends
        self.assertIn("it stays: the scene at least 0.50 s (its shot ends while it is lit), ours 0.17 s",
                      D.compare(long, scene))
        self.assertFalse(any(s.startswith("it stays") or s.startswith("it goes") for s in D.compare(D.timing(
            D.curves(hit(2)[:14]), 24), scene)))                            # a scene cut after 2 frames: ours is not "longer"


if __name__ == "__main__":
    unittest.main()


def ink(colour_paper=(250, 250, 250), colour_ink=(8, 8, 8)):
    """an impact frame: the whole picture ink and paper (the disc paper, the rest ink)"""
    f = np.empty((H, W, 3), dtype=np.uint8)
    f[:] = colour_ink
    f[(XX - 80) ** 2 + (YY - 45) ** 2 <= 24 * 24] = colour_paper
    return f


class TestSilhouettes(unittest.TestCase):
    """the V3 doc, VFX stage G.1: the one-frame silhouette beat (mono, or a pink negative) is read and compared"""

    def with_flash(self, at, paper=(250, 250, 250), ink_c=(8, 8, 8), run=1):
        frames = list(hit(2))
        for k in range(run):
            frames[at + k] = ink(paper, ink_c)
        return np.stack(frames)

    def test_a_one_frame_ink_and_paper_frame_in_the_hold_is_a_mono_silhouette(self):
        c = D.curves(self.with_flash(13))
        self.assertGreaterEqual(float(c["flat"][13]), D.TWO_TONE)
        self.assertLess(float(c["flat"][12]), D.TWO_TONE)
        self.assertEqual(D.silhouettes(c), [(13, 1, "mono")])
        t = D.timing(c, 24.0)
        self.assertEqual([s["kind"] for s in t["silhouettes"]], ["mono"])
        self.assertEqual(t["silhouettes"][0]["at"], 13 - t["hit"])

    def test_a_pink_negative_is_tinted_and_a_long_dark_stretch_is_none(self):
        c = D.curves(self.with_flash(13, paper=(255, 230, 245), ink_c=(150, 0, 60)))  # a dark magenta ink (luma 0.14)
        self.assertEqual(D.silhouettes(c), [(13, 1, "tinted")])
        # a KNOWN LIMIT: a negative whose ink is a MID-tone pink (luma ~0.4) is not near black or white, so it is not
        # read as two-tone at all
        mid = D.curves(self.with_flash(13, paper=(255, 240, 250), ink_c=(230, 60, 150)))
        self.assertEqual(D.silhouettes(mid), [])
        c2 = D.curves(self.with_flash(13, paper=(255, 240, 250), ink_c=(30, 0, 12)))
        self.assertEqual(D.silhouettes(c2)[0][2], "tinted")
        long = D.curves(self.with_flash(10, run=6))                        # six frames: a cut to black, not a beat
        self.assertEqual(D.silhouettes(long), [])
        self.assertEqual(D.silhouettes(D.curves(hit(2))), [])

    def test_compare_says_the_scene_flashes_one_and_ours_none(self):
        scene = D.timing(D.curves(self.with_flash(13)), 24.0)
        ours = D.timing(D.curves(hit(2)), 24.0)
        said = D.compare(scene, ours)
        self.assertTrue(any(s.startswith("a silhouette frame: the scene flashes 1 (mono") for s in said), said)
        self.assertFalse(any("silhouette" in s for s in D.compare(scene, scene)))
        # an older read with no two-tone measure is not compared on it
        old = dict(ours)
        old.pop("silhouettes")
        self.assertFalse(any("silhouette" in s for s in D.compare(scene, old)))
