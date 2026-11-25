"""kit/vfx's V0-V2 tools and the beat chart write where the ACTIVE game's play command records and looks (card t6rx,
found 2026-11-12): games/<Name>/build/vfx with a game active (KIT_GAME or games/.active), else build/vfx. Before,
denseclip / dailies / stylesheet / animatic / chart wrote the project's build/vfx whatever game was active, so a game's
recording got no dailies and its animatic preset sat where `kit vfx play --animatic` does not look.

Each case imports the tools in a fresh interpreter whose working folder is a made project (the paths are read when a
module loads, as the kit's commands run them)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

VFX = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "vfx"))

PROBE = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
import gameroot, denseclip, dailies, stylesheet, animatic, chart
out = {"booth": denseclip.BOOTH, "play": denseclip.PLAY, "dailies": dailies.OUT, "stylesheet": stylesheet.OUT,
       "animatic": animatic.OUT, "charts": chart.OUT, "root": gameroot.game_root()}
if sys.platform == "win32":
    import capture
    out["capture_play"] = capture.play_dir().replace("\\", "/")
print(json.dumps(out))
"""


def probe(cwd, game=None, active=None):
    env = dict(os.environ)
    env.pop("KIT_GAME", None)
    if game is not None:
        env["KIT_GAME"] = game
    if active is not None:
        os.makedirs(os.path.join(cwd, "games"), exist_ok=True)
        with open(os.path.join(cwd, "games", ".active"), "w", encoding="utf-8") as f:
            f.write(active + "\n")
    r = subprocess.run([sys.executable, "-c", PROBE, VFX], cwd=cwd, env=env, capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(r.stderr[-2000:])
    return json.loads(r.stdout.strip().splitlines()[-1])


class GameRoot(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        os.makedirs(os.path.join(self.dir, "games", "Duel"))

    def tearDown(self):
        self.tmp.cleanup()

    def check_under(self, got, base):
        for key in ("booth", "play", "dailies", "stylesheet", "animatic", "charts"):
            self.assertEqual(got[key], f"{base}/{key}", key)
        if "capture_play" in got:
            self.assertEqual(got["capture_play"], f"{base}/play")

    def test_a_game_named_by_kit_game_gets_its_own_build_vfx(self):
        got = probe(self.dir, game="Duel")
        self.assertEqual(got["root"].replace("\\", "/"), "games/Duel")
        self.check_under(got, "games/Duel/build/vfx")

    def test_the_active_file_names_the_game_too(self):
        self.check_under(probe(self.dir, active="Duel"), "games/Duel/build/vfx")

    def test_no_game_none_and_a_missing_game_are_the_project_root(self):
        self.check_under(probe(self.dir), "build/vfx")
        self.check_under(probe(self.dir, game="none"), "build/vfx")
        self.check_under(probe(self.dir, game="NoSuchGame"), "build/vfx")  # as Config.game(): no folder, no game
        # KIT_GAME=none wins over the active file, as on the Luau side
        self.check_under(probe(self.dir, game="none", active="Duel"), "build/vfx")


if __name__ == "__main__":
    unittest.main()
