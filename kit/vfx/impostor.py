"""kit vfx impostor - ONE simulated cloud seen from a ring of 8 to 16 angles (the V3 doc, VFX stage E.1: "8-16-angle
view-dependent impostor flipbooks").

    lune run kit vfx impostor <sim> --angles 8 [--light top] [--specs assets/textures] [--force]

A GPU sim (kit/vfx/gpusim.py, recipe gpu_smoke / gpu_fire) can be rendered from round the side by a "view_variant"
spec ({"recipe": "view_variant", "of": <sim>, "yaw": 90}); a sprite's `views` table then picks, every play, the one
nearest where the camera is round the effect (VfxStage pickView, the player the same). Written by hand that was a spec
per angle and a table to keep in step with them: nobody made more than two. This writes the whole ring at once -
<sim>_v045.json ... one per angle after 0 (the sim itself is the 0 view), each copying the sim's sheet (frames, grid,
cell, post) - and prints the `views` table for the sprite. gpusim renders them with the sim (same simulation, turned),
the packer packs them, kit upload uploads them: nothing else is new.

A spec that is already there is left alone unless --force (it may have been tuned); one whose "of" is another sim is
never written over. Prints one JSON line last: {"status", "summary", "next_action", "views", "written"}.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gameroot  # noqa: E402

LIGHTS = ("top", "left", "right", "back", "front")
COPIED = ("frames", "grid", "cell", "post", "size")


def yaws(angles):
    """the ring's angles in degrees, 0 first: 360 / angles apart, each to a tenth of a degree"""
    return [round(360.0 * k / angles, 1) for k in range(angles)]


def key_of(yaw):
    """a yaw as the views table keys it ("45", "22.5") and as a spec name tail ("045", "022_5")"""
    text = f"{yaw:g}"
    whole, _, frac = text.partition(".")
    return text, whole.zfill(3) + (f"_{frac}" if frac else "")


def plan(sim_name, sim, angles, light=None):
    """-> ({views key: texture name}, {spec name: spec}) for the ring (the 0 view is the sim itself)"""
    views, specs = {}, {}
    for yaw in yaws(angles):
        k, tail = key_of(yaw)
        if yaw == 0:
            views[k] = sim_name
            continue
        name = f"{sim_name}_v{tail}"
        spec = {"engine": "fx", "recipe": "view_variant", "of": sim_name, "yaw": yaw,
                **{c: sim[c] for c in COPIED if c in sim},
                "about": f"{sim_name}'s simulation seen from {yaw:g} degrees round it (kit vfx impostor, one of {angles})"}
        if light:
            spec["light"] = light
        views[k] = name
        specs[name] = spec
    return views, specs


def emit(status, summary, next_action, **extra):
    print(json.dumps({"status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status != "fail" else 1


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kit vfx impostor")
    ap.add_argument("sim")
    ap.add_argument("--angles", type=int, default=8)
    ap.add_argument("--light", default=None)
    ap.add_argument("--specs", default=None)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    specs_dir = a.specs or os.path.join(gameroot.game_root(), "assets", "textures")
    if not 8 <= a.angles <= 16:
        return emit("fail", f"impostor: --angles {a.angles}: 8 to 16 (fewer pops from view to view; more is memory for nothing)",
                    "lune run kit vfx impostor <sim> --angles 8")
    if a.light is not None and a.light not in LIGHTS:
        return emit("fail", f"impostor: --light is one of {', '.join(LIGHTS)}", "drop --light: each view keeps the sim's own")
    path = os.path.join(specs_dir, f"{a.sim}.json")
    if not os.path.isfile(path):
        return emit("fail", f"impostor: no spec {path}", "name a GPU sim's texture key (kit/vfx/gpusim.py)")
    sim = json.load(open(path, encoding="utf-8"))
    if sim.get("engine") != "fx" or not str(sim.get("recipe", "")).startswith("gpu_"):
        return emit("fail", f"impostor: {a.sim} is not a GPU sim (recipe {sim.get('recipe')!r}): only a simulated volume can be "
                    "seen from round the side", "kit/vfx/gpusim.py: recipe gpu_smoke or gpu_fire")
    views, specs = plan(a.sim, sim, a.angles, a.light)
    written, kept = [], []
    for name, spec in specs.items():
        out = os.path.join(specs_dir, f"{name}.json")
        if os.path.isfile(out):
            try:
                old = json.load(open(out, encoding="utf-8"))
            except (OSError, ValueError):
                old = {}
            if old.get("of") != a.sim:
                return emit("fail", f"impostor: {out} is there and is not a view of {a.sim} (of {old.get('of')!r}): not written over",
                            "rename one of them")
            if not a.force:
                kept.append(name)
                continue
        with open(out, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(spec, fh, indent=1)
            fh.write("\n")
        written.append(name)
    return emit("ok", f"impostor: {a.sim} from {a.angles} angles - {len(written)} view spec(s) written"
                + (f", {len(kept)} kept as they were" if kept else ""),
                f'lune run kit vfx (renders and packs them); then on the sprite: "views": {json.dumps(views)}',
                views=views, written=written, kept=kept)


if __name__ == "__main__":
    sys.exit(main())
