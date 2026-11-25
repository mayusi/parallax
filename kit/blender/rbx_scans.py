"""rbx_scans.py — scanned PBR materials for a.material(..., scan="Metal008") (kit-owned code).

Real surfaces have real variation: a scanned material's colour mottling, its roughness patches, its scratches and
grain. The kit keeps the owner-approved scans (ambientCG, CC0: VETLOG.md) in ~/.cache/roblox-kit/materials/<ID>/
(KIT_MATERIALS overrides), pinned in pins.json (file, size, sha256, the tile's real size when ambientCG lists it).
This module finds a scan's maps and measures, once, its average colour (linear, as a.material's `color` is) and its
average roughness — so a material can keep the scan's VARIATION while taking the build's own colour and roughness:
tint = color / average colour; roughness = rough + (scan roughness - its average).
No bpy at import: kit/test/python/test_scans.py runs find() and the arithmetic as plain python.
"""

import json
import os

ROOT = os.environ.get("KIT_MATERIALS") or os.path.join(os.path.expanduser("~"), ".cache", "roblox-kit", "materials")
MAPS = {"color": "Color", "rough": "Roughness", "height": "Displacement", "normal": "NormalGL", "metal": "Metalness"}
DEFAULT_TILE_M = 1.0  # a scan with no listed size covers about a metre


class ScanMissing(LookupError):
    """(LookupError, not KeyError: a KeyError prints its message through repr, escaping it)"""


def _pins(root=None):
    path = os.path.join(root or ROOT, "pins.json")
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def available(root=None):
    return sorted(_pins(root))


def find(scan, root=None):
    """-> {"id", "maps": {kind: path}, "tile_m": metres one repeat covers}; ScanMissing if it is not in the cache"""
    root = root or ROOT
    pins = _pins(root)
    if scan not in pins:
        have = ", ".join(sorted(pins)) or "none (no scans fetched)"
        raise ScanMissing(f'scan "{scan}" is not in {root} — available: {have}. A new scan is a download: vet it '
                          f"and get the owner's OK on the exact file (VETLOG.md)")
    folder = os.path.join(root, scan)
    maps = {}
    for kind, suffix in MAPS.items():
        hits = [n for n in pins[scan].get("maps", []) if n.rsplit(".", 1)[0].endswith("_" + suffix)]
        if hits and os.path.isfile(os.path.join(folder, hits[0])):
            maps[kind] = os.path.join(folder, hits[0])
    if "color" not in maps:
        raise ScanMissing(f'scan "{scan}" has no colour map in {folder}')
    tile = pins[scan].get("tile_cm")
    tile_m = (max(tile) / 100.0) if tile else DEFAULT_TILE_M
    return {"id": scan, "maps": maps, "tile_m": tile_m, "folder": folder}


def srgb_to_linear(c):
    """one sRGB value (0..1) -> linear"""
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def tint(color, mean_linear):
    """the multiply that moves a scan's average colour onto `color` (linear RGB), each channel within 0..4"""
    return tuple(min(4.0, max(0.0, c / max(m, 1e-4))) for c, m in zip(color, mean_linear))


def stats(scan, measure, root=None):
    """{"mean_color": linear RGB, "mean_rough": 0..1} — measured once by `measure(path, srgb)` -> mean per channel,
    then kept beside the maps (kit_stats.json) so every build reads the same numbers"""
    s = find(scan, root)
    path = os.path.join(s["folder"], "kit_stats.json")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    out = {"mean_color": [round(v, 5) for v in measure(s["maps"]["color"], True)[:3]]}
    if "rough" in s["maps"]:
        out["mean_rough"] = round(measure(s["maps"]["rough"], False)[0], 5)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    return out
