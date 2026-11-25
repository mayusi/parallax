"""kit/vfx/denseclip.py, dailies.py and breakdown.py --dense on real (made) video: two small clips whose every
frame is known (kit/selftest/vfx/dailies/clips.py) go through ffmpeg and back, so the read is proven on encoded
video - a held drawing must stay one drawing after h264 - and the pictures are checked for the one thing they are
for: every frame large (640 px), two a picture, so a reader gets them at full size."""

import contextlib
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "vfx"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "selftest", "vfx", "dailies"))
import breakdown  # noqa: E402
import clips  # noqa: E402
import dailies  # noqa: E402
import denseclip as DC  # noqa: E402

FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def run(tool, argv):
    """a tool's main -> (exit code, its JSON line)"""
    said = io.StringIO()
    with contextlib.redirect_stdout(said):
        code = tool.main(argv)
    return code, json.loads(said.getvalue().strip().splitlines()[-1])


class TestShots(unittest.TestCase):
    def test_a_beat_is_read_shot_by_shot_between_its_cuts(self):
        shots = DC.shots_of(10.7, 13.5, [10.0, 10.7, 11.67, 12.03, 13.5], 30.0, 60.0)
        self.assertEqual(len(shots), 3)
        self.assertAlmostEqual(shots[0][0], 10.7 + 1 / 30.0, places=3)     # one frame in from the cut ...
        self.assertAlmostEqual(shots[0][1], 11.67 - 1 / 30.0, places=3)    # ... and one before the next

    def test_a_shot_the_beat_barely_touches_is_not_its_shot(self):
        # the beat is written to a tenth of a second by eye: 0.1 s of a 2 s neighbour is not this beat
        shots = DC.shots_of(10.0, 11.0, [8.1, 10.1, 11.0], 30.0, 60.0)
        self.assertEqual(len(shots), 1)
        self.assertAlmostEqual(shots[0][0], 10.1 + 1 / 30.0, places=3)

    def test_a_short_beat_inside_a_long_shot_is_still_that_shots(self):
        # a hit of 0.2 s is a whole beat (a review, 2026-11-12: it came back with no shot at all)
        self.assertEqual(len(DC.shots_of(1.0, 1.2, [], 24.0, 5.0)), 1)
        self.assertEqual(len(DC.shots_of(1.0, 1.29, [], 24.0, 5.0)), 1)
        self.assertEqual(len(DC.shots_of(0.75, 1.25, [1.0], 24.0, 5.0)), 2)     # half of the beat on each side of a cut

    def test_a_recording_with_no_steady_frame_rate_is_not_read_at_a_thousand_a_second(self):
        self.assertEqual(DC.steady_rate("30/1", "30/1"), 30.0)
        self.assertAlmostEqual(DC.steady_rate("1000/1", "30000/1001"), 29.97, places=2)
        self.assertEqual(DC.steady_rate("90000/1", "0/0"), 30.0)
        self.assertEqual(DC.steady_rate(None, None), 30.0)

    def test_a_beats_stretch_of_our_clock_goes_by_time_and_is_never_under_three_frames(self):
        # a chart's rows are not always in time order (katana_water_set: 0, .05, .08, .9, .45), and a flash of one
        # frame is a beat too (a review, 2026-11-12: such beats came back as "ours never lights up")
        beats = [{"t": 0.0}, {"t": 0.05}, {"t": 0.08}, {"t": 0.9}, {"t": 0.45}]
        fps, length = 30.0, 2.0
        got = [DC.stretch(beats, k, fps, length) for k in range(len(beats))]
        for a, b in got:
            self.assertGreaterEqual(round((b - a) * fps), 3)                # three frames at least, every one
        self.assertAlmostEqual(got[3][1], length)                           # the LAST beat in time runs to the end ...
        self.assertAlmostEqual(got[4][1], 0.9 - 2 / fps)                    # ... and the last ROW stops two frames short of it
        self.assertAlmostEqual(got[1][1], 0.05 + 3 / fps)                   # a 0.03 s beat is read over three frames
        self.assertEqual(DC.stretch([{"t": 1.95}], 0, fps, length)[1], length)     # never past the recording

    def test_a_recording_is_real_time_every_hit_stop_before_a_beat_moves_it(self):
        # the chart's times are the EFFECT's clock; the player's clock stands still through a hit-stop while the
        # recording runs on. A beat at 1.89 s after holds of 0.12 and 0.06 s starts at 2.00 s of the recording - read
        # at its chart time, its stretch showed the beat before it (found by the timing animatic's own check, 2026-11-12)
        # The clock is the RECORDER's, frame by frame (a review, 2026-11-12: a continuous sum of the holds was up to a
        # frame and a half off): one step of 1/30 s a frame, the frame taken AFTER the step, a hold counted in whole
        # frames. Frame 8 is the first to show 0.30 s (it stops ON the hit-stop), frames 9-11 hold it (0.12 s is three
        # frames and a rest that the fourth spends), frame 12 moves on.
        stops = {"hitstop": [{"at": 0.3, "hold": 0.12}, {"at": 1.5, "hold": 0.06}], "duration": 3.4}
        shown = DC.frame_times(stops, 30.0)
        self.assertEqual([round(t, 3) for t in shown[6:13]], [0.233, 0.267, 0.3, 0.3, 0.3, 0.3, 0.333])
        self.assertEqual([round(t, 3) for t in shown[46:50]], [1.467, 1.5, 1.5, 1.533])     # 0.06 s: one held frame
        clock = DC.clock_of(stops, 30.0)
        frame = lambda t: int(round(clock(t) * 30))  # noqa: E731
        # (a hold AT a time is not before it: the frame that hits is the first frame of its own hold)
        self.assertEqual([frame(t) for t in (0.0, 0.3, 0.31, 1.5, 1.51, 1.89)], [0, 8, 12, 47, 49, 60])
        beats = [{"t": 0.0}, {"t": 0.31}, {"t": 0.85}, {"t": 1.89}, {"t": 2.19}]
        a, b = DC.stretch(beats, 3, 30.0, 3.6, clock)
        self.assertAlmostEqual(a, 60 / 30.0)                               # where the RECORDING has the beat ...
        self.assertAlmostEqual(b, 69 / 30.0 - 2 / 30.0)                    # ... to two frames before the next one
        self.assertEqual(DC.stretch(beats, 3, 30.0, 3.6), (1.89, 2.19 - 2 / 30.0))     # no clock: the chart's own times
        # a hold with no length given is the player's own 0.08 s: the frame that stops and two held ones
        plain = DC.clock_of({"hitstop": [{"at": 1.01}], "duration": 3.0}, 30.0)
        self.assertEqual([int(round(plain(t) * 30)) for t in (1.01, 1.02, 2.0)], [30, 33, 62])
        # a preset with no hit-stop: frame i shows the clock after i + 1 steps, so a moment is seen a frame "early"
        self.assertAlmostEqual(DC.clock_of(None, 30.0)(1.49), 44 / 30.0)
        self.assertAlmostEqual(DC.clock_of({"layers": []}, 24.0)(1.49), 35 / 24.0)
        # (a preset that gives no length plays five seconds, as in the player: a moment after that is in no frame, and
        # is given the first moment past the recording)
        self.assertAlmostEqual(DC.clock_of(None, 30.0)(7.0), 150 / 30.0)
        # two hit-stops at one moment: the player takes the first only
        both = DC.frame_times({"hitstop": [{"at": 0.51, "hold": 0.11}, {"at": 0.51, "hold": 0.3}], "duration": 1.0}, 30.0)
        self.assertEqual(sum(1 for t in both if abs(t - 0.51) < 1e-9), 4)  # 0.11 s: the frame that stops + three held
        # slow motion: the clock at half speed from 1 s to 2 s takes two seconds to cross it
        slow = DC.clock_of({"timewarp": [[1.0, 0.5], [2.0, 0.5]], "duration": 3.0}, 30.0)
        self.assertAlmostEqual(slow(0.49), 14 / 30.0)
        self.assertAlmostEqual(slow(1.99) - slow(1.01), 2 * 0.98, delta=1.5 / 30)
        self.assertAlmostEqual(slow(2.9) - slow(2.1), 0.8, delta=1.5 / 30)

    def test_the_clock_is_the_recorders_own_held_to_a_real_recording(self):
        # GOLDEN, from the player itself: the times its recorder posted for the frames of the FlameArc set's animatic
        # (2026-11-12, 30 frames a second; hit-stops of 0.12 s at 0.300 s and 0.06 s at 1.933 s, 3.4 s long), and the
        # number of frames in the video it wrote (107). The model must give those times and that many frames: a
        # frame more or less, and every beat after a hit-stop is read a frame off.
        posted = [0.033, 0.067, 0.1, 0.133, 0.167, 0.2, 0.233, 0.267, 0.3, 0.333, 0.367, 0.4, 0.433, 0.467, 0.5, 0.533,
                  0.567, 0.6, 0.633, 0.667, 0.7, 0.733, 0.767, 0.8, 0.833, 0.867, 0.9, 0.933, 0.967, 1.0, 1.033, 1.067,
                  1.1, 1.133, 1.167, 1.2, 1.233, 1.267, 1.3, 1.333, 1.367, 1.4, 1.433, 1.467, 1.5, 1.533, 1.567, 1.6,
                  1.633, 1.667, 1.7, 1.733, 1.767, 1.8, 1.833, 1.867, 1.9, 1.933, 1.966, 2.0, 2.033, 2.066, 2.1, 2.133,
                  2.166, 2.2, 2.233, 2.266, 2.3, 2.333, 2.366, 2.4, 2.433, 2.466, 2.5, 2.533, 2.566, 2.6, 2.633, 2.666,
                  2.7, 2.733, 2.766, 2.8, 2.833, 2.866, 2.9, 2.933, 2.966, 3.0, 3.033, 3.066, 3.1, 3.133, 3.166, 3.2,
                  3.233, 3.266, 3.3, 3.333, 3.366, 3.4, 3.433]
        shown = DC.frame_times({"duration": 3.4, "hitstop": [{"at": 0.3, "hold": 0.12}, {"at": 1.933, "hold": 0.06}]}, 30.0)
        self.assertEqual(sorted({float(f"{t:.3f}") for t in shown}), posted)      # (the recorder posts toFixed(3))
        self.assertEqual(len(shown), 107)
        held = {t: sum(1 for s in shown if f"{s:.3f}" == f"{t:.3f}") for t in (0.3, 1.933)}
        self.assertEqual(held, {0.3: 4, 1.933: 2})                         # the frame that stops, and the held ones

    def test_the_clock_holds_through_slow_motion_and_long_hit_stops_of_a_real_recording(self):
        # GOLDEN, from the player itself: starblade's recording (2026-10, 30 frames a second, 13.5 s: twelve keys of
        # slow motion, hit-stops of 1.5 s and 0.9 s). Its recorder posted 498 different times for the 569 frames of
        # the video it wrote. The model must give those very times: their count, a digest of all of them, a run of
        # them through the slowest part, and how many frames each hit-stop holds
        played = {"duration": 13.5, "hitstop": [{"at": 4.06, "hold": 1.5, "span": 1.07}, {"at": 5.66, "hold": 0.9, "span": 0.36}],
                  "timewarp": [[0.4, 1], [2.6, 1], [3.55, 0.78], [3.8, 0.26], [4.05, 0.234], [4.1, 0.65], [4.55, 0.78], [4.8, 0.715],
                               [5.6, 0.65], [5.7, 0.325], [6.2, 0.52], [7.2, 1]]}
        shown = DC.frame_times(played, 30.0)
        self.assertEqual(len(shown), 569)
        posted = sorted({float(f"{t:.3f}") for t in shown})               # (the recorder posts toFixed(3))
        self.assertEqual(len(posted), 498)
        self.assertEqual(hashlib.sha1(",".join(f"{t:.3f}" for t in posted).encode()).hexdigest()[:16], "473ed86c2f85e3cd")
        self.assertEqual(posted[118:128], [3.728, 3.741, 3.754, 3.766, 3.777, 3.787, 3.797, 3.806, 3.814, 3.823])
        self.assertEqual((posted[0], posted[100], posted[200], posted[300], posted[400], posted[-1]),
                         (0.033, 3.305, 5.083, 6.966, 10.283, 13.516))
        held = {t: sum(1 for x in shown if f"{x:.3f}" == f"{t:.3f}") for t in (4.06, 5.66)}
        self.assertEqual(held, {4.06: 45, 5.66: 28})                       # 1.5 s and 0.9 s of frames, the stopping one in

    def test_the_clock_is_of_the_preset_as_it_was_played(self):
        # a preset's FILE can name a hit-stop by a beat ("at": "blast": 5.66 s only once expanded). The clock never
        # crashes on what is not a number - it leaves it out - and the played preset is read from the bundle the play
        # command gave the player, when that is the recording's
        file_s = {"duration": 2.0, "beats": {"blast": 0.9}, "hitstop": [{"at": 0.51, "hold": 0.11}, {"at": "blast", "hold": 0.3}],
                  "timewarp": [[1.0, 0.5], ["later", 0.5], [1.5, 0.5]]}
        clock, left = DC.numbers_only(file_s)
        self.assertEqual((clock["hitstop"], clock["timewarp"], left), ([{"at": 0.51, "hold": 0.11}], [[1.0, 0.5], [1.5, 0.5]], 2))
        # (the player reads a slow-motion key's first two numbers, whatever follows them)
        self.assertEqual(DC.numbers_only({"timewarp": [[1.0, 0.5, "ease"], [1.5, 0.5]]}), ({"timewarp": [[1.0, 0.5], [1.5, 0.5]]}, 0))
        self.assertEqual(len(DC.frame_times(file_s, 30.0)), len(DC.frame_times(clock, 30.0)))
        for odd in (None, [], "x", {"hitstop": "x", "timewarp": [[1], "y"], "duration": "long"}, {"hitstop": [{"hold": 1}, 7, {"at": float("nan")}]}):
            self.assertEqual(len(DC.frame_times(odd, 30.0)), 150, odd)     # no length: the player's own 5 s
        root = tempfile.mkdtemp(prefix="kit_played_")
        here = os.getcwd()
        os.chdir(root)
        try:
            os.makedirs(DC.PLAY)
            os.makedirs(DC.BOOTH)
            bundle, shot = os.path.join(DC.PLAY, "fx.json"), os.path.join(DC.BOOTH, "fx_play_hero.mp4")
            # no bundle: the file's own numbers; exact only for a preset that is not composed and lost nothing
            self.assertEqual(DC.played("fx", shot, {"duration": 2.0, "hitstop": [{"at": 0.5, "hold": 0.1}]}),
                             ({"duration": 2.0, "hitstop": [{"at": 0.5, "hold": 0.1}]}, True))
            self.assertEqual(DC.played("fx", shot, file_s), (clock, False))
            self.assertFalse(DC.played("fx", shot, {"duration": 2.0, "use": [{"part": "p"}]})[1])
            # (an overlay's `time` stretches the length and every hit-stop when the preset is expanded: composed too)
            self.assertFalse(DC.played("fx", shot, {"duration": 2.0, "hitstop": [{"at": 0.5, "hold": 0.1}], "overlay": {"time": 1.5}})[1])
            # the bundle, written before the recording: the preset as it was played, exactly
            expanded = dict(file_s, hitstop=[{"at": 0.51, "hold": 0.11}, {"at": 0.9, "hold": 0.3}], timewarp=[[1.0, 0.5], [1.5, 0.5]])
            json.dump({"name": "fx", "preset": expanded}, open(bundle, "w"))
            open(shot, "wb").write(b"x")
            os.utime(bundle, (1000, 1000))
            os.utime(shot, (1010, 1010))
            got, exact = DC.played("fx", shot, file_s)
            self.assertEqual((got["hitstop"], exact), ([{"at": 0.51, "hold": 0.11}, {"at": 0.9, "hold": 0.3}], True))
            os.utime(bundle, (1100, 1100))                                 # written again after it: used, not sure
            self.assertEqual(DC.played("fx", shot, file_s), (got, False))
            # a bundle of the same name from long before the recording is not this recording's either (another play,
            # another build folder): for a composed preset it is used and NOT sure; a preset that is not composed
            # says all there is to say itself, and the stale bundle is not looked at
            os.utime(bundle, (1010 - DC.RECORDS_IN - 60, 1010 - DC.RECORDS_IN - 60))
            self.assertEqual(DC.played("fx", shot, file_s), (got, False))
            plain = {"duration": 2.0, "hitstop": [{"at": 0.5, "hold": 0.1}]}
            self.assertEqual(DC.played("fx", shot, plain), ({"duration": 2.0, "hitstop": [{"at": 0.5, "hold": 0.1}]}, True))
            # ... unless its file was edited after the recording: then nothing says what was recorded
            file_path = os.path.join(root, "fx.json")
            json.dump(plain, open(file_path, "w"))
            os.utime(file_path, (1005, 1005))
            self.assertTrue(DC.played("fx", shot, plain, file_path)[1])
            os.utime(file_path, (1500, 1500))
            self.assertFalse(DC.played("fx", shot, plain, file_path)[1])
            self.assertIn("CAUTION", DC.caution({"clock_exact": False}))
            self.assertEqual(DC.caution({"clock_exact": True}), "")
            os.remove(shot)                                                # no recording to compare with: not sure
            self.assertEqual(DC.played("fx", shot, file_s), (got, False))
        finally:
            os.chdir(here)
            shutil.rmtree(root, ignore_errors=True)

    def test_a_very_long_shot_is_read_round_the_beat_only(self):
        (a, b), = DC.shots_of(20.0, 22.0, [5.0, 40.0], 30.0, 60.0)
        self.assertAlmostEqual(a, 20.0 - DC.MARGIN + 1 / 30.0, places=3)
        self.assertAlmostEqual(b, 22.0 + DC.MARGIN - 1 / 30.0, places=3)

    def test_the_numbers_file_keeps_a_list_of_numbers_on_one_line(self):
        data = {"beats": [{"holds": [2, 3, 2, 3, 1], "scene": [10.7, 13.5], "hue": [-5.0, 55.0], "files": ["a.png", "b.png"]}]}
        path = os.path.join(tempfile.mkdtemp(prefix="kit_dump_"), "t.json")
        DC.dump(data, path)
        text = open(path, encoding="utf-8").read()
        self.assertEqual(json.loads(text), data)                           # the same numbers ...
        self.assertIn('"holds": [2, 3, 2, 3, 1],', text)                   # ... a hundred holds are one line, not a hundred
        self.assertIn('"hue": [-5.0, 55.0],', text)
        self.assertTrue(text.endswith("}\n"))
        shutil.rmtree(os.path.dirname(path), ignore_errors=True)

    def test_the_frames_shown_are_centred_on_the_arrival(self):
        shot = {"frames": 60, "timing": {"hit": 30}}
        self.assertEqual(DC.shown(shot, 12), (26, 37))                     # a third before it, the rest after
        self.assertEqual(DC.shown({"frames": 60, "timing": {"hit": 58}}, 12), (48, 59))   # never past the last frame
        self.assertEqual(DC.shown({"frames": 60, "timing": None}, 12), (0, 11))


@unittest.skipUnless(FFMPEG, "ffmpeg / ffprobe not on PATH")
class TestOnVideo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="kit_dailies_test_")
        cls.scene = clips.write(os.path.join(cls.tmp, "scene.mp4"), clips.scene_frames(), 24)
        cls.ours = clips.write(os.path.join(cls.tmp, "ours.mp4"), clips.our_frames(), 30)
        cls.blank = clips.write(os.path.join(cls.tmp, "blank.mp4"), clips.blank_frames(), 30)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_every_frame_of_the_clip_comes_back_and_a_part_is_the_same_frames(self):
        info = DC.probe(self.scene)
        self.assertEqual((round(info[0]), info[2], info[3]), (24, clips.W, clips.H))
        whole = DC.frames(self.scene, 0.0, info[1], 160, info)
        self.assertEqual(whole.shape, (24, 90, 160, 3))
        part = DC.frames(self.scene, 0.0, info[1], 160, info, 8, 11)       # counted from the same start
        self.assertEqual(len(part), 4)
        self.assertLess(float(np.abs(part.astype(int) - whole[8:12].astype(int)).mean()), 0.5)

    def test_the_scene_read_through_video_fire_in_one_frame_on_twos_until_the_cut(self):
        t = DC.read(self.scene, 0.0, 1.0, clips.HUE)["timing"]
        self.assertEqual((t["hit"], t["arrive"], t["stay"], t["on"], t["frozen"]), (8, 0, 16, 2, 0))
        self.assertEqual((t["cut_in"], t["stay_cut"]), (False, True))
        self.assertEqual(t["holds"], [2] * 8)                              # a held drawing is one drawing after h264

    def test_ours_read_whole_and_timed_over_a_stretch_keeps_the_recordings_frame_numbers(self):
        whole = DC.read(self.ours, 0.0, DC.probe(self.ours)[1], clips.HUE)
        t = whole["timing"]
        self.assertEqual((t["hit"], t["arrive"], t["stay"], t["go"], t["frozen"], t["on"]), (13, 2, 7, 3, 4, 1))
        part = DC.within(whole, 0.4, 1.0)                                  # frames 12..30 of the recording
        self.assertEqual(part["stretch"], [12, 30])
        self.assertEqual(part["timing"]["hit"], 13)                        # still the recording's frame 13
        self.assertEqual(part["timing"]["seconds"]["hit"], round(13 / 30.0, 3))
        self.assertTrue(part["timing"]["cut_in"])                          # the stretch opens on it already lit
        self.assertIn("the stretch opens on it already lit", DC.says(part))
        self.assertIsNone(DC.within(whole, 0.0, 0.03))                     # under 3 frames: nothing to time

    def test_dailies_say_what_differs_and_make_pictures_a_reader_gets_at_full_size(self):
        out = os.path.join(self.tmp, "look")
        code, got = run(dailies, ["probe", "--ours", self.ours, "--scene-clip", self.scene, "--hue", "5,55", "--out", out])
        self.assertEqual((code, got["status"]), (0, "pass"))
        for said in ("it arrives: the scene in one frame, ours over 0.07 s",
                     "it stays: the scene at least 0.67 s (its shot ends while it is lit), ours 0.23 s",
                     "a freeze while it stays: the scene none in the 0.67 s its shot shows, ours 0.13 s (4 of its frames)",
                     "the scene is drawn on twos, ours on ones"):
            self.assertIn(said, got["summary"])
        self.assertTrue(got["summary"].endswith("LOOK: " + out.replace(os.sep, "/") + "/"), got["summary"])
        from PIL import Image
        files = got["beats"][0]["files"]
        self.assertEqual(files[0], "beat0_page.png")
        self.assertEqual(len(files), 1 + 6)                                # 12 frames, two a picture
        strip = Image.open(os.path.join(out, files[1]))
        self.assertTrue(1280 <= strip.width <= 1568, strip.width)          # two 640 px frames: not shrunk by a reader
        self.assertGreater(strip.height, 2 * 360)                          # the scene's row above ours
        stored = json.load(open(os.path.join(out, "dailies.json"), encoding="utf-8"))
        self.assertEqual(stored["beats"][0]["scene"]["timing"]["on"], 2)
        self.assertEqual(stored["beats"][0]["ours"]["timing"]["frozen"], 4)
        self.assertIs(stored["beats"][0]["key"], True)                     # which beat is the key one is stored, not guessed

    def test_a_folder_that_is_not_a_dailies_folder_is_left_alone(self):
        out = os.path.join(self.tmp, "not_dailies")
        os.makedirs(out)
        keep = os.path.join(out, "beat_drawing_i_made.png")
        open(keep, "wb").write(b"mine")
        code, got = run(dailies, ["x", "--ours", self.ours, "--out", out])
        self.assertEqual(code, 1)
        self.assertIn("not a dailies folder", got["summary"])
        self.assertTrue(os.path.isfile(keep))

    def test_ours_alone_is_shown_as_large_and_says_it_is_alone(self):
        out = os.path.join(self.tmp, "alone")
        code, got = run(dailies, ["alone", "--ours", self.ours, "--hue", "5,55", "--out", out])
        self.assertEqual((code, got["status"]), (0, "pass"))
        self.assertIn("OURS ALONE", got["summary"])
        self.assertIsNone(got["beats"][0]["scene"])
        self.assertTrue(os.path.isfile(os.path.join(out, "beat0_01.png")))

    def test_a_recording_that_shows_nothing_fails_the_dailies(self):
        out = os.path.join(self.tmp, "blank")
        code, got = run(dailies, ["blank", "--ours", self.blank, "--scene-clip", self.scene, "--hue", "5,55", "--out", out])
        self.assertEqual((code, got["status"]), (1, "fail"))
        self.assertIn("ours never lights up", got["summary"])

    def test_breakdown_dense_writes_the_scenes_timing_beside_the_beat_sheet(self):
        root = os.path.join(self.tmp, "project")
        measured = os.path.join(root, "assets", "effects", "refs_measured")
        os.makedirs(measured)
        json.dump({"set": "fire", "clip": self.scene.replace(os.sep, "/"), "clip_fps": 24.0, "window": [0.0, 1.0], "fps": 2.0,
                   "frames": 2, "cuts": [], "threshold": 0.35}, open(os.path.join(measured, "fire.breakdown.json"), "w"))
        json.dump({"schema": 1, "duration": 1.0, "beats": [{"beat": "0 key the fire", "scene": [0.2, 0.9], "t": 0.0,
                                                             "len": 0.5, "hold": 0.0, "slow": 1.0, "key": True}]},
                  open(os.path.join(measured, "fire.chart.json"), "w"))
        json.dump({"hue": [5.0, 55.0]}, open(os.path.join(measured, "fire_scene.json"), "w"))
        here = os.getcwd()
        os.chdir(root)
        try:
            code, got = run(breakdown, ["fire", "--dense"])
            self.assertEqual((code, got["status"]), (0, "pass"), got)
            self.assertIn("0 key the fire: the light arrives at 0.3", got["summary"])     # in the clip's own seconds
            self.assertIn("arrives in one frame", got["summary"])
            self.assertTrue(got["summary"].endswith("LOOK: build/vfx/breakdown/fire_dense/"))
            stored = json.load(open(os.path.join(measured, "fire.timing.json"), encoding="utf-8"))
            self.assertEqual(stored["beats"][0]["shots"][0]["timing"]["on"], 2)
            sheet = open(os.path.join(measured, "fire.timing.md"), encoding="utf-8").read()
            self.assertIn("| **0 key the fire** |", sheet)
            self.assertIn("in one frame, at 0.3", sheet)
            self.assertIn("on twos", sheet)
            self.assertTrue(os.path.isfile(os.path.join("build", "vfx", "breakdown", "fire_dense", "beat0_page.png")))
            code, got = run(breakdown, ["nothing", "--dense"])              # no breakdown yet: said, not guessed
            self.assertEqual(code, 1)
            self.assertIn("no breakdown to read from", got["summary"])
        finally:
            os.chdir(here)


if __name__ == "__main__":
    unittest.main()
