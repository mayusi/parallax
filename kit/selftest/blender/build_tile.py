"""build_tile.py — fixtures for A TILE and A STYLISED LOOK (a.tile, a.stylise, rbx_tile; the 3D methods audit, stage
X). By the word after `--`:
  (none)   a TILE of worn paint, 8 studs a tile: its maps must repeat both ways (`tile_seam` holds), the manifest
           must carry `tile` (the studs and the four maps a MaterialVariant takes).
  ball     a STYLISED ball and block: the light painted into the colour in three flat tones, the surface matt -
           after the build `STYLE {json}`: the tones counted on the ball's colour map, top against underside.
  metal    a.stylise on a metal material: the build must STOP and say why (build_tile_metal.py).
  unlit    the stylised ball again, the painted light kept out of the bake behind the builder's back: `stylised`
           must FAIL - it reads the colour map, not the ask (build_tile_unlit.py).
  ramp     the tile again, its maps written lighter left to right behind the builder's back: `tile_seam` must
           FAIL (build_tile_ramp.py).
Used by `lune run kit selftest`. Never "fix" this file."""

import json
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
import rbx  # noqa: E402
import rbx_cutout  # noqa: E402

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
HOW = next((w for w in ("ball", "metal", "ramp", "unlit") if w in ARGS), "tile")

def tiles():
    """a tile, or the tile with its maps tampered with"""
    if HOW == "tile":
        a = rbx.Asset("_selftest_tile", tex=256, size=(8.0, 0.1, 8.0))
        a.material("paint", color=(0.35, 0.42, 0.3), rough=0.7, wear=0.4)
        a.tile("paint", studs=8)
        a.build()
        manifest = json.load(open(os.path.join(rbx.BUILD, "models", f"{a.name}.manifest.json"), encoding="utf-8"))
        print("TILE " + json.dumps(manifest.get("tile")))

    elif HOW == "ramp":
        import rbx_tile  # noqa: E402

        # (the map as written gets lighter left to right: the check must read the MAP, not trust the fade)
        rbx_tile.tileable = lambda px, blend=0.125: px * np.linspace(0.3, 1.0, px.shape[1])[None, :, None]
        a = rbx.Asset("_selftest_tile_ramp", tex=256, size=(8.0, 0.1, 8.0))
        a.material("paint", color=(0.35, 0.42, 0.3), rough=0.7, wear=0.4)
        a.tile("paint", studs=8)
        a.build()


def styled():
    """the stylised ball and block (or its metal / unlit twin), and what its maps hold"""
    a = rbx.Asset("_selftest_style_" + HOW, tex=256, size=(2.0, 3.0, 2.0), ground=True)
    a.material("clay", color=(0.75, 0.45, 0.3), rough=0.5, metal=1.0 if HOW == "metal" else 0.0)
    a.box("Block", (2.0, 1.0, 2.0), (0, 0.5, 0), "clay", bevel=0)
    a.sphere("Ball", 1.0, (0, 2.0, 0), "clay")
    a.stylise(bands=3, shade=0.4)
    if HOW == "unlit":
        a.rebake = True                                   # (always a fresh bake: the first ask below is the bake's)
        _real, _calls = rbx.Asset._style_map, []

        def _first_time_nothing(self, obj, group):
            _calls.append(group)
            return None if len(_calls) == 1 else _real(self, obj, group)      # (the bake asks first; the check after)

        rbx.Asset._style_map = _first_time_nothing
    a.build()
    if HOW == "unlit":
        return   # (nothing to read back)

    manifest = json.load(open(os.path.join(rbx.BUILD, "models", f"{a.name}.manifest.json"), encoding="utf-8"))
    obj = bpy.data.objects[a.name]
    tex_ = manifest["groups"]["main"]["textures"]


    def read(key):
        rel = tex_[key]
        img = bpy.data.images.load(rel if os.path.isabs(rel) else os.path.join(rbx.REPO, rel), check_existing=False)
        n_ = img.size[0]
        px = np.empty(n_ * n_ * 4, np.float32)
        img.pixels.foreach_get(px)
        return px.reshape(n_, n_, 4)[..., :3].mean(axis=2), n_


    luma, n = read("color")
    rough, _n = read("rough" if "rough" in tex_ else "roughness")
    me = obj.data
    me.calc_loop_triangles()
    nt = len(me.loop_triangles)
    uv = np.empty(len(me.loops) * 2, np.float64)
    me.uv_layers.active.data.foreach_get("uv", uv)
    tri, tv, tp = np.empty(nt * 3, np.int64), np.empty(nt * 3, np.int64), np.empty(nt, np.int64)
    me.loop_triangles.foreach_get("loops", tri)
    me.loop_triangles.foreach_get("vertices", tv)
    me.loop_triangles.foreach_get("polygon_index", tp)
    co = np.empty(len(me.vertices) * 3, np.float64)
    me.vertices.foreach_get("co", co)
    m = np.array(rbx.BL_FROM_RBX.inverted() @ obj.matrix_world, np.float64)
    co = co.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3]
    ids = np.zeros(len(me.polygons), np.int32)
    me.attributes["kit_part"].data.foreach_get("value", ids)
    ball = ids[tp] == list(obj["kit_parts"]).index("Ball")
    rows, cols, pts = rbx_cutout.texels(uv.reshape(-1, 2)[tri.reshape(-1, 3)[ball]], co[tv.reshape(-1, 3)[ball]], n)
    up, down = pts[:, 1] > 2.7, pts[:, 1] < 1.5
    lum = luma[rows, cols]
    hist = np.histogram(lum, bins=40, range=(0, 1))[0]
    print("STYLE " + json.dumps({
        "top": round(float(np.median(lum[up])), 3), "under": round(float(np.median(lum[down])), 3),
        "peaks": int((hist > 0.04 * len(lum)).sum()),              # the bins that hold a tone
        "rough": round(float(np.median(rough[rows, cols])), 3)}))


# (never an early exit: Blender prints on the verdict's own line after one, and the kit cannot read it)
if HOW in ("tile", "ramp"):
    tiles()
else:
    styled()
