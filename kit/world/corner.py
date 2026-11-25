"""corner.py - ONE 40 x 40 stud CORNER of a world, rendered at full size (LIMITATIONS_FIXES_V3.md stage A.3, W2: "drive
ONE 40x40 corner (a plaza corner with its lamp, door, window ...) to --stage corner (>= 7/10) before scaling any full
street"). The whole built world, FRAMED on the square of CORNER studs on the ground at a station's target (nothing
is cut away: what stands round the corner is in the frame as built) (the world's own stations:
build/worlds/look/<Name>/stations.json); two views of it: from the station's own eye, pulled in to the corner, and a
three-quarter view from above its outer corner. Rendered by kit/world/look_blender.py into build/worlds/corner/<Name>/
(corner_eye.png, corner_three.png) with corner.json saying which station it is of (kit/world/stages.py reads it).
python kit/world/corner.py <Name> --at <station> --blender <blender.exe> [--build <dir>] -> one JSON line."""
import json
import math
import os
import subprocess
import sys

CORNER = 40.0  # studs a side
RES = "1920x1080"


def views(station, size=CORNER):
    """the two views of the corner at a station's target: [{name, at, target}] (Roblox axes)"""
    eye = station.get("cam") or station.get("at")  # (stations.json: "cam" and "target", Roblox axes)
    tgt = station.get("target")
    if not (isinstance(eye, list) and isinstance(tgt, list) and len(eye) == 3 and len(tgt) == 3):
        raise ValueError("the station has no camera (cam / target)")
    dx, dz = tgt[0] - eye[0], tgt[2] - eye[2]
    d = math.hypot(dx, dz) or 1.0
    ux, uz = dx / d, dz / d
    # from its eye, pulled in so the square fills the frame (a 70-degree lens sees 40 studs at ~30 studs)
    near = [tgt[0] - ux * size * 0.8, tgt[1] + 5.0, tgt[2] - uz * size * 0.8]
    # three-quarter, from above the square's outer corner (to the right of the eye's line)
    rx, rz = -uz, ux
    three = [tgt[0] - ux * size * 0.7 + rx * size * 0.7, tgt[1] + size * 0.6, tgt[2] - uz * size * 0.7 + rz * size * 0.7]
    return [{"name": "corner_eye", "at": near, "target": [tgt[0], tgt[1] + 4.0, tgt[2]], "labels": []},
            {"name": "corner_three", "at": three, "target": [tgt[0], tgt[1] + 2.0, tgt[2]], "labels": []}]


def main(a):
    name = a[0]
    at = a[a.index("--at") + 1] if "--at" in a else None
    blender = a[a.index("--blender") + 1] if "--blender" in a else "blender"
    build = a[a.index("--build") + 1] if "--build" in a else "build/worlds"
    world = os.path.join(build, f"{name}.json")
    stations = os.path.join(build, "look", name, "stations.json")
    if not os.path.isfile(world) or not os.path.isfile(stations):
        return {"status": "fail", "summary": f"{name} is not built and looked at ({world}, {stations})",
                "next_action": f"lune run kit world, then lune run kit world look {name}"}
    with open(stations, encoding="utf-8") as f:
        st = json.load(f)
    st = st.get("stations", st) if isinstance(st, dict) else st
    names = [s.get("name") for s in st if isinstance(s, dict)]
    pick = next((s for s in st if isinstance(s, dict) and s.get("name") == at), None)
    if pick is None:
        return {"status": "fail", "summary": f"no station {at!r} in {name} ({', '.join(str(n) for n in names)})",
                "next_action": f"lune run kit world corner {name} --at <one of: {', '.join(str(n) for n in names)}>"}
    try:
        vs = views(pick)
    except ValueError as e:
        return {"status": "fail", "summary": f"station {at}: {e}", "next_action": f"lune run kit world look {name}"}
    with open(world, encoding="utf-8") as f:
        w = json.load(f)
    w["views"] = vs
    tmp = os.path.join(build, f"{name}.corner.json")  # (beside the world: its meshes are found from there)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(w, f)
    out = os.path.join(build, "corner", name)
    os.makedirs(out, exist_ok=True)
    for f in os.listdir(out):
        if f.endswith(".png"):
            os.remove(os.path.join(out, f))
    run = subprocess.run([blender, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                          os.path.join(os.path.dirname(os.path.abspath(__file__)), "look_blender.py"), "--", tmp,
                          os.path.join(out, "_render"), "--res", RES], capture_output=True, text=True)
    made = []
    rdir = os.path.join(out, "_render")
    for v in vs:
        src = os.path.join(rdir, f"view_{v['name']}.png")
        if os.path.isfile(src):
            dst = os.path.join(out, f"{v['name']}.png")
            os.replace(src, dst)
            made.append(dst)
    if len(made) != len(vs):
        return {"status": "fail", "summary": f"the corner render failed ({run.returncode})",
                "next_action": (run.stdout + run.stderr)[-300:]}
    with open(os.path.join(out, "corner.json"), "w", encoding="utf-8") as f:
        json.dump({"world": name, "at": at, "size": CORNER, "views": vs}, f, indent=1)
    return {"status": "pass", "summary": f"corner of {name} at {at}: {len(made)} renders in {out}",
            "next_action": f"LOOK at {made[0]} and {made[1]} beside the station's reference, show the owner; his 7 or "
                           f"more: lune run kit approve world {name} \"<his words>\" --by owner --stage corner",
            "renders": made}


if __name__ == "__main__":
    r = main(sys.argv[1:])
    print(json.dumps(r))
    sys.exit(0 if r["status"] == "pass" else 1)
