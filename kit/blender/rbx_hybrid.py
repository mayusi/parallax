"""rbx_hybrid.py — the BUILD side of the hybrid route (kit/gen/hybrid_fabricate.py): an AI part placed from the
route's manifest (build/hybrid/<asset>/hybrid.json), its quad game mesh with its dense skin as its high.

    import rbx_hybrid as H
    a = rbx.Asset("h9_hilt", ..., low=12000)               # the high-and-low route: the high bakes into the low
    a.cad("Guard", ...); a.cad("Grip", ...); a.cast("Hilt", ["Guard", "Grip"], "bronze", fillet_mm=2.0)
    H.ai_part(a, "h9_hilt", "Pommel", height=0.2, pos=(0, 0, 0), group="pommel")
    a.ornament("refs/h9/guard_scroll.png", at=(...), width=0.3, cut=True)

A part the manifest does not name as made (not fabricated yet, or not an AI part) is refused by name - the build
never falls back to a stand-in."""

import json
import os

import rbx


def manifest(asset):
    path = os.path.join(rbx.BUILD, "hybrid", asset, "hybrid.json")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"hybrid: no manifest for {asset} ({path}) - run python kit/gen/hybrid_fabricate.py "
                                f"{asset} --plate ... --part <Name>=x0,y0,x1,y1 first")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def ai_part(a, asset, name, **kw):
    """the AI part `name` from the manifest: a.import_mesh(<its quad low>, high=<its skin>, **kw) -> the part"""
    part = (manifest(asset).get("parts") or {}).get(name)
    if not part or part.get("route") != "ai_part" or not part.get("low"):
        raise ValueError(f"hybrid: {name} is not an AI part the manifest made for {asset} (its parts: "
                         f"{', '.join(sorted((manifest(asset).get('parts') or {})))})")
    return a.import_mesh(name, part["low"], high=part["high"], **kw)
