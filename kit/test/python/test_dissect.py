"""kit library inspect DISSECTS each part (kit/refs/dissect.py): what it is made of beyond its size. A model built in
Blender with known answers, measured back:
- edges + bevels: a 40 x 20 x 10 mm box with 1 mm ROUND edges (4 segments), one with 0.5 mm CHAMFERS, one SHARP
- how it was made: a roughened dense sphere (a sculpt), a clean sphere (smooth), the sharp box (cad)
- UV + texture density: two plates on one 1024 map — 20 x 20 mm (51.2 px/mm), 40 x 20 mm squeezed (stretched)
- baked detail: a plate whose normal map carries 1.27 mm checkering: its pitch and relief measured back
- wear: a box with bright edges in its colour map (worn) and an even one (clean)
- faceting: 16- and 64-sided cylinders; seams: a plate cut through its middle by a UV seam."""

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
import bpy, sys
out = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)
def box(name, x, bevel=None, segments=1):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x, 0, 0))
    o = bpy.context.object
    o.name = name
    o.scale = (0.040, 0.020, 0.010)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        m = o.modifiers.new("Bevel", "BEVEL")
        m.width, m.segments, m.limit_method, m.profile = bevel, segments, "NONE", 0.5
    return o
box("RoundBox", 0.0, bevel=0.001, segments=4)    # three boxes side by side, touching: one object
box("ChamferBox", 0.040, bevel=0.0005, segments=1)
box("SharpBox", 0.080)
# a SCULPT: a dense sphere with its surface roughened 0.15 mm; a SMOOTH sphere beside it (each touching the next)
import random
random.seed(7)
bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=5, radius=0.010, location=(0.110, 0, 0))
sc = bpy.context.object
sc.name = "Sculpt"
for v in sc.data.vertices:
    v.co += v.normal * random.uniform(-0.00015, 0.00015)
bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=4, radius=0.010, location=(0.130, 0, 0))
bpy.context.object.name = "Smooth"
# two textured plates on the sharp box, one 1024 x 1024 map, UVs filling it: EVEN (20 x 20 mm: 51.2 px/mm) and
# STRETCHED (40 x 20 mm squeezed into the same square: twice the px/mm one way)
img = bpy.data.images.new("Tex1024", 1024, 1024)
mat = bpy.data.materials.new("Textured")
mat.use_nodes = True
tex = mat.node_tree.nodes.new("ShaderNodeTexImage")
tex.image = img
mat.node_tree.links.new(tex.outputs["Color"], mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"])
for name, x, sx in (("EvenPlate", 0.065, 0.020), ("StretchPlate", 0.090, 0.040)):
    bpy.ops.mesh.primitive_plane_add(size=1, location=(x, 0, 0.0050))
    o = bpy.context.object
    o.name = name
    o.scale = (sx, 0.020, 1)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    o.data.materials.append(mat)
# a DETAIL plate on the round box: a 20 mm square whose 1024 normal map carries CHECKERING at 1.27 mm (20 lines per
# inch) — two crossed waves, slopes up to 0.3: a relief of ~0.23 mm between its 1st and 99th percentile
import numpy as np
N = 1024
P = 1.27 * N / 20.0
yy, xx = np.mgrid[0:N, 0:N] + 0.5
A = 0.3 * P / (2 * np.pi)
gx = A * 2 * np.pi / P * np.cos(2 * np.pi * xx / P)
gy = A * 2 * np.pi / P * np.cos(2 * np.pi * yy / P)
nrm = np.dstack([-gx, -gy, np.ones_like(gx)])
nrm /= np.linalg.norm(nrm, axis=2, keepdims=True)
chk = bpy.data.images.new("Checkering", N, N)
chk.colorspace_settings.name = "Non-Color"
chk.pixels.foreach_set(np.dstack([nrm * 0.5 + 0.5, np.ones((N, N, 1))]).astype(np.float32).ravel())
chk.pack()
dm = bpy.data.materials.new("Checkered")
dm.use_nodes = True
nt = dm.node_tree
ti = nt.nodes.new("ShaderNodeTexImage")
ti.image = chk
nm = nt.nodes.new("ShaderNodeNormalMap")
nt.links.new(ti.outputs["Color"], nm.inputs["Color"])
nt.links.new(nm.outputs["Normal"], nt.nodes["Principled BSDF"].inputs["Normal"])
bpy.ops.mesh.primitive_plane_add(size=1, location=(0.0, 0, 0.0050))
dp = bpy.context.object
dp.name = "DetailPlate"
dp.scale = (0.020, 0.020, 1)
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
dp.data.materials.append(dm)
# WEAR: a 40 x 20 x 10 mm box whose 512 colour map is bright (0.9) in a band along every edge of every face (8% of
# the face's side: 0.8-3.2 mm) and dark (0.1) inside; a CLEAN box with one even colour
def textured_box(name, x, worn):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x, 0, 0))
    o = bpy.context.object
    o.name = name
    o.scale = (0.040, 0.020, 0.010)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    arr = np.full((512, 512, 4), 0.1, np.float32)
    arr[..., 3] = 1.0
    if worn:
        uvl = o.data.uv_layers.active.data
        yy, xx = np.mgrid[0:512, 0:512] + 0.5
        for poly in o.data.polygons:
            us = [uvl[li].uv[:] for li in poly.loop_indices]
            u0, u1 = min(u[0] for u in us) * 512, max(u[0] for u in us) * 512
            v0, v1 = min(u[1] for u in us) * 512, max(u[1] for u in us) * 512
            inside = (xx >= u0) & (xx <= u1) & (yy >= v0) & (yy <= v1)
            frac = np.minimum(np.minimum((xx - u0) / (u1 - u0), (u1 - xx) / (u1 - u0)),
                              np.minimum((yy - v0) / (v1 - v0), (v1 - yy) / (v1 - v0)))
            arr[inside & (frac < 0.08), :3] = 0.9
    im = bpy.data.images.new(name + "Tex", 512, 512)
    im.pixels.foreach_set(arr.ravel())
    im.pack()
    mt = bpy.data.materials.new(name + "Mat")
    mt.use_nodes = True
    tn = mt.node_tree.nodes.new("ShaderNodeTexImage")
    tn.image = im
    mt.node_tree.links.new(tn.outputs["Color"], mt.node_tree.nodes["Principled BSDF"].inputs["Base Color"])
    o.data.materials.append(mt)
textured_box("WornBox", 0.160, True)
textured_box("CleanBox", 0.200, False)
# FACETING: a 16-sided cylinder (22.5 deg a step) and a 64-sided one (5.6), standing on the clean box
for name, x, sides in (("Faceted", 0.190, 16), ("Fine", 0.210, 64)):
    bpy.ops.mesh.primitive_cylinder_add(vertices=sides, radius=0.008, depth=0.040, location=(x, 0, 0.025))
    bpy.context.object.name = name
# a SEAM ACROSS A FLAT: a plate cut in two by a UV seam through its middle (on the worn box)
bpy.ops.mesh.primitive_plane_add(size=0.020, location=(0.160, 0, 0.0051))
sp = bpy.context.object
sp.name = "SeamPlate"
bpy.context.view_layer.objects.active = sp
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.mesh.subdivide(number_cuts=1)
bpy.ops.object.mode_set(mode="OBJECT")
for e in sp.data.edges:
    v0, v1 = (sp.data.vertices[i].co for i in e.vertices)
    e.use_seam = abs(v0.x) < 1e-6 and abs(v1.x) < 1e-6  # the middle line across the plate
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.unwrap(method="ANGLE_BASED", margin=0.02)
bpy.ops.object.mode_set(mode="OBJECT")
bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", export_apply=True)
'''


def _result(out):
    for line in out.splitlines():
        if line.startswith('{"schema"'):
            return json.loads(line)
    raise AssertionError("no result line:\n" + out[-3000:])


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class TestDissect(unittest.TestCase):
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
                            os.path.join(KIT, "refs", "inspect_model.py"), "--", glb, "--name", "dissect", "--out",
                            cls.tmp, "--px", "128"],
                           capture_output=True, text=True, timeout=300, env=dict(os.environ, KIT_BUILD=cls.tmp))
        cls.result = _result(p.stdout)
        with open(os.path.join(cls.tmp, "dissect.inspect.json"), encoding="utf-8") as fh:
            cls.parts = {q["name"]: q for q in json.load(fh)["parts"]}

    def test_round_bevel_measured(self):
        e = self.parts["RoundBox"]["edges"]
        self.assertEqual(e["sharp_edges"], 0, e)
        self.assertAlmostEqual(e["bevel_size_mm"]["typical"], 1.0, delta=0.15)  # the fillet radius
        self.assertLess(e["chamfer_share"], 0.2)
        self.assertGreaterEqual(e["round_segments"], 3)
        self.assertGreater(e["bevelled_share"], 0.95)

    def test_chamfer_measured(self):
        e = self.parts["ChamferBox"]["edges"]
        self.assertAlmostEqual(e["bevel_size_mm"]["typical"], 0.5, delta=0.075)  # the chamfer's offset
        self.assertGreater(e["chamfer_share"], 0.9)
        self.assertGreater(e["bevelled_share"], 0.95)

    def test_sharp_box_has_no_bevels(self):
        e = self.parts["SharpBox"]["edges"]
        self.assertEqual(e["bevels"], 0)
        self.assertEqual(e["sharp_edges"], 12)
        self.assertAlmostEqual(e["sharp_mm"], 4 * (40 + 20 + 10), delta=1.0)
        self.assertEqual(e["bevelled_share"], 0.0)
        self.assertGreater(e["flat_share"], 0.99)
        # WHERE they are: its 12 edges join into one run round the box, square
        self.assertEqual(len(e["sharp_runs"]), 1)
        self.assertAlmostEqual(e["sharp_runs"][0]["mm"], 4 * (40 + 20 + 10), delta=1.0)
        self.assertEqual(e["sharp_runs"][0]["deg"], 90)
        self.assertNotIn("share_unreliable", e)

    def test_how_it_was_made(self):
        self.assertEqual(self.parts["SharpBox"]["surface"]["made_as"], "cad")
        self.assertEqual(self.parts["Smooth"]["surface"]["made_as"], "smooth")
        self.assertEqual(self.parts["Sculpt"]["surface"]["made_as"], "sculpt_or_scan")
        self.assertGreater(self.parts["Sculpt"]["surface"]["noise_deg"], 3 * self.parts["Smooth"]["surface"]["noise_deg"])

    def test_uv_and_texture_density(self):
        even, stretch = self.parts["EvenPlate"]["uv_layout"], self.parts["StretchPlate"]["uv_layout"]
        self.assertAlmostEqual(even["px_per_mm"], 1024 / 20, delta=0.5)
        self.assertEqual(even["stretched_share"], 0.0)
        self.assertAlmostEqual(stretch["px_per_mm"], (1024 * 1024 / (40 * 20)) ** 0.5, delta=0.5)
        self.assertGreater(stretch["stretched_share"], 0.95)
        self.assertEqual(self.parts["EvenPlate"]["material"][0]["maps"], {"Base Color": [1024, 1024]})
        # Blender's default cube UVs (one cross-shaped island, its cuts on the cube's edges) on a 40 x 20 x 10 box:
        # every face gets the same square of UV, so the box is stretched
        box = self.parts["SharpBox"]["uv_layout"]
        self.assertEqual(box["islands"], 1)
        self.assertEqual(box["seams_on_hard_edges"], 1.0)
        self.assertGreater(box["stretched_share"], 0.95)

    def test_baked_detail_pattern_and_relief(self):
        d = self.parts["DetailPlate"]["baked_detail"]
        self.assertTrue(d["pattern"]["found"], d)
        self.assertAlmostEqual(d["pattern"]["pitch_mm"], 1.27, delta=0.127)
        self.assertGreater(d["strength_deg"], 5)
        self.assertTrue(0.15 < d["relief_mm"] < 0.35, d)
        self.assertTrue(os.path.isfile(d["relief_png"]))
        self.assertIsNone(self.parts["EvenPlate"]["baked_detail"])  # no normal map, nothing baked

    def test_edge_wear(self):
        worn, clean = self.parts["WornBox"]["colour_wear"], self.parts["CleanBox"]["colour_wear"]
        self.assertGreater(worn["edge_wear"], 0.5, worn)   # bright edges (0.9) against dark flats (0.1)
        self.assertLess(abs(clean["edge_wear"]), 0.05, clean)
        self.assertIsNone(self.parts["SharpBox"]["colour_wear"])  # no colour map: nothing to sample

    def test_faceting(self):
        self.assertAlmostEqual(self.parts["Faceted"]["edges"]["facet_deg"], 22.5, delta=1.5)
        self.assertLess(self.parts["Fine"]["edges"]["facet_deg"], 6.5)
        # how far its facets sit from the true curve: r (1 - cos(step / 2)) = 8 mm x (1 - cos 11.25 deg) = 0.154 mm
        self.assertAlmostEqual(self.parts["Faceted"]["edges"]["facet_sag_mm"], 0.154, delta=0.02)
        self.assertLess(self.parts["Fine"]["edges"]["facet_sag_mm"], 0.02)
        self.assertIsNone(self.parts["SharpBox"]["edges"]["facet_deg"])  # no curve: nothing faceted

    def test_seams_across_flats(self):
        self.assertEqual(self.parts["SeamPlate"]["uv_layout"]["seams_across_flats"], 1.0)
        self.assertEqual(self.parts["SharpBox"]["uv_layout"]["seams_across_flats"], 0.0)  # cut on its edges


if __name__ == "__main__":
    unittest.main()
