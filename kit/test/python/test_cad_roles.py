"""a.cad(..., edge_roles=) — each edge rounded by its ROLE, not one size for the whole part (the owner, 2026-10-22:
"most parts of the gun are all smooth edges ... only some places are maybe straightened out edges"). The fixture
kit/selftest/blender/build_cad_roles.py rounds a slab 2 mm, keeps its top face's 4 edges crisp and rounds its left
end 0.6 mm: the facts say how many edges each radius took, and the mesh stays closed."""

import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
import cad_check  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
BLENDER = cad_check.blender()
MANIFEST = os.path.join(REPO, "build", "models", "_selftest_cad_roles.manifest.json")


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class CadRoles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.path.isfile(MANIFEST):
            os.remove(MANIFEST)
        script = os.path.join(REPO, "kit", "selftest", "blender", "build_cad_roles.py")
        cls.run_ = subprocess.run([BLENDER, "-b", "--factory-startup", "-P", script, "--", "--no-preview"], cwd=REPO,
                                  capture_output=True, text=True, timeout=900)
        assert cls.run_.returncode == 0 and os.path.isfile(MANIFEST), (cls.run_.stderr or cls.run_.stdout)[-800:]
        with open(MANIFEST, encoding="utf-8") as fh:
            m = json.load(fh)
        cls.cad = {c["part"]: c for c in (m.get("design") or {}).get("cad") or m.get("facts", {}).get("cad") or []}

    def test_each_role_took_its_edges(self):
        roles = {r: n for r, n in self.cad["Roles"]["edge_roles"]}
        self.assertEqual(roles.get(0.0), 4, roles)          # (the top face's four edges kept crisp)
        # (the left end: its own 3 edges, and where it meets the 2 mm rounds — new hard edges, rounded 0.6 too)
        self.assertGreaterEqual(roles.get(0.6, 0), 3, roles)
        self.assertGreaterEqual(roles.get(2.0, 0), 8, roles)

    def test_the_part_stays_closed(self):
        self.assertEqual(self.cad["Roles"].get("open_edges"), 0)


if __name__ == "__main__":
    unittest.main()
