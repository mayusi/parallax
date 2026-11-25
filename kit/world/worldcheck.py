"""check.py — prove a world PLAYS, by numbers, in seconds (no Studio): `kit world check <Name|blueprint.json>`.

Reads build/worlds/<name>.json (parts with collide/class, terrain ground sampled by the compiler, objectives,
zones, player numbers, checks) and models an R6 character on a voxel grid:
  STANDABLE  a floor top with 5 studs of headroom over a 2x2 footprint
  MOVES      walk to a neighbour column (a rise up to `step`), climb a ledge up to `jump` (default 7.2 = the
             default JumpHeight), drop any height, gap-jump across open air up to `gap` studs (16 st/s for 0.54 s)
Gates (errors): a spawn that cannot reach another spawn or an objective; a TRAP (a reachable place from which no
  spawn can be reached again: a pit you fall into for good) of `trap_cells` or more.
  SCALE: with "scale": "<sheet>" (r6) every claim (stairs; a part's "fit"; the "fit" op) out of the rig's numbers
  (doors, steps, rails, sills, ceilings, alleys, streets, run walls, push-up walls, roof gaps) - SCALE_SHEETS.
  DESIGN: primitive-only generators (design_lint); the terrain ROUTE (terrain_route: land made by rivers or real
  elevation, proved by re-making the heightmap - the owner's SampleRegion_terrain_v1; "route_cache": false re-proves).
Warnings (next_action "improve ..."): unreachable walkable areas (a platform with no way up), spawn unfairness
  (path distance to the centre / objectives differs by more than `fair` %), cramped camera (where a third-person
  camera 12 studs back hits a wall within 4 studs, over `camera_pct` % of the reachable floor), too little open
  room for knockback (battlegrounds: share of floor with `open` studs to the nearest wall), exposure balance
  between spawns.
Sheet: build/worlds/checks/<name>.png — reachability (+ spawns, objectives, traps, unreachable), exposure (how
  much of the map sees each spot), camera clearance, open room for knockback, the sightline histogram.
blueprint "player": { "step": 1, "jump": 7.2, "gap": 8, "height": 5 } · "checks": { "open": 30, "fair": 15,
  "camera_pct": 20, "trap_cells": 12, "res": 1 } · "objectives": [{ "name": "Centre", "pos": [x, y, z] }]
"""

import hashlib
import json
import math
import os
import re
import sys

import numpy as np

PLAYER = {"step": 1.0, "jump": 7.2, "gap": 8.7, "height": 5.0, "eye": 4.5, "speed": 16.0}
CHECKS = {"open": 30.0, "fair": 15.0, "camera_pct": 20.0, "trap_cells": 12, "res": 1.0, "unreachable_cells": 30, "exposure_points": 700,
          "landmark_pct": 70.0, "pacing_s": 60.0,
          "route_cache": True}


# ------------------------------------------------------------------ scale sheets (a piece out of scale FAILS)
# A blueprint's "scale": "<sheet>" holds every claim (the "fits": stairs claim themselves, a part's "fit": "<kind>", the
# "fit" op) to the rig's numbers. Ranges are [min, max] studs (None = no limit). Alleys, streets and run walls are also
# MEASURED in the voxel grid (the free span across them / a flush face), not only taken at their word.
# r6: the owner's R6 rig (5 tall, 2 wide), JumpHeight 7.2 + one air hike (Power 1.0) at the 28 studs/s test pace:
# 0.92 s in the air over a level gap = 25.9 studs; roof gaps <= 20 keep a margin (round 8 W4, 2026-10-29).
SCALE_SHEETS = {
    "r6": {
        "door": {"w": (4.5, 6.0), "h": (7.5, 9.0)},  # a house door: the body + a hand of headroom, never a barn gate
        "gate": {"w": (8.0, None), "h": (12.0, None)},  # a grand entrance (cathedral, hall): claimed as one, on purpose
        "room": {"h": (12.0, 14.0)},  # a storey's clear ceiling height
        "step": {"rise": (0.9, 1.1), "run": (1.8, 2.5), "width": (4.0, None)},
        "rail": {"h": (2.8, 3.4)},  # a parapet / balustrade top over its floor
        "sill": {"h": (3.2, 3.8)},  # a window's sill over its floor
        "alley": {"w": (8.0, None)},
        "street": {"w": (30.0, None)},  # room for the 30-100 studs/s run
        "runwall": {"len": (40.0, None), "h": (10.0, None)},  # Config.WallRun.MinWallHeight 8 + margin; flush (measured)
        "pushwall": {"h": (18.0, 24.0)},  # the wall push-ups: 3 leg pushes of ~7 studs
        "roofgap": {"gap": (2.0, 20.0)},  # jumpable with the air hike; under 2 is a crack to fall in
        # what the GENERATORS claim for themselves (building floors, room ceilings, their doorways): a floor above at
        # least 12 clear (the 5-stud rig + its 7.2 jump; Vaelmouth's 11-stud storeys were "a room a head too low"),
        # a doorway at least a house door - minimums only: the owner wants it "big, bigger than the rigs"
        "ceiling": {"h": (12.0, None)},
        "opening": {"w": (4.5, None), "h": (7.5, None)},
        # LIMITATIONS_FIXES_V3.md stage A.2 (the physical scale, 1 stud = 0.28 m): a cottage's frontage and depth from
        # 23 studs (a house you walk into, not a shed); a MAIN street 29..43 wide (measured like a street: wider is a
        # square, narrower a lane); and LAMPS BY PLACE (stage C: "Avenues ~110 st alternating; Lanes junctions / doors
        # only; Squares corners only - killing 'a lamp everywhere'") - an avenue's lamps 90..130 apart along it, each
        # on the other side from the last; a lane's within "lane" studs of a junction or a door it names ("at"); a
        # square's within "square" studs of one of its corners
        "exterior": {"w": (23.0, None), "d": (23.0, None)},
        "mainstreet": {"w": (29.0, 43.0)},
        "lamp_spacing": {"avenue": (90.0, 130.0), "lane": (None, 12.0), "square": (None, 15.0)},
    },
}
LAMP_PLACES = ("avenue", "lane", "square")
LAMP_SIDE = 20.0  # studs from an avenue's or a lane's centre line within which a lamp is that street's


def _within(v, rng):
    lo, hi = rng
    return v is not None and (lo is None or v >= lo - 1e-6) and (hi is None or v <= hi + 1e-6)


def _span(g, x, y, z, ax, cap=240.0):
    """the free run (studs) across the point along axis ax (0 = x, 2 = z) in the body band (1..5 over y)"""
    res = g.res
    iy0 = int(np.floor((y + 1 - g.lo[1]) / res))
    iy1 = max(iy0 + 1, int(np.ceil((y + 5 - g.lo[1]) / res)))
    total = 0.0
    for sgn in (-1, 1):
        d = res / 2
        while d < cap:
            pt = [x, y, z]
            pt[ax] += sgn * d
            i = g.index(pt)
            if not (0 <= i[0] < g.n[0] and 0 <= i[2] < g.n[2]):
                return None  # off the map: open, not a lane
            if g.occ[i[0], max(0, iy0):min(g.n[1], iy1), i[2]].any():
                break
            d += res
        if d >= cap:
            return None
        total += d - res / 2  # (the face lies between the last free sample and the first solid one: the midpoint)
    return total


# ---- a lane that runs on neither axis (2026-11-13: a turned house, a bent street). The voxel march above walks one
# world axis: across a lane typed at 45 degrees it read the lane 1.4 times too wide, and a 6-stud lane passed as 8.
# An OBLIQUE lane is measured ACROSS itself on what stands there, each kind of thing by its own shape:
#   - an upright box (a wall, a post, a slab: nearly every part) by where the line meets it, exactly - whatever its
#     height in the body band, however thin;
#   - any other part (a ball, a cylinder, a wedge, a tilted box) and a terrain solid by the same solid test the
#     voxels are filled by (part_inside), marched 0.25 along the line at 16 heights of the band, then to the face;
#   - the land by its own heights (where it stands higher than the voxels' first body cell would be solid);
#   - a scanned mesh by its voxels (its real shape is only in them), to the near side of the first solid cell: up to
#     a cell NARROW, never wide.
# The lane is as wide as the nearest of these on each side. (A fresh reader, 2026-11-13: the first version read three
# heights and missed a bench between them; it let the voxels speak only when 2 cells short and so missed a low bank.)
OBLIQUE_STEP = 0.25  # studs: the march along the line for what is not an upright box
_BODY = (1.0, 5.0)  # over the lane's floor: the band the voxel march reads
_BODY_HEIGHTS = tuple(_BODY[0] + 0.125 + 0.25 * i for i in range(16))


def _is_oblique(dx, dz, eps=1e-6):
    return abs(dx) > eps and abs(dz) > eps


def _upright_box(q):
    r = q.get("rot")
    return (q.get("class") != "WedgePart" and (q.get("shape") or "Block") == "Block"
            and (r is None or abs(abs(r[1][1]) - 1.0) < 1e-9))


class Lane:
    """what a slanted lane is measured against: made once a world (scale_check), or by hand in a test"""

    def __init__(self, parts, grounds=(), terrain_solids=(), grid=None):
        solid = [q for q in parts if is_solid(q) and not q.get("backdrop")]
        mesh = [q for q in solid if q.get("_points") is not None]
        boxed = [q for q in solid if q.get("_points") is None]
        for op in terrain_solids:  # (the terrain's own balls, cylinders and blocks: shapes like any part's)
            if op["kind"] == "sdf":  # (sdf land is in the voxels a lane's march reads, when it has a grid; no box)
                continue
            sp, c = op["spec"], op["spec"]["center"]
            if op["kind"] == "ball":
                boxed.append({"pos": c, "size": [2 * sp["radius"]] * 3, "shape": "Ball"})
            elif op["kind"] == "cylinder":  # (upright: its own X is the world's Y)
                boxed.append({"pos": c, "size": [sp["height"], 2 * sp["radius"], 2 * sp["radius"]], "shape": "Cylinder",
                              "rot": [[0, -1, 0], [1, 0, 0], [0, 0, 1]]})
            elif op["kind"] == "block":
                boxed.append({"pos": c, "size": sp["size"]})
        self.boxes = [q for q in boxed if _upright_box(q)]
        self.others = [q for q in boxed if not _upright_box(q)]
        self.other_boxes = _solid_boxes(self.others)
        self.every = self.boxes + self.others  # (run_on asks every part by its own shape)
        self.every_boxes = _solid_boxes(self.every)
        if self.boxes:
            self.c = np.array([q["pos"] for q in self.boxes], float)
            self.h = np.array([q["size"] for q in self.boxes], float) / 2
            rots = np.array([q.get("rot") or [[1, 0, 0], [0, 1, 0], [0, 0, 1]] for q in self.boxes], float)
            # a part's own X and Z on the ground (world = R * local: the columns of R)
            self.ax = rots[:, [0, 2], 0]
            self.az = rots[:, [0, 2], 2]
        self.grounds = [gr for gr in grounds if not gr.get("backdrop")]
        self.res = float(grid.res) if grid is not None else 1.0
        self.mesh = None
        if grid is not None and mesh:
            self.mesh = Grid.__new__(Grid)
            self.mesh.res, self.mesh.lo, self.mesh.n = grid.res, grid.lo, grid.n
            self.mesh.occ = np.zeros_like(grid.occ)
            for q in mesh:
                self.mesh.fill_part(q)

    # -- upright boxes: where the line meets each, exactly
    def _boxes_run(self, x, y, z, ux, uz, cap):
        if not self.boxes:
            return None
        in_band = (self.c[:, 1] + self.h[:, 1] > y + _BODY[0] + 1e-9) & (self.c[:, 1] - self.h[:, 1] < y + _BODY[1] - 1e-9)
        if not in_band.any():
            return None
        o = np.array([x, z]) - self.c[:, [0, 2]]
        d = np.array([ux, uz])
        best = np.full(len(self.boxes), np.inf)
        lo_t = np.full(len(self.boxes), -np.inf)
        hi_t = np.full(len(self.boxes), np.inf)
        miss = ~in_band
        for axis, half in ((self.ax, self.h[:, 0]), (self.az, self.h[:, 2])):
            oo = np.einsum("ij,ij->i", o, axis)
            dd = axis @ d
            flat = np.abs(dd) < 1e-12
            miss |= flat & (np.abs(oo) > half)
            safe = np.where(flat, 1.0, dd)
            t1, t2 = (-half - oo) / safe, (half - oo) / safe
            lo_t = np.where(flat, lo_t, np.maximum(lo_t, np.minimum(t1, t2)))
            hi_t = np.where(flat, hi_t, np.minimum(hi_t, np.maximum(t1, t2)))
        hit = ~miss & (hi_t >= np.maximum(lo_t, 0.0))
        best[hit] = np.maximum(lo_t[hit], 0.0)
        t = float(best.min())
        return t if t <= cap else None

    # -- everything marched: the other parts, the land
    def _marched_run(self, x, y, z, ux, uz, cap):
        lo, hi = self.other_boxes
        cand = []
        if len(self.others):
            ex, ez = x + ux * cap, z + uz * cap
            near = ((hi[:, 0] >= min(x, ex) - 0.5) & (lo[:, 0] <= max(x, ex) + 0.5) & (hi[:, 2] >= min(z, ez) - 0.5)
                    & (lo[:, 2] <= max(z, ez) + 0.5) & (hi[:, 1] >= y + _BODY[0]) & (lo[:, 1] <= y + _BODY[1]))
            cand = [self.others[i] for i in np.nonzero(near)[0]]
        if not cand and not self.grounds:
            return None
        land_at = y + _BODY[0] + self.res / 2  # (the voxels' first body cell is solid where the land reaches its middle)

        def blocked(ts):
            ts = np.atleast_1d(np.asarray(ts, float))
            out = np.zeros(len(ts), bool)
            if cand:
                pts = np.concatenate([np.stack([x + ux * ts, np.full(len(ts), y + h), z + uz * ts], axis=1) for h in _BODY_HEIGHTS])
                m = np.zeros(len(pts), bool)
                for q in cand:
                    m |= part_inside(q, pts)
                out |= m.reshape(len(_BODY_HEIGHTS), len(ts)).any(axis=0)
            for gr in self.grounds:
                out |= _ground_height(gr, x + ux * ts, z + uz * ts) >= land_at
            return out

        ts = np.arange(0.0, cap + OBLIQUE_STEP, OBLIQUE_STEP)
        for i in range(0, len(ts), 128):
            chunk = ts[i:i + 128]
            hit = np.nonzero(blocked(chunk))[0]
            if len(hit):
                k = i + int(hit[0])
                if k == 0:
                    return 0.0  # (the claim's own line is inside something)
                a, b = ts[k - 1], ts[k]
                for _ in range(36):  # (to the face itself: `a` is free, `b` is inside)
                    mid = (a + b) / 2
                    if blocked(mid)[0]:
                        b = mid
                    else:
                        a = mid
                return float(b)  # (never short of the face: a lane exactly as wide as the sheet asks is not "narrow")
        return None

    # -- a scanned mesh: its voxels, to the near side of the first solid cell
    def _mesh_run(self, x, y, z, ux, uz, cap):
        g = self.mesh
        if g is None:
            return None
        res = g.res
        iy0 = int(np.floor((y + _BODY[0] - g.lo[1]) / res))
        iy1 = max(iy0 + 1, int(np.ceil((y + _BODY[1] - g.lo[1]) / res)))
        d = 0.0
        while d < cap:
            i = g.index([x + ux * d, y, z + uz * d])
            if not (0 <= i[0] < g.n[0] and 0 <= i[2] < g.n[2]):
                return None
            if g.occ[i[0], max(0, iy0):min(g.n[1], iy1), i[2]].any():
                # where the line enters that cell
                enter = 0.0
                for u, o, lo_c in ((ux, x, g.lo[0] + i[0] * res), (uz, z, g.lo[2] + i[2] * res)):
                    if abs(u) > 1e-12:
                        enter = max(enter, min((lo_c - o) / u, (lo_c + res - o) / u))
                return max(0.0, min(enter, d))
            d += res / 4
        return None

    def run(self, x, y, z, ux, uz, cap=240.0):
        """how far a body gets from (x, y, z) along the unit direction (ux, uz) before something solid; None = open"""
        found = [t for t in (self._boxes_run(x, y, z, ux, uz, cap), self._marched_run(x, y, z, ux, uz, cap),
                             self._mesh_run(x, y, z, ux, uz, cap)) if t is not None]
        return min(found) if found else None

    def run_on(self, x, y, z, ux, uz, climb=0.0, cap=64.0, step=0.25):
        """how far a body gets from (x, y, z) along the unit direction (ux, uz) on a floor that is a PLANE - it
        climbs `climb` studs for every stud that way - before something solid; None = open within `cap`.
        Every part is asked by its own shape (part_inside) in the body band over the floor WHERE THE BODY IS, marched
        `step` and then to the face. (run() holds one height: across a hill it read the uphill ground, a kerb and
        a spawn pad as walls, and stood clear of what is low on the downhill side.)"""
        ex, ez = x + ux * cap, z + uz * cap
        cand = []
        if self.every:
            lo, hi = self.every_boxes
            y0, y1 = y + min(0.0, climb * cap) + _BODY[0], y + max(0.0, climb * cap) + _BODY[1]
            near = ((hi[:, 0] >= min(x, ex) - 0.5) & (lo[:, 0] <= max(x, ex) + 0.5) & (hi[:, 2] >= min(z, ez) - 0.5)
                    & (lo[:, 2] <= max(z, ez) + 0.5) & (hi[:, 1] >= y0) & (lo[:, 1] <= y1))
            cand = [self.every[i] for i in np.nonzero(near)[0]]

        def blocked(ts):
            ts = np.atleast_1d(np.asarray(ts, float))
            out = np.zeros(len(ts), bool)
            if cand:
                pts = np.concatenate([np.stack([x + ux * ts, y + climb * ts + h, z + uz * ts], axis=1) for h in _BODY_HEIGHTS])
                m = np.zeros(len(pts), bool)
                for q in cand:
                    m |= part_inside(q, pts)
                out |= m.reshape(len(_BODY_HEIGHTS), len(ts)).any(axis=0)
            for gr in self.grounds:
                out |= _ground_height(gr, x + ux * ts, z + uz * ts) >= y + climb * ts + _BODY[0] + self.res / 2
            return out

        found = []
        if cand or self.grounds:
            ts = np.arange(0.0, cap + step, step)
            hit = np.nonzero(blocked(ts))[0]
            if len(hit):
                k = int(hit[0])
                if k == 0:
                    return 0.0  # (the claim's own line is inside something)
                a, b = ts[k - 1], ts[k]
                for _ in range(24):  # (to the face itself: `a` is free, `b` is inside)
                    mid = (a + b) / 2
                    if blocked(mid)[0]:
                        b = mid
                    else:
                        a = mid
                found.append((a + b) / 2)
        mesh = self._mesh_run(x, y, z, ux, uz, cap)
        if mesh is not None:
            found.append(mesh)
        return min(found) if found else None

    def span(self, x, y, z, ux, uz, cap=240.0):
        """the free run ACROSS (x, y, z) along +-(ux, uz): the two faces' distance, or None when a side is open"""
        total = 0.0
        for sgn in (-1, 1):
            t = self.run(x, y, z, sgn * ux, sgn * uz, cap)
            if t is None:
                return None
            total += t
        return total

    def proud(self, pts):
        """is any of these points inside something solid? (a turned run wall's face, asked of everything)"""
        pts = np.asarray(pts, float)
        every = self.boxes + self.others
        if every:
            lo, hi = _solid_boxes(every)
            near = np.all(hi >= pts.min(axis=0) - 0.5, axis=1) & np.all(lo <= pts.max(axis=0) + 0.5, axis=1)
            if any(part_inside(every[k], pts).any() for k in np.nonzero(near)[0]):
                return True
        for gr in self.grounds:
            if (_ground_height(gr, pts[:, 0], pts[:, 2]) >= pts[:, 1]).any():
                return True
        if self.mesh is not None:
            g = self.mesh
            idx = np.floor((pts - g.lo) / g.res).astype(int)
            ok = np.all((idx >= 0) & (idx < g.n), axis=1)
            if ok.any() and g.occ[idx[ok, 0], idx[ok, 1], idx[ok, 2]].any():
                return True
        return False


def _ground_height(gr, xs, zs):
    """a ground op's height at world points (bilinear, as the voxels are filled); -inf off its edge"""
    hx = np.array(gr["heights"], dtype=float).reshape(gr["nx"], gr["nz"])
    fx = (np.asarray(xs, float) - gr["x0"]) / gr["step"]
    fz = (np.asarray(zs, float) - gr["z0"]) / gr["step"]
    ok = (fx >= 0) & (fx <= gr["nx"] - 1) & (fz >= 0) & (fz <= gr["nz"] - 1)
    x0 = np.clip(np.floor(fx).astype(int), 0, max(gr["nx"] - 2, 0))
    z0 = np.clip(np.floor(fz).astype(int), 0, max(gr["nz"] - 2, 0))
    x1, z1 = np.minimum(x0 + 1, gr["nx"] - 1), np.minimum(z0 + 1, gr["nz"] - 1)
    tx, tz = np.clip(fx - x0, 0, 1), np.clip(fz - z0, 0, 1)
    h = hx[x0, z0] * (1 - tx) * (1 - tz) + hx[x1, z0] * tx * (1 - tz) + hx[x0, z1] * (1 - tx) * tz + hx[x1, z1] * tx * tz
    return np.where(ok, h, -np.inf)


def _solid_boxes(solids):
    if not solids:
        return np.zeros((0, 3)), np.zeros((0, 3))
    los, his = zip(*(part_aabb(q) for q in solids))
    return np.array(los), np.array(his)


def _lane_of(w, g):
    terr = w.get("terrain") or {}
    return Lane(w.get("parts") or [], terr.get("ground") or [], terr.get("solids") or [], g)


def scale_check(w, g):
    """[errors], {stats}: every claim against the sheet; alleys / streets / run walls measured too"""
    name = w.get("scale")
    fits = w.get("fits") or []
    if not name:
        return [], {}
    sheet = SCALE_SHEETS.get(name)
    if sheet is None:
        return [f'scale: no sheet "{name}" (known: {", ".join(SCALE_SHEETS)})'], {}
    errors, counts = [], {}
    lane = None  # (made once, for the first lane or run wall that runs on neither axis)
    for f in fits:
        kind = f.get("kind")
        rule = sheet.get(kind)
        label = f'{kind} "{f.get("name") or "?"}" at ({f["pos"][0]:.0f}, {f["pos"][2]:.0f})'
        if rule is None:
            errors.append(f"scale: {label}: no {name} rule for a {kind} (known: {', '.join(sheet)})")
            continue
        if kind not in ("alley", "street", "mainstreet") and (f.get("ground") is not None or f.get("cross") is not None):
            errors.append(f'scale: {label}: "ground" / "cross" are an alley\'s or a street\'s (a {kind} has one height: pos)')
            continue
        counts[kind] = counts.get(kind, 0) + 1
        size = f.get("size") or [None, None, None]
        got = {}
        if kind in ("door", "gate", "opening"):
            got = {"w": size[0], "h": size[1]}
        elif kind in ("room", "rail", "pushwall", "ceiling"):
            got = {"h": size[1]}
        elif kind == "sill":
            got = {"h": f.get("sill", size[1])}
        elif kind == "step":
            got = {"rise": f.get("rise"), "run": f.get("run"), "width": f.get("width")}
        elif kind == "runwall":
            got = {"len": max(size[0], size[2]), "h": size[1]}
        elif kind == "roofgap":
            a, b = f.get("from"), f.get("to")
            got = {"gap": math.dist(a, b) if a and b else size[0]}
        elif kind == "lamp_spacing":
            errors.extend(f"scale: {label}: {why}" for why in lamp_spacing(w, f, rule))
            continue
        elif kind == "exterior":
            got = {"w": size[0], "d": size[2]}
        elif kind in ("alley", "street", "mainstreet"):
            a, b = f.get("from"), f.get("to")
            if not (a and b):
                errors.append(f"scale: {label}: an {kind} claim needs from / to (its centre line)")
                continue
            ax = 2 if abs(b[0] - a[0]) >= abs(b[1] - a[1]) else 0  # measure across the line
            # a sample at every stud along the line. (One every 8 studs - the first way - read a street as wide as
            # it is BETWEEN the samples: a lamp post, a stall leg, two posts face to face in a 32-stud street stood
            # unseen unless a sample fell on them: card mkmc, where a town passed or failed by where its posts fell.)
            oblique = _is_oblique(b[0] - a[0], b[1] - a[1])
            # (a lane on neither axis is read by a line a hair wide at each sample: four lines a stud, so a post
            # half a stud thick always stands on one; on an axis and on a slope a sample reads a whole stud)
            n = max(2, int(math.ceil(math.dist(a, b) * (4 if oblique else 1))) + 1)
            spans = []
            # a street on SLOPING ground says its floor: "ground": [its height at from, at to] and, where the hill
            # also climbs ACROSS the street, "cross": studs up for every stud to the street's left (from -> to seen
            # from above, +x east and +z south: the side (-(dz), dx)). Its body band (1..5 studs over the floor)
            # then follows the floor's plane, point by point. Without it the band stands over ONE height (pos[1]):
            # on a climbing street the ground itself came into the band and the street read 0 studs wide, and a
            # claim lifted clear of the ground let anything low at its downhill end hide.
            ground, cross = f.get("ground"), f.get("cross")

            def number(v):
                return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)

            sloped = isinstance(ground, (list, tuple)) and len(ground) == 2 and all(number(v) for v in ground)
            if ground is not None and not sloped:
                errors.append(f'scale: {label}: "ground" is the floor\'s height at from and at to: two numbers')
                continue
            if cross is not None and not (sloped and number(cross)):
                errors.append(f'scale: {label}: "cross" is one number (the floor\'s climb across the street), with "ground"')
                continue
            length = math.dist(a, b)
            if sloped and length < 1e-6:
                errors.append(f"scale: {label}: from and to are one point: a claim on sloping ground needs a line")
                continue
            if oblique or sloped:
                lane = lane or _lane_of(w, g)
                ux, uz = -(b[1] - a[1]) / length, (b[0] - a[0]) / length  # (across the line)
            for k in range(n):
                t = k / (n - 1)
                px, pz = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
                if sloped:
                    # every part by its own shape, over the floor's plane, in a COLUMN a stud wide along the
                    # street - the very column of cells the march reads at this sample on level ground (a line a
                    # hair wide missed a lamp post beside the sample, and two posts not quite opposite each other
                    # read as one side open): five probes across the stud the sample stands in
                    ax_, az_ = (b[0] - a[0]) / length, (b[1] - a[1]) / length  # (along the street)
                    here = px * ax_ + pz * az_  # (how far along, from the world's origin)
                    start = math.floor(here + 1e-9)
                    sides = []
                    for sgn in (-1, 1):
                        runs = []
                        for step in (0.0, 0.25, 0.5, 0.75):  # (the stud's far edge is the next sample's first probe)
                            off = start + step - here
                            tt = t + off / length
                            r = lane.run_on(px + ax_ * off, ground[0] + (ground[1] - ground[0]) * tt, pz + az_ * off,
                                            sgn * ux, sgn * uz, sgn * (cross or 0.0))
                            if r is not None:
                                runs.append(r)
                        sides.append(min(runs) if runs else None)
                    sp = None if None in sides else sides[0] + sides[1]
                elif oblique:
                    sp = lane.span(px, f["pos"][1], pz, ux, uz)
                else:
                    sp = _span(g, px, f["pos"][1], pz, ax)
                if sp is not None:
                    spans.append(sp)
            got = {"w": min(spans) if spans else None}
            if not spans:
                errors.append(f"scale: {label}: no walls either side to measure (is it a lane?)")
                continue
        bad = [f"{k} {got.get(k) if got.get(k) is None else round(got[k], 2)} (wants {r[0]}..{'' if r[1] is None else r[1]})"
               for k, r in rule.items() if not _within(got.get(k), r)]
        if kind == "runwall" and not bad:
            # flush: one long face free of anything proud for its whole length, 2..h-1 up (a ray-run catches on a bump)
            ax = 0 if size[0] >= size[2] else 2
            other = 2 - ax
            ok_face = False
            # (a wall turned by its step's "turn": its faces are looked for in its own frame, turned as its CFrame is)
            yaw = math.radians(float(f.get("yaw") or 0.0))
            cy, sy = math.cos(yaw), math.sin(yaw)
            turned = abs(math.sin(2 * yaw)) > 1e-9  # (off both axes: the voxels of a slanted face are steps)
            if turned:
                lane = lane or _lane_of(w, g)
            for sgn in (-1, 1):
                clear = True
                face = []
                for t in np.arange(-size[ax] / 2 + 1, size[ax] / 2 - 1 + 1e-6, max(1.0, g.res)):
                    for yy in np.arange(f["pos"][1] - size[1] / 2 + 2, f["pos"][1] + size[1] / 2 - 1 + 1e-6, max(1.0, g.res)):
                        off = [0.0, 0.0, 0.0]
                        off[ax] = t
                        off[other] = sgn * (size[other] / 2 + g.res * 0.75)
                        pt = [f["pos"][0] + cy * off[0] + sy * off[2], yy, f["pos"][2] - sy * off[0] + cy * off[2]]
                        if turned:
                            face.append(pt)
                            continue
                        i = g.index(pt)
                        if 0 <= i[0] < g.n[0] and 0 <= i[1] < g.n[1] and 0 <= i[2] < g.n[2] and g.occ[i[0], i[1], i[2]]:
                            clear = False
                            break
                    if not clear:
                        break
                if turned and face:
                    # the same points, asked of the things themselves (the wall's own face is 0.75 cells behind them)
                    clear = not lane.proud(face)
                ok_face = ok_face or clear
            if not ok_face:
                bad.append("not flush: something stands proud on both long faces")
        if bad:
            errors.append(f"scale: {label} does not fit the {name} rig: " + "; ".join(bad))
    return errors, {"scale_sheet": name, "scale_claims": counts}


# ------------------------------------------------------------------ voxels


_MESH_CACHE = {}


def mesh_points(mesh_dir, name):
    """a world mesh's own vertices (its <name>.mesh.json from kit world import: base64 float32 triangle soup, Y up),
    centred on its bounds and divided by its size -> (N,3) in -0.5..0.5, or None when the mesh has no data"""
    if name in _MESH_CACHE:
        return _MESH_CACHE[name]
    pts = None
    path = os.path.join(mesh_dir, f"{name}.mesh.json") if mesh_dir else ""
    if path and os.path.isfile(path):
        try:
            import base64
            with open(path, encoding="utf-8") as fh:
                d = json.load(fh)
            v = np.frombuffer(base64.b64decode(d["position"]), dtype="<f4").reshape(-1, 3).astype(float)
            lo, hi = np.array(d["min"], float), np.array(d["max"], float)
            pts = (v - (lo + hi) / 2) / np.maximum(hi - lo, 1e-6)
        except (OSError, ValueError, KeyError, TypeError):
            pts = None
    _MESH_CACHE[name] = pts
    return pts


def mesh_hulls(w, mesh_dir=None):
    """a scanned rock's placeholder is its BOUNDING box, the rock fills much less of it (round, tapering): checked
    as the full box its flat top read as unreachable floor and the gaps between overlapping boxes as traps. A solid
    mesh whose own vertices are on disk (build/worldmeshes/<mesh>.mesh.json) is checked as its REAL shape: every
    column it covers is solid from its lowest to its highest point there (a rock face's ridge, not a 70-stud table).
    Without them it is 75 % of the footprint and 80 % of the height, standing on the same base."""
    for p in w.get("parts") or []:
        if p.get("mesh") and p.get("meshCollide") and p.get("size") and p.get("pos"):
            local = mesh_points(mesh_dir, p["mesh"])
            if local is not None and len(local):
                p["_points"] = np.array(p["pos"], float) + (local * np.array(p["size"], float)) @ rot_matrix(p).T
            # (the reduced box stays the part's size: the look lint's roads / clips read it, the voxels read _points)
            sx, sy, sz = p["size"]
            p["size"] = [sx * 0.75, sy * 0.8, sz * 0.75]
            p["pos"] = [p["pos"][0], p["pos"][1] - sy * 0.1, p["pos"][2]]
def is_solid(p):
    """what a player bumps into: a colliding part, or a world-mesh placeholder whose mesh collides (scanned rocks,
    spires: the placeholder itself is CanCollide=false until WorldMeshes swaps it at runtime)"""
    return bool(p.get("meshCollide")) or (p.get("collide", True) and not p.get("mesh"))
def rot_matrix(p):
    r = np.array(p.get("rot") or [[1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=float)
    return r


def part_inside(p, pts, min_half=0.0):
    """pts (N,3) world -> bool mask of points inside the part's solid (Block, Ball, Cylinder on X, Wedge)."""
    r = rot_matrix(p)
    local = (pts - np.array(p["pos"], dtype=float)) @ r  # world = R*local + pos  ->  local = R^T (w - pos)
    # min_half: a part thinner than a voxel still blocks it (sampled only at cell centres, a 0.3-stud wall that
    # covered no centre did not exist: a closed room read as walkable)
    # (no extra margin: it closed 3-stud doors and 5.5-stud-tall doorways at 2-stud cells; corner seams are sealed
    # by the diagonal moves' side-column checks instead)
    hx, hy, hz = np.maximum(np.array(p["size"], dtype=float) / 2, min_half)
    shape = p.get("shape") or "Block"
    if p.get("class") == "WedgePart":
        inside = (np.abs(local[:, 0]) <= hx) & (np.abs(local[:, 1]) <= hy) & (np.abs(local[:, 2]) <= hz)
        # Roblox wedge: full height at the back (+Z), sloping down to the front (-Z)
        return inside & ((local[:, 1] + hy) <= (local[:, 2] + hz) * (2 * hy) / max(2 * hz, 1e-6))
    if shape == "Ball":
        rad = min(hx, hy, hz)
        return np.sum(local**2, axis=1) <= rad * rad
    if shape == "Cylinder":
        rad = min(hy, hz)
        return (np.abs(local[:, 0]) <= hx) & (local[:, 1] ** 2 + local[:, 2] ** 2 <= rad * rad)
    return (np.abs(local[:, 0]) <= hx) & (np.abs(local[:, 1]) <= hy) & (np.abs(local[:, 2]) <= hz)


def part_aabb(p):
    r = rot_matrix(p)
    half = np.array(p["size"], dtype=float) / 2
    ext = np.abs(r) @ half
    c = np.array(p["pos"], dtype=float)
    return c - ext, c + ext


class Grid:
    def __init__(self, lo, hi, res):
        self.res = res
        self.lo = np.floor(np.array(lo) / res) * res
        self.n = np.maximum(1, np.ceil((np.array(hi) - self.lo) / res).astype(int))
        self.occ = np.zeros(tuple(self.n), dtype=bool)  # [x, y, z]

    def centre(self, ix, iy, iz):
        return self.lo + (np.stack([ix, iy, iz], axis=-1) + 0.5) * self.res

    def index(self, pt):
        return np.floor((np.array(pt, dtype=float) - self.lo) / self.res).astype(int)

    def fill_points(self, pts):
        """a mesh's real shape: per column, solid from its lowest to its highest vertex in that column"""
        idx = np.floor((pts - self.lo) / self.res).astype(int)
        ok = np.all((idx >= 0) & (idx < self.n), axis=1)
        idx = idx[ok]
        if not len(idx):
            return
        col = idx[:, 0] * self.n[2] + idx[:, 2]
        top = np.full(self.n[0] * self.n[2], -1)
        bot = np.full(self.n[0] * self.n[2], self.n[1])
        np.maximum.at(top, col, idx[:, 1])
        np.minimum.at(bot, col, idx[:, 1])
        cols = np.nonzero(top >= 0)[0]
        xs, zs = cols // self.n[2], cols % self.n[2]
        ys = np.arange(self.n[1])[None, :]
        self.occ[xs, :, zs] |= (ys >= bot[cols, None]) & (ys <= top[cols, None])

    def fill_part(self, p):
        if p.get("_points") is not None:
            return self.fill_points(p["_points"])
        a, b = part_aabb(p)
        i0 = np.clip(np.floor((a - self.lo) / self.res).astype(int), 0, self.n)
        i1 = np.clip(np.ceil((b - self.lo) / self.res).astype(int), 0, self.n)
        if np.any(i1 <= i0):
            return
        xs, ys, zs = (np.arange(i0[k], i1[k]) for k in range(3))
        gx, gy, gz = np.meshgrid(xs, ys, zs, indexing="ij")
        pts = self.centre(gx.ravel(), gy.ravel(), gz.ravel())
        m = part_inside(p, pts, self.res / 2 + 1e-6)
        if m.any():
            self.occ[gx.ravel()[m], gy.ravel()[m], gz.ravel()[m]] = True

    def fill_ground(self, g):
        hx = np.array(g["heights"], dtype=float).reshape(g["nx"], g["nz"])
        ix = np.arange(self.n[0])
        iz = np.arange(self.n[2])
        cx = self.lo[0] + (ix + 0.5) * self.res
        cz = self.lo[2] + (iz + 0.5) * self.res
        fx = (cx - g["x0"]) / g["step"]
        fz = (cz - g["z0"]) / g["step"]
        okx = (fx >= 0) & (fx <= g["nx"] - 1)
        okz = (fz >= 0) & (fz <= g["nz"] - 1)
        if not okx.any() or not okz.any():
            return
        # bilinear sample of the height field at every column centre inside the op
        x0 = np.clip(np.floor(fx).astype(int), 0, g["nx"] - 2) if g["nx"] > 1 else np.zeros_like(ix)
        z0 = np.clip(np.floor(fz).astype(int), 0, g["nz"] - 2) if g["nz"] > 1 else np.zeros_like(iz)
        tx = np.clip(fx - x0, 0, 1)[:, None]
        tz = np.clip(fz - z0, 0, 1)[None, :]
        h00 = hx[x0][:, z0]
        h10 = hx[np.minimum(x0 + 1, g["nx"] - 1)][:, z0]
        h01 = hx[x0][:, np.minimum(z0 + 1, g["nz"] - 1)]
        h11 = hx[np.minimum(x0 + 1, g["nx"] - 1)][:, np.minimum(z0 + 1, g["nz"] - 1)]
        h = h00 * (1 - tx) * (1 - tz) + h10 * tx * (1 - tz) + h01 * (1 - tx) * tz + h11 * tx * tz
        mask = okx[:, None] & okz[None, :]
        ycent = self.lo[1] + (np.arange(self.n[1]) + 0.5) * self.res
        solid = ycent[None, :, None] <= h[:, None, :]
        self.occ |= solid & mask[:, None, :]

    def fill_solid(self, op):
        s = op["spec"]
        if op["kind"] == "sdf":
            return self.fill_sdf(op)
        c = s["center"]
        if op["kind"] == "ball":
            self.fill_part({"pos": c, "size": [2 * s["radius"]] * 3, "shape": "Ball"})
        elif op["kind"] == "cylinder":  # terrain cylinders stand upright (axis Y)
            r = s["radius"]
            a = np.array(c) - [r, s["height"] / 2, r]
            b = np.array(c) + [r, s["height"] / 2, r]
            i0 = np.clip(np.floor((a - self.lo) / self.res).astype(int), 0, self.n)
            i1 = np.clip(np.ceil((b - self.lo) / self.res).astype(int), 0, self.n)
            gx, gy, gz = np.meshgrid(*(np.arange(i0[k], i1[k]) for k in range(3)), indexing="ij")
            pts = self.centre(gx.ravel(), gy.ravel(), gz.ravel())
            m = (pts[:, 0] - c[0]) ** 2 + (pts[:, 2] - c[2]) ** 2 <= r * r
            self.occ[gx.ravel()[m], gy.ravel()[m], gz.ravel()[m]] = True
        elif op["kind"] == "block":
            self.fill_part({"pos": c, "size": s["size"]})

    def fill_sdf(self, op):
        """LAND AS A SIGNED DISTANCE (an "sdf" terrain op: kit/world/sdf.py, the game's rules in src/kit/SdfRules.luau):
        the cells inside what it makes are land; the cells inside its cutting shapes are taken OUT of the land that
        was there (a cave under the heights, a doorway through a hill) - so it is filled after the ground"""
        sdf = _load_kit_module("sdf")
        lo, hi = sdf.bounds(op["spec"])
        i0 = np.clip(np.floor((np.array(lo) - self.lo) / self.res).astype(int), 0, self.n)
        i1 = np.clip(np.ceil((np.array(hi) - self.lo) / self.res).astype(int), 0, self.n)
        if (i1 <= i0).any():
            return
        gx, gy, gz = np.meshgrid(*(np.arange(i0[k], i1[k]) for k in range(3)), indexing="ij")
        pts = self.centre(gx.ravel(), gy.ravel(), gz.ravel())
        d, cut = sdf.at_many(op["spec"], pts)
        out = (cut < 0) & (d >= 0)
        self.occ[gx.ravel()[out], gy.ravel()[out], gz.ravel()[out]] = False
        land = d < 0
        self.occ[gx.ravel()[land], gy.ravel()[land], gz.ravel()[land]] = True


# ------------------------------------------------------------------ standing + moving
def standable_levels(g, height, foot=2):
    """Per column the floor heights (cell index of the first free cell above a solid) with `height` studs of
    headroom over a foot x foot footprint. Returns L [nx, nz, K] (cell index, -1 = none)."""
    occ = g.occ
    nh = max(1, int(math.ceil(height / g.res)))
    free = ~occ
    # headroom: nh free cells starting at y (inclusive), via a cumulative sum along y
    cs = np.concatenate([np.zeros((occ.shape[0], 1, occ.shape[2]), int), np.cumsum(free, axis=1)], axis=1)
    ny = occ.shape[1]
    head = np.zeros_like(occ)
    if ny > nh:
        head[:, : ny - nh + 1, :] = (cs[:, nh:, :] - cs[:, : ny - nh + 1, :]) == nh
    # footprint: the headroom must hold over foot x foot columns (a 2-stud-wide body) - over SOME such square that
    # holds the cell, whichever side of it the rest of the body stands. (One square only was tried: the cell and
    # its neighbour toward -x and -z. A flight of steps was then judged by the way it climbs: toward +z the
    # neighbour is the step below, free; toward -z it is the step above, solid at that height - so a flight
    # climbing north or west read as blocked at every other step, and a building's second flight, which comes
    # back the other way, could not be climbed: card u3re, 2026-11-15.)
    # g.squares[i, y, j] = the square whose low corner is the cell (i, j) - cells i..i+fp-1, j..j+fp-1 - has the
    # headroom at y. A cell is stood on when a square holding it has; two cells are JOINED by the walk only when
    # ONE square holds both (build_graph): two cells each stood on through a different square let a body through
    # a 1-stud gap between two staggered walls (a fresh reader, 2026-11-15).
    fp = max(1, int(round(foot / g.res)))
    g.foot = fp
    g.squares = None
    if fp > 1:
        sq = np.ones_like(head)
        for a in range(fp):
            for b in range(fp):
                shifted = np.zeros_like(head)
                shifted[: head.shape[0] - a, :, : head.shape[2] - b] = head[a:, :, b:]
                sq &= shifted
        g.squares = sq
        any_side = np.zeros_like(head)
        for a in range(fp):
            for b in range(fp):
                any_side[a:, :, b:] |= sq[: head.shape[0] - a, :, : head.shape[2] - b]
        head = any_side
    support = np.zeros_like(occ)
    support[:, 1:, :] = occ[:, :-1, :]
    stand = head & support & free
    K = int(stand.sum(axis=1).max()) if stand.any() else 1
    K = max(1, K)
    L = -np.ones((occ.shape[0], occ.shape[2], K), dtype=int)
    xs, ys, zs = np.nonzero(stand)
    order = np.lexsort((ys, zs, xs))
    xs, ys, zs = xs[order], ys[order], zs[order]
    col = xs * occ.shape[2] + zs
    first = np.r_[True, col[1:] != col[:-1]]
    rank = np.arange(len(col)) - np.maximum.accumulate(np.where(first, np.arange(len(col)), 0))
    L[xs, zs, rank] = ys
    return L


def build_graph(g, L, P):
    """Directed edges between standable cells: walk / climb / drop to the 8 neighbours, gap jumps over air."""
    nx, nz, K = L.shape
    nid = lambda x, z, k: (x * nz + z) * K + k  # noqa: E731
    step = P["step"] / g.res
    jump = P["jump"] / g.res
    src, dst, cost = [], [], []
    xs, zs = np.meshgrid(np.arange(nx), np.arange(nz), indexing="ij")
    ny = g.occ.shape[1]
    # how many solid cells lie under each height of each column: a count between two heights is what stands
    # between them
    solid_below = np.concatenate([np.zeros((nx, 1, nz), int), np.cumsum(g.occ, axis=1)], axis=1)
    fp = getattr(g, "foot", 1)
    squares = getattr(g, "squares", None)

    def shared_square(ax_, az_, bx_, bz_, y):
        """is there ONE body-sized square, with its headroom at y, that holds both cells"""
        if squares is None:
            return np.ones(len(ax_), bool)
        ok = np.zeros(len(ax_), bool)
        lo_x, hi_x = np.maximum(ax_, bx_) - fp + 1, np.minimum(ax_, bx_)
        lo_z, hi_z = np.maximum(az_, bz_) - fp + 1, np.minimum(az_, bz_)
        yy = np.clip(y, 0, ny - 1)
        for ox in range(fp):
            for oz in range(fp):
                cx, cz = lo_x + ox, lo_z + oz
                inside = (cx <= hi_x) & (cz <= hi_z) & (cx >= 0) & (cz >= 0)
                ok |= inside & squares[np.clip(cx, 0, nx - 1), yy, np.clip(cz, 0, nz - 1)]
        return ok

    def nothing_between(cx, cz, y_low, y_high):
        """is the column free of anything solid from y_low up to y_high (a slab, a roof, a ceiling)"""
        lo = np.clip(y_low, 0, ny)
        hi = np.clip(np.maximum(y_high, y_low), 0, ny)
        return solid_below[cx, hi, cz] - solid_below[cx, lo, cz] == 0

    for dx in (-1, 0, 1):
        for dz in (-1, 0, 1):
            if dx == 0 and dz == 0:
                continue
            x2, z2 = xs + dx, zs + dz
            ok = (x2 >= 0) & (x2 < nx) & (z2 >= 0) & (z2 < nz)
            a_x, a_z, b_x, b_z = xs[ok], zs[ok], x2[ok], z2[ok]
            d = math.hypot(dx, dz)
            head_n = max(1, int(math.ceil(P["height"] / g.res)))
            for k in range(K):
                ya = L[a_x, a_z, k]
                for k2 in range(K):
                    yb = L[b_x, b_z, k2]
                    m = (ya >= 0) & (yb >= 0) & (yb - ya <= jump)
                    if dx and dz and m.any():
                        # no corner cutting: both side columns must be free for the body at the start height
                        sel = np.nonzero(m)[0]
                        ys = ya[sel]
                        ok = np.ones(len(sel), bool)
                        for sx, sz in ((a_x[sel] + dx, a_z[sel]), (a_x[sel], a_z[sel] + dz)):
                            for hy in range(head_n):
                                yy = np.minimum(ys + hy, g.occ.shape[1] - 1)
                                ok &= ~g.occ[sx, yy, sz]
                        m[sel[~ok]] = False
                    if m.any():
                        # the body moves as ONE square: both cells in it, with its headroom at the higher of the two
                        # floors; and it passes through nothing - going UP, the column it leaves is free from its
                        # own floor to the head of the body on the higher one; going DOWN, the column it enters is
                        # free from the lower floor up (the walk used to drop a body through a slab or a roof into
                        # the room under it: a closed hut read as entered from its roof)
                        sel = np.nonzero(m)[0]
                        y_a, y_b = ya[sel], yb[sel]
                        top = np.maximum(y_a, y_b)
                        ok = shared_square(a_x[sel], a_z[sel], b_x[sel], b_z[sel], top)
                        ok &= nothing_between(a_x[sel], a_z[sel], y_a, top + head_n)
                        ok &= nothing_between(b_x[sel], b_z[sel], y_b, top + head_n)
                        m[sel[~ok]] = False
                    if m.any():
                        src.append(nid(a_x[m], a_z[m], k))
                        dst.append(nid(b_x[m], b_z[m], k2))
                        rise = np.maximum(yb[m] - ya[m], 0)
                        cost.append(d + np.where(rise > step, 2.0, 0.0))  # a climb costs a jump
    # gap jumps over open air, straight + diagonal, on the real arc: take-off speed v = sqrt(2 g J) up, `speed`
    # studs/s across (Roblox: g = 196.2). Up to the apex distance any landing up to J high works (slow down in the
    # air); beyond it the landing height follows the parabola; falls of up to 3 J extend the range.
    G, J, run = 196.2, P["jump"], float(P.get("speed", 16.0))
    v = math.sqrt(2 * G * J)
    apex_d = run * v / G

    def rise_at(d):
        if d <= apex_d:
            return J
        t = d / run
        return v * t - G * t * t / 2

    t_far = (v + math.sqrt(v * v + 2 * G * 3 * J)) / G
    head = max(1, int(math.ceil(P["height"] / g.res)))
    for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
        unit = math.hypot(dx, dz) * g.res
        reach = int(min(P["gap"] * 1.6, run * t_far) / unit)
        for dist in range(2, reach + 1):
            allowed = rise_at(dist * unit) / g.res
            x2, z2 = xs + dx * dist, zs + dz * dist
            ok = (x2 >= 0) & (x2 < nx) & (z2 >= 0) & (z2 < nz)
            a_x, a_z, b_x, b_z = xs[ok], zs[ok], x2[ok], z2[ok]
            for k in range(K):
                ya = L[a_x, a_z, k]
                for k2 in range(K):
                    yb = L[b_x, b_z, k2]
                    m = (ya >= 0) & (yb >= 0) & (yb - ya <= allowed) & (yb >= ya - 3 * jump)
                    if not m.any():
                        continue
                    # the air between must be free for the body at the take-off height (no wall in the way); a
                    # diagonal jump also needs both side columns of every step free (a 0.1-stud corner seam let
                    # diagonal jumps into a closed room)
                    clear = np.ones(m.sum(), bool)
                    sx, sz, sy = a_x[m], a_z[m], ya[m]
                    steps = [(sx + dx * t, sz + dz * t) for t in range(1, dist)]
                    # the body is 2 studs wide and flies as ONE piece: a straight jump needs the column beside its line
                    # free too - the SAME side from take-off to landing (a body that leaves along one wall cannot
                    # arrive along the other: checked toward one side only, and only between the two ends, a jump
                    # crossed a 1-stud gap between two staggered walls - a fresh reader, 2026-11-15)
                    fp = max(1, int(round(2 / g.res))) - 1

                    def free_at(cx, cz, y0):
                        cx = np.clip(cx, 0, g.occ.shape[0] - 1)
                        cz = np.clip(cz, 0, g.occ.shape[2] - 1)
                        ok = np.ones(len(sy), bool)
                        top = np.minimum(y0 + head, g.occ.shape[1])
                        for hy in range(head):
                            yy = np.minimum(y0 + hy, g.occ.shape[1] - 1)
                            ok &= ~g.occ[cx, yy, cz] | (y0 + hy >= top)
                        return ok

                    for cx, cz in steps:
                        clear &= free_at(cx, cz, sy)
                        # (a jump UP rises on the way: the air it crosses is free up to the head of the body on the
                        # higher floor - it went through a doorway 5.5 high and landed on a deck 7 up behind it)
                        inb = (cx >= 0) & (cx < nx) & (cz >= 0) & (cz < nz)
                        clear &= ~inb | nothing_between(np.clip(cx, 0, nx - 1), np.clip(cz, 0, nz - 1), sy, np.maximum(sy, yb[m]) + head)
                    if fp and not (dx and dz):
                        either = np.zeros(m.sum(), bool)
                        ey = yb[m]
                        for sgn in (fp, -fp):
                            ox, oz = (sgn if dz else 0), (sgn if dx else 0)
                            side = np.ones(m.sum(), bool)
                            for cx, cz in steps:
                                side &= free_at(cx + ox, cz + oz, sy)
                            # (the other half of the body at the take-off, on its floor, and at the landing, on its)
                            side &= free_at(sx + ox, sz + oz, sy)
                            side &= free_at(sx + dx * dist + ox, sz + dz * dist + oz, np.maximum(sy, ey))
                            either |= side
                        clear &= either
                    if dx and dz:
                        for t in range(1, dist + 1):
                            clear &= free_at(sx + dx * t, sz + dz * (t - 1), sy)
                            clear &= free_at(sx + dx * (t - 1), sz + dz * t, sy)
                    # ... and the landing is reached through nothing: its column free from its own floor up to the
                    # head of the body at the take-off height (a jump off a roof never lands in the room under it)
                    clear &= nothing_between(b_x[m], b_z[m], yb[m], np.maximum(sy, yb[m]) + head)
                    # ... and it rises through nothing: the column it leaves is free up to the head of the body on the
                    # higher floor (a jump from under a deck never comes up through the deck)
                    clear &= nothing_between(sx, sz, sy, np.maximum(sy, yb[m]) + head)
                    keep = np.nonzero(m)[0][clear]
                    if len(keep):
                        src.append(nid(a_x[keep], a_z[keep], k))
                        dst.append(nid(b_x[keep], b_z[keep], k2))
                        cost.append(np.full(len(keep), dist * math.hypot(dx, dz) + 2.0))
    n = nx * nz * K
    if not src:
        return n, np.zeros(0, int), np.zeros(0, int), np.zeros(0)
    return n, np.concatenate(src), np.concatenate(dst), np.concatenate(cost)


def fine_walk(x0, x1, z0, z1, ytop, g, L, reach, back, solids, terr, P):
    """the walk again at 1-stud cells inside one box (x0..x1, z0..z1, from the grid's floor to ytop), entered at the
    box's rim where the coarse pass reached the same column at the same height (and left the same way: `back`).
    -> (wx, wy, wz, valid, forward, backward) per fine node, or None when the rim touches no coarse floor."""
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import breadth_first_order

    res = g.res
    f = Grid(np.array([x0, g.lo[1], z0]), np.array([x1, ytop, z1]), 1.0)
    for gr in [x for x in terr.get("ground", []) if not x.get("backdrop")]:
        f.fill_ground(gr)
    for op in terr.get("solids", []):
        f.fill_solid(op)
    for p in solids:
        a, b = part_aabb(p)
        if np.all(b >= f.lo) and np.all(a <= f.lo + f.n * f.res):
            f.fill_part(p)
    Lf = standable_levels(f, P["height"])
    n, src, dst, _ = build_graph(f, Lf, P)
    if n == 0:
        return None
    nxf, nzf, Kf = Lf.shape
    ids = np.arange(nxf * nzf * Kf)
    fx, fz, fk = ids // (nzf * Kf), (ids // Kf) % nzf, ids % Kf
    lev = Lf[fx, fz, fk]
    valid = lev >= 0
    wx = f.lo[0] + (fx + 0.5)
    wz = f.lo[2] + (fz + 0.5)
    wy = f.lo[1] + lev
    rim = valid & ((fx < 3) | (fx >= nxf - 3) | (fz < 3) | (fz >= nzf - 3))
    nx_, nz_, K = L.shape
    cx = np.clip(np.floor((wx - g.lo[0]) / res).astype(int), 0, nx_ - 1)
    cz = np.clip(np.floor((wz - g.lo[2]) / res).astype(int), 0, nz_ - 1)
    fwd_seeds, back_seeds = [], []
    for i in np.nonzero(rim)[0]:
        for k in range(K):
            lv = L[cx[i], cz[i], k]
            if lv >= 0 and abs(g.lo[1] + lv * res - wy[i]) <= res + 1:
                node = (cx[i] * nz_ + cz[i]) * K + k
                if reach[node]:
                    fwd_seeds.append(i)
                if back is not None and back[node]:
                    back_seeds.append(i)
                break
    if not fwd_seeds:
        return None
    A = csr_matrix((np.ones(len(src)), (src, dst)), shape=(n, n))

    def spread(M, seeds):
        got = np.zeros(n, bool)
        for s in seeds:
            if not got[s]:
                got[breadth_first_order(M, s, directed=True, return_predecessors=False)] = True
        return got

    fwd = spread(A, fwd_seeds)
    bwd = spread(A.T.tocsr(), back_seeds) if back is not None else None
    return wx, wy, wz, valid, fwd, bwd


def fine_reach(plat, g, L, reach, solids, terr, P, margin=24.0):
    """one unreachable floor walked again at 1-stud cells (a box of the floor + `margin` studs): the fraction of the
    platform's fine floor reached (None: nothing to enter from)"""
    r = fine_walk(plat["x"][0] - margin, plat["x"][1] + margin, plat["z"][0] - margin, plat["z"][1] + margin,
                  plat["y"] + P["height"] + 6, g, L, reach, None, solids, terr, P)
    if r is None:
        return None
    wx, wy, wz, valid, fwd, _ = r
    on = valid & (wx >= plat["x"][0]) & (wx <= plat["x"][1]) & (wz >= plat["z"][0]) & (wz <= plat["z"][1]) & (np.abs(wy - plat["y"]) <= 2.5)
    if not on.any():
        return None
    return float(fwd[on].sum() / on.sum())


def fine_trap(pos, y, g, L, reach, back, solids, terr, P, margin=16.0):
    """a small trap walked again at 1-stud cells around it: the fine trap area (sq studs) within 4 studs of the
    coarse pocket — reached from the rim but with no way back to it (None: the box could not be entered)"""
    r = fine_walk(pos[0] - margin, pos[0] + margin, pos[1] - margin, pos[1] + margin, y + P["height"] + 6,
                  g, L, reach, back, solids, terr, P)
    if r is None:
        return None
    wx, wy, wz, valid, fwd, bwd = r
    near = valid & (np.abs(wx - pos[0]) <= 4) & (np.abs(wz - pos[1]) <= 4)
    return float((near & fwd & ~bwd).sum())


def nearest_node(g, L, pos):
    i = g.index(pos)
    nx, nz, K = L.shape
    best, bd = None, 1e9
    for r in range(0, 8):
        for x in range(max(0, i[0] - r), min(nx, i[0] + r + 1)):
            for z in range(max(0, i[2] - r), min(nz, i[2] + r + 1)):
                for k in range(K):
                    y = L[x, z, k]
                    if y < 0:
                        continue
                    d = abs(x - i[0]) + abs(z - i[2]) + abs(y - i[1]) * 0.5
                    if d < bd:
                        best, bd = (x * nz + z) * K + k, d
        if best is not None:
            return best
    return None


# ------------------------------------------------------------------ sight + camera + room
def los_mask(g, a, b, step=0.75):
    """a (N,3), b (N,3) world points -> bool: the segment crosses no solid voxel."""
    d = b - a
    length = np.linalg.norm(d, axis=1)
    n = max(2, int(np.ceil(length.max() / step)))
    ok = np.ones(len(a), bool)
    for t in np.linspace(0, 1, n)[1:-1]:
        p = a + d * t
        idx = np.floor((p - g.lo) / g.res).astype(int)
        inb = np.all((idx >= 0) & (idx < g.n), axis=1)
        hit = np.zeros(len(a), bool)
        hit[inb] = g.occ[idx[inb, 0], idx[inb, 1], idx[inb, 2]]
        ok &= ~hit
    return ok


def road_samples(w, every=16.0):
    """points along every worn road / trail (the paints), in walking order per road: [(road index, (x, y, z))]"""
    out = []
    for ri, stroke in enumerate(w.get("paints") or []):
        pts = [np.array(p, float) for p in stroke.get("points") or [] if isinstance(p, (list, tuple)) and len(p) == 3]
        carry = 0.0
        for a, b in zip(pts, pts[1:]):
            seg = float(np.linalg.norm(b - a))
            d = carry
            while d < seg:
                out.append((ri, a + (b - a) * (d / max(seg, 1e-9))))
                d += every
            carry = d - seg
        if pts:
            out.append((ri, pts[-1]))
    return out


def guidance(w, g, P, C):
    """AAA gaps W2 + W10 along the roads (the paints): is a LANDMARK in view (the compiled landmarks' tops, the world's
    weenies), and how long does a walk go between POINTS OF INTEREST (objectives, landmarks, spawns)?
    -> (warnings, stats)"""
    warns, stats = [], {}
    samples = road_samples(w)
    if not samples:
        return warns, stats
    eye = np.array([p for _, p in samples]) + [0, P["eye"], 0]
    marks = [m for m in w.get("landmarks") or [] if isinstance(m.get("top"), list)]
    if marks:
        seen = np.zeros(len(eye), bool)
        for m in marks:
            top = np.array(m["top"], float) + [0, 3, 0]
            near = np.linalg.norm(eye[:, [0, 2]] - top[[0, 2]], axis=1) < 1500
            if near.any():
                ok = los_mask(g, eye[near], np.repeat(top[None, :], int(near.sum()), 0), step=0.9 * g.res)
                seen[np.nonzero(near)[0][ok]] = True
        pct = float(seen.mean() * 100)
        stats["landmark_view_pct"] = round(pct, 1)
        if pct < C["landmark_pct"]:
            # the longest stretch of one road without a landmark in view
            best, cur, start, best_at = 0, 0, None, None
            for i, (ri, p) in enumerate(samples):
                same = i > 0 and samples[i - 1][0] == ri
                if not seen[i]:
                    cur = cur + 1 if same else 1
                    start = p if cur == 1 else start
                    if cur > best:
                        best, best_at = cur, (start, p)
                else:
                    cur = 0
            where = f" (the longest blind stretch: {best * 16:.0f} studs from ({best_at[0][0]:.0f}, {best_at[0][2]:.0f}) to ({best_at[1][0]:.0f}, {best_at[1][2]:.0f}))" if best_at else ""
            warns.append(f"improve: a landmark is in view from only {pct:.0f} % of the roads (min {C['landmark_pct']:.0f} %){where} — raise or light a landmark there, or clear the view to one")
    else:
        warns.append("improve: no landmark — mark the world's weenie (\"landmark\": true on its step: the castle, the great tree)")
    pois = [np.array(o["pos"], float) for o in w.get("objectives") or [] if isinstance(o.get("pos"), list)]
    pois += [np.array(m["top"], float) for m in marks]
    pois += [np.array(p["pos"], float) for p in w.get("parts") or [] if p.get("spawn")]
    if pois:
        P2 = np.array([[p[0], p[2]] for p in pois])
        worst, worst_at, run_d, run_from = 0.0, None, 0.0, None
        prev = None
        for ri, p in samples:
            if prev is not None and prev[0] == ri:
                run_d += float(np.linalg.norm(p - prev[1]))
            else:
                run_d, run_from = 0.0, p
            if float(np.min(np.linalg.norm(P2 - p[[0, 2]], axis=1))) < 80:
                run_d, run_from = 0.0, p
            if run_d > worst:
                worst, worst_at = run_d, (run_from, p)
            prev = (ri, p)
        gap_s = worst / P.get("speed", 16.0)
        stats["pacing_max_gap_s"] = round(gap_s, 1)
        if gap_s > C["pacing_s"]:
            warns.append(f"improve: {gap_s:.0f} s of road with nothing to find (max {C['pacing_s']:.0f} s) from ({worst_at[0][0]:.0f}, {worst_at[0][2]:.0f}) to ({worst_at[1][0]:.0f}, {worst_at[1][2]:.0f}) — a point of interest there (a ruin, a camp, a grace, a vista)")
    return warns, stats


def look_lint(w, out=None):
    """What a generated world gets wrong that the play check never sees (warnings, with a place to look):
    floaters (solid parts touching neither the ground nor anything that does), buried parts (wholly under the
    land: wasted budget), trees growing through buildings, rocks / trunks / stones blocking a road or worn trail.
    out (a dict, optional) gets "floaters": [(name, pos), ...] - read by fixture_lint."""
    parts = [p for p in w.get("parts", []) if not p.get("backdrop")]
    grounds = [g for g in (w.get("terrain") or {}).get("ground", []) if not g.get("backdrop")]
    if not parts:
        return []

    solids_t = (w.get("terrain") or {}).get("solids") or []

    def gh(x, z):
        best = None
        for op in solids_t:  # terrain balls / blocks are land too (an island, a ledge)
            sp = op.get("spec") or {}
            if op.get("kind") == "sdf":  # (sdf land: its top over this place, looked for from above, a stud at a time)
                sdf = _load_kit_module("sdf")
                lo_, hi_ = sdf.bounds(sp)
                if lo_[0] <= x <= hi_[0] and lo_[2] <= z <= hi_[2]:
                    y = hi_[1]
                    while y >= lo_[1]:
                        if sdf.at(sp, x, y, z)[0] < 0:
                            under, over = y, y + 1.0  # (the surface lies between: halved down to a hundredth)
                            while over - under > 0.01:
                                mid = (under + over) / 2
                                if sdf.at(sp, x, mid, z)[0] < 0:
                                    under = mid
                                else:
                                    over = mid
                            best = over if best is None else max(best, over)
                            break
                        y -= 1.0
                continue
            c = sp.get("center")
            if not c:
                continue
            if op.get("kind") == "ball" and sp.get("radius"):
                d2 = (x - c[0]) ** 2 + (z - c[2]) ** 2
                if d2 < sp["radius"] ** 2:
                    h = c[1] + (sp["radius"] ** 2 - d2) ** 0.5
                    best = h if best is None else max(best, h)
            elif op.get("kind") == "block" and sp.get("size"):
                sz = sp["size"]
                if abs(x - c[0]) <= sz[0] / 2 and abs(z - c[2]) <= sz[2] / 2:
                    h = c[1] + sz[1] / 2
                    best = h if best is None else max(best, h)
        for g in grounds:
            fx, fz = (x - g["x0"]) / g["step"], (z - g["z0"]) / g["step"]
            if 0 <= fx <= g["nx"] - 1 and 0 <= fz <= g["nz"] - 1:
                # bilinear, like the compiler's ground (nearest-sample reads a slope a little high or low)
                ix, iz = min(int(fx), g["nx"] - 2), min(int(fz), g["nz"] - 2)
                tx, tz = fx - ix, fz - iz
                H, nz = g["heights"], g["nz"]
                h = (H[ix * nz + iz] * (1 - tx) + H[(ix + 1) * nz + iz] * tx) * (1 - tz) + (H[ix * nz + iz + 1] * (1 - tx) + H[(ix + 1) * nz + iz + 1] * tx) * tz
                best = h if best is None else max(best, h)
        return best

    boxes = [part_aabb(p) for p in parts]
    under = []  # the land at the part's middle and corners (None off the map)
    for (a, b) in boxes:
        hs = [gh(x, z) for x, z in ((a[0], a[2]), (b[0], a[2]), (a[0], b[2]), (b[0], b[2]), ((a[0] + b[0]) / 2, (a[2] + b[2]) / 2))]
        hs = [h for h in hs if h is not None]
        under.append((min(hs), max(hs)) if hs else (None, None))
    warns = []

    def where(i):
        p = parts[i]
        return f"{p.get('name', 'Part')} at ({p['pos'][0]:.0f}, {p['pos'][1]:.0f}, {p['pos'][2]:.0f})"

    # buried: the whole part below the land
    buried = [i for i, (a, b) in enumerate(boxes) if under[i][1] is not None and b[1] < under[i][0] - 0.3]
    if buried:
        warns.append(f"look: {len(buried)} part(s) lie wholly under the land (wasted budget), e.g. {where(buried[0])}")

    # floaters: connectivity from the ground through touching solid parts
    solid = [i for i, p in enumerate(parts) if is_solid(p)]
    cell = 16.0
    index = {}
    for i in solid:
        a, b = boxes[i]
        for cx in range(int(np.floor(a[0] / cell)), int(np.floor(b[0] / cell)) + 1):
            for cz in range(int(np.floor(a[2] / cell)), int(np.floor(b[2] / cell)) + 1):
                index.setdefault((cx, cz), []).append(i)

    def touching(i):
        a, b = boxes[i]
        seen = set()
        for cx in range(int(np.floor(a[0] / cell)), int(np.floor(b[0] / cell)) + 1):
            for cz in range(int(np.floor(a[2] / cell)), int(np.floor(b[2] / cell)) + 1):
                for j in index.get((cx, cz), ()):
                    if j == i or j in seen:
                        continue
                    seen.add(j)
                    c, d = boxes[j]
                    if np.all(a <= d + 0.35) and np.all(c <= b + 0.35):
                        yield j

    floor_y = min((boxes[i][0][1] for i in solid), default=0.0)
    grounded = [i for i in solid if ((boxes[i][0][1] <= floor_y + 1.0) if under[i][0] is None else (boxes[i][0][1] <= under[i][1] + 0.6))]
    held = set(grounded)
    queue = list(grounded)
    while queue:
        i = queue.pop()
        for j in touching(i):
            if j not in held:
                held.add(j)
                queue.append(j)
    floaters = [i for i in solid if i not in held]
    if out is not None:
        out["floaters"] = [(str(parts[i].get("name") or "Part"), list(parts[i]["pos"])) for i in floaters]
    if floaters:
        warns.append(f"look: {len(floaters)} solid part(s) float, touching neither the land nor anything on it, e.g. {where(floaters[0])}")

    # trees through buildings
    tree = {"Trunk", "Needles", "Canopy", "Frond", "Branch"}
    built = {"Wall", "TowerWall", "Building", "RuinWall", "Log", "Roof", "Slab", "RoomFloor"}
    clips = set()
    bindex = {}
    for j, q in enumerate(parts):
        if q.get("name") in built:
            c, d = boxes[j]
            for cx in range(int(np.floor(c[0] / cell)), int(np.floor(d[0] / cell)) + 1):
                for cz in range(int(np.floor(c[2] / cell)), int(np.floor(d[2] / cell)) + 1):
                    bindex.setdefault((cx, cz), []).append(j)
    for i, p in enumerate(parts):
        if p.get("name") in tree:
            a, b = boxes[i]
            hit = False
            for cx in range(int(np.floor(a[0] / cell)), int(np.floor(b[0] / cell)) + 1):
                for cz in range(int(np.floor(a[2] / cell)), int(np.floor(b[2] / cell)) + 1):
                    for j in bindex.get((cx, cz), ()):
                        c, d = boxes[j]
                        if np.all(a + 0.5 < d) and np.all(c + 0.5 < b):
                            hit = True
                            break
                    if hit:
                        break
                if hit:
                    break
            if hit:
                clips.add(i)
    if clips:
        warns.append(f"look: {len(clips)} tree part(s) grow through a building or wall, e.g. {where(min(clips))}")

    # things standing in the way on a road / worn trail
    roads = [boxes[i] for i, p in enumerate(parts) if p.get("name") in ("Road", "Path", "PathJoint")]
    strokes = w.get("paints") or []
    blockers = []
    for i, p in enumerate(parts):
        if not (p.get("name") in ("Rock", "Spire", "Boulder", "Gravestone", "Trunk", "Stone", "TrunkCollider")
                or p.get("meshCollide")) or not is_solid(p):
            continue
        a, b = boxes[i]
        if under[i][1] is not None and b[1] - under[i][1] < 1.5:
            continue  # flush with the land: you walk over it
        hit = any(np.all(a[[0, 2]] < d[[0, 2]]) and np.all(c[[0, 2]] < b[[0, 2]]) for (c, d) in roads)
        if not hit:
            x, z = p["pos"][0], p["pos"][2]
            for s in strokes:
                pts = s.get("points") or []
                r = s.get("width", 8) / 2
                for k in range(len(pts) - 1):
                    (x1, _, z1), (x2, _, z2) = pts[k], pts[k + 1]
                    vx, vz = x2 - x1, z2 - z1
                    t = max(0.0, min(1.0, ((x - x1) * vx + (z - z1) * vz) / max(vx * vx + vz * vz, 1e-9)))
                    if (x - x1 - vx * t) ** 2 + (z - z1 - vz * t) ** 2 < r * r:
                        hit = True
                        break
                if hit:
                    break
        if hit:
            blockers.append(i)
    if blockers:
        warns.append(f"look: {len(blockers)} rock(s) / trunk(s) stand in a road or worn trail, e.g. {where(blockers[0])} — add the road to that step's \"avoid\"")
    return warns


# ------------------------------------------------------------------ street fixtures (ERRORS: V3 stage C)
# LIMITATIONS_FIXES_V3.md stage C: "enforcing kit world check structural gates: 0 floating plinths, >= 7 st clear
# footpath". A FIXTURE is a thing set out to stand on the street (named for one: a plinth, a pedestal, a lamp's pole or
# post, a bollard, a bench, a fountain, a statue, a pump, a well, a brazier, a fingerpost / milestone, a drain grate or
# a cellar hatch, a lantern). One that floats - touching neither the land nor anything that stands on it (look_lint's
# floaters: a row of lamps typed at y 0 over a valley) - is an error; other floaters stay look warnings (a test
# platform, a spawn pad, a fallen rock). A ROAD part ("Road", "Path", "Street", "Pavement", "Sidewalk", "Footpath")
# keeps FOOTPATH studs clear across it past every solid thing standing ON it (half its footprint or more on the road:
# a wall or a gate the road runs through lies mostly off it) taller than a step (FOOTPATH_STEP): a narrower road, all
# of its width. NOT measured: painted roads (terrain strokes: no part to stand on), a road's joint
# pieces, and whether a street with no fixtures is wide enough (that is the scale sheet's street claim).
FIXTURE_WORDS = {
    "plinth", "pedestal", "pole", "post", "lamppost", "bollard", "bench", "fountain", "statue", "pump", "well",
    "brazier", "fingerpost", "milestone", "grate", "hatch", "lantern", "signpost",
}
FOOTPATH = 7.0  # studs of clear way along a road past the things on it
FOOTPATH_STEP = 1.5  # studs: what stands lower than this on a road is walked over (a kerb, a drain grate's lip)
ROAD_NAMES = {"Road", "Path", "Street", "Pavement", "Sidewalk", "Footpath"}


def _name_words(name):
    """'LampPole2' -> {'lamp', 'pole', 'lamppole'}: the CamelCase words of a part's name, and the whole of it"""
    s = str(name or "")
    words = re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+", s)
    return {x.lower() for x in words} | {re.sub(r"[^a-z]", "", s.lower())}


def is_fixture(name):
    return bool(_name_words(name) & FIXTURE_WORDS)


def fixture_lint(look):
    """[errors]: street fixtures that float (look: the dict look_lint filled)"""
    bad = [(n, pos) for n, pos in look.get("floaters") or [] if is_fixture(n)]
    if not bad:
        return []
    n, pos = bad[0]
    return [f"fixture: {len(bad)} street fixture(s) float, touching neither the land nor anything on it, e.g. {n} at "
            f"({pos[0]:.0f}, {pos[1]:.0f}, {pos[2]:.0f}) - stand it on the land (a row's \"ground\": true) or on what "
            "holds it (LIMITATIONS_FIXES_V3.md stage C: 0 floating plinths)"]


def footpath_lint(w):
    """([errors], {stats}): every road part keeps FOOTPATH studs clear across it past the solid things standing on it"""
    parts = [p for p in w.get("parts", []) if not p.get("backdrop")]
    roads = [i for i, p in enumerate(parts) if p.get("name") in ROAD_NAMES and isinstance(p.get("size"), list)]
    if not roads:
        return [], {"footpath_roads": 0}
    boxes = [part_aabb(p) for p in parts]
    cell = 16.0
    index = {}
    for i, p in enumerate(parts):
        if p.get("name") in ROAD_NAMES or p.get("name") == "PathJoint" or not is_solid(p):
            continue
        a, b = boxes[i]
        for cx in range(int(np.floor(a[0] / cell)), int(np.floor(b[0] / cell)) + 1):
            for cz in range(int(np.floor(a[2] / cell)), int(np.floor(b[2] / cell)) + 1):
                index.setdefault((cx, cz), []).append(i)
    errors = []
    narrow = 0
    worst = None
    for ri in roads:
        rp = parts[ri]
        r = rot_matrix(rp)
        size = np.array(rp["size"], float)
        centre = np.array(rp["pos"], float)
        # the road's own axes: across = the narrower of its two flat sides, up = the third
        flat = sorted(range(3), key=lambda k: abs(r[1, k]))[:2]  # (the two local axes nearest horizontal)
        up = ({0, 1, 2} - set(flat)).pop()
        along, across = (flat[0], flat[1]) if size[flat[0]] >= size[flat[1]] else (flat[1], flat[0])
        L, W = size[along] / 2, size[across] / 2
        top = centre[1] + abs(r[1, up]) * size[up] / 2
        need = min(FOOTPATH, 2 * W)
        a, b = boxes[ri]
        seen = set()
        spans = []  # (along0, along1, across0, across1) of each thing on it
        for cx in range(int(np.floor(a[0] / cell)), int(np.floor(b[0] / cell)) + 1):
            for cz in range(int(np.floor(a[2] / cell)), int(np.floor(b[2] / cell)) + 1):
                for j in index.get((cx, cz), ()):
                    if j in seen:
                        continue
                    seen.add(j)
                    c, d = boxes[j]
                    if c[1] > top + FOOTPATH_STEP or d[1] < top + FOOTPATH_STEP:
                        continue  # (above head height off the road, or low enough to step over)
                    q = parts[j]
                    qr = rot_matrix(q)
                    qh = np.array(q["size"], float) / 2
                    corners = np.array([[sx, sy, sz] for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]) * qh
                    world = corners @ qr.T + np.array(q["pos"], float)
                    loc = (world - centre) @ r  # (into the road's frame)
                    whole = (loc[:, along].max() - loc[:, along].min()) * (loc[:, across].max() - loc[:, across].min())
                    a0, a1 = max(loc[:, along].min(), -L), min(loc[:, along].max(), L)
                    c0, c1 = max(loc[:, across].min(), -W), min(loc[:, across].max(), W)
                    # (it stands ON the road: half its footprint or more - a wall or a gate the road runs through or
                    # beside lies mostly off it)
                    if a1 - a0 > 0.25 and c1 - c0 > 0.25 and (a1 - a0) * (c1 - c0) >= 0.5 * whole:
                        spans.append((a0, a1, c0, c1, j))
        for (a0, a1, _, _, j) in spans:
            # the clear way beside it: across the road, less everything standing beside it along the road
            cuts = sorted((s[2], s[3]) for s in spans if s[0] < a1 and a0 < s[1])
            best, at = 0.0, -W
            for c0, c1 in cuts:
                best = max(best, c0 - at)
                at = max(at, c1)
            best = max(best, W - at)
            if best < need - 1e-6:
                narrow += 1
                if worst is None or best < worst[0]:
                    q = parts[j]
                    worst = (best, q.get("name", "Part"), q["pos"], rp["pos"], need)
    if worst:
        best, qn, qp, rpos, need = worst
        errors.append(f"footpath: {narrow} thing(s) on a road leave less than {need:.0f} studs clear across it - the "
                      f"worst {qn} at ({qp[0]:.0f}, {qp[1]:.0f}, {qp[2]:.0f}) leaves {best:.1f} on the road at "
                      f"({rpos[0]:.0f}, {rpos[2]:.0f}) - move it to the road's edge or off it (LIMITATIONS_FIXES_V3.md "
                      f"stage C: a >= {FOOTPATH:.0f}-stud clear footpath)")
    return errors, {"footpath_roads": len(roads), "footpath_narrow": narrow}

# ------------------------------------------------------------------ z-fighting (an ERROR: card my7f, V3 stage A.1)
# Two faces that lie in one plane (within ZFIGHT_TOL studs), face the same way and overlap by more than ZFIGHT_AREA
# square studs FLICKER in Roblox: GothicCourtyard's house floors (WoodPlanks, top at y = 0) on the court's Slate floor
# (top at y = 0) showed stone in one Studio capture and planks in the next (2026-11-12). The compiler's own warning
# was never shown here (card px2n) and it cried wolf: it counts two faces of the SAME look, which draw the same
# pixels (IF Roblox maps a material in world space - not yet seen in Studio), and it skips every turned part.
# This one measures block parts (Part / SpawnLocation, shape Block) at any angle, counts a pair only when the two
# looks differ (material or colour) and drops an overlap only when ALL of it lies buried inside OPAQUE parts (a grid
# of probes a twentieth of a stud out of the face, its edges included: a wall's top under the wall above it, a slab's
# edge inside a wall). Faces that face DOWN (a ceiling's, a balcony's, an arch's underside: card my7f's "z-fighting
# misses ceilings", LIMITATIONS_FIXES_V4 5.1) count only where a player could look up at them: straight down from the
# overlap's middle the first thing is a floor (an opaque part's top, the land of a ground op, a terrain solid) at
# least ZFIGHT_CEIL_CLEAR studs below. A foot on the land or on a slab (nothing between) and an underside with
# nothing at all below it (under the world) are unseen and stay out. NOT measured: wedges, meshes, trusses, and
# terrain (a voxel field, not a plane). The 0.03 band is the V3 spec's number, not one measured against Roblox's depth
# precision; the 2-stud clearance is chosen (a gap a head cannot get under is seen only edge-on), not measured.
ZFIGHT_TOL = 0.03  # studs between the two planes
ZFIGHT_AREA = 0.1  # square studs of overlap
ZFIGHT_BURY_OPACITY = 0.05  # a part more see-through than this buries nothing (glass, a haze card)
ZFIGHT_CEIL_CLEAR = 2.0  # studs from an underside down to the floor under it: less, and nobody looks up at it
_ZF_NQ = 50.0  # normals bucketed by component in steps of 1/50 (neighbouring buckets are searched too)


def _zf_floor_below(q, boxes, grounds, skip):
    """how far straight down from the point q the first floor lies: an opaque box's top face hit by the ray (boxes =
    [(centre, rotation, half sizes)]), a ground op's land; None when nothing at all is under it (under the world)"""
    best = None
    for o, (c, r, h) in enumerate(boxes):
        if o in skip:
            continue
        # the ray q + t * (0, -1, 0), t >= 0, against the turned box (slabs in the box's own axes)
        p = (q - c) @ r
        d = -r[1, :]  # the ray's direction in the box's axes
        t0, t1 = 0.0, math.inf
        hit = True
        for a in range(3):
            if abs(d[a]) < 1e-12:
                if abs(p[a]) > h[a] + 1e-6:
                    hit = False
                    break
                continue
            ta, tb = (-h[a] - p[a]) / d[a], (h[a] - p[a]) / d[a]
            if ta > tb:
                ta, tb = tb, ta
            t0, t1 = max(t0, ta), min(t1, tb)
            if t0 > t1:
                hit = False
                break
        if hit and (best is None or t0 < best):
            best = t0
    for gr in grounds:
        hy = float(_ground_height(gr, [q[0]], [q[2]])[0])
        if np.isfinite(hy) and hy <= q[1] + 1e-6:
            best = q[1] - hy if best is None else min(best, q[1] - hy)
    return best


def _zf_clip(poly, a, b, c):
    """the part of a convex polygon where a*u + b*v <= c (Sutherland-Hodgman, one edge)"""
    out = []
    for m in range(len(poly)):
        P, Q = poly[m], poly[(m + 1) % len(poly)]
        fp, fq = a * P[0] + b * P[1] - c, a * Q[0] + b * Q[1] - c
        if fp <= 0:
            out.append(P)
        if (fp < 0) != (fq < 0) and abs(fp - fq) > 1e-12:
            t = fp / (fp - fq)
            out.append((P[0] + t * (Q[0] - P[0]), P[1] + t * (Q[1] - P[1])))
    return out


def _zf_area(poly):
    s = 0.0
    for m in range(len(poly)):
        x0, y0 = poly[m]
        x1, y1 = poly[(m + 1) % len(poly)]
        s += x0 * y1 - x1 * y0
    return abs(s) / 2


def _zf_probes(poly, step=0.5, cap=15):
    """points over a convex polygon, its edges included: a grid (at most cap x cap) clipped to it, its corners pulled
    a hundredth of a stud in, and the middle of each edge"""
    us = [q[0] for q in poly]
    vs = [q[1] for q in poly]
    mu, mv = sum(us) / len(us), sum(vs) / len(vs)
    pts = [(mu, mv)]
    for q in poly:
        d = math.hypot(q[0] - mu, q[1] - mv) or 1.0
        pts.append((q[0] + (mu - q[0]) * 0.01 / d, q[1] + (mv - q[1]) * 0.01 / d))
    for m in range(len(poly)):
        P, Q = poly[m], poly[(m + 1) % len(poly)]
        e = ((P[0] + Q[0]) / 2, (P[1] + Q[1]) / 2)
        d = math.hypot(e[0] - mu, e[1] - mv) or 1.0
        pts.append((e[0] + (mu - e[0]) * 0.01 / d, e[1] + (mv - e[1]) * 0.01 / d))
    nu = min(cap, max(2, int((max(us) - min(us)) / step) + 1))
    nv = min(cap, max(2, int((max(vs) - min(vs)) / step) + 1))

    def inside(u, v):
        sgn = 0
        for m in range(len(poly)):
            P, Q = poly[m], poly[(m + 1) % len(poly)]
            c = (Q[0] - P[0]) * (v - P[1]) - (Q[1] - P[1]) * (u - P[0])
            if abs(c) < 1e-12:
                continue
            if sgn == 0:
                sgn = 1 if c > 0 else -1
            elif (c > 0) != (sgn > 0):
                return False
        return True

    for a in range(nu):
        for b in range(nv):
            u = min(us) + (max(us) - min(us)) * (a + 0.5) / nu
            v = min(vs) + (max(vs) - min(vs)) * (b + 0.5) / nv
            if inside(u, v):
                pts.append((u, v))
    return pts


def zfight_lint(w, tol=ZFIGHT_TOL, min_area=ZFIGHT_AREA):
    """-> (errors, pairs): every pair of seen block faces of two looks in one plane, overlapping. pairs = [{a, b,
    area, gap, at, looks}] (the largest first)."""
    seen = [p for p in w.get("parts", []) if p.get("class") in ("Part", "SpawnLocation")
            and (p.get("shape") or "Block") == "Block" and float(p.get("transparency") or 0) < 1]
    if not seen:
        return [], []
    rots = [rot_matrix(p) for p in seen]
    lo, hi = [], []
    for p, r in zip(seen, rots):
        e = np.abs(r) @ (np.array(p["size"], float) / 2)
        c = np.array(p["pos"], float)
        lo.append(c - e)
        hi.append(c + e)
    lo, hi = np.array(lo), np.array(hi)
    opaque = np.array([float(p.get("transparency") or 0) <= ZFIGHT_BURY_OPACITY for p in seen])
    sizes = [np.array(p["size"], float) / 2 for p in seen]
    poss = [np.array(p["pos"], float) for p in seen]

    def buried(q, skip):
        """is the point inside an opaque seen part other than the two?"""
        for o in np.nonzero(opaque & np.all((lo <= q + 1e-6) & (hi >= q - 1e-6), axis=1))[0]:
            if o in skip:
                continue
            if np.all(np.abs((q - poss[o]) @ rots[o]) <= sizes[o] + 1e-6):
                return True
        return False

    # what a ceiling is looked up at from: the opaque seen parts and the terrain's solids (boxes), the ground ops' land
    terr = w.get("terrain") or {}
    floor_boxes = [(poss[o], rots[o], sizes[o]) for o in range(len(seen)) if opaque[o]]
    floor_owner = [o for o in range(len(seen)) if opaque[o]]  # (box k is seen part floor_owner[k])
    for s in terr.get("solids") or []:
        if s.get("size") and s.get("pos"):
            floor_boxes.append((np.array(s["pos"], float), rot_matrix(s), np.array(s["size"], float) / 2))
    grounds = terr.get("ground") or []

    # every face (a face that faces down is a ceiling: measured where it is seen from below): its part, normal, plane
    # offset, middle, in-plane axes and half sizes
    faces = []
    for i, (p, r) in enumerate(zip(seen, rots)):
        h = sizes[i]
        for ax in range(3):
            j, k = (ax + 1) % 3, (ax + 2) % 3
            for s in (-1, 1):
                n = s * r[:, ax]
                fc = poss[i] + n * h[ax]
                faces.append((i, n, float(n @ fc), fc, r[:, j], h[j], r[:, k], h[k]))
    if not faces:
        return [], []
    # each face's own box in the world (grown by the band), for a quick test before any polygon is clipped
    flo = np.array([f[3] - np.abs(f[4]) * f[5] - np.abs(f[6]) * f[7] - tol for f in faces])
    fhi = np.array([f[3] + np.abs(f[4]) * f[5] + np.abs(f[6]) * f[7] + tol for f in faces])
    looks = [(seen[f[0]].get("material"), tuple(seen[f[0]].get("color") or ())) for f in faces]
    buckets = {}
    keys = []
    for fi, f in enumerate(faces):
        n, d = f[1], f[2]
        key = (int(round(n[0] * _ZF_NQ)), int(round(n[1] * _ZF_NQ)), int(round(n[2] * _ZF_NQ)), math.floor(d / tol))
        keys.append(key)
        buckets.setdefault(key, []).append(fi)
    bucket_idx = {k: np.array(v) for k, v in buckets.items()}
    pairs = []
    steps = (-1, 0, 1)
    for fa, A in enumerate(faces):
        ka = keys[fa]
        cand = []
        for dx in steps:
            for dy in steps:
                for dz in steps:
                    for dd in steps:
                        b = bucket_idx.get((ka[0] + dx, ka[1] + dy, ka[2] + dz, ka[3] + dd))
                        if b is not None:
                            cand.append(b[b > fa])
        if not cand:
            continue
        cand = np.concatenate(cand)
        if cand.size == 0:
            continue
        near = cand[np.all((flo[cand] <= fhi[fa]) & (fhi[cand] >= flo[fa]), axis=1)]
        ia, na, da, ca, ua, hua, va, hva = A
        for fb in near.tolist():
            ib, nb, db, cb, ub, hub, vb, hvb = faces[fb]
            if ia == ib or looks[fa] == looks[fb] or float(na @ nb) < 0.9999 or abs(da - db) > tol:
                continue  # (one part; one look - the same pixels either way; not one plane)
            corners = [cb + su * hub * ub + sv * hvb * vb for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
            poly = [(float((q - ca) @ ua), float((q - ca) @ va)) for q in corners]
            for e in ((1, 0, hua), (-1, 0, hua), (0, 1, hva), (0, -1, hva)):
                poly = _zf_clip(poly, *e)
                if not poly:
                    break
            if len(poly) < 3:
                continue
            area = _zf_area(poly)
            if area <= min_area:
                continue
            if all(buried(ca + ua * u + va * v + na * 0.05, (ia, ib)) for u, v in _zf_probes(poly)):
                continue
            mu = sum(q[0] for q in poly) / len(poly)
            mv = sum(q[1] for q in poly) / len(poly)
            at = ca + ua * mu + va * mv
            ceiling = bool(na[1] < -0.7)
            if ceiling:  # (an underside: only where a floor lies under it, a head's room below)
                skip = {k for k, o in enumerate(floor_owner) if o in (ia, ib)}
                gap = _zf_floor_below(at + na * 0.01, floor_boxes, grounds, skip)
                if gap is None or gap + 0.01 < ZFIGHT_CEIL_CLEAR - 1e-6:
                    continue
            pa, pb = seen[ia], seen[ib]
            pairs.append({"a": pa.get("name"), "b": pb.get("name"), "area": round(area, 2), "gap": round(abs(da - db), 3),
                          "at": [round(float(x), 1) for x in at],
                          "looks": [f"{pa.get('material')}", f"{pb.get('material')}"], "ceiling": ceiling})
    pairs.sort(key=lambda x: -x["area"])
    if not pairs:
        return [], []
    total = sum(x["area"] for x in pairs)
    top = pairs[0]
    ceil = sum(1 for x in pairs if x["ceiling"])
    errors = [f"z-fighting: {len(pairs)} pair(s) of faces of two looks lie in one plane and overlap ({total:.0f} sq studs; "
              f"the largest: \"{top['a']}\" ({top['looks'][0]}) and \"{top['b']}\" ({top['looks'][1]}), {top['area']:.0f} sq studs at "
              f"({top['at'][0]:.0f}, {top['at'][1]:.1f}, {top['at'][2]:.0f})"
              f"{', an underside seen from the floor below' if top['ceiling'] else ''})"
              f"{f' ({ceil} of them undersides: ceilings)' if ceil else ''} - they flicker in Roblox; move one face 0.08+ "
              f"studs clear of the other, or cut one where the other lies"]
    return errors, pairs


# ------------------------------------------------------------------ design checks (blueprint-level quality gates)
# Grandparented names: blueprints that existed before this check was introduced (2026-11-10).
# They warn instead of erroring so they don't block existing projects. New blueprints (name not in this set) fail.
_PRIMITIVE_GRANDFATHERED = frozenset({
    # selftest fixtures: they deliberately use primitives and are excluded from the design gate
    "SelftestTrap", "SelftestTrapFixed", "SelftestScale", "SelftestScaleFixed",
    "SelftestValley", "SelftestVaelmouth", "SelftestVaelmouthFixed",
    "SelftestTown", "SelftestTownTight",  # (the town-plan generator's pair: the layout is under test, not the look)
    "SelftestTownBent", "SelftestTownBentTight",  # (the same pair with "bend": 8)
    "SelftestTownSlope",  # (a town on a slope: the ground, the houses' levels and the claims are under test, not the look)
    "SelftestTownYards",  # (a bent town with dressed yards: where the yards' things stand is under test, not the look)
    "SelftestRooms",  # (a house cut into rooms: the walk through its doors is under test, not its look)
    "SelftestZFight", "SelftestZFightFixed",  # (two floors in one plane, and a house lifted clear: z-fighting under test)
})

# Generators that have a mesh-upgrade path and default to primitive parts when no mesh is supplied.
# key = blueprint step key, value = the JSON field that enables real meshes.
_MESH_GENERATORS = {
    "forest": "meshes",   # forest.meshes: [names] — real mesh trees; without it: procedural lollipop parts
    "tree": "mesh",       # tree.mesh: name — real mesh tree; without it: Trunk/Canopy/Needles primitives
    "rocks": "meshes",    # rocks.meshes: [names] — real scanned rocks; without it: tilted box clusters
}
# "building" always produces primitive wall parts; there is no mesh-building alternative in the compiler.
_BUILDING_ALWAYS_PRIMITIVE = True


def _find_blueprint(world_path, name):
    """Given a compiled world path (…/build/worlds/<Name>.json), try to find the matching blueprint.
    Looks for assets/worlds/<Name>.json at the same level as build/, and two levels up (a game inside a repo).
    Also checks kit/selftest/world/_<name_lower>.json for selftest fixtures."""
    build_dir = os.path.dirname(os.path.abspath(world_path))  # …/build/worlds
    root_candidates = [
        os.path.dirname(os.path.dirname(build_dir)),          # one up: <game>/
        os.path.dirname(os.path.dirname(os.path.dirname(build_dir))),  # two up: <repo>/
    ]
    for root in root_candidates:
        candidate = os.path.join(root, "assets", "worlds", f"{name}.json")
        if os.path.isfile(candidate):
            return candidate
        # selftest fixtures: kit/selftest/world/_<snake_case_name>.json
        # e.g. SelftestPrimitive → _selftest_primitive.json
        import re as _re
        snake = _re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
        selftest_candidate = os.path.join(root, "kit", "selftest", "world", f"_{snake}.json")
        if os.path.isfile(selftest_candidate):
            return selftest_candidate
    return None


def _is_name(v):
    return isinstance(v, str) and bool(v.strip())


def _laid_steps(bp):
    """every step a blueprint comes to, its prefabs opened (kit/lib/worldprefab.luau Prefab.flat: the same list) - so
    a building is not hidden from the design gate by being put in a prefab"""
    steps = bp.get("build") or []
    prefabs = bp.get("prefabs")
    if not isinstance(prefabs, dict):
        return steps
    out = []

    def opened(items, depth):
        for step in items:
            spec = step.get("prefab") if isinstance(step, dict) and len(step) == 1 else None
            inner = prefabs.get(spec.get("name")) if isinstance(spec, dict) and isinstance(spec.get("name"), str) else None
            if isinstance(inner, list) and depth < 4 and len(out) < 8000:
                opened(inner, depth + 1)
            else:
                out.append(step)

    opened(steps, 0)
    return out


def design_lint(world_path, name, blueprint=None):
    """Check the blueprint for primitive-only generators (no mesh assets) that cap the world's visual quality.
    Faults found in a grandfathered blueprint are warnings; in a new blueprint they are errors. blueprint: the path the
    compiled world names (kit world flatten writes it; a game's build folder is no guide to a kit selftest fixture).
    Returns ([errors], [warnings], {stats})."""
    bp_path = blueprint if isinstance(blueprint, str) and os.path.isfile(blueprint) else _find_blueprint(world_path, name)
    if not bp_path:
        return [], [], {}
    try:
        with open(bp_path, encoding="utf-8") as fh:
            bp = json.load(fh)
    except (OSError, ValueError):
        return [], [], {}
    build_steps = _laid_steps(bp)
    faults = []
    for step in build_steps:
        if not isinstance(step, dict):
            continue
        for gen, mesh_field in _MESH_GENERATORS.items():
            spec = step.get(gen)
            if spec is None:
                continue
            if not spec.get(mesh_field):
                label = spec.get("name") or f"{gen} at {spec.get('center') or spec.get('pos') or '?'}"
                faults.append(f'design: "{gen}" step "{label}" uses only primitive parts — add "{mesh_field}": [<mesh names>] (scanned or generated) to reach AAA quality; graveyard: showcase_worlds_x5 2026-10-14')
        # (a building with a "skin" - a whole-building mesh, kit world meshes kind "gothic_house" - is seen as its mesh;
        # one with a "facade" - the prefix of its modules, kit/lib/worldfacade.luau - as its modules)
        if _BUILDING_ALWAYS_PRIMITIVE and step.get("building") is not None and not ((step["building"] or {}).get("skin") or _is_name((step["building"] or {}).get("facade"))):
            spec = step["building"]
            label = spec.get("name") or f"building at {spec.get('center') or '?'}"
            faults.append(f'design: "building" step "{label}" produces primitive box-and-wall geometry — replace with mesh buildings (kit world import) or a ruin / props assembly; graveyard: showcase_worlds_x5 2026-10-14')
        # (a "town" step is a plan of buildings: without "skins" every house of it is the same box-and-wall geometry)
        # ("skins" is a NAME: true, a number or a list skins nothing in the compiler, and is no way round this gate)
        _skins = step["town"].get("skins") if isinstance(step.get("town"), dict) else None
        if _BUILDING_ALWAYS_PRIMITIVE and isinstance(step.get("town"), dict) and not (isinstance(_skins, str) and _skins.strip()):
            label = step["town"].get("name") or "town"
            faults.append(f'design: "town" step "{label}" builds every house as primitive box-and-wall geometry — give it "skins": "<prefix>" and one house mesh per type (lune run kit world town <Name> lists the types); graveyard: showcase_worlds_x5 2026-10-14')
        # (a "city" step is a regular grid of box blocks with window bands: the same primitive look, and the layout the
        # town plan replaces - streets round a closed square, terraced lots, a landmark; the owner on the District,
        # 2026-10-31: "the city does not feel or look like a genuine proper open world")
        if _BUILDING_ALWAYS_PRIMITIVE and step.get("city") is not None:
            spec = step["city"] if isinstance(step["city"], dict) else {}
            label = spec.get("name") or f"city at {spec.get('center') or '?'}"
            faults.append(f'design: "city" step "{label}" is a regular grid of primitive box blocks — lay the place out with a "town" step (streets round a closed square, terraced lots, the landmark closing the gate street: lune run kit world town <Name>) and give it "skins"; graveyard: showcase_worlds_x5 2026-10-14')
    if not faults:
        return [], [], {"design_blueprint": bp_path}
    grandfathered = name in _PRIMITIVE_GRANDFATHERED
    if grandfathered:
        return [], [f"improve: {f}" for f in faults], {"design_blueprint": bp_path, "design_grandfathered": True}
    else:
        return faults, [], {"design_blueprint": bp_path}


# ------------------------------------------------------------------ lamps (the owner's District verdict, 2026-10-28)
# "I actually love this theme you went after ... this is beautiful ... I hate the fact that you added a lamp everywhere"
# (9/10, then "the public utility fixtures ... the lamps" on 2026-11-03). The kit's own row generator set a lamp every 24
# studs by default. A new world's lamps stand apart, each with a reason (a gate, a stair head, a crossing): the median
# lamp has fewer than LAMP_CROWD others within LAMP_REACH. The worlds that existed before the check (the
# _PRIMITIVE_GRANDFATHERED set) are not measured at all (their check output stays as it was).
LAMP_REACH = 80.0  # studs: the other lamps a lamp has within this reach (a pair across a street is 1)
LAMP_CROWD = 3  # the median lamp with this many others in reach = a lamp everywhere
LAMP_MIN = 6  # fewer lamps than this are a few lamps with a reason
LAMP_SAME = 4.0  # studs: parts of one lamp (its lit head on an arm, its mesh skin) closer than this are one lamp


def lamp_points(w):
    """the world's lamps, one point (x, z) each: a lit part named like a lamp (the row generator's LampHead, a Lamp /
    Lantern part with a light) or a lamp mesh placeholder, parts within LAMP_SAME merged into one lamp"""
    pts = []
    for p in w.get("parts") or []:
        if p.get("backdrop") or not isinstance(p.get("pos"), list) or len(p["pos"]) < 3:
            continue
        nm = str(p.get("name") or "").lower()
        mesh = str(p.get("mesh") or "").lower()
        lit = any(isinstance(c, dict) and c.get("kind") == "light" for c in p.get("children") or [])
        if (lit and ("lamp" in nm or "lantern" in nm)) or ("lamp" in mesh or "lantern" in mesh):
            try:
                pts.append((float(p["pos"][0]), float(p["pos"][2])))
            except (TypeError, ValueError):
                continue
    lamps = []
    for x, z in pts:
        if all((x - a) ** 2 + (z - b) ** 2 > LAMP_SAME ** 2 for a, b in lamps):
            lamps.append((x, z))
    return lamps


def lamp_spacing(w, f, rule):
    """[why ...]: a "lamp_spacing" claim held to its place's rule (SCALE_SHEETS lamp_spacing)
    { kind: "lamp_spacing", place: "avenue", from, to }: the lamps within LAMP_SIDE of the line, in order along it,
      stand rule.avenue apart, each on the other side of the line from the last
    { place: "lane", from, to, at: [[x, z], ...] }: every lamp within LAMP_SIDE of the line stands within rule.lane
      of a junction or a door it names
    { place: "square", pos, size: [w, h, d] }: every lamp on the square stands within rule.square of a corner"""
    place = f.get("place")
    if place not in LAMP_PLACES:
        return [f'"place" is one of {" | ".join(LAMP_PLACES)} (got {place!r})']
    lamps = lamp_points(w)
    if place == "square":
        size = f.get("size") or []
        if len(size) < 3:
            return ["a square's lamps need its size: [w, h, d]"]
        cx, cz = f["pos"][0], f["pos"][2]
        hw, hd = size[0] / 2, size[2] / 2
        corners = [(cx - hw, cz - hd), (cx + hw, cz - hd), (cx + hw, cz + hd), (cx - hw, cz + hd)]
        on = [(x, z) for x, z in lamps if abs(x - cx) <= hw + 1e-6 and abs(z - cz) <= hd + 1e-6]
        far = [(x, z) for x, z in on if min(math.dist((x, z), c) for c in corners) > rule["square"][1] + 1e-6]
        if far:
            x, z = far[0]
            return [f"{len(far)} lamp(s) stand off the square's corners (a square is lit at its corners, within "
                    f"{rule['square'][1]:.0f} studs), e.g. one at ({x:.0f}, {z:.0f})"]
        return []
    a, b = f.get("from"), f.get("to")
    if not (a and b) or math.dist(a, b) < 1e-6:
        return [f"a {place}'s lamps need from / to (its centre line)"]
    L = math.dist(a, b)
    ux, uz = (b[0] - a[0]) / L, (b[1] - a[1]) / L
    on = []
    for x, z in lamps:
        t = (x - a[0]) * ux + (z - a[1]) * uz
        side = (x - a[0]) * -uz + (z - a[1]) * ux
        if -1e-6 <= t <= L + 1e-6 and abs(side) <= LAMP_SIDE:
            on.append((t, side, x, z))
    on.sort()
    if place == "lane":
        at = [p for p in f.get("at") or [] if isinstance(p, (list, tuple)) and len(p) == 2]
        far = [(x, z) for _, _, x, z in on if not at or min(math.dist((x, z), p) for p in at) > rule["lane"][1] + 1e-6]
        if far:
            x, z = far[0]
            return [f"{len(far)} lamp(s) on the lane stand where it names no junction or door (\"at\"; within "
                    f"{rule['lane'][1]:.0f} studs), e.g. one at ({x:.0f}, {z:.0f}) - a lane is lit only where it meets "
                    "another or at a door"]
        return []
    lo, hi = rule["avenue"]
    if len(on) < 2:
        return [f"an avenue's lamps: {len(on)} found within {LAMP_SIDE:.0f} studs of its line (it is lit along its length)"]
    out = []
    for (t0, s0, x0, z0), (t1, s1, x1, z1) in zip(on, on[1:]):
        gap = t1 - t0
        if not _within(gap, (lo, hi)):
            out.append(f"two lamps {gap:.0f} studs apart along the avenue at ({x0:.0f}, {z0:.0f}) and ({x1:.0f}, "
                       f"{z1:.0f}) (wants {lo:.0f}..{hi:.0f})")
        if s0 * s1 >= 0:
            out.append(f"two lamps in a row on one side of the avenue at ({x0:.0f}, {z0:.0f}) and ({x1:.0f}, {z1:.0f})"
                       " (each on the other side from the last)")
    return out[:3]


def lamp_density(w, name):
    """([errors], [warnings], {stats}): one point per lamp - a lit part named like a lamp (the row generator's LampHead,
    a Lamp / Lantern part with a light) or a lamp mesh placeholder, parts within LAMP_SAME merged - and how many other
    lamps each has within LAMP_REACH (a crowd, not a spacing: a street lit on both sides pairs lamps across it)"""
    if name in _PRIMITIVE_GRANDFATHERED:
        return [], [], {}
    pts = []
    for p in w.get("parts") or []:
        if p.get("backdrop") or not isinstance(p.get("pos"), list) or len(p["pos"]) < 3:
            continue
        nm = str(p.get("name") or "").lower()
        mesh = str(p.get("mesh") or "").lower()
        lit = any(isinstance(c, dict) and c.get("kind") == "light" for c in p.get("children") or [])
        if (lit and ("lamp" in nm or "lantern" in nm)) or ("lamp" in mesh or "lantern" in mesh):
            try:
                pts.append((float(p["pos"][0]), float(p["pos"][2])))
            except (TypeError, ValueError):
                continue
    if not pts:
        return [], [], {"lamps": 0}
    from scipy.spatial import cKDTree

    arr = np.array(pts, float)
    tree = cKDTree(arr)
    taken = np.zeros(len(arr), bool)
    lamps = []
    for i in range(len(arr)):  # (one lamp per cluster of its parts)
        if taken[i]:
            continue
        for j in tree.query_ball_point(arr[i], LAMP_SAME):
            taken[j] = True
        lamps.append(arr[i])
    stats = {"lamps": len(lamps)}
    if len(lamps) < LAMP_MIN:
        return [], [], stats
    lamps = np.array(lamps)
    near = np.array([len(n) - 1 for n in cKDTree(lamps).query_ball_point(lamps, LAMP_REACH)])
    crowd = float(np.median(near))
    stats["lamp_crowd_median"] = crowd
    if crowd < LAMP_CROWD:
        return [], [], stats
    return [f"design: a lamp everywhere - {len(lamps)} lamps, the median one has {crowd:.0f} others within {LAMP_REACH:.0f} studs "
            "(keep a lamp only where it has a reason: a gate, a stair head, a crossing - a pair across a street counts as one "
            "stop; light comes from the moon, fires and windows) - the owner on the District, 2026-10-28: \"I hate the fact "
            "that you added a lamp everywhere\""], [], stats


# ------------------------------------------------------------------ STEEP LAND WITH NO ROCK (V3 stage E.3)
# LIMITATIONS_FIXES_V3.md stage E.3: "auto-scatter biome-graded photoscan rock / cliff skirts wherever terrain slope
# > 42 deg". Roblox terrain is 4-stud voxels: a slope that steep reads as a staircase of grass and mud, never a cliff
# (the cliffs step: "Roblox terrain cannot hold a sharp cliff"). Measured on the play land's own height samples, past
# the outer STEEP_RIM studs (the cliffs step leaves the land's rim alone too): a sample steeper than STEEP_SLOPE is
# covered when a rock / cliff / boulder / scree part or mesh stands within its own half-width + STEEP_REACH. A new
# world whose bare steep land is more than STEEP_BARE_MAX of its play land FAILS (give it a "cliffs" step with rock
# faces, or soften the land); the worlds built before this gate warn "improve:" (measured 2026-11-19: SampleRegion 29 %,
# SamplePeak 32 %, the terrain selftests 3..30 %). NOT measured: whether the rocks look right, or are the right rocks.
STEEP_SLOPE = 42.0  # degrees
STEEP_BARE_MAX = 0.01  # share of the play land (past the rim)
STEEP_RIM = 48.0  # studs in from the land's edge
STEEP_REACH = 6.0  # studs past a rock's half-width that it covers
STEEP_ROCK_WORDS = ("rock", "cliff", "boulder", "scree", "crag")  # ("spire", "face": a church spire, a "Surface" part)
_STEEP_GRANDFATHERED = _PRIMITIVE_GRANDFATHERED | frozenset({
    "BigTerrain", "SelftestTerrainForged", "SelftestTerrainRivers", "SelftestTerrainV1", "SelftestValley",
})


def steep_lint(w, name):
    """([errors], [warnings], {stats}): the play land steeper than STEEP_SLOPE with no rock on it"""
    grounds = [g for g in (w.get("terrain") or {}).get("ground", []) if not g.get("backdrop")]
    if not grounds:
        return [], [], {}
    rocks = []
    for q in w.get("parts") or []:
        words = (str(q.get("name") or "") + " " + str(q.get("mesh") or "")).lower()
        if any(r in words for r in STEEP_ROCK_WORDS) and isinstance(q.get("size"), list) and isinstance(q.get("pos"), list):
            rocks.append((float(q["pos"][0]), float(q["pos"][2]), max(float(q["size"][0]), float(q["size"][2])) / 2))
    R = np.array(rocks, float) if rocks else np.zeros((0, 3))
    land = steep = bare = 0
    where = None
    for g in grounds:
        nx, nz, st = int(g["nx"]), int(g["nz"]), float(g["step"])
        H = np.array(g["heights"], float).reshape(nx, nz)
        if nx < 3 or nz < 3:
            continue
        gx, gz = np.gradient(H, st)
        slope = np.degrees(np.arctan(np.hypot(gx, gz)))
        xs = float(g["x0"]) + np.arange(nx) * st
        zs = float(g["z0"]) + np.arange(nz) * st
        inner_x = (xs - xs[0] >= STEEP_RIM) & (xs[-1] - xs >= STEEP_RIM)
        inner_z = (zs - zs[0] >= STEEP_RIM) & (zs[-1] - zs >= STEEP_RIM)
        inner = np.outer(inner_x, inner_z)
        land += int(inner.sum())
        idx = np.argwhere(inner & (slope > STEEP_SLOPE))
        steep += len(idx)
        for i, j in idx:
            x, z = xs[i], zs[j]
            if len(R) and np.any((R[:, 0] - x) ** 2 + (R[:, 1] - z) ** 2 <= (R[:, 2] + STEEP_REACH) ** 2):
                continue
            bare += 1
            if where is None:
                where = (x, z, float(slope[i, j]))
    stats = {"steep_samples": steep, "steep_bare": bare, "steep_bare_share": round(bare / land, 4) if land else 0.0}
    if not land or bare / land <= STEEP_BARE_MAX:
        return [], [], stats
    x, z, sl = where
    say = (f"{100 * bare / land:.1f} % of the play land is steeper than {STEEP_SLOPE:.0f} deg with no rock on it (Roblox's "
           f"4-stud voxels draw it as a staircase, never a cliff), e.g. at ({x:.0f}, {z:.0f}), {sl:.0f} deg - give it a "
           "\"cliffs\" step with rock faces, or soften the land (LIMITATIONS_FIXES_V3.md stage E.3)")
    if name in _STEEP_GRANDFATHERED:
        return [], [f"improve: {say}"], stats
    return [f"steep: {say}"], [], stats


# ------------------------------------------------------------------ the terrain ROUTE (the owner's SampleRegion_terrain_v1)
# The owner on SampleRegion's first terrain (2026-10-14): "the quality of the terrain is horrid" - land from noise + thermal
# erosion alone (graveyard SampleRegion_terrain_v1; the route he was given: rivers (stream-power incision) + the painter,
# or real elevation data). A ROUTE gate, never a look gate: every heightmap a world's blueprint uses (play land and far
# ring) must record the river route (kit world terrain --stream > 0) or real land (a DEM fetched by kit world dem, used
# by its design's "dem" or --from), and the claim is PROVED: kit/world/terrain.py is re-run on the recorded recipe and
# must give the same heights (a flag written into the metadata alone never passes), then the route must have done the
# work - re-made WITHOUT its river step the land must move (a token --stream 1 does not), or the land must follow the
# real elevation (a DEM at "relief": 0.001 under noise does not). A ground op making relief from noise, or carrying its
# own heights, has no route at all. The look stays the owner's verdict. Why not measure the land instead: ~45 slope,
# drainage and shape measures on a 9-pair A/B made with terrain.py (rivers on / off, same design + seed) never told the
# two apart - on a designed vale the river step moves the interior ~2 studs and cuts in the 128-stud band at the map
# edge (kit lesson world, board/plans/archive/2026-11-10-terrain-route-evidence.md). Grandfathered by CONTENT where it is used
# (the blueprint + sha1 of the heights / of the ground op, as kit/anim/clip.py's _SWITCH_GATE_GRANDFATHERED): the
# terrains made the old way before this gate warn "improve:"; re-made, or used anywhere else, they fail.
_TERRAIN_ROUTE_GRANDFATHERED = {
    ("kit/selftest/world/_selftest_valley.json", "8c5806fd85ff22eb55d57ec257dd0906bb231079"): "_selftest_valley.hm.json (2026-10-13)",
}
ROUTE_TOLERANCE = 0.05  # studs: the re-made heights must match the file's (2-decimal) heights this closely
RIVER_EFFECT_MIN = 0.03  # the river step's OWN cut (the recipe re-made with erosion 0 + thermal 0, with vs without its
#   rivers: the droplets after it are chaotic) >= 3 % of the relief on average - the kit's recipe (stream 80 / K 0.015)
#   cuts 6.3-25 % (SampleRegion 6.7, its far ring 9.0, SamplePeak 6.3, fbm 22), a token (stream 1 / 5, K 0.001) 0.1-1.9 %
DEM_FOLLOW_MIN = 0.6  # real land: the heights' correlation with the elevation they were made from
ROUTE_CACHE = os.path.join("build", "worlds", "checks", "terrain_routes.json")  # the proofs, keyed by content
_ROUTE_PROOF = 2  # (the proof's version: a cached proof of an older version is made again)
_HERE = os.path.dirname(os.path.abspath(__file__))
_TERRAIN_PY = os.path.join(_HERE, "terrain.py")
_ROUTE_RULE = ("the route the owner's verdict on SampleRegion_terrain_v1 rules out (\"the quality of the terrain is horrid\": "
               "noise + thermal erosion alone)")
_ROUTE_NOTE = "a route gate: it holds how the land is made; the look stays the owner's verdict"


def _heights_hash(hm):
    """sha1 of the heights as loaded (json.dumps) - the content a grandfathered terrain is known by"""
    return hashlib.sha1(json.dumps(hm.get("heights")).encode()).hexdigest()


def _json_hash(obj):
    return hashlib.sha1(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def _file_sha1(path):
    h = hashlib.sha1()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _num(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _project_rel(path):
    """a path as the kit writes it: relative to the project root (the working directory), with forward slashes"""
    try:
        return os.path.relpath(os.path.abspath(path)).replace(os.sep, "/")
    except ValueError:  # (another drive)
        return os.path.abspath(path).replace(os.sep, "/")


def _game_root(bp_path):
    """<game>/assets/worlds/<Name>.json -> <game> (its heightmap sources and recipes are written relative to it)"""
    d = os.path.dirname(os.path.abspath(bp_path))
    if os.path.basename(d) == "worlds" and os.path.basename(os.path.dirname(d)) == "assets":
        return os.path.dirname(os.path.dirname(d))
    return None


def _active_game_root():
    """the kit's active game folder, as Config.game finds it (KIT_GAME, else games/.active), or None"""
    name = (os.environ.get("KIT_GAME") or "").strip()
    if not name:
        try:
            with open(os.path.join("games", ".active"), encoding="utf-8") as fh:
                name = fh.read().strip()
        except OSError:
            name = ""
    if not name or name == "none" or not os.path.isdir(os.path.join("games", name)):
        return None
    return os.path.join("games", name)


def _resolve(rel, bases):
    """a path the kit wrote (game-relative or project-relative, like Config.resolve) -> an existing file, or None"""
    if not isinstance(rel, str) or not rel:
        return None
    if os.path.isabs(rel):
        return rel if os.path.isfile(rel) else None
    for b in bases:
        if b is None:
            continue
        p = os.path.join(b, rel)
        if os.path.isfile(p):
            return p
    return None


def _recipe_file(rel, bases, hm_path, kind=None):
    """a file the recipe names (its design / source image) -> an existing file, or None: as written (game- or
    project-relative), else beside the heightmap by its file name, else (a design) beside it as <stem>.design.json -
    kit world terrain keeps a terrain's design next to it under the same stem (SampleRegion.hm.json, SampleRegion.design.json)"""
    found = _resolve(rel, bases)
    if found or not isinstance(rel, str) or not rel:
        return found
    here = os.path.dirname(os.path.abspath(hm_path))
    cands = [os.path.join(here, os.path.basename(rel))]
    if kind == "design":
        cands.append(os.path.join(here, os.path.basename(hm_path).split(".")[0] + ".design.json"))
    return next((c for c in cands if os.path.isfile(c)), None)


def _dem_sidecar_ok(path):
    """real elevation = a DEM fetched by kit world dem: its sidecar (kit/world/dem.py sidecar()) records the source,
    the box and the real width"""
    try:
        with open(os.path.splitext(str(path))[0] + ".json", encoding="utf-8") as fh:
            m = json.load(fh)
    except (OSError, ValueError):
        return False
    if not isinstance(m, dict):
        return False
    box = m.get("bbox")
    return (isinstance(m.get("source"), str) and m["source"].strip() != "" and _num(m.get("width_m")) > 0
            and isinstance(box, list) and len(box) == 4 and all(isinstance(v, (int, float)) for v in box))


def _recipe_text(opts, how=None):
    """the recorded recipe in words: 'a design + 90000 erosion droplets + thermal erosion x20, no rivers'"""
    base = "a design" if opts.get("design") else ("an image" if opts.get("from") else "noise")
    base += {"dem": " on a DEM", "from": " (a DEM)"}.get(how, "")
    bits = [base]
    if _num(opts.get("erosion")) > 0:
        bits.append(f"{_num(opts.get('erosion')):.0f} erosion droplets")
    if _num(opts.get("thermal")) > 0:
        bits.append(f"thermal erosion x{_num(opts.get('thermal')):.0f}")
    s = _num(opts.get("stream"))
    return " + ".join(bits) + (f", rivers (stream {s:g})" if s > 0 else ", no rivers")


def _route_of(opts, bases, hm_path):
    """the route a recipe claims -> (route "rivers" | "real land" | None, the design file, the real-land file, how it
    was used: "dem" (the design's) | "from" (the base image))"""
    design = _recipe_file(opts.get("design"), bases, hm_path, "design") if opts.get("design") else None
    land, how = None, None
    if design:
        try:
            with open(design, encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, ValueError):
            d = None
        dem = d.get("dem") if isinstance(d, dict) else None
        if isinstance(dem, dict) and isinstance(dem.get("file"), str) and dem["file"]:
            # (where terrain.py's dem_base looks: as written, then beside the design)
            near = os.path.join(os.path.dirname(os.path.abspath(design)), dem["file"])
            land = dem["file"] if os.path.isfile(dem["file"]) else (near if os.path.isfile(near) else dem["file"])
            how = "dem"
    if land is None and opts.get("from"):
        img = _recipe_file(opts["from"], bases, hm_path)
        if img and _dem_sidecar_ok(img):  # (a base image is real land only with kit world dem's sidecar)
            land, how = img, "from"
    if _num(opts.get("stream")) > 0:
        return "rivers", design, land, how
    if land:
        return "real land", design, land, how
    return None, design, None, None


def _load_kit_module(name):
    """kit/world/<name>.py as a module: the generator's own loaders read the land the way it was made"""
    import importlib.util

    spec = importlib.util.spec_from_file_location(f"kit_world_{name}_for_check", os.path.join(_HERE, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _remake(hm, opts, design, bases, hm_path, route=None, land=None, how=None, timeout=900):
    """PROVE a claimed route: kit/world/terrain.py re-run on the recorded recipe must give the same heights; then the
    route must have done the work - rivers: re-made WITHOUT the river step, the land moves >= RIVER_EFFECT_MIN of its
    relief; real land: a kit world dem sidecar, and the heights follow the elevation (r >= DEM_FOLLOW_MIN).
    -> {"ok", "max_dh", "why" (could not re-make it: never cached), "fault" (the route did not do the work), ...}"""
    import shutil
    import subprocess
    import tempfile

    def fail(why):
        return {"ok": False, "max_dh": None, "why": why}

    if hm.get("made_by") != "kit/world/terrain.py":
        return fail(f"it was not made by kit world terrain (made_by {hm.get('made_by')!r}): no recipe to re-make")
    try:
        mine = np.asarray(hm.get("heights") or [], float)
    except (TypeError, ValueError):
        return fail("its heights are not all numbers")
    args = []
    for k, v in opts.items():
        if k in ("design", "from", "flat", "stamp", "sink") or isinstance(v, bool) or not isinstance(v, (int, float)):
            continue  # (the generator's numeric flags; the files and flats below)
        args += [f"--{k}", repr(float(v))]
    if opts.get("design"):
        if not design:
            return fail(f"its design {opts['design']} is missing")
        args += ["--design", os.path.abspath(design)]
    if opts.get("from"):
        img = _recipe_file(opts["from"], bases, hm_path)
        if not img:
            return fail(f"its source image {opts['from']} is missing")
        args += ["--from", os.path.abspath(img)]
    try:
        for f in opts.get("flat") or []:
            args += ["--flat", ",".join(repr(float(x)) for x in f)]
    except (TypeError, ValueError):
        return fail(f"its recorded flats are not [x, z, r] numbers: {opts.get('flat')!r}")
    # land forms placed by name are part of the recipe (kit/world/terrain.py --stamp). The "worked" ones are in the
    # land the rivers cut, so every re-make lays them; the others are laid on the finished land, so only the re-make
    # of the land itself has them (a tall cone laid afterwards must not thin the river step's share of the relief)
    laid_after = []
    recorded = opts.get("stamp")
    if recorded is not None:
        if not isinstance(recorded, list) or not all(isinstance(st, str) for st in recorded):
            return fail(f"its recorded stamps are not a list of texts: {recorded!r}")
        for st in recorded:
            if st.strip().endswith(",worked"):
                args += ["--stamp", st]
            else:
                laid_after += ["--stamp", st]
    # where the rivers drain inside the land (--sink) is part of the heights' recipe: every re-make drains the same
    sunk = opts.get("sink")
    if sunk is not None:
        if not isinstance(sunk, list) or not all(isinstance(st, str) for st in sunk):
            return fail(f"its recorded sinks are not a list of texts: {sunk!r}")
        for st in sunk:
            args += ["--sink", st]
    tmp = tempfile.mkdtemp(prefix="kit_terrain_route_")

    def make(extra, tag):
        out = os.path.join(tmp, f"{tag}.hm.json")
        try:
            r = subprocess.run([sys.executable, _TERRAIN_PY, out] + args + extra + ["--no-paint"], capture_output=True,
                               text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return None, f"kit/world/terrain.py did not finish re-making it in {timeout} s"
        if r.returncode != 0 or not os.path.isfile(out):
            tail = ((r.stderr or "").strip().splitlines() or (r.stdout or "").strip().splitlines() or ["?"])[-1][:160]
            return None, f"kit/world/terrain.py could not re-make it ({tail})"
        with open(out, encoding="utf-8") as fh:
            again = json.load(fh)
        return again, None

    try:
        again, why = make(laid_after, "remade")
        if why:
            return fail(why)
        theirs = np.asarray(again.get("heights") or [], float)
        if mine.size == 0 or mine.shape != theirs.shape or (hm.get("nx"), hm.get("nz")) != (again.get("nx"), again.get("nz")):
            return {"ok": False, "max_dh": None, "why": None, "grid": f"{again.get('nx')}x{again.get('nz')} instead of {hm.get('nx')}x{hm.get('nz')}"}
        dh = float(np.max(np.abs(mine - theirs)))
        proof = {"ok": dh <= ROUTE_TOLERANCE, "max_dh": round(dh, 3), "why": None}
        if not proof["ok"]:
            return proof
        if route == "rivers":
            # the river step's own cut: the recipe without the (chaotic) droplets and thermal after it, with vs without
            # its rivers - a token stream barely moves the land
            wet, why = make(["--erosion", "0", "--thermal", "0"], "rivers_only")
            dry, why2 = (None, why) if why else make(["--stream", "0", "--erosion", "0", "--thermal", "0"], "no_rivers")
            if why or why2:
                return fail(why or why2)
            a = np.asarray(wet.get("heights") or [], float)
            b = np.asarray(dry.get("heights") or [], float)
            if a.size == 0 or a.shape != b.shape:
                return fail("its recipe without erosion gives another grid")
            cut = float(np.mean(np.abs(a - b)))
            share = cut / (float(a.max() - a.min()) or 1.0)
            proof["cut"], proof["effect"] = round(cut, 2), round(share, 4)
            if share < RIVER_EFFECT_MIN:
                proof["ok"] = False
                proof["fault"] = (f"its river step barely carved the land: on its own it cuts only {cut:.2f} studs on average "
                                  f"({share * 100:.1f} % of the relief; the kit's river recipe, stream 80 / streamK 0.015, cuts "
                                  f"6-25 %, the floor is {RIVER_EFFECT_MIN * 100:.0f} %) - a token stream")
        elif route == "real land":
            if not _dem_sidecar_ok(land):
                proof["ok"] = False
                proof["fault"] = (f"{os.path.basename(str(land))} has no kit world dem sidecar (source, bbox, width_m): only "
                                  "elevation fetched by kit world dem counts as real land")
            else:
                n = int(_num(hm.get("nx")))
                try:
                    if how == "dem":
                        base, _ = _load_kit_module("dem").load(land, n)
                    else:
                        base = _load_kit_module("terrain").from_image(land, n)
                    base = np.asarray(base, float).ravel()
                except Exception as e:  # (an unreadable DEM: not proved; tried again next time)
                    return fail(f"its elevation {os.path.basename(str(land))} cannot be read ({type(e).__name__})")
                ok_std = base.size == mine.size and base.std() > 0 and mine.std() > 0
                r = float(np.corrcoef(base, mine)[0, 1]) if ok_std else 0.0
                proof["follow"] = round(r, 3)
                if not r >= DEM_FOLLOW_MIN:
                    proof["ok"] = False
                    proof["fault"] = (f"its heights follow the elevation by only r = {r:.2f} (the floor is {DEM_FOLLOW_MIN}): the "
                                      "noise and shapes on top make this land, not the real elevation")
        return proof
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _route_cache_load(path):
    try:
        with open(path, encoding="utf-8") as fh:
            c = json.load(fh)
        return c if isinstance(c, dict) else {}
    except (OSError, ValueError):
        return {}


def _route_cache_save(path, new):
    """merge new proofs into the proofs file (another check may have written since it was read)"""
    if not new:
        return
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        cur = _route_cache_load(path)
        cur.update(new)
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(cur, fh, indent=1, sort_keys=True)
        os.replace(tmp, path)
    except OSError:
        pass  # (a proof not kept is only made again)
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass


def terrain_route(world_path, name, blueprint=None, cache_path=None, use_cache=True):
    """The terrain route gate: every heightmap the blueprint uses records rivers (stream > 0) or real land (a kit world
    dem DEM), PROVED by re-making it with kit/world/terrain.py (proofs cached by content in ROUTE_CACHE unless
    use_cache is false); a ground op making relief from noise or carrying its own heights has no route. A terrain
    without one is an error, a grandfathered one (_TERRAIN_ROUTE_GRANDFATHERED: blueprint + content) a warning.
    Returns ([errors], [warnings], {stats})."""
    import time

    bp_path = blueprint if isinstance(blueprint, str) and os.path.isfile(blueprint) else _find_blueprint(world_path, name)
    if not bp_path:
        return [], [], {}
    try:
        with open(bp_path, encoding="utf-8") as fh:
            bp = json.load(fh)
    except (OSError, ValueError):
        return [], [], {}
    terr = bp.get("terrain") if isinstance(bp, dict) else None
    if not isinstance(terr, list):
        return [], [], {}  # (no terrain list: nothing made, or the compiler refused it)
    bp_rel = _project_rel(bp_path)
    bases = [_game_root(bp_path), _active_game_root(), "", os.path.dirname(os.path.abspath(bp_path))]
    cache = None if use_cache else {}
    new = {}
    errors, warns, rows = [], [], []
    for i, t in enumerate(terr):
        if not isinstance(t, dict):
            continue
        g = t.get("ground")
        if isinstance(g, dict):
            noise = g.get("noise") if isinstance(g.get("noise"), dict) else {}
            amp = _num(noise.get("amplitude"))
            samples = g.get("samples")
            if isinstance(samples, dict) and samples.get("heights") is not None:
                what = "carries its own heights (samples) and no recorded recipe"
            elif amp != 0:
                what = f"makes its relief from noise (amplitude {amp:g})"
            else:
                continue  # (a flat ground: no land made)
            gsha = _json_hash(g)
            label = f"ground #{i + 1}{' (far ring)' if g.get('backdrop') else ''}"
            msg = f"terrain {label} {what} - {_ROUTE_RULE}"
            gfix = ("keep a ground flat (no noise), or make the land with kit world terrain on the river route (--stream 80 "
                    "--streamK 0.015) or from real land (a design \"dem\": kit world dem)")
            row = {"source": f"ground #{i + 1}", "content_sha1": gsha, "route": None}
            if (bp_rel, gsha) in _TERRAIN_ROUTE_GRANDFATHERED:
                warns.append(f"improve: {msg}; grandfathered by its content (made before this gate, 2026-11-10): changed, "
                             f"it must take the route - {gfix}")
                row["grandfathered"] = True
            else:
                errors.append(f"design: {msg}; {gfix}. ({_ROUTE_NOTE})")
            rows.append(row)
            continue
        op = t.get("heightmap")
        if not isinstance(op, dict):
            continue
        src = op.get("source")
        label = f"{src}{' (far ring)' if op.get('backdrop') else ''}"
        path = _resolve(src, bases)
        hm = None
        if path:
            try:
                with open(path, encoding="utf-8") as fh:
                    hm = json.load(fh)
            except (OSError, ValueError):
                hm = None
        if not isinstance(hm, dict) or not isinstance(hm.get("heights"), list):
            where = "cannot be read as a heightmap" if path else "cannot be found where the compiler looks (the blueprint's game, the active game, the project)"
            errors.append(f"design: terrain {label}: its heightmap {where} - its route cannot be checked; fix the source and "
                          f"re-compile the world. ({_ROUTE_NOTE})")
            rows.append({"source": src, "route": None, "missing": True})
            continue
        opts = hm.get("options") if isinstance(hm.get("options"), dict) else {}
        hsha = _heights_hash(hm)
        stem = os.path.basename(path).split(".")[0]
        fix = (f"re-make it on the river route (lune run kit world terrain {stem} --stream 80 --streamK 0.015"
               + (f" --design {opts['design']}" if isinstance(opts.get("design"), str) else "")
               + ") or from real land (a design \"dem\": kit world dem)")
        route, design, land, how = _route_of(opts, bases, path)
        row = {"source": src, "heights_sha1": hsha, "route": route}
        if route is None:
            notes = ""
            if opts.get("design") and not design:
                notes += f"; its design {opts['design']} is missing, so no \"dem\" can be seen"
            if opts.get("from"):
                notes += "; its base image has no kit world dem sidecar, so it is not real elevation"
            msg = f"terrain {label} was made without rivers or real elevation ({_recipe_text(opts)}{notes}) - {_ROUTE_RULE}"
            if (bp_rel, hsha) in _TERRAIN_ROUTE_GRANDFATHERED:
                warns.append(f"improve: {msg}; grandfathered by its heights' hash (made before this gate, 2026-11-10): "
                             f"re-made, or used in another world, it must take the route - {fix}")
                row["grandfathered"] = True
            else:
                errors.append(f"design: {msg}; {fix}. ({_ROUTE_NOTE})")
            rows.append(row)
            continue
        # a claimed route is PROVED: re-made from its recorded recipe, the heights must come back, and the route must
        # have done the work (cached by content)
        if cache is None:
            cache = _route_cache_load(cache_path or ROUTE_CACHE)
        try:
            key = _json_hash({
                "v": _ROUTE_PROOF, "route": route, "how": how, "heights": hsha, "nx": hm.get("nx"), "nz": hm.get("nz"),
                "recipe": opts, "design": _file_sha1(design) if design else None,
                "land": _file_sha1(land) if land and os.path.isfile(str(land)) else land,
            })
        except OSError as e:
            key, proof = None, {"ok": False, "max_dh": None, "why": f"its design / elevation cannot be read ({e})"}
        else:
            proof = cache.get(key)
        row["cached"] = key is not None and proof is not None
        if key is not None and proof is None:
            proof = _remake(hm, opts, design, bases, path, route, land, how)
            if proof.get("why") is None:  # (a proof either way is kept; "could not re-make it" is tried again)
                proof["terrain_py"] = _file_sha1(_TERRAIN_PY)[:12]
                proof["curve_py"] = _file_sha1(os.path.join(_HERE, "curve.py"))[:12]  # (a river's curve is made by it)
                proof["date"] = time.strftime("%Y-%m-%d")
                cache[key] = proof
                if use_cache:
                    new[key] = proof
        row["proved"] = bool(proof.get("ok"))
        for k in ("max_dh", "effect", "follow"):
            if k in proof:
                row[k] = proof[k]
        if not proof.get("ok"):
            claim = f"terrain {label} claims the {route} route ({_recipe_text(opts, how)})"
            if proof.get("why"):
                errors.append(f"design: {claim} but it cannot be proved: {proof['why']}; {fix}. ({_ROUTE_NOTE})")
            elif proof.get("fault"):
                errors.append(f"design: {claim} but {proof['fault']}; {fix}. ({_ROUTE_NOTE})")
            else:
                apart = f"a {proof['grid']} grid" if proof.get("grid") else f"heights up to {proof.get('max_dh')} studs apart"
                errors.append(f"design: {claim} but its heights do not come from that recipe: kit/world/terrain.py re-run on it "
                              f"gives {apart} (a recipe in the metadata is proved, never trusted); {fix}. ({_ROUTE_NOTE})")
        rows.append(row)
    if use_cache:
        _route_cache_save(cache_path or ROUTE_CACHE, new)
    return errors, warns, {"terrain_routes": rows}

def run(world_path, out_dir):
    with open(world_path, encoding="utf-8") as fh:
        w = json.load(fh)
    # the world's meshes: <root>/build/worlds/<Name>.json -> <root>/build/worldmeshes
    mesh_hulls(w, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(world_path))), "worldmeshes"))
    name = w.get("name") or os.path.splitext(os.path.basename(world_path))[0]
    P = dict(PLAYER)
    P.update(w.get("player") or {})
    C = dict(CHECKS)
    C.update(w.get("checks") or {})
    solids = [p for p in w["parts"] if is_solid(p) and not p.get("backdrop")]
    if not solids and not (w.get("terrain") or {}).get("ground"):
        return {"status": "fail", "summary": "nothing solid to stand on", "next_action": "add a floor / terrain ground"}
    los, his = [], []
    for p in solids:
        a, b = part_aabb(p)
        los.append(a)
        his.append(b)
    for gr in [g for g in (w.get("terrain") or {}).get("ground", []) if not g.get("backdrop")]:
        hs = np.array(gr["heights"], float)
        los.append([gr["x0"], hs.min() - 2, gr["z0"]])
        his.append([gr["x0"] + (gr["nx"] - 1) * gr["step"], hs.max(), gr["z0"] + (gr["nz"] - 1) * gr["step"]])
    # (the terrain's own solids are land too: a grid that stops over the ground would cut an arch or a ridge off and
    # call its top reachable)
    for op in (w.get("terrain") or {}).get("solids", []):
        sp = op.get("spec") or {}
        if op.get("kind") == "sdf":
            a, b = _load_kit_module("sdf").bounds(sp)
        elif op.get("kind") == "ball" and sp.get("center") and sp.get("radius"):
            a, b = [c - sp["radius"] for c in sp["center"]], [c + sp["radius"] for c in sp["center"]]
        elif op.get("kind") == "block" and sp.get("center") and sp.get("size"):
            a, b = [sp["center"][k] - sp["size"][k] / 2 for k in range(3)], [sp["center"][k] + sp["size"][k] / 2 for k in range(3)]
        elif op.get("kind") == "cylinder" and sp.get("center") and sp.get("radius") and sp.get("height"):
            half = [sp["radius"], sp["height"] / 2, sp["radius"]]
            a, b = [sp["center"][k] - half[k] for k in range(3)], [sp["center"][k] + half[k] for k in range(3)]
        else:
            continue
        if los:  # (only as far as the world goes sideways: a far-off solid does not widen the map)
            a = [max(a[0], min(l[0] for l in los)), a[1], max(a[2], min(l[2] for l in los))]
            b = [min(b[0], max(h[0] for h in his)), b[1], min(b[2], max(h[2] for h in his))]
            if a[0] > b[0] or a[2] > b[2]:
                continue
        los.append(a)
        his.append(b)
    lo = np.min(los, axis=0) - [2, 2, 2]
    hi = np.max(his, axis=0) + [2, P["height"] + 4, 2]
    res = float(C["res"])
    area = (hi[0] - lo[0]) * (hi[2] - lo[2])
    if area / res**2 > 400_000:  # big maps: 2-stud cells keep it to seconds
        res = 2.0
    g = Grid(lo, hi, res)
    for gr in [g for g in (w.get("terrain") or {}).get("ground", []) if not g.get("backdrop")]:
        g.fill_ground(gr)
    for op in (w.get("terrain") or {}).get("solids", []):
        g.fill_solid(op)
    for p in solids:
        g.fill_part(p)
    L = standable_levels(g, P["height"])
    n, src, dst, cost = build_graph(g, L, P)
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import breadth_first_order, dijkstra

    A = csr_matrix((np.ones(len(src)), (src, dst)), shape=(n, n))
    W = csr_matrix((cost * res, (src, dst)), shape=(n, n))
    nx_, nz_, K = L.shape
    valid = (L >= 0).ravel()
    spawns = [p for p in w["parts"] if p.get("spawn")]
    starts = []
    for s in spawns:
        top = np.array(s["pos"], float) + [0, s["size"][1] / 2 + 0.5, 0]
        nd = nearest_node(g, L, top)
        if nd is not None:
            starts.append((s, nd))
    objectives = [(o.get("name", f"objective {i + 1}"), nearest_node(g, L, o["pos"]), o["pos"]) for i, o in enumerate(w.get("objectives") or [])]
    errors, warns = [], []
    if not spawns:
        warns.append("no spawn: nothing to walk from (add a spawn step)")
    reach = np.zeros(n, bool)
    for _, nd in starts:
        reach[breadth_first_order(A, nd, directed=True, return_predecessors=False)] = True
    back = np.zeros(n, bool)
    AT = A.T.tocsr()
    for _, nd in starts:
        back[breadth_first_order(AT, nd, directed=True, return_predecessors=False)] = True
    # spawn <-> spawn and spawn -> objective
    dist_from = {}
    for s, nd in starts:
        dist_from[nd] = dijkstra(W, directed=True, indices=nd)
    for i, (s, nd) in enumerate(starts):
        for j, (s2, nd2) in enumerate(starts):
            if i != j and not np.isfinite(dist_from[nd][nd2]):
                errors.append(f"spawn at ({s['pos'][0]:.0f}, {s['pos'][2]:.0f}) cannot reach the spawn at ({s2['pos'][0]:.0f}, {s2['pos'][2]:.0f}) — add stairs / a ramp / a door")
        for oname, ond, opos in objectives:
            if ond is None:
                errors.append(f'objective "{oname}" at {opos} has no floor to stand on')
            elif not np.isfinite(dist_from[nd][ond]):
                errors.append(f'spawn at ({s["pos"][0]:.0f}, {s["pos"][2]:.0f}) cannot reach objective "{oname}"')
    # the rig's scale sheet: a door / stair / rail / ceiling / lane out of scale is an ERROR
    serr, sstats = scale_check(w, g)
    errors.extend(serr)
    # traps: reachable, but no way back to any spawn
    fine_ok = []  # what the finer local check cleared (the coarse grid's quantization), reported in stats
    trap = reach & ~back & valid
    trap_cells = int(trap.sum())
    trap_pos = []
    if trap_cells:
        from scipy.ndimage import label as _label

        ids = np.nonzero(trap)[0]
        x, z, k = ids // (nz_ * K), (ids // K) % nz_, ids % K
        wx = g.lo[0] + (x + 0.5) * res
        wz = g.lo[2] + (z + 0.5) * res
        # POCKET by pocket (connected trap columns): one sum over the map named a pocket "near" a spot between pockets
        # 500 studs apart. On a coarse map each pocket is walked again at 1-stud cells; one the fine walk can get
        # in AND out of is the grid's quantization (fine_rechecked), every other counts. The gate is unchanged: the
        # trap area that remains still errors past trap_cells.
        grid2 = np.zeros((nx_, nz_), bool)
        grid2[x, z] = True
        lab, n_lab = _label(grid2, structure=np.ones((3, 3), bool))
        pid = lab[x, z]
        kept = np.zeros(len(ids), bool)
        for i_p in range(1, n_lab + 1):
            sel = pid == i_p
            cells = int(sel.sum())
            if cells * res * res < 4:  # (a pocket smaller than a 2 x 2 body is voxel noise, not a trap)
                continue
            pos = [round(float(np.mean(wx[sel])), 1), round(float(np.mean(wz[sel])), 1)]
            fine = None
            if res > 1 and cells < C["trap_cells"]:
                ty = float(g.lo[1] + np.median(L[x[sel], z[sel], k[sel]]) * res)
                fine = fine_trap(pos, ty, g, L, reach, back, solids, w.get("terrain") or {}, P)
            if fine is not None and fine < 4:
                fine_ok.append({"trap": pos, "coarse_sq_studs": round(cells * res * res), "fine_sq_studs": fine})
            else:
                kept |= sel
        trap_cells = int(kept.sum())
        if trap_cells:
            kx, kz, kk = x[kept], z[kept], k[kept]
            kwx, kwz = wx[kept], wz[kept]
            # the biggest remaining pocket is the one named
            big = max(range(1, n_lab + 1), key=lambda i_p: int((kept & (pid == i_p)).sum()))
            bs = kept & (pid == big)
            trap_pos = [round(float(np.mean(wx[bs])), 1), round(float(np.mean(wz[bs])), 1)]
            n_kept = len({int(v) for v in pid[kept]})
            span = f"x {wx[bs].min():.0f}..{wx[bs].max():.0f}, z {wz[bs].min():.0f}..{wz[bs].max():.0f}, {g.lo[1] + np.median(L[x[bs], z[bs], k[bs]]) * res:.0f} up"
            more = f" (+{n_kept - 1} more pocket(s))" if n_kept > 1 else ""
            msg = f"{trap_cells * res * res:.0f} sq studs are a TRAP; the biggest near ({trap_pos[0]}, {trap_pos[1]}) [{span}]{more}: you can get in and never get back to a spawn — add a way out (stairs, a ramp, a ledge under {P['jump']} studs)"
            if trap_cells >= C["trap_cells"]:
                errors.append(msg)
            else:
                warns.append("improve: " + msg)
    unreachable = valid & ~reach
    platforms = []
    if starts and unreachable.sum() >= C["unreachable_cells"]:
        # unreachable AREAS, each on its own: thin strips (wall tops, rails: under 5 studs wide) are decoration and
        # stay quiet; a real platform / roof / floor with no way up is named with where it is and how high
        from scipy.ndimage import distance_transform_edt, label

        ids = np.nonzero(unreachable)[0]
        x, z, k = ids // (nz_ * K), (ids // K) % nz_, ids % K
        y = L[x, z, k]
        for band in np.unique((y * res // 4).astype(int)):  # (4-stud height bands: one floor at a time)
            sel = (y * res // 4).astype(int) == band
            grid2 = np.zeros((nx_, nz_), bool)
            grid2[x[sel], z[sel]] = True
            lab, n_lab = label(grid2)
            for i in range(1, n_lab + 1):
                mask = lab == i
                width = 2 * distance_transform_edt(mask).max() * res
                cells = int(mask.sum())
                if width < 5 or cells * res * res < C["unreachable_cells"]:
                    continue
                cx, cz = np.nonzero(mask)
                platforms.append({
                    "sq_studs": round(cells * res * res),
                    "x": [round(float(g.lo[0] + cx.min() * res)), round(float(g.lo[0] + (cx.max() + 1) * res))],
                    "z": [round(float(g.lo[2] + cz.min() * res)), round(float(g.lo[2] + (cz.max() + 1) * res))],
                    "y": round(float(g.lo[1] + np.median(y[sel]) * res), 1),
                })
        platforms.sort(key=lambda p: -p["sq_studs"])
        if res > 1 and platforms:
            # the finer LOCAL check (mission 05 5.6): at 2-stud cells a 4-stud stair flight is reachable only when it
            # happens to sit on the grid; each unreachable floor is walked again at 1-stud cells in a box around it,
            # entered from the floor the coarse pass reached. Only a floor the fine walk REACHES is dropped.
            kept = []
            terr = w.get("terrain") or {}
            for p in platforms[:8]:
                frac = fine_reach(p, g, L, reach, solids, terr, P)
                if frac is not None and frac >= 0.5:
                    fine_ok.append({**p, "fine_reached": round(frac, 2)})
                else:
                    kept.append(p)
            platforms = kept + platforms[8:]
        for p in platforms[:4]:
            warns.append(f"improve: {p['sq_studs']} sq studs of floor no one can reach at x {p['x'][0]}..{p['x'][1]}, z {p['z'][0]}..{p['z'][1]}, {p['y']} studs up — a platform with no way up (stairs, a ledge under {P['jump']} studs), or decoration (then CanCollide off)")
    # the reachable floor as points (for sight, camera, room)
    rid = np.nonzero(reach & valid)[0]
    rx, rz, rk = rid // (nz_ * K), (rid // K) % nz_, rid % K
    ry = L[rx, rz, rk]
    floor = np.stack([g.lo[0] + (rx + 0.5) * res, g.lo[1] + ry * res, g.lo[2] + (rz + 0.5) * res], axis=1)
    stats = {"reachable_sq_studs": round(float(len(rid) * res * res)), "trap_sq_studs": round(trap_cells * res * res),
             "unreachable_sq_studs": round(float(unreachable.sum() * res * res)), "res": res}
    if fine_ok:
        stats["fine_rechecked"] = fine_ok  # floors the 1-stud local walk reached (the coarse grid could not)
    rng = np.random.default_rng(1)
    exposure = np.zeros(len(floor))
    sight_lengths = np.zeros(0)
    if len(floor) > 1:
        m = min(int(C["exposure_points"] if res <= 1 else C["exposure_points"] * 0.6), len(floor))
        pick = rng.choice(len(floor), m, replace=False)
        eyes = floor[pick] + [0, P["eye"], 0]
        vis = np.zeros((m, m), bool)
        lengths = []
        for i in range(m - 1):
            j = np.arange(i + 1, m)
            ok = los_mask(g, np.repeat(eyes[i : i + 1], len(j), 0), eyes[j], step=0.9 * res)  # (one sample per voxel)
            vis[i, j] = ok
            vis[j, i] = ok
            lengths.append(np.linalg.norm(eyes[j][ok] - eyes[i], axis=1))
        sight_lengths = np.concatenate(lengths) if lengths else np.zeros(0)
        exp_pick = vis.mean(axis=1)
        # spread to every floor point from its nearest sample
        from scipy.spatial import cKDTree

        _, near = cKDTree(eyes[:, [0, 2]]).query(floor[:, [0, 2]])
        exposure = exp_pick[near]
        stats["sightline_median"] = round(float(np.median(sight_lengths)), 1) if len(sight_lengths) else 0
        stats["sightline_p90"] = round(float(np.percentile(sight_lengths, 90)), 1) if len(sight_lengths) else 0
        stats["exposure_mean"] = round(float(exposure.mean()), 3)
    # camera clearance: 8 directions, 12 studs back + 3 up from the head; cramped = hit within 4 studs
    cam = np.zeros(len(floor))
    if len(floor):
        head = floor + [0, P["eye"], 0]
        hits = np.zeros(len(floor))
        for ang in np.linspace(0, 2 * np.pi, 8, endpoint=False):
            back4 = head + np.array([math.cos(ang) * 4, 1, math.sin(ang) * 4])
            hits += ~los_mask(g, head, back4, step=0.5)
        cam = hits / 8
        cramped = float((cam >= 0.5).mean() * 100)
        stats["camera_cramped_pct"] = round(cramped, 1)
        if cramped > C["camera_pct"]:
            warns.append(f"improve: the third-person camera is cramped on {cramped:.0f} % of the floor (a wall within 4 studs behind the player in half the directions) — widen corridors / raise ceilings")
    # open room: distance from each floor point to the nearest wall (solid between 1 and 5 studs above the floor)
    room = np.zeros(len(floor))
    if len(floor):
        from scipy.ndimage import distance_transform_edt

        # per floor level (2-stud bins): a wall = solid between 1 and `height` studs above THAT floor (one band
        # for the whole map measured walls at the wrong height on multi-level maps)
        bins = (ry * res // 2).astype(int)
        for b in np.unique(bins):
            sel = bins == b
            y1 = max(0, int(np.min(ry[sel])) + max(1, int(round(1 / res))))
            y2 = min(g.n[1], y1 + int(P["height"] / res))
            if y2 <= y1:
                continue
            band = g.occ[:, y1:y2, :].any(axis=1)
            room[sel] = (distance_transform_edt(~band) * res)[rx[sel], rz[sel]]
        open_share = float((room >= C["open"]).mean() * 100)
        stats["open_room_pct"] = round(open_share, 1)
        stats["open_room_max"] = round(float(room.max()), 1)
    # spawn fairness: path distance to the objectives (or to the floor's centre)
    fair = {}
    if len(starts) > 1:
        targets = [(o[0], o[1]) for o in objectives if o[1] is not None]
        if not targets and len(floor):
            c = floor.mean(axis=0)
            targets = [("the centre", nearest_node(g, L, c))]
        for tname, tnd in targets:
            if tnd is None:
                continue
            ds = [float(dist_from[nd][tnd]) for _, nd in starts]
            if all(np.isfinite(ds)) and max(ds) > 0:
                spread = (max(ds) - min(ds)) / max(ds) * 100
                fair[tname] = {"distances": [round(d, 1) for d in ds], "spread_pct": round(spread, 1)}
                if spread > C["fair"] and max(ds) - min(ds) > 8:  # (12 vs 10 studs is 17 % but nothing)
                    warns.append(f"improve: spawns are unfair to {tname}: path distances {', '.join(f'{d:.0f}' for d in ds)} studs ({spread:.0f} % apart, max {C['fair']} %)")
    stats["fairness"] = fair
    stats.update(sstats)
    lookout = {}
    look = look_lint(w, lookout)
    warns.extend(look)
    stats["look_warnings"] = len(look)
    errors.extend(fixture_lint(lookout))  # (a street fixture that floats: V3 stage C)
    fe, fs = footpath_lint(w)  # (a road keeps 7 studs clear past what stands on it: V3 stage C)
    errors.extend(fe)
    stats.update(fs)
    ze, zpairs = zfight_lint(w)  # (faces of two looks in one plane flicker: an error, card my7f)
    errors.extend(ze)
    stats["zfight_pairs"] = len(zpairs)
    stats["zfight"] = zpairs[:8]
    # design gates: primitive-only generators
    de, dw, ds = design_lint(world_path, name, w.get("blueprint"))
    errors.extend(de)
    warns.extend(dw)
    stats.update(ds)
    # the terrain route (the owner's SampleRegion_terrain_v1 verdict): rivers or real land, proved by re-making it
    te, tw, ts = terrain_route(world_path, name, w.get("blueprint"), use_cache=bool(C.get("route_cache", True)))
    errors.extend(te)
    warns.extend(tw)
    stats.update(ts)
    # lamps: a new world's lamps stand apart, each with a reason (the owner's District verdict)
    le, lw, ls = lamp_density(w, name)
    errors.extend(le)
    warns.extend(lw)
    stats.update(ls)
    # steep land with no rock on it (V3 stage E.3)
    se, sw, ss = steep_lint(w, name)
    errors.extend(se)
    warns.extend(sw)
    stats.update(ss)
    gw, gs = guidance(w, g, P, C)  # (landmarks in view + pacing along the roads: AAA gaps W2 / W10)
    warns.extend(gw)
    stats.update(gs)
    png = os.path.join(out_dir, f"{name}.png")
    draw(png, name, g, L, floor, reach, valid, trap, nz_, K, exposure, cam, room, sight_lengths, spawns, objectives, errors, warns, stats, C)
    status = "fail" if errors else "pass"
    nxt = errors[0] if errors else (next((x for x in warns if x.startswith("improve")), None) or f"look at {png.replace(os.sep, '/')}")
    summary = (f"{name}: {stats['reachable_sq_studs']} sq studs walkable from the spawns, {len(errors)} error(s), {len(warns)} warning(s)"
               + (f"; sightlines median {stats.get('sightline_median')} studs" if "sightline_median" in stats else "")
               + (f" — {errors[0]}" if errors else ""))
    return {"status": status, "summary": summary, "next_action": nxt, "errors": errors, "warnings": warns, "stats": stats, "sheet": png.replace(os.sep, "/")}


def draw(png, name, g, L, floor, reach, valid, trap, nz_, K, exposure, cam, room, sight, spawns, objectives, errors, warns, stats, C):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    BG, FG = "#14161b", "#e8e6e1"
    ext = [g.lo[0], g.lo[0] + g.n[0] * g.res, g.lo[2] + g.n[2] * g.res, g.lo[2]]  # +X right, +Z down (as kit world)
    top = np.where(L.max(axis=2) >= 0, L.max(axis=2), np.nan).T * g.res + g.lo[1]
    fig, axes = plt.subplots(2, 3, figsize=(16, 10.5), facecolor=BG)
    flat = lambda: None  # noqa: E731

    def base(ax, title):
        ax.set_facecolor(BG)
        ax.imshow(top, extent=ext, cmap="Greys_r", alpha=0.55, interpolation="nearest")
        ax.set_title(title, color=FG, fontsize=10, loc="left")
        ax.tick_params(colors="#8a8f99", labelsize=7)
        for s in spawns:
            ax.add_patch(plt.Circle((s["pos"][0], s["pos"][2]), 3.5, fill=False, color="white", lw=2.2, zorder=5))
            ax.plot(s["pos"][0], s["pos"][2], marker="o", ms=4, color="white", zorder=5)
        for o in objectives:
            ax.plot(o[2][0], o[2][2], marker="*", ms=14, color="#ffd34d")

    def scatter(ax, vals, cmap, vmin, vmax, label):
        if len(floor):
            sc = ax.scatter(floor[:, 0], floor[:, 2], c=vals, s=max(1.5, 6 * g.res * g.res), marker="s", cmap=cmap, vmin=vmin, vmax=vmax, linewidths=0)
            cb = fig.colorbar(sc, ax=ax, fraction=0.04)
            cb.ax.tick_params(colors="#8a8f99", labelsize=7)
            cb.set_label(label, color="#8a8f99", fontsize=8)

    ax = axes[0][0]
    base(ax, "1 reachability: green = walkable from a spawn · red = no one gets there · orange = trap")
    nx_ = L.shape[0]
    ids = np.nonzero(valid)[0]
    x, z, k = ids // (nz_ * K), (ids // K) % nz_, ids % K
    # what you would see from above: the TOP standable level of each column decides its colour
    colkey = x * nz_ + z
    order = np.lexsort((k, colkey))
    last = np.r_[colkey[order][1:] != colkey[order][:-1], True]
    top_ids = ids[order][last]
    x, z = top_ids // (nz_ * K), (top_ids // K) % nz_
    col = np.where(trap[top_ids], 2, np.where(reach[top_ids], 0, 1))
    colors = np.array(["#3fbf6a", "#e0473e", "#ff9e3d"])[col]
    ax.scatter(g.lo[0] + (x + 0.5) * g.res, g.lo[2] + (z + 0.5) * g.res, c=colors, s=max(1.5, 6 * g.res * g.res), marker="s", linewidths=0)
    _ = nx_, flat
    base(axes[0][1], "2 exposure: how much of the map sees this spot (dark = cover)")
    scatter(axes[0][1], exposure, "inferno", 0, max(0.05, float(np.percentile(exposure, 98)) if len(exposure) else 1), "share seen from")
    base(axes[0][2], "3 camera: share of directions where a wall is within 4 studs behind")
    scatter(axes[0][2], cam, "RdYlGn_r", 0, 1, "cramped")
    base(axes[1][0], f"4 open room: studs to the nearest wall (knockback needs {C['open']:.0f})")
    scatter(axes[1][0], room, "viridis", 0, max(C["open"] * 1.5, 1), "studs")
    ax = axes[1][1]
    ax.set_facecolor(BG)
    if len(sight):
        ax.hist(sight, bins=40, color="#5ec8ff")
    ax.set_title("5 sightline lengths between eye points (studs)", color=FG, fontsize=10, loc="left")
    ax.tick_params(colors="#8a8f99", labelsize=7)
    ax = axes[1][2]
    ax.axis("off")
    lines = [f"{name}  ({'FAIL' if errors else 'pass'})", ""]
    for e in errors:
        lines.append("ERROR " + e)
    for wv in warns:
        lines.append("warn  " + wv)
    lines.append("")
    for k2, v in stats.items():
        if k2 not in ("fairness", "terrain_routes"):
            lines.append(f"{k2:<22}{v}")
    for t, f in stats.get("fairness", {}).items():
        lines.append(f"fair to {t}: {f['distances']} ({f['spread_pct']} %)")
    for r in stats.get("terrain_routes", []):
        how = "grandfathered" if r.get("grandfathered") else ("proved" if r.get("proved") else "NOT proved") if r.get("route") else "made the rejected way"
        lines.append(f"terrain {os.path.basename(str(r.get('source')))}: {r.get('route') or 'no rivers / real land'}, {how}")
    import textwrap

    wrapped = []
    for ln in lines:
        wrapped += textwrap.wrap(ln, 70) or [""]
    ax.text(0, 1, "\n".join(wrapped[:46]), color=FG, family="monospace", fontsize=7.4, va="top")
    fig.tight_layout()
    os.makedirs(os.path.dirname(png), exist_ok=True)
    fig.savefig(png, dpi=80, facecolor=BG)
    plt.close(fig)


def main(argv):
    if not argv:
        print(json.dumps({"status": "fail", "summary": "usage: check.py build/worlds/<name>.json [--out DIR]", "next_action": "lune run kit world check <Name>"}))
        return 1
    out_dir = os.path.join("build", "worlds", "checks")
    if "--out" in argv:
        out_dir = argv[argv.index("--out") + 1]
    path = argv[0]
    if not os.path.isfile(path):
        print(json.dumps({"status": "fail", "summary": f"no compiled world {path}", "next_action": "lune run kit world (compiles assets/worlds/*.json)"}))
        return 1
    r = run(path, out_dir)
    print(json.dumps(r))
    return 0 if r["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
