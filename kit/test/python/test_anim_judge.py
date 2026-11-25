"""The anim judge packet (kit/anim/judge.py): for a built clip it writes build/judge/anim/<Name>/ with the strip, a
motion grid of every frame and a PROMPT.md that carries the measured motion. Runs only when `kit anim` has built the
Slash clip (the packet is made from build outputs, not from sources)."""

import json
import os
import subprocess
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
BUILT = os.path.isfile(os.path.join(ROOT, "build", "animations", "Slash.clip.json")) and os.path.isfile(
    os.path.join(ROOT, "build", "animations", "Slash.png"))


@unittest.skipUnless(BUILT, "needs build/animations/Slash.* (run: lune run kit anim Slash)")
class JudgePacket(unittest.TestCase):
    def test_packet_has_strip_motion_and_prompt(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "kit", "anim", "judge.py"), "packet", "Slash"],
                           capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        verdict = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(verdict["status"], "pass", verdict)
        folder = os.path.join(ROOT, "build", "judge", "anim", "Slash")
        for name in ("strip.png", "motion.png", "PROMPT.md", "packet.json"):
            self.assertTrue(os.path.isfile(os.path.join(folder, name)), name)
        with open(os.path.join(folder, "PROMPT.md"), encoding="utf-8") as fh:
            prompt = fh.read()
        self.assertIn("Hit", prompt)             # the measured event timing is in the brief
        self.assertIn("studs/s", prompt)         # and the fastest effector's speed
        with open(os.path.join(folder, "packet.json"), encoding="utf-8") as fh:
            packet = json.load(fh)
        self.assertGreater(packet["frames"], 4)
        self.assertEqual(packet["metrics"]["problems"], [])


if __name__ == "__main__":
    unittest.main()
