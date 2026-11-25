"""selftest_inputs.py — what `kit selftest`'s cache keys on (owner 2026-11-20: "a content-hash cache, busted on kit/lib/
changes, so untouched fixtures don't cold-boot Blender repeatedly"). Every file the kit's gates and fixtures are made of
(git's tracked + untracked-not-ignored files under kit/, src/kit/ and assets/rigs/) belongs to ONE lane's folders or to
the COMMON part (kit/lib, kit/cmd, kit/blender, kit/tools, ... everything not named below). A lane's key is the sha256
of the common part, its own folders and the lanes it reads: a change to the common part busts every case; a change to
kit/anim busts the anim cases (and the world cases, which read kit/anim) and nothing else. The "kit" key (a case whose
label names no lane) covers every file.

    python kit/scripts/selftest_inputs.py              -> {"lanes": {"3d": sha, ..., "kit": sha}, "files": n}
    python kit/scripts/selftest_inputs.py --changed    -> {"changed": [lanes touched by uncommitted changes]}
"""

import hashlib
import json
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# a lane's own folders (a path under one of them belongs to that lane; anything else is common)
LANE_DIRS = {
    "3d": ["kit/gen/", "kit/materials/", "kit/blender/", "kit/selftest/blender/", "kit/selftest/sheet/",
           "kit/selftest/sculpt/", "kit/selftest/uvcheck/", "kit/selftest/scan/"],
    "vfx": ["kit/vfx/", "kit/selftest/vfx/"],
    "anim": ["kit/anim/", "kit/selftest/anim/", "assets/rigs/"],
    "world": ["kit/world/", "kit/selftest/world/"],
    "ui": ["kit/ui/", "kit/selftest/ui/"],
    "sfx": ["kit/audio/", "kit/selftest/audio/"],
    # PROMPT-X (its cases are labelled "prompt-x ..."; only `kit prompt` and `kit start --prompt` run kit/prompt)
    "prompt": ["kit/prompt/", "kit/selftest/prompt/"],
}
# the lanes a lane's code reads (measured 2026-11-20: kit/world names kit/anim and kit/vfx, kit/ui names kit/vfx,
# kit/audio names kit/world) - their folders are part of its key
# kit/blender is the 3d lane's (PARALLAX_FINAL_CLOSURE_SPEC A2, 2026-11-22: as common, one edit there re-ran all seven
# lanes); the lanes whose cases reach it read 3d: sfx (kit/audio/match.py imports kit/blender/cmaes.py) and vfx (kit
# calibrate runs kit/blender/calibration.py on the effects' skies)
READS = {"world": ["anim", "vfx"], "ui": ["vfx"], "sfx": ["world", "anim", "vfx", "3d"], "vfx": ["3d"]}
# never part of any key: the notes, the skill pages and the kit's own unit tests (no gate or fixture reads them)
SKIP = ("kit/knowledge/", "kit/skills/", "kit/test/")
WHERE = ["kit", "src/kit", "assets/rigs"]


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True).stdout.decode("utf-8", "replace")


def wanted(p):
    return bool(p) and not p.startswith(SKIP) and "__pycache__" not in p


def digests():
    """{path: content digest}: a file the working tree has as the index does keeps git's own blob id (no read - the
    fixtures hold .blend files, pictures and clips); a changed or untracked one is read and hashed"""
    out = {}
    for row in git("ls-files", "-s", "-z", "--", *WHERE).split("\0"):
        meta, _, path = row.partition("\t")
        if wanted(path):
            out[path] = "git:" + meta.split(" ")[1]
    dirty = git("diff", "--name-only", "-z", "--", *WHERE).split("\0")
    dirty += git("ls-files", "-o", "--exclude-standard", "-z", "--", *WHERE).split("\0")
    present = []
    for path in dirty:
        if not wanted(path):
            continue
        if os.path.isfile(os.path.join(ROOT, path)):
            present.append(path)
        else:
            out.pop(path, None)  # (deleted in the working tree)
    if present:
        # the SAME id git gives the content once it is committed (git hash-object applies the path's filters, line
        # endings included): a file's key never changes because it was committed, only because its content did
        ids = subprocess.run(["git", "hash-object", "--stdin-paths"], cwd=ROOT, input="\n".join(present).encode(),
                             capture_output=True, check=True).stdout.decode().split()
        for path, oid in zip(present, ids):
            out[path] = "git:" + oid
    return out


def lane_of(path):
    for lane, dirs in LANE_DIRS.items():
        if path.startswith(tuple(dirs)):
            return lane
    return None


def keys():
    parts = {lane: hashlib.sha256() for lane in LANE_DIRS}
    common = hashlib.sha256()
    n = 0
    table = digests()
    for p in sorted(table):
        n += 1
        line = f"{p}\0{table[p]}\n".encode()
        lane = lane_of(p)
        (parts[lane] if lane else common).update(line)
    done = {lane: h.hexdigest() for lane, h in parts.items()}
    base = common.hexdigest()
    out = {}
    for lane in LANE_DIRS:
        own = [lane] + READS.get(lane, [])
        out[lane] = hashlib.sha256((base + "".join(done[x] for x in own)).encode()).hexdigest()
    out["kit"] = hashlib.sha256((base + "".join(done[x] for x in sorted(done))).encode()).hexdigest()
    return out, n


def changed():
    """the lanes whose inputs the working tree changed against HEAD (a common file -> every lane)"""
    out = git("status", "--porcelain", "-z", "--untracked-files=all", "--", *WHERE)
    lanes = set()
    entries = out.split("\0")
    i = 0
    while i < len(entries):
        e = entries[i]
        i += 1
        if len(e) < 4:
            continue
        path = e[3:]
        if e[0] in "RC":  # (a rename carries its old path as the next entry)
            i += 1
        if path.startswith(SKIP) or "__pycache__" in path:
            continue
        lane = lane_of(path)
        if lane is None:
            return sorted(list(LANE_DIRS) + ["kit"])
        lanes.add(lane)
        for reader, reads in READS.items():
            if lane in reads:
                lanes.add(reader)
    return sorted(lanes)


if __name__ == "__main__":
    if "--changed" in sys.argv:
        print(json.dumps({"changed": changed()}))
    else:
        k, n = keys()
        print(json.dumps({"lanes": k, "files": n}))
