"""A follower's travel is swept WITH its driver's (card ver5: "a follower's travel is never checked together with
its driver's"): a hand that follows its arm (a.couple, ratio 1) doubles the arm's turn, so at the arm's 45 degrees
the hand stands straight up into a ceiling. Swept each alone - the arm with a rigid hand, the hand with the arm at
rest - neither reaches it; swept together the build must say the arm, carrying its follower, drives into it."""

import json
import os
import subprocess
import tempfile
import textwrap
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
BLENDER = os.environ.get("BLENDER", os.environ.get("KIT_BLENDER") or os.environ.get("BLENDER") or r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")


@unittest.skipUnless(os.path.isfile(BLENDER), "Blender 5.2 is not installed")
class FollowerTravel(unittest.TestCase):
    def build(self, couple):
        src = textwrap.dedent(f"""
            import sys, json
            sys.path.insert(0, {os.path.join(ROOT, 'kit', 'blender')!r})
            import rbx, rbx_mech
            a = rbx.Asset('_selftest_follow_travel', tex=64, size=(3.6, 2.8, 1.0), bevel=0,
                          allow_floating=('Arm', 'Hand'))
            a.material('body', color=(0.5, 0.52, 0.56))
            a.box('Base', (3.5, 0.5, 1.0), (0.75, 0.25, 0), 'body', bevel=0)
            a.box('Post', (0.2, 2.3, 0.6), (-0.7, 1.65, 0), 'body', bevel=0)
            a.box('Ceiling', (1.9, 0.25, 0.6), (0.15, 2.675, 0), 'body', bevel=0)
            a.box('Arm', (1.0, 0.1, 0.1), (0.5, 1.0, 0), 'body', bevel=0, group='arm')
            a.box('Hand', (1.0, 0.1, 0.1), (1.5, 1.0, 0), 'body', bevel=0, group='hand')
            a.joint('Arm', 'arm', 'hinge', (0, 0, 1), pivot=(0, 1.0, 0), min=0, max=45)
            a.joint('Hand', 'hand', 'hinge', (0, 0, 1), pivot=(1.0, 1.0, 0), min=0, max=45, parent='arm')
            if {couple!r}:
                a.couple('Hand', drives='Arm', ratio=1.0)
            seen = []
            real = rbx_mech.interference
            def spy(objs, joints):
                out = real(objs, joints)
                seen.append(out)
                return out
            rbx_mech.interference = spy
            a.build()
            probs, facts = seen[-1] if seen else ([], {{}})
            print('TRAVEL ' + json.dumps({{'problems': probs, 'facts': {{k: v for k, v in facts.items() if 'follows' in k}}}}))
            """)
        path = os.path.join(tempfile.mkdtemp(), "follow.py")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(src)
        env = dict(os.environ, KIT_BUILD=tempfile.mkdtemp(), KIT_GAME="none")
        out = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P", path, "--",
                              "--no-preview"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=900, env=env)
        line = [x for x in out.stdout.splitlines() if x.startswith("TRAVEL ")]
        self.assertTrue(line, out.stdout[-1500:] + out.stderr[-1500:])
        return json.loads(line[0][7:])

    def test_free_joints_reach_nothing(self):
        got = self.build(False)
        self.assertEqual([p for p in got["problems"] if "Ceiling" in p or "main" in p], [], got)

    def test_a_follower_carried_by_its_driver_is_swept_with_it(self):
        got = self.build(True)
        self.assertEqual(got["facts"].get("Hand@follows"), "Arm", got)
        said = [p for p in got["problems"] if "its follower Hand" in p]
        self.assertTrue(said, got)
        self.assertIn("drives into 'main'", said[0])


if __name__ == "__main__":
    unittest.main()
