"""blender_path.py — cross-OS Blender executable discovery.

Order (the same as kit/lib/run.luau Run.tool("blender"), so the Python tools and the Luau commands run one Blender):
  1. env KIT_BLENDER
  2. env BLENDER
  3. the OS's install folders — Windows: Program Files, then LOCALAPPDATA's Programs (newest "Blender X.Y" first,
     compared as numbers); macOS: /Applications, then ~/Applications; Linux: /usr/bin, /usr/local/bin, /snap/bin,
     then the newest /opt/blender*/blender (compared as numbers)
  4. `blender` on PATH (shutil.which) - after the install folders, so an old Blender on the PATH never wins over an
     installed one
  5. Returns None when nothing is found; callers should fail with:
         raise RuntimeError("no Blender found — set KIT_BLENDER to blender.exe")
"""

import glob
import os
import re
import shutil
import sys


def _newest_glob(pattern):
    """Return the path with the highest version number from a glob, or None. A tie (the same numbers) goes to the
    plainer folder name - the shorter, then the first in order ("Blender 5.2" before "Blender 5.2 Alpha") - the same
    rule as kit/lib/run.luau."""
    # (byte for byte as Luau compares: ASCII digits, ASCII lower case, the name's UTF-8 bytes and their length)
    def _ver(p):
        nums = re.findall(r"[0-9]+", os.path.basename(os.path.dirname(p)))
        return [int(n) for n in nums] if nums else []

    def _name(p):
        raw = os.path.basename(os.path.dirname(p)).encode("utf-8")
        return bytes(c + 32 if 65 <= c <= 90 else c for c in raw)

    best = None
    for p in glob.glob(pattern):
        if best is None:
            best = p
            continue
        a, b = _ver(p), _ver(best)
        name, best_name = _name(p), _name(best)
        if a > b or (a == b and (len(name), name) < (len(best_name), best_name)):
            best = p
    return best


def find_blender():
    """Return the Blender executable path, or None if not found."""
    # 1. env KIT_BLENDER
    v = os.environ.get("KIT_BLENDER")
    if v and os.path.isfile(v):
        return v

    # 2. env BLENDER
    v = os.environ.get("BLENDER")
    if v and os.path.isfile(v):
        return v

    # 3. the OS's install folders
    v = _os_scan()
    if v:
        return v

    # 4. PATH
    return shutil.which("blender") or None


def _os_scan():
    """the OS's usual install folders, newest version first -> a path or None"""
    platform = sys.platform
    if platform == "win32":
        local_data = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
        for base in (
            "C:/Program Files/Blender Foundation",
            os.path.join(local_data, "Programs", "Blender Foundation"),
        ):
            hit = _newest_glob(os.path.join(base, "Blender *", "blender.exe"))
            if hit:
                return hit
    elif platform == "darwin":
        home = os.path.expanduser("~")
        for candidate in (
            "/Applications/Blender.app/Contents/MacOS/Blender",
            home + "/Applications/Blender.app/Contents/MacOS/Blender",
        ):
            if os.path.isfile(candidate):
                return candidate
    else:
        # Linux / other
        for candidate in ("/usr/bin/blender", "/usr/local/bin/blender", "/snap/bin/blender"):
            if os.path.isfile(candidate):
                return candidate
        hit = _newest_glob("/opt/blender*/blender")
        if hit:
            return hit

    return None
