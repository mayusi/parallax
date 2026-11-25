"""pick.py — turn one ranked reference candidate into a project reference, WITH its attribution.

    python kit/refs/pick.py build/refs/<slug> <rank-number | file> --as <asset>_<view>

Copies the picture to refs/<asset>_<view>.<ext> and adds a row to refs/SOURCES.md (file | source | licence | use): the
source page, the size, the licence and its author — what CC BY / CC BY-SA require you to keep. Refuses a candidate whose
licence is not usable in a game (non-commercial / no-derivatives / unknown). Nothing here touches the network.
"""

import json
import os
import shutil
import sys

USABLE = {"cc0": "CC0", "pdm": "Public domain", "by": "CC BY", "by-sa": "CC BY-SA"}
HEADER = "# Reference sources\n\n| file | source | licence | use |\n|---|---|---|---|\n"


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra},
                     ensure_ascii=False))
    return 0 if status == "pass" else 1


def sources_row(file, path, meta, licence, credit, use="modelling reference"):
    """one refs/SOURCES.md row: the source page, the size of the file KEPT (a search often downloads a thumbnail, not
    the original), the licence with its URL and the author — what CC BY / CC BY-SA ask a user to keep"""
    from PIL import Image  # noqa: PLC0415

    with Image.open(path) as im:
        w, h = im.size
    size = f"{w}x{h} as kept, {max(1, round(os.path.getsize(path) / 1024))} KB"
    url = meta.get("license_url") or ""
    lic = f"{licence} ({url})" if url else licence
    return (f"| {file} | {meta.get('page') or meta.get('url')} ({size}; via {meta.get('source')}, retrieved "
            f"{meta.get('retrieved')}) | {lic} — {credit} | {use} ({meta.get('title', '')[:60].replace('|', '/')}) |\n")


def main(argv):
    if len(argv) < 2 or "--as" not in argv:
        return emit("fail", "refs pick: needs the candidates folder, a rank number (or file) and --as <asset>_<view>",
                    "lune run kit refs pick build/refs/<slug> 1 --as crate_side")
    folder, which, name = argv[0], argv[1], argv[argv.index("--as") + 1]
    index = os.path.join(folder, "index.json")
    if which.isdigit():
        if not os.path.isfile(index):
            return emit("fail", f"refs pick: {folder} has no ranking yet", f"lune run kit refs rank {folder}")
        with open(index, encoding="utf-8") as fh:
            ranked = json.load(fh)["ranked"]
        k = int(which) - 1
        if not 0 <= k < len(ranked):
            return emit("fail", f"refs pick: #{which} is not in the ranking (1..{len(ranked)})", f"look at {folder}/contact.png")
        src = os.path.join(folder, ranked[k]["file"])
    else:
        src = os.path.join(folder, which)
    if not os.path.isfile(src) or not os.path.isfile(src + ".json"):
        return emit("fail", f"refs pick: {src} or its licence record is missing", "pick a picture kit refs find saved")
    with open(src + ".json", encoding="utf-8") as fh:
        meta = json.load(fh)
    lic = meta.get("license")
    if lic not in USABLE:
        return emit("fail", f"refs pick: {os.path.basename(src)} is licensed '{lic}' — not usable in a game",
                    "pick a CC0 / public domain / CC BY / CC BY-SA picture")
    os.makedirs("refs", exist_ok=True)
    dst = "refs/" + name + os.path.splitext(src)[1].lower()
    shutil.copyfile(src, dst)
    version = meta.get("license_version") or ""
    licence = version if version.lower().startswith(("cc", "public")) else f"{USABLE[lic]} {version}".strip()
    credit = (meta.get("creator") or "unknown author").replace("|", "/")
    row = sources_row(os.path.basename(dst), dst, meta, licence, credit)
    sources = os.path.join("refs", "SOURCES.md")
    text = open(sources, encoding="utf-8").read() if os.path.isfile(sources) else HEADER
    if not text.endswith("\n"):
        text += "\n"
    # one row per picture: a re-pick under the same name replaces its row, and an older pick of it under another
    # extension (a .png where a .jpg now stands) goes with its row
    stem = name + "."
    for old in os.listdir("refs"):
        if old.startswith(stem) and old != os.path.basename(dst) and old.rsplit(".", 1)[-1].lower() in ("jpg", "jpeg",
                                                                                                         "png", "webp"):
            os.remove(os.path.join("refs", old))
    text = "".join(line for line in text.splitlines(keepends=True) if not line.startswith(f"| {stem}"))
    with open(sources, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text + row)
    return emit("pass", f"refs pick: {dst} ({licence}, {credit[:40]}) — attribution added to refs/SOURCES.md",
                f"trace it: lune run kit trace {dst} --name {name}" + (" --cutout" if lic else ""),
                file=dst.replace("\\", "/"))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
