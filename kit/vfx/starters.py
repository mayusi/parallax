"""starters.py - the record of the kit's starter pieces (kit/vfx/starters.json): every effect, mesh, texture and part
that `kit init` seeds into a new project, by the sha256 of its text (line endings read as LF). Every version a starter
ever shipped with stays listed, so an untouched copy from an older release is still recognised after an upgrade.

A project's piece whose text is a recorded starter's is the KIT's piece (kit/lib/starters.luau, kit/vfx/vault.py): the
making gates and the VFX vault hold it from its first edit. The record, not kit/starter/, is what decides: kit/starter
is not fingerprinted (promote and upgrades add to it), while this record is kit-owned like the gates' own code
(kit/lib/integrity.luau: `kit status` flags an edit; the guard lets only a kit-lane session edit kit/) and is written
only in the kit's home (kit/.source), where the starters are made:

    python kit/vfx/starters.py --check            exit 1 when a starter's current text is not in the record
    python kit/vfx/starters.py --write            the kit's home only (`kit promote vfx` runs it)

Pieces (kit/cmd/setup.luau init + kit/lib/library.luau unpackVfx): kit/starter/vfx/<name>.json -> effect/<name>,
kit/starter/vfx/meshes/<name>.json -> mesh/<name>, kit/starter/textures/<name>.json -> texture/<name>, and each
example's packed kit/starter/vfx/_deps/<example>/parts|textures/<name>.json -> part/<name> | texture/<name> (hashed as
packed, with their `__DEPS__/textures/` placeholder: a project's copy is compared with it put back).
"""
import argparse
import glob
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.normpath(os.path.join(HERE, ".."))
RECORD = os.path.join(HERE, "starters.json")
ABOUT = ("The kit's starter pieces as `kit init` seeds them into a new project, by the sha256 of their text (line "
         "endings read as LF); every version a starter shipped with. A project's piece with one of these texts is the "
         "kit's: the making gates and the VFX vault hold it from its first edit. Written in the kit's home only "
         "(python kit/vfx/starters.py --write; kit promote vfx runs it).")


def text_sha(data):
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def pieces(kit=KIT):
    """{key: sha256} of every starter piece as it is now in <kit>/starter"""
    starter = os.path.join(kit, "starter")
    vfx = os.path.join(starter, "vfx")
    found = {}

    def add(kind, path):
        with open(path, "rb") as fh:
            found[f"{kind}/{os.path.basename(path)[:-5]}"] = text_sha(fh.read())

    for p in sorted(glob.glob(os.path.join(vfx, "*.json"))):
        if not os.path.basename(p).startswith("_"):
            add("effect", p)
    for p in sorted(glob.glob(os.path.join(vfx, "meshes", "*.json"))):
        add("mesh", p)
    for p in sorted(glob.glob(os.path.join(starter, "textures", "*.json"))):
        if not os.path.basename(p).startswith("_"):
            add("texture", p)
    for kind, sub in (("part", "parts"), ("texture", "textures")):
        for p in sorted(glob.glob(os.path.join(vfx, "_deps", "*", sub, "*.json"))):
            key = f"{kind}/{os.path.basename(p)[:-5]}"
            with open(p, "rb") as fh:
                sha = text_sha(fh.read())
            found.setdefault(key, sha)
            if found[key] != sha:  # (one name, two packed texts: both are the kit's)
                found[key + "#" + sha[:12]] = sha
    return found


def read(path=RECORD):
    """the record's {key: set(sha256)}; a missing or broken record recognises nothing (never a quiet way round)"""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    out = {}
    for key, shas in (data.get("pieces") or {}).items() if isinstance(data, dict) else []:
        if isinstance(shas, list):
            out.setdefault(key.split("#")[0], set()).update(s for s in shas if isinstance(s, str))
    return out


def missing(kit=KIT, path=RECORD):
    have = read(path)
    return sorted(k for k, sha in pieces(kit).items() if sha not in have.get(k.split("#")[0], set()))


def write(kit=KIT, path=RECORD):
    try:
        with open(path, encoding="utf-8") as fh:
            old = (json.load(fh) or {}).get("pieces") or {}
    except (OSError, ValueError):
        old = {}
    merged = {k: sorted(set(v)) for k, v in old.items() if isinstance(v, list)}
    for key, sha in pieces(kit).items():
        base = key.split("#")[0]
        merged[base] = sorted(set(merged.get(base, [])) | {sha})
    body = json.dumps({"schema": 1, "about": ABOUT, "pieces": dict(sorted(merged.items()))}, indent=1,
                      ensure_ascii=True) + "\n"
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(body)
    return len(merged)


def emit(status, summary, next_action):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action}))
    return 0 if status == "pass" else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--kit", default=KIT, help="the kit folder whose starter/ and vfx/starters.json are used")
    a = ap.parse_args()
    kit = os.path.abspath(a.kit)
    path = os.path.join(kit, "vfx", "starters.json")
    if a.write:
        if not os.path.isfile(os.path.join(kit, ".source")):
            return emit("fail", "vfx starters: the starter record is the kit's - it is written in the kit's home only "
                        "(kit/.source); a project gets it with the kit", "lune run parallax update / upgrade")
        n = write(kit, path)
        return emit("pass", f"vfx starters: {n} starter piece(s) recorded in {path}", "commit kit/vfx/starters.json")
    gone = missing(kit, path)
    if gone:
        return emit("fail", f"vfx starters: {len(gone)} starter piece(s) not in the record (e.g. {', '.join(gone[:4])})",
                    "in the kit's home: python kit/vfx/starters.py --write, then commit kit/vfx/starters.json")
    return emit("pass", f"vfx starters: every starter piece is in the record ({len(pieces(kit))})", "none")


if __name__ == "__main__":
    sys.exit(main())
