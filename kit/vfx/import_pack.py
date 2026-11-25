"""import_pack.py — a vetted pack of single sprites (PNG) becomes texture specs in one go: every image in a directory
tree gets an `assets/textures/<prefix>_<name>.json` with `"recipe": "import"` (kit/vfx/fxlab.py loads it, fxfinish
finishes + gates + registers it, the library lists it under its pack).

    python kit/vfx/import_pack.py <dir> --prefix kn --pack "Kenney Particle Pack 1.1 (CC0, VETLOG 2026-10-11)"
                                  [--out assets/textures] [--alpha glow|coverage] [--color color|gray] [--cell 512]
                                  [--only slash,trace,...] (substring match) [--skip Rotated,preview,sample] [--dry]

Names: the file's stem, lower-cased, non-alphanumerics -> "_" (slash_01.png -> kn_slash_01). Existing specs are kept
(never overwritten). Prints one JSON line.
"""

import json
import os
import re
import sys


def main():
    argv = sys.argv[1:]
    if not argv or argv[0].startswith("--"):
        print(__doc__)
        return 2
    src = argv[0]
    opts = {"--prefix": "pk", "--pack": "", "--out": "assets/textures", "--alpha": "glow", "--color": "color", "--only": "", "--skip": "Rotated,preview,sample", "--cell": "512", "--dry": None, "--plate": None}
    i = 1
    while i < len(argv):
        if argv[i] == "--dry":
            opts["--dry"] = True
            i += 1
        elif argv[i].startswith("--") and i + 1 < len(argv):
            opts[argv[i]] = argv[i + 1]
            i += 2
        else:
            i += 1
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,20}", opts["--prefix"]):
        print(json.dumps({"schema": 1, "status": "fail", "summary": f"bad --prefix {opts['--prefix']!r}: letters, digits, _ and - only", "next_action": "use a short prefix such as kn, ks, ul"}))
        return 1
    if not os.path.isdir(src):
        print(json.dumps({"schema": 1, "status": "fail", "summary": f"no directory {src}", "next_action": "download + vet the pack first (VETLOG.md), then point --dir at its PNG folder"}))
        return 1
    only = [s.strip().lower() for s in opts["--only"].split(",") if s.strip()]
    skip = [s.strip().lower() for s in opts["--skip"].split(",") if s.strip()]
    made, kept, files = [], [], []
    for root, _, names in os.walk(src):
        if any(s in root.lower() for s in skip):
            continue
        for f in sorted(names):
            if not f.lower().endswith(".png"):
                continue
            stem = re.sub(r"[^a-z0-9]+", "_", os.path.splitext(f)[0].lower()).strip("_")
            if any(s in stem for s in skip):
                continue
            if only and not any(o in stem for o in only):  # substring match: --only slash also takes fire_slash
                continue
            files.append((os.path.join(root, f).replace(os.sep, "/"), stem))
    for path, stem in files:
        key = f"{opts['--prefix']}_{stem}"
        spec_path = os.path.join(opts["--out"], f"{key}.json")
        if os.path.exists(spec_path):
            kept.append(key)
            continue
        post = {"alpha": opts["--alpha"], "exposure": 1.0}
        if opts["--color"] != "color":
            post["color"] = opts["--color"]
        spec = {"engine": "fx", "recipe": "import", "about": f"{stem.replace('_', ' ')} — single sprite from {opts['--pack'] or src}", "pack": opts["--pack"] or os.path.basename(src.rstrip('/')),
                "source": path, "frames": 1, "grid": 1, "cell": int(opts["--cell"]), "premultiply": True, "post": post}
        if opts["--plate"] is not None:  # a full-screen drawn plate (impact.image): the source aspect kept, opaque, edge to edge
            spec.update({"plate": True, "cell": 0, "about": spec["about"].replace("single sprite", "full-screen drawn plate (impact.image: shown edge to edge)")})
            spec["post"] = {"alpha": "coverage", "exposure": 1.0}
        made.append(key)
        if not opts["--dry"]:
            os.makedirs(opts["--out"], exist_ok=True)
            with open(spec_path, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(spec, fh, indent=1)
                fh.write("\n")
    print(json.dumps({"schema": 1, "status": "pass", "summary": f"{len(made)} spec(s) written, {len(kept)} already there, {len(files)} image(s) seen" + (" (dry run)" if opts["--dry"] else ""),
                      "next_action": "lune run kit vfx (finish + gate + register + library), then LOOK at build/textures/_library.png", "made": made, "kept": kept}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
