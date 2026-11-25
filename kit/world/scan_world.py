"""scan_world.py - A REAL THING, PHOTOGRAPHED, SET INTO A WORLD (kit world scan; the owner's method list:
"Photo-based environment reconstruction"). The 3D lane's photogrammetry route (kit/tools/photoscan.py: COLMAP, vetted
2026-11-16 - photos -> a checked, levelled, metric, textured GLB) makes the mesh; this brings it into the world's mesh
registry (kit/world/import_blender.py) AT ITS REAL SIZE IN STUDS, so a rocks / scatter / forest / mesh step places it
as the thing it is.

    python kit/world/scan_world.py <Name> --from <photos folder> --size <metres> [--axis height|length|width]
                                    [--quality low|medium|high] [--tool <photoscan.py>]
                                    [--meshes <worldmeshes dir>] [--scans <dir>] [--work <dir>]
(kit world scan passes the three folders from the kit's config: the active game's build when one is active.)

--size is REQUIRED: a world places things at their real size, and photos alone have none (photoscan says so).
The tool: kit/tools/photoscan.py of this checkout when it has one, else the main checkout's (the route lives on main;
this branch never merges it) - found through git's own list of worktrees.
-> build/worldscans/<Name>.scan.glb + .scan.json (the tool's report), build/worldmeshes/<Name>__*.fbx/.png/.mesh.json
+ its entries in build/worldmeshes/meshes.json, all IN STUDS (the importer scales the mesh before it writes anything),
the asset and its pieces stamped "scan": { photos, metres, axis, report, tool, commit }. One JSON line."""
import argparse
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
_KIT = os.path.join(REPO, "kit")
if _KIT not in sys.path:
    sys.path.insert(0, _KIT)
from blender_path import find_blender  # noqa: E402

STUD_M = 0.28  # metres per stud (kit/world/web.py: a Roblox character is 5 studs, ~1.4 m, at this scale)


def blender():
    """Blender as every kit tool finds it (kit/blender_path.py: KIT_BLENDER / BLENDER, the OS's install folders newest
    first, then PATH) -> its path or None"""
    return find_blender()


def say(status, summary, next_action, **more):
    print(json.dumps(dict({"status": status, "summary": summary, "next_action": next_action}, **more)))
    return 0 if status == "pass" else 1


def find_tool(given=None):
    """the photogrammetry tool -> its path, or None"""
    if given:
        return given if os.path.isfile(given) else None
    own = os.path.join(REPO, "kit", "tools", "photoscan.py")
    if os.path.isfile(own):
        return own
    try:
        out = subprocess.run(["git", "-C", REPO, "worktree", "list", "--porcelain"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=30).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    # the checkout on main; failing that (main's checkout on another branch for a moment, detached) the FIRST entry,
    # which git always lists as the main working tree. Another branch's linked worktree is never taken.
    first, path = None, None
    for line in out.splitlines():
        if line.startswith("worktree "):
            path = line[len("worktree "):].strip()
            first = first or path
        elif line.strip() == "branch refs/heads/main" and path:
            tool = os.path.join(path, "kit", "tools", "photoscan.py")
            return tool if os.path.isfile(tool) else None
    if first:
        tool = os.path.join(first, "kit", "tools", "photoscan.py")
        if os.path.isfile(tool):
            return tool
    return None


def commit_of(tool):
    """the commit the tool's checkout is on, and whether the tool has edits not committed -> 'sha' or 'sha+edits'"""
    d = os.path.dirname(tool)
    try:
        sha = subprocess.run(["git", "-C", d, "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=30).stdout.strip()
        dirty = subprocess.run(["git", "-C", d, "status", "--porcelain", "--", os.path.basename(tool)],
                               capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=30).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return None
    return (sha + "+edits" if dirty else sha) or None


def main(argv):
    ap = argparse.ArgumentParser(prog="kit world scan")
    ap.add_argument("name")
    ap.add_argument("--from", dest="photos", required=False)
    ap.add_argument("--size", type=float, default=None)
    ap.add_argument("--axis", default="height", choices=("height", "length", "width"))
    ap.add_argument("--quality", default="medium", choices=("low", "medium", "high"))
    ap.add_argument("--tool", default=None)
    ap.add_argument("--meshes", default=os.path.join(REPO, "build", "worldmeshes"))
    ap.add_argument("--scans", default=os.path.join(REPO, "build", "worldscans"))
    ap.add_argument("--work", default=None)
    try:
        a = ap.parse_args(argv)
    except SystemExit:
        return say("fail", "scan: usage: <Name> --from <photos> --size <metres> [--axis ...] [--quality ...]",
                   "lune run kit world scan <Name> --from <photos> --size <metres>")
    name = a.name
    if not name.replace("_", "").isalnum() or not name.isascii():
        return say("fail", f"scan: the name is letters, digits and _ (got {name})", "name it again")
    if not a.photos or not os.path.isdir(a.photos):
        return say("fail", f"scan: --from is the folder of photos (got {a.photos})", "give the folder the photos are in")
    if a.size is None or not (0.01 <= a.size <= 500):
        return say("fail", "scan: --size is a size you know of the real thing, in metres (0.01 to 500): a world places "
                   "things at their real size, and photos alone have none",
                   "measure the thing (its height, say) and give --size <metres> --axis height")
    meshes = os.path.abspath(a.meshes)
    reg_path = os.path.join(meshes, "meshes.json")
    reg = {}
    if os.path.isfile(reg_path):
        with open(reg_path, encoding="utf-8") as fh:
            reg = json.load(fh)
    if name in reg and not reg[name].get("scan"):
        return say("fail", f"scan: {name} is already a world mesh that was not scanned (made by kit world meshes or "
                   "import): a scan may not replace it", "name the scan another way")
    tool = find_tool(a.tool)
    if not tool:
        return say("fail", "scan: no photogrammetry tool - kit/tools/photoscan.py is not in this checkout, nor in the "
                   "checkout on main (nor the repository's main working tree)",
                   "the 3D lane's route (kit/tools/photoscan.py) must be committed on main")
    exe = blender()
    if not exe:
        return say("fail", "scan: no Blender (the BLENDER env var, the 5.2 install, or blender on PATH) to bring the "
                   "mesh into the world", "install Blender 5.2 or set BLENDER")
    out = os.path.abspath(a.scans)
    work = os.path.abspath(a.work) if a.work else os.path.join(REPO, "build", "scan", name)
    os.makedirs(out, exist_ok=True)
    glb = os.path.join(out, f"{name}.scan.glb")
    report_path = os.path.join(out, f"{name}.scan.json")
    for old in (glb, report_path):  # (nothing of an earlier scan of this name is taken for this one)
        if os.path.isfile(old):
            os.remove(old)
    run = subprocess.run([sys.executable, tool, os.path.abspath(a.photos), name, "--quality", a.quality, "--size",
                          str(a.size), "--axis", a.axis, "--out", out, "--work", work],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    said = [ln for ln in run.stdout.splitlines() if ln.startswith("summary:")]
    if run.returncode != 0 or not os.path.isfile(glb) or not os.path.isfile(report_path):
        return say("fail", "scan: the photogrammetry route did not make it - " + (said[-1][9:] if said else
                   (run.stderr.strip().splitlines() or ["(no word)"])[-1]), "fix what it names and run it again")
    with open(report_path, encoding="utf-8") as fh:
        report = json.load(fh)
    # into the world's meshes: the importer scales it into studs BEFORE it writes the FBX, the .mesh.json and the
    # registry (all three agree), and stamps the asset and every piece
    os.makedirs(meshes, exist_ok=True)
    stamp = {"photos": os.path.abspath(a.photos).replace("\\", "/"), "metres": a.size, "axis": a.axis,
             "report": report_path.replace("\\", "/"), "studs_per_m": round(1 / STUD_M, 4),
             "tool": tool.replace("\\", "/"), "commit": commit_of(tool)}
    items = os.path.join(out, f"{name}.import.json")
    with open(items, "w", encoding="utf-8") as fh:
        json.dump([{"name": name, "file": glb, "maxTris": 20000, "texRes": 1024, "scale": 1.0 / STUD_M,
                    "scan": stamp}], fh)
    imp = subprocess.run([exe, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                          os.path.join(REPO, "kit", "world", "import_blender.py"), "--", items, meshes],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    reg = {}
    if os.path.isfile(reg_path):
        with open(reg_path, encoding="utf-8") as fh:
            reg = json.load(fh)
    entry = reg.get(name) or {}
    if imp.returncode != 0 or entry.get("scan") != stamp:
        tail = (imp.stdout.strip().splitlines() or imp.stderr.strip().splitlines() or ["(no word)"])[-1]
        return say("fail", f"scan: the scanned mesh did not come into the world's meshes - {tail[:300]}",
                   "read the import's line (an earlier scan of this name, if any, is still the one placed)")
    h = entry["size"][1]
    return say("pass", f"scan: {name}: a real thing {a.size:g} m along its {a.axis}, {entry['tris']} triangles in "
               f"{len(entry['parts'])} piece(s), {h:.1f} studs tall in the world -> build/worldmeshes",
               f'LOOK at {glb}; place it at its real size: {{ "mesh": {{ "mesh": "{name}", "pos": [x, y, z] }} }} (no '
               f'"height"); scatter / rocks / forest set it by their own sizes (a scatter part {h / 1.4:.1f} tall keeps '
               f'it real); in a game once uploaded (lune run kit upload)', entry=entry,
               report=report)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
