"""The PRODUCT studio (Asset._studio(look="product"): the judge's and the showcase's pictures) lights polished steel the
way a product photographer does: the same polished steel ball shows far more light-and-dark contrast in it than in the
honest soft-sky studio (where it read as matte grey primer), and the honest studio is still the default."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
import cad_check  # noqa: E402

KIT = os.path.abspath(os.path.join(HERE, "..", ".."))
BLENDER = cad_check.blender()

RENDER = r'''
import json, os, sys, types
sys.path.insert(0, os.path.join(sys.argv[sys.argv.index("--") + 1], "blender"))
import bpy, numpy as np, rbx
from mathutils import Vector
out = sys.argv[sys.argv.index("--") + 2]
sc = bpy.context.scene
for o in list(sc.objects):
    bpy.data.objects.remove(o)
bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, segments=64, ring_count=32)
ball = bpy.context.active_object
bpy.ops.object.shade_smooth()
mat = bpy.data.materials.new("Steel")
mat.use_nodes = True
b = mat.node_tree.nodes.get("Principled BSDF")
b.inputs["Base Color"].default_value = (0.62, 0.625, 0.63, 1)
b.inputs["Metallic"].default_value = 1.0
b.inputs["Roughness"].default_value = 0.18
ball.data.materials.append(mat)
cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
sc.collection.objects.link(cam)
d = (rbx.BL_FROM_RBX.to_3x3() @ Vector((-0.75, 0.4, -0.6))).normalized()
cam.location = d * 4.0
cam.rotation_euler = (-cam.location).to_track_quat("-Z", "Y").to_euler()
cam.data.lens = 60
sc.camera = cam
sc.render.engine = "CYCLES"
sc.cycles.device = "CPU"
sc.cycles.samples = 16
sc.cycles.use_denoising = False
sc.render.resolution_x = sc.render.resolution_y = 96
ns = types.SimpleNamespace(scene=sc, collection=sc.collection)
got = {}
for look in ("default", "honest", "product"):
    for o in list(bpy.data.objects):
        if o.name.startswith("StudioSoftbox"):
            bpy.data.objects.remove(o)
    if look == "default":
        rbx.Asset._studio(ns, [ball], (0.035, 0.037, 0.042))
    else:
        rbx.Asset._studio(ns, [ball], (0.035, 0.037, 0.042), look=look)
    p = os.path.join(os.path.dirname(out), f"ball_{look}.png")
    sc.render.filepath = p
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(p)
    px = np.array(img.pixels[:], dtype=np.float32).reshape(96, 96, 4)
    lum = px[24:72, 24:72, :3] @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)  # (the ball's middle)
    got[look] = {"std": float(lum.std()), "mean": float(lum.mean())}
with open(out, "w") as fh:
    json.dump(got, fh)
'''


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class TestProductStudio(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        script, out = os.path.join(cls.tmp, "render.py"), os.path.join(cls.tmp, "got.json")
        with open(script, "w", encoding="utf-8") as fh:
            fh.write(RENDER)
        subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P", script, "--", KIT, out],
                       check=True, capture_output=True, timeout=600, env=dict(os.environ, KIT_BUILD=cls.tmp))
        with open(out, encoding="utf-8") as fh:
            cls.got = json.load(fh)

    def test_polished_steel_shows_contrast_in_the_product_studio(self):
        self.assertGreater(self.got["product"]["std"], 1.3 * self.got["honest"]["std"], self.got)  # (measured: 1.58x)

    def test_the_honest_studio_is_the_default(self):
        self.assertAlmostEqual(self.got["default"]["std"], self.got["honest"]["std"], delta=0.01)
        self.assertAlmostEqual(self.got["default"]["mean"], self.got["honest"]["mean"], delta=0.01)


if __name__ == "__main__":
    unittest.main()
