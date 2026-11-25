"""kit family <name> - A FAMILY OF MODULES THAT SNAP, checked as one (kit/blender/rbx_family.py).

Every built asset that called a.module(grid, family="<name>") carries, in its manifest, the cut its mesh leaves on
each gridded side (one raster a grid cell). This reads them all, gives every side-cell shape a CONNECTOR id, says
which connectors MEET face to face with no seam, and fails on a SEAM: two sides that almost meet (a wall a little
thicker, a lip a little off) - what a player sees where two modules stand side by side. Writes the family table
<build>/families/<name>.json - per module and side, the connectors there and what each meets - for the world
builder and the game (src/kit Modules snaps by it). Prints one JSON line (summary / next_action).
  python kit/tools/family.py <name> [--build <dir>] [--only <asset,asset,...>]
--only names the family's modules (a module renamed or dropped leaves its old manifest behind in the build)."""

import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_family  # noqa: E402


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))


def main(argv):
    def flag(name):
        if name not in argv:
            return None
        k = argv.index(name)
        if k + 1 >= len(argv) or argv[k + 1].startswith("--"):
            raise SystemExit(emit("usage", f"family: {name} needs a value", "lune run kit family <name> "
                                  "[--build <dir>] [--only a,b]") or 2)
        return argv[k + 1]
    build = flag("--build") or os.environ.get("KIT_BUILD") or os.path.join(ROOT, "build")
    only = flag("--only")
    only = set(x.strip() for x in only.split(",") if x.strip()) if only else None
    vals = {v for v in (flag("--build"), flag("--only")) if v}
    args = [a for a in argv if not a.startswith("--") and a not in vals]
    if not args:
        emit("usage", "family: name the family (kit family <name>)", "lune run kit family <name>")
        return 2
    name = args[0]
    build = build if os.path.isabs(build) else os.path.join(ROOT, build)
    modules, missing = {}, []
    for path in sorted(glob.glob(os.path.join(build, "models", "*.manifest.json"))):
        try:
            with open(path, encoding="utf-8") as fh:
                m = json.load(fh)
        except (OSError, ValueError):
            continue
        mod = m.get("module") or {}
        if mod.get("family") != name:
            continue
        asset = os.path.basename(path)[: -len(".manifest.json")]
        if only is not None and asset not in only:
            continue
        if not mod.get("sides"):
            missing.append(asset)
            continue
        modules[asset] = mod["sides"]
    if not modules:
        emit("fail", f'family {name}: no built module of the family (a.module(grid, family="{name}"))',
             "build the family's modules first (lune run kit asset <name>)")
        return 1
    got = rbx_family.family(modules)
    meets = {}
    for m, sides in got["sides"].items():
        for s, grid in sides.items():
            for v, row in enumerate(grid):
                for u, cid in enumerate(row):
                    if cid == "open":
                        continue
                    for mate in got["mates"].get(cid, []):
                        for (m2, s2, v2, u2) in got["connectors"].get(mate, []):
                            meets.setdefault(f"{m}.{s}.{v}.{u}", []).append(f"{m2}.{s2}.{v2}.{u2}")
    table = {"family": name, "modules": sorted(modules), "sides": got["sides"], "mates": got["mates"],
             "meets": meets, "whole": got["whole"], "seams": got["seams"], "turned": got["turned"],
             "unmeasured": missing}
    out = os.path.join(build, "families", f"{name}.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(table, fh, indent=1)
    rel = os.path.relpath(out, ROOT).replace("\\", "/")
    lonely = sorted(c for c, ms in got["mates"].items() if not ms)
    pairs = ", ".join(c + " meets " + "/".join(ms) for c, ms in sorted(got["mates"].items()) if ms) or "none meet"
    said = f"family {name}: {len(modules)} modules, {len(got['mates'])} connectors ({pairs})"
    if lonely:
        said += f"; meeting nothing: {', '.join(lonely)}"
    if got["turned"]:
        t0 = got["turned"][0]
        said += (f"; {len(got['turned'])} side(s) almost meet their own mirror ({t0[0]} {t0[1]}: a one-sided shape - "
                 "never stand it turned 180 degrees onto itself)")
    if missing:
        emit("fail", f"{said}; NOT MEASURED: {', '.join(missing)} - its build cut no sides (off its grid: "
             "module_grid failed; or built before a.module(family=))", "fix the module's grid and rebuild it, "
             "then lune run kit family " + name, table=os.path.relpath(out, ROOT).replace("\\", "/"))
        return 1
    if got["seams"]:
        first = got["seams"][0]
        seam = (f"{len(got['seams'])} seam(s) - {first[0]} {first[1]} almost meets {first[4]} {first[5]} "
                f"(IoU {first[8]:.2f}: a lip, a step, a wall a little thicker)")
        emit("fail", f"{said}; {seam} · table {rel}", "make the two sides one shape (the same section where they "
             "meet), rebuild both, then lune run kit family " + name, table=rel)
        return 1
    emit("pass", f"{said} · table {rel}", "snap them by the table (src/kit Modules) or build the next module",
         table=rel)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
