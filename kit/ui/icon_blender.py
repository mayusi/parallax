"""icon_blender.py — the Blender half of `kit ui icon make` (run headless by kit/ui/icon.py):

    blender -b --factory-startup --python-exit-code 2 -P kit/ui/icon_blender.py -- --svg <clean.svg> --out <mask.png> --size 512

Imports the icon's SVG (its background square already removed), fills the curves flat white and renders them from
straight above on a transparent film: a crisp, anti-aliased MASK at `size` px that icon.py then styles.
"""
import sys

import bpy  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
svg, out, size = argv[argv.index("--svg") + 1], argv[argv.index("--out") + 1], int(argv[argv.index("--size") + 1])
for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
bpy.ops.import_curve.svg(filepath=svg)
curves = [o for o in bpy.data.objects if o.type == "CURVE"]
mat = bpy.data.materials.new("white")
mat.use_nodes = True
nt = mat.node_tree
for n in list(nt.nodes):
    nt.nodes.remove(n)
em = nt.nodes.new("ShaderNodeEmission")
em.inputs["Color"].default_value = (1, 1, 1, 1)
outn = nt.nodes.new("ShaderNodeOutputMaterial")
nt.links.new(em.outputs["Emission"], outn.inputs["Surface"])
for o in curves:
    o.data.dimensions = "2D"
    o.data.fill_mode = "BOTH"
    o.data.materials.clear()
    o.data.materials.append(mat)
# the icon's viewBox is 512 units; the importer scales it — frame what was imported
xs, ys = [], []
for o in curves:
    for c in o.bound_box:
        v = o.matrix_world @ __import__("mathutils").Vector(c)
        xs.append(v.x)
        ys.append(v.y)
sc = bpy.context.scene
cam = bpy.data.cameras.new("cam")
cam.type = "ORTHO"
# the full 512-unit page is 512 * (importer scale); the background square is gone, so frame the PAGE, not the ink:
# icons keep the margins they were drawn with
page = 512 * 0.000282222  # (Blender's SVG importer: 1 px = 0.2822 mm)
cam.ortho_scale = page
co = bpy.data.objects.new("cam", cam)
sc.collection.objects.link(co)
co.location = (page / 2, -page / 2 if min(ys or [0]) < 0 else page / 2, 1.0)
sc.camera = co
try:  # (Blender 4.2-4.x called it EEVEE_NEXT; 5.x is EEVEE again — the engine list is dynamic, so just try)
    sc.render.engine = "BLENDER_EEVEE"
except TypeError:
    sc.render.engine = "BLENDER_EEVEE_NEXT"
sc.render.resolution_x = sc.render.resolution_y = size
sc.render.film_transparent = True
sc.render.image_settings.file_format = "PNG"
sc.render.image_settings.color_mode = "RGBA"
sc.view_settings.view_transform = "Standard"
sc.render.filepath = out
bpy.ops.render.render(write_still=True)
print("ICON_DONE", len(curves), round(min(xs or [0]), 4), round(max(xs or [0]), 4), round(min(ys or [0]), 4), round(max(ys or [0]), 4))
