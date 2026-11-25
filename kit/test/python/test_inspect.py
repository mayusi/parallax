"""kit library inspect: a reference model looked at INSIDE, part by part — the owner (2026-10-07): "we don't only measure
from the outside, we genuinely check them out in Blender too". A small model built in Blender with known answers:
a ring with a through-hole, a pin that flies in from the left (an assembly animation), a coil spring, a red metal body,
a backdrop to leave out. Every number the inspection reports is checked against what was built."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
import cad_check  # noqa: E402

KIT = os.path.join(HERE, "..", "..")
BLENDER = cad_check.blender()

BUILD = r'''
import bpy, math, sys
out = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)
def keep(o, name):
    o.name = name
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    return o
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0)); body = keep(bpy.context.object, "Body")
body.scale = (1, 1, 1); body.dimensions = (2.0, 0.3, 0.6); bpy.ops.object.transform_apply(scale=True)
red = bpy.data.materials.new("RedMetal"); red.use_nodes = True
bsdf = red.node_tree.nodes["Principled BSDF"]
bsdf.inputs["Base Color"].default_value = (0.8, 0.1, 0.1, 1); bsdf.inputs["Metallic"].default_value = 0.9
bsdf.inputs["Roughness"].default_value = 0.3
body.data.materials.append(red)
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0.45)); top = keep(bpy.context.object, "Top")
top.dimensions = (1.8, 0.3, 0.3); bpy.ops.object.transform_apply(scale=True)
# a ring standing up at the front, touching the body: its hole is seen through from the side
bpy.ops.mesh.primitive_torus_add(major_radius=0.25, minor_radius=0.06, major_segments=48, minor_segments=16,
                                 location=(1.31, 0, 0), rotation=(math.pi / 2, 0, 0))
keep(bpy.context.object, "Ring")
# a pin into the body's LEFT side (+Y: the kit's side view looks from -Y), flying in from the left
bpy.ops.mesh.primitive_cylinder_add(radius=0.03, depth=0.4, vertices=24, location=(-0.5, 0.35, 0),
                                    rotation=(math.pi / 2, 0, 0))
pin = keep(bpy.context.object, "Pin")
pin.location = (-0.5, 3.0, 0); pin.keyframe_insert("location", frame=1)
pin.location = (-0.5, 0.35, 0); pin.keyframe_insert("location", frame=20)
# a coil spring lying on the top
cu = bpy.data.curves.new("SpringCurve", "CURVE"); cu.dimensions = "3D"
sp = cu.splines.new("POLY"); n = 6 * 24
sp.points.add(n)
for k in range(n + 1):
    t = k / n
    sp.points[k].co = (-0.6 + 0.5 * t, 0.06 * math.cos(2 * math.pi * 6 * t), 0.672 + 0.06 * math.sin(2 * math.pi * 6 * t), 1)
cu.bevel_depth, cu.bevel_resolution, cu.use_fill_caps = 0.012, 2, True
spring = bpy.data.objects.new("Spring", cu); bpy.context.scene.collection.objects.link(spring)
bpy.context.view_layer.objects.active = spring; spring.select_set(True)
bpy.ops.object.convert(target="MESH")
bpy.ops.mesh.primitive_plane_add(size=12, location=(0, 0, -3)); keep(bpy.context.object, "Floor")
bpy.context.scene.frame_start, bpy.context.scene.frame_end = 1, 20
bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", export_animations=True)
'''


def _result(out):
    for line in out.splitlines():
        if line.startswith('{"schema"') or line.startswith('{"status"'):
            return json.loads(line)
    raise AssertionError("no result line:\n" + out[-3000:])


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class TestInspect(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        script = os.path.join(cls.tmp, "build.py")
        with open(script, "w", encoding="utf-8") as fh:
            fh.write(BUILD)
        glb = os.path.join(cls.tmp, "fixture.glb")
        subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P", script, "--", glb],
                       check=True, capture_output=True, timeout=300)
        p = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                            os.path.join(KIT, "refs", "inspect_model.py"), "--", glb, "--name", "fixture", "--out",
                            cls.tmp, "--length-mm", "200", "--part", "ring", "--px", "300"],
                           capture_output=True, text=True, timeout=300, env=dict(os.environ, KIT_BUILD=cls.tmp))
        cls.result = _result(p.stdout)
        jpath = os.path.join(cls.tmp, "fixture.inspect.json")
        s = subprocess.run([sys.executable, os.path.join(KIT, "refs", "inspect_sheet.py"), jpath],
                           capture_output=True, text=True, timeout=300)
        cls.sheet = _result(s.stdout)
        with open(jpath, encoding="utf-8") as fh:
            cls.data = json.load(fh)
        cls.parts = {q["name"]: q for q in cls.data["parts"]}

    def test_the_object_and_only_the_object(self):
        self.assertEqual(self.result["status"], "pass", self.result)
        self.assertEqual(sorted(self.parts), ["Body", "Pin", "Ring", "Spring", "Top"])
        self.assertIn("Floor", [d["name"] for d in self.data["dropped"]])

    def test_a_through_hole_is_counted_and_seen(self):
        ring = self.parts["Ring"]
        self.assertTrue(ring["closed"])
        self.assertEqual(ring["holes"], 1)
        self.assertEqual(self.parts["Body"]["holes"], 0)
        # the ring's opening from its broad side: 0.38 m across, scaled to the 200 mm length (2.62 m -> x 0.0763)
        opening = ring["see_through"][0]["d_mm"]
        self.assertAlmostEqual(opening, 0.38 * 200 / 2.62, delta=3.0)

    def test_kinds(self):
        self.assertEqual(self.parts["Pin"]["kind"], "pin")
        self.assertEqual(self.parts["Spring"]["kind"], "spring")

    def test_what_touches_what(self):
        pairs = {frozenset(c[:2]) for c in self.data["contacts"]}
        for a, b in (("Body", "Top"), ("Body", "Ring"), ("Body", "Pin"), ("Top", "Spring")):
            self.assertIn(frozenset((a, b)), pairs, (a, b))

    def test_the_way_in_from_the_animation(self):
        m = self.data["motion"]
        self.assertEqual(m["assembly_order"], ["Pin"])
        self.assertIn("left", self.parts["Pin"]["motion"]["comes_in_from"])
        self.assertIn("Body", m["never_moves"])

    def test_material_read(self):
        mat = self.parts["Body"]["material"][0]
        r, g, b = (int(mat["base_srgb"][i:i + 2], 16) for i in (1, 3, 5))
        self.assertLess(abs(r - 0xe7) + abs(g - 0x59) + abs(b - 0x59), 9, mat)  # linear (0.8, 0.1, 0.1) as sRGB
        self.assertAlmostEqual(mat["metallic"], 0.9, delta=0.01)
        self.assertAlmostEqual(mat["roughness"], 0.3, delta=0.01)

    def test_pictures(self):
        for p in self.data["parts"]:
            self.assertTrue(os.path.isfile(os.path.join(KIT, "..", p["tile"])), p["tile"])
        views = [c["view"] for c in self.data["closeups"]]
        self.assertEqual(len(views), 4)
        self.assertEqual(self.sheet["status"], "pass")
        self.assertEqual(len(self.sheet["sheets"]), 2)  # the parts sheet + the ring's close-up sheet


if __name__ == "__main__":
    unittest.main()
