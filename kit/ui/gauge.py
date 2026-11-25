"""gauge.py — an ornate gauge HUD from one small spec: a rendered plate, its live cells laid over the plate's wells
(from the render's anchors), an emblem, a pip row, a name — written out as a normal screen spec for kit ui.

    python kit/ui/gauge.py <Screen> [--specs assets/ui]

assets/ui/<Screen>.gauge.json:
{
  "identity": "action", "quality": "hero", "kind": "hud",
  "plate": "gauge_gear",                       // assets/ui/art/<identity>/<plate>.png + .anchors.json (kit ui render)
  "plate_width": 1180,                         // on-screen width of the plate at 1080p (the height follows)
  "at": [150, 40],                             // the plate's top-left on screen
  "fills": [9, 4],                             // live cells per row (<= the anchors' cells); the rest stay empty
  "fill": "hp", "fill_empty": null,            // tokens: the lit cell colour; an unlit cell colour or null (bare well)
  "cells": {"art_lit": "cell_lit", "art_unlit": "cell_unlit"},   // or RENDERED cells (kit ui render "gem" items), stretched over the wells
  "emblem": {"art": "emblem_gear", "size": 300, "at": [-40, -60]},   // relative to the plate's top-left
  "pips": {"art": "pip_claw", "count": 10, "lit": 4, "size": [40, 48], "gap": 6, "at": [200, 236], "unlit_alpha": 0.5},
  // or lit and unlit as their own pictures: "pips": {"art_lit": "pearl_lit", "art_unlit": "pearl_unlit", "count": 9, "lit": 5, ...}
  // or a traced strip: "pips": {"strip": "t_pips_gear"} (the reference's own pip row, lit state baked in)
  // "from_trace": true — every piece traced with kit ui trace carries its box in the picture: the emblem, the
  //   pips strip and the name are then placed where the picture has them, relative to the plate, at the plate's
  //   on-screen scale (plate_width / the plate's box width). That is the 1:1 layout.
  "name": {"text": "SWIFT", "font": "GrenzeGotisch", "size": 44, "color": "danger", "at": [250, -8]},
  "scale": {"phone": 0.55, "tablet": 0.8}, "focus": "Hud.Plate.Emblem"
}
Every cell is a slant plate tinted with the fill token (so Ui.bar-style scripts can light them: Hud.Plate.Row0.C3).
"""
import argparse
import json
import os
import sys


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--specs", default="assets/ui")
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    gpath = os.path.join(a.specs, f"{a.name}.gauge.json")
    if not os.path.isfile(gpath):
        print(json.dumps({"schema": 1, "status": "fail", "summary": f"no {gpath}", "next_action": "write it (the shape: top of kit/ui/gauge.py)"}))
        return 1
    g = load(gpath)
    ident = g.get("identity")
    art_dir = os.path.join(a.specs, "art", ident or "")
    plate = g["plate"]
    anchors_path = os.path.join(art_dir, f"{plate}.anchors.json")
    if not os.path.isfile(anchors_path):
        print(json.dumps({"schema": 1, "status": "fail", "summary": f"no anchors for {plate}", "next_action": f"lune run kit ui render {ident}/{plate}   (a gauge item writes {plate}.anchors.json)"}))
        return 1
    an = load(anchors_path)
    pw, ph = an["size"]
    width = float(g.get("plate_width", 1180))
    # the traced layout: pieces placed by their boxes in the reference picture, relative to the plate's box
    from_trace = bool(g.get("from_trace"))
    plate_trace = load(os.path.join(art_dir, f"{plate}.trace.json")) if os.path.isfile(os.path.join(art_dir, f"{plate}.trace.json")) else None
    em = g.get("emblem")
    if from_trace and plate_trace and g.get("crest_width") and em and em.get("art"):
        # the MEASURED crest sets the scale (crest_width = the real HUD's crest in screen px, from REFS.md), so a
        # gallery sheet's zoom never decides how big the gauge is
        em_trace = os.path.join(art_dir, f"{em['art']}.trace.json")
        if os.path.isfile(em_trace):
            width = plate_trace["box"][2] * float(g["crest_width"]) / load(em_trace)["box"][2]
    k = width / pw
    height = round(ph * k)
    ox, oy = g.get("at", [150, 40])
    kref = None
    if from_trace and plate_trace:
        kref = width / plate_trace["box"][2]  # screen px per reference px

    def placed(piece, default_at, default_size, nudge=None):
        """where a traced piece sits relative to the plate (screen px), and its on-screen size; `nudge` = [dx, dy]
        screen px added to the traced place (for a crop that put one piece onto another)"""
        tr_path = os.path.join(art_dir, f"{piece}.trace.json")
        if kref and os.path.isfile(tr_path):
            tr = load(tr_path)
            bx, by, bw, bh = tr["box"]
            px, py = plate_trace["box"][0], plate_trace["box"][1]
            dx, dy = nudge or [0, 0]
            return [round((bx - px) * kref) + dx, round((by - py) * kref) + dy], [round(bw * kref), round(bh * kref)]
        return default_at, default_size
    fill = g.get("fill", "hp")
    fill_empty = g.get("fill_empty")
    fills = g.get("fills", [])
    kids = []
    # the plate itself, then each row's cells over its wells
    kids.append({"type": "image", "name": "Art", "image": f"art:{ident}/{plate}", "fit": "stretch", "size": [round(width), height], "pos": [0, 0], "z": 1,
                 "motion": {"enter": {"type": "sweep", "duration": 0.35}}})
    for r, row in enumerate(an["rows"]):
        lit = fills[r] if r < len(fills) else len(row["cells"])
        cells = []
        for c, cell in enumerate(row["cells"]):
            colour = fill if c < lit else fill_empty
            cw_, ch_ = round(cell["w"] * k), round(cell["h"] * k)
            inset = max(1, round(ch_ * 0.14))
            gem_art = g.get("cells", {}).get("art_lit" if c < lit else "art_unlit") if isinstance(g.get("cells"), dict) else None
            gem_anchor = os.path.join(art_dir, f"{gem_art}.anchors.json") if gem_art else None
            if gem_art and os.path.isfile(gem_anchor):
                ga = load(gem_anchor)
                gr, gsz = ga["gem"], ga["size"]
                sx, sy = cw_ / gr["w"], ch_ / gr["h"]
                rot = float(cell.get("rot", 0) or 0)
                # the picture is placed by its centre so it can turn with the bar: the slab's centre = the well's centre
                wcx, wcy = cell["x"] * k + cw_ / 2, cell["y"] * k + ch_ / 2
                pcx = wcx + (gsz[0] / 2 - (gr["x"] + gr["w"] / 2)) * sx
                pcy = wcy + (gsz[1] / 2 - (gr["y"] + gr["h"] / 2)) * sy
                cells.append({"type": "image", "name": f"C{c + 1}", "image": f"art:{ident}/{gem_art}", "fit": "stretch",
                              "size": [round(gsz[0] * sx), round(gsz[1] * sy)], "anchor": "center",
                              "pos": [round(pcx), round(pcy)], "z": 3 if c < lit else 2, **({"rotation": rot} if rot else {}),
                              "motion": {"enter": "fade", **({"loop": {"type": "breathe", "speed": 0.9}} if c < lit else {})}})
                continue
            if colour is None:
                continue
            cell_art = os.path.join(art_dir, f"{plate}_cell.png")
            if os.path.isfile(cell_art):
                # a traced plate: the reference's own lit cell, stretched over the well (plus its frame)
                fr = round(an.get("cell_frame_px", 0) * k)
                cells.append({"type": "image", "name": f"C{c + 1}", "image": f"art:{ident}/{plate}_cell", "fit": "stretch",
                              "size": [cw_ + 2 * fr, ch_ + 2 * fr], "pos": [round(cell["x"] * k) - fr, round(cell["y"] * k) - fr], "z": 2,
                              "motion": {"enter": "fade"}})
                continue
            # a cell = a dark slant with a bright slant inset (the glassy slab with a dark edge); the bright one is
            # the node scripts tint (Hud.Plate.Row0.C3), the dark one its frame
            rot = float(cell.get("rot", 0) or 0)
            cells.append({"type": "plate", "name": f"C{c + 1}", "plate": "slant", "color": colour,
                          "size": [cw_, ch_], "anchor": "center", "pos": [round(cell["x"] * k + cw_ / 2), round(cell["y"] * k + ch_ / 2)], "z": 2,
                          **({"rotation": rot} if rot else {}), "motion": {"enter": "fade"},
                          "children": [
                              {"type": "plate", "name": "Edge", "plate": "slant", "color": "shadow", "imageAlpha": 0.55,
                               "size": ["100%", "100%"], "pos": [0, 0], "z": 1},
                              {"type": "plate", "name": "Glass", "plate": "slant", "color": colour,
                               "size": [cw_ - 2 * inset, ch_ - 2 * inset], "pos": [inset, inset], "z": 2},
                              {"type": "plate", "name": "Shine", "plate": "slant", "color": "text", "imageAlpha": 0.72,
                               "size": [cw_ - 2 * inset, max(1, round((ch_ - 2 * inset) * 0.38))], "pos": [inset, inset], "z": 3}]})
        kids.append({"type": "panel", "name": f"Row{r}", "size": [round(width), height], "pos": [0, 0], "z": 2,
                     "motion": {"stagger": 0.02}, "children": cells})
    if em:
        size = em.get("size", 300)
        at, sz = placed(em["art"], em.get("at", [-40, -60]), [size, size], em.get("nudge"))
        kids.append({"type": "image", "name": "Emblem", "image": f"art:{ident}/{em['art']}", "fit": "fit", "size": sz,
                     "pos": at, "z": 4, "motion": {"enter": {"type": "pop", "duration": 0.3}}})
    pp = g.get("pips")
    if pp and pp.get("art_lit") and pp.get("strip"):
        # live pips: the reference's own lit and unlit pip, `count` of them spread along the traced strip's box
        at, sz = placed(pp["strip"], pp.get("at", [200, 236]), pp.get("size", [600, 90]))
        n = int(pp.get("count", 10))
        lit = int(pp.get("lit", 0))
        pw_, ph_ = pp.get("pip_size", [round(sz[1] * 0.72), sz[1]])
        span = sz[0] - pw_
        pips = []
        for i in range(n):
            litp = i < lit
            art = pp["art_lit"] if litp else pp.get("art_unlit", pp["art_lit"])
            x_ = round(at[0] + (span * i / max(1, n - 1)) * float(pp.get("spread", 0.92)))
            pips.append({"type": "image", "name": f"P{i + 1}", "image": f"art:{ident}/{art}", "fit": "fit", "size": [pw_, ph_],
                         "pos": [x_, at[1]], "z": 3,
                         "motion": {"enter": {"type": "fade", "delay": 0.1 + i * 0.03}, **({"loop": {"type": "breathe", "speed": 1.3}} if litp else {})}})
        kids.append({"type": "panel", "name": "Pips", "size": [sz[0], sz[1]], "pos": [at[0], at[1]], "z": 3, "children": [
            {**p_, "pos": [p_["pos"][0] - at[0], 0]} for p_ in pips]})
    elif pp and pp.get("strip"):
        at, sz = placed(pp["strip"], pp.get("at", [200, 236]), pp.get("size", [600, 90]))
        kids.append({"type": "image", "name": "Pips", "image": f"art:{ident}/{pp['strip']}", "fit": "fit", "size": sz, "pos": at, "z": 3,
                     "motion": {"enter": {"type": "sweep", "delay": 0.1, "duration": 0.3}}})
    elif pp:
        w_, h_ = pp.get("size", [40, 48])
        gap = pp.get("gap", 6)
        x0, y0 = pp.get("at", [200, 236])
        pips = []
        for i in range(int(pp.get("count", 10))):
            litp = i < int(pp.get("lit", 0))
            own_unlit = (not litp) and pp.get("art_unlit")
            art = pp.get("art_lit", pp.get("art")) if litp else (pp["art_unlit"] if own_unlit else pp.get("art_lit", pp.get("art")))
            pips.append({"type": "image", "name": f"P{i + 1}", "image": f"art:{ident}/{art}", "fit": "fit", "size": [w_, h_],
                         "imageAlpha": 0.0 if (litp or own_unlit) else float(pp.get("unlit_alpha", 0.55)),
                         "imageColor": None if (litp or own_unlit) else pp.get("unlit_color", "line2"),
                         "motion": {"enter": "fade", **({"loop": {"type": "breathe", "speed": 1.3}} if litp else {})}})
        for p_ in pips:
            if p_["imageColor"] is None:
                del p_["imageColor"]
        kids.append({"type": "panel", "name": "Pips", "size": [int(pp.get("count", 10)) * (w_ + gap), h_], "pos": [x0, y0], "z": 3,
                     "layout": {"dir": "horizontal", "gap": gap, "align": "center", "justify": "start"},
                     "motion": {"stagger": 0.03}, "children": pips})
    nm = g.get("name")
    if nm and nm.get("art"):
        at, sz = placed(nm["art"], nm.get("at", [250, -8]), nm.get("size_px", [420, 56]), nm.get("nudge"))
        kids.append({"type": "image", "name": "Name", "image": f"art:{ident}/{nm['art']}", "fit": "fit", "size": sz, "pos": at, "z": 5,
                     "motion": {"enter": {"type": "slam", "duration": 0.22, "ease": "back"}}})
    elif nm:
        kids.append({"type": "label", "name": "Name", "text": nm["text"], "font": nm.get("font", "GrenzeGotisch"), "textSize": nm.get("size", 44),
                     "textColor": nm.get("color", "danger"), "textOutline": "shadow", "textOutlineWidth": 3, "rotation": nm.get("rot", -4),
                     "size": [nm.get("width", 420), nm.get("size", 44) + 12], "pos": nm.get("at", [250, -8]), "align": "left", "z": 5,
                     "motion": {"enter": {"type": "slam", "duration": 0.22, "ease": "back"}}})
    screen = {
        "name": a.name, "identity": ident, "quality": g.get("quality", "hero"), "focus": g.get("focus", "Hud.Plate.Emblem"),
        "kind": g.get("kind", "hud"), "enabled": False, "insets": g.get("insets", "core"), "scale": g.get("scale", {"phone": 0.55, "tablet": 0.8}),
        "generated_from": f"{a.name}.gauge.json (kit ui gauge — edit that, not this)",
        "root": {"type": "panel", "name": "Hud", "size": ["100%", "100%"], "children": [
            {"type": "panel", "name": "Plate", "size": [round(width), height], "pos": [ox, oy],
             "at": g.get("plate_at", {"phone": {"pos": [10, 20]}}), "motion": {"stagger": 0.04}, "children": kids}
        ]},
    }
    out = os.path.join(a.specs, f"{a.name}.json")
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(screen, fh, indent=1)
    cells_total = sum(len(r["cells"]) for r in an["rows"])
    print(json.dumps({"schema": 1, "status": "pass", "summary": f"{a.name}: gauge screen written from {plate} ({cells_total} wells, {sum(min(f, len(r['cells'])) for f, r in zip(fills, an['rows']))} lit)",
                      "next_action": f"lune run kit ui {a.name} --motion, then LOOK"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
