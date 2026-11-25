"""prop_rig.py — A PROP'S RIG FROM DATA, and its motion held to its joints (the owner's method lists 2026-11-13:
object animation - "NOT there: a clip pipeline for props"; the audit: board/plans/archive/2026-11-13-anim-methods-audit.md).
The lane animates any rig that has a file in kit/anim/rigs/ (kit/anim/clip.py and kit/lib/animrig.luau read it; a
keyframe spec names it with "rig"), but the only way to get one was a probe of a model in Studio. A prop is simpler
than a character: boxes on hinges and slides. This writes its rig file from a few lines of data, and holds any clip
on it to what its joints can do.

    python kit/anim/prop_rig.py make <prop.json> --out <rig.json>
    python kit/anim/prop_rig.py clip <clip.json> --rig <rig.json>
    python kit/anim/prop_rig.py go <prop.json> <spec.json>... --out <dir> [--keep <dir>]
        THE WHOLE WAY (`lune run kit anim prop <Prop>`): the prop's rig, then each keyframe spec (the kit's own spec
        format, "rig": the prop's name, its keys posing the prop's parts: {"Lid": [90, 0, 0]} degrees, or {"rot",
        "pos"}) compiled by the kit's own compiler (kit/anim/prop_clip.luau -> kit/lib/anim.luau) to a clip and to
        the KeyframeSequence model the game plays, the clip HELD to the prop's joints in between: a spec whose clip
        breaks a joint leaves NO model in --out, and what the last build of the prop left there is removed first.
        -> --out: <Clip>.model.json only (the game's tree);  --keep (default --out): <prop>.rig.json,
           <Clip>.clip.json, <prop>.props.json (what was built from what, what was refused and why)
        A spec's pose values are each joint's OWN turn and slide, relative to its parent ({"Lid": [90, 0, 0]}).
        ONE NUMBER poses a hinge or a slide by itself: {"Lid": 90} is 90 degrees about the Lid's own hinge axis
        (whatever way that axis points: a diagonal hinge needs no Euler triple typed by hand), {"Tray": 1.2} is 1.2
        studs along its runner. A hinge posed so is turned key to key in DEGREES, not by the shortest way: a wheel
        keyed 0 then 720 turns twice (its clip keeps the degrees as a "turn" track; the model the game plays is
        then written frame by frame, since the engine takes the short way between two keyframes).

The prop file (studs, the prop standing at rest, every part axis-aligned):
    {"name": "Chest", "root": "Base",
     "parts": {"Base": {"size": [4, 2, 3], "at": [0, 1, 0]},
               "Lid":  {"size": [4, 0.5, 3], "at": [0, 2.25, 0], "parent": "Base", "joint": "Hinge",
                        "pivot": [0, 2, 1.5], "hinge": {"axis": [1, 0, 0], "min": 0, "max": 110}},
               "Tray": {"size": [3, 0.3, 2], "at": [0, 1.2, 0], "parent": "Base", "joint": "Runner",
                        "pivot": [0, 1.2, 0], "slide": {"axis": [0, 0, -1], "min": 0, "max": 1.8}}}}
  at      the part's centre            pivot   where its joint sits (it must touch the part and its parent)
  hinge   the part TURNS about `axis` through the pivot, between min and max degrees from rest (min below max;
          the range need not hold 0 - a part built where it never stops; up to HINGE_TURNS turns either way - a
          wheel that turns twice is 0 to 720; exactly min -180, max 180 is a part that spins freely, held to its
          axis only)
  slide   the part SLIDES along `axis`, between min and max studs (min below max; 0 need not be inside)
  (neither: the part is fixed to its parent)

A PROP THE 3D LANE BUILT (`go` given a built model's manifest, build/models/<asset>.manifest.json; `lune run kit anim
prop <asset> --model`): a model whose build script names moving parts (a.joint) is spawned in the game by
src/kit/Models.luau as a part "Root" at the model's origin, one part a group (named as the group), and a Motor6D for
each hinge and slide, its frame at the joint's pivot with its X axis the joint's axis. `from_model` writes THAT rig,
with the same frames: the clip's part names are the group names, and a pose is said as everywhere in the kit, in
the space of the part's parent at rest (a wheel on a [0, 0, 1] axis: {"wheel": [0, 0, 90]}; a pin on a [0, -1, 0]
runner: {"pin": {"pos": [0, -0.1, 0]}}). The compiler turns that into the joint's own Transform (a turn about the
joint's X: what Models.pose sets), so the model the game already spawns is the model the clip plays on.

A model spawned as a TOOL (Models.tool) has its root renamed Handle: `go ... --tool` (`kit anim prop <asset> --model
--tool`) writes the rig and the clips for that. `stale <manifest> --props <prop>.props.json` (`kit anim prop <asset>
--model --check`) says whether the clips a build left were made on the joints the model has NOW (a part renamed, an
axis turned, a range changed since: the clips are refused until built again).

`make` refuses a prop that cannot be one (a part with no parent, a loop, a pivot that touches nothing, a joint that
is both). The rig it writes is the kit's own rig format (the same fields a Studio probe writes) plus "kind": "prop"
and each joint's "limits".
`clip` (and the build's motion gates, kit/anim/metrics.py, for every clip whose rig is a prop) holds a clip to the
joints: a hinged part may only turn about its axis (TWIST degrees off it is a part twisting off its hinge), inside
its range, and may not slide (SLIP studs); a sliding part may only move along its axis, inside its range, and may not
turn; a fixed part and the root may not move at all. A fault is named with the part, the frame and how far.

THE GAME'S PLAYER: src/kit/AnimProp.luau (an AnimationController + Animator on the spawned model, the prop's clip
stepped on the character's clip's time, its markers said once). A moving part may hang on a part that does not move
(a bolt on a fixed post, a sight on a fixed rail): the game spawns it so (Models.spawn: a plain group is welded to
the root, a fixed joint to its parent), and the rig carries that fixed part - "welded": true, kind "fixed" - so the
clip's pose tree runs through it as the game's joints do.
WHAT THIS IS NOT YET (card r66z): a model that never ships (private, a master) is not told apart.
`stale-all <build/animations/props> <build/models>` is the check the animation build and its verify gate run by
themselves (kit/cmd/anim.luau AnimCmd.propsStale): every prop built on a model, against that model now. A prop typed as a prop FILE has no Roblox
model at all: build it in the 3D lane with a.joint and use its manifest.
Parts are axis-aligned boxes at rest; a joint's pivot touches both its parts (a pendulum needs its rod as a part)."""
import datetime
import json
import math
import os
import sys

import numpy as np

TOUCH = 0.05         # studs a pivot may sit outside a part's box and still touch it
TWIST = 2.0          # degrees a hinged part may turn off its axis (or a sliding / fixed part may turn at all)
SLIP = 0.02          # studs a hinged / fixed part may slide (or a sliding part may leave its axis)
OVER = 0.5           # degrees (hinge) a clip may pass a range's end - a solver's rounding, not a swing through the stop
OVER_SLIDE = 0.01    # studs (slide)
HINGE_TURNS = 10     # turns either way a hinge's range may run (a wheel, a winch: a range past a half turn)
HALF = 179.0         # degrees between two stored frames past which a turn cannot be said: the engine takes the short way
TURN_AGREE = 0.5     # degrees a clip's "turn" track (the degrees it was keyed in) may differ from its frames


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def _vec(v, n=3):
    return (isinstance(v, list) and len(v) == n
            and all(not isinstance(x, bool) and isinstance(x, (int, float)) and math.isfinite(x) for x in v))


def _box_gap(point, centre, size):
    """how far a point lies outside an axis-aligned box (0 = on or in it)"""
    d = np.abs(np.asarray(point, float) - np.asarray(centre, float)) - np.asarray(size, float) / 2.0
    return float(np.linalg.norm(np.maximum(d, 0.0)))


def problems(spec):
    """what makes the prop file not a prop -> [words]"""
    out = []
    if not isinstance(spec, dict) or not isinstance(spec.get("parts"), dict) or not spec["parts"]:
        return ["a prop file is {\"name\", \"root\", \"parts\": {<Part>: {\"size\", \"at\", ...}}}"]
    parts = spec["parts"]
    if not isinstance(spec.get("name"), str) or not spec["name"].isidentifier():
        out.append("the prop has no name (one word: letters, digits, underscores)")
    elif spec["name"].lower() in ("r6", "r15", "both"):
        out.append(f"the prop cannot be named {spec['name']}: that is a character rig's name")
    root = spec.get("root")
    if not isinstance(root, str) or root not in parts:
        out.append(f"its root '{root}' is not one of its parts")
        root = None
    for name, p in parts.items():
        if not isinstance(p, dict) or not _vec(p.get("size")) or not _vec(p.get("at")) or min(p["size"]) <= 0:
            out.append(f"{name}: a part has a size [x, y, z] (each above 0) and a centre `at` [x, y, z]")
            continue
        if name == root:
            if any(k in p for k in ("parent", "pivot", "hinge", "slide")):
                out.append(f"{name}: the root stands still - it has no parent, pivot or joint")
            continue
        par = p.get("parent")
        if not isinstance(par, str) or par not in parts or par == name:
            out.append(f"{name}: its parent '{par}' is not another part of the prop")
            continue
        if not _vec(p.get("pivot")):
            out.append(f"{name}: it has no pivot [x, y, z] (where its joint sits)")
            continue
        ok_parent = isinstance(parts[par], dict) and _vec(parts[par].get("size")) and _vec(parts[par].get("at"))
        for who, q in ((name, p), (par, parts[par] if ok_parent else None)):
            if q is not None and _box_gap(p["pivot"], q["at"], q["size"]) > TOUCH:
                out.append(f"{name}: its pivot is {_box_gap(p['pivot'], q['at'], q['size']):.2f} studs off {who} - a joint sits "
                           "where the two parts touch")
        if "hinge" in p and "slide" in p:
            out.append(f"{name}: a joint turns (hinge) or slides (slide), not both")
        for kind in ("hinge", "slide"):
            if kind not in p:
                continue
            j = p[kind]
            if (not isinstance(j, dict) or not _vec(j.get("axis")) or float(np.linalg.norm(j["axis"])) < 1e-6
                    or any(isinstance(j.get(k), bool) or not isinstance(j.get(k), (int, float)) or not math.isfinite(j.get(k))
                           for k in ("min", "max"))
                    or not j["min"] < j["max"]):
                out.append(f"{name}: its {kind} is {{\"axis\": [x, y, z], \"min\", \"max\"}} with min below max (from rest)")
            elif kind == "hinge" and (j["min"] < -360 * HINGE_TURNS or j["max"] > 360 * HINGE_TURNS):
                out.append(f"{name}: a hinge's range lies inside {-360 * HINGE_TURNS} to {360 * HINGE_TURNS} degrees "
                           f"({HINGE_TURNS} turns either way)")
    named = {}
    for name, p in parts.items():                            # one joint, one name (the game finds a joint by it)
        if isinstance(p, dict) and name != root:
            named.setdefault(str(p.get("joint") or name), []).append(name)
    for joint, who in named.items():
        if len(who) > 1:
            out.append(f"{who[1]}: its joint is named {joint}, as {who[0]}'s is - one joint, one name")
    seen = set()
    for name in parts:                                       # no loops: every part leads to the root
        if name in seen or root is None:
            continue
        chain, cur = set(), name
        while isinstance(cur, str) and isinstance(parts.get(cur), dict) and cur != root and cur not in chain and cur not in seen:
            chain.add(cur)
            cur = parts[cur].get("parent")
        if cur != root and not (isinstance(cur, str) and cur in seen):
            out.append(f"{name}: it does not lead back to the root {root} (a loop, or a parent that is not a part)")
        else:
            seen.update(chain)
    return out


def _cf(pos):
    """a position as the kit's 12-number CFrame (identity turn)"""
    return [round(float(v), 6) for v in pos] + [1, 0, 0, 0, 1, 0, 0, 0, 1]


def build(spec, today=None):
    """the prop file -> the kit's rig (raises ValueError naming the first problem)"""
    bad = problems(spec)
    if bad:
        raise ValueError(bad[0] + (f" (+{len(bad) - 1} more)" if len(bad) > 1 else ""))
    parts, root = spec["parts"], spec["root"]
    order, left = [], [n for n in parts if n != root]
    placed = {root}
    while left:                                              # parents before their children
        for n in list(left):
            if parts[n]["parent"] in placed:
                order.append(n)
                placed.add(n)
                left.remove(n)
    joints, limits = {}, {}
    for n in order:
        p = parts[n]
        piv, par = np.array(p["pivot"], float), parts[p["parent"]]
        joints[n] = {"c0": _cf(piv - np.array(par["at"], float)), "c1": _cf(piv - np.array(p["at"], float)),
                     "joint": str(p.get("joint") or n), "parent": p["parent"]}
        kind = "hinge" if "hinge" in p else "slide" if "slide" in p else "fixed"
        lim = {"kind": kind}
        if kind != "fixed":
            ax = np.array(p[kind]["axis"], float)
            lim.update(axis=[round(float(v), 6) for v in ax / np.linalg.norm(ax)], min=float(p[kind]["min"]),
                       max=float(p[kind]["max"]))
        limits[n] = lim
    origin = np.array(parts[root]["at"], float)              # the rig's space: the root at its own centre
    return {"schema": 1, "rig": spec["name"], "kind": "prop", "root": root, "order": order, "jointType": "Motor6D",
            "hipHeight": 0, "classes": {n: "Part" for n in parts},
            "sizes": {n: [float(v) for v in parts[n]["size"]] for n in parts},
            "rest": {n: _cf(np.array(parts[n]["at"], float) - origin) for n in parts},
            "joints": joints, "limits": limits,
            "source": {"date": today or datetime.date.today().isoformat(), "tool": "kit/anim/prop_rig.py make",
                       "from": "a prop file (data, no Studio probe)"}}


def is_model(spec):
    """a built model's manifest (the 3D lane's), not a prop file"""
    return isinstance(spec, dict) and "parts" not in spec and isinstance(spec.get("groups"), dict) and "joints" in spec


def model_problems(m):
    """what makes a built model's manifest not a prop the lane can animate -> [words]"""
    if not is_model(m):
        return ["a built model's manifest is {\"asset\", \"groups\": {...}, \"joints\": {...}} (build/models/<asset>.manifest.json)"]
    out = []
    name, groups, joints = m.get("asset"), m["groups"], m.get("joints")
    if not isinstance(name, str) or not name.isidentifier():
        out.append("the model has no name (`asset`: one word: letters, digits, underscores)")
    elif name.lower() in ("r6", "r15", "both"):
        out.append(f"the prop cannot be named {name}: that is a character rig's name")
    if not isinstance(joints, dict) or not any(isinstance(j, dict) and j.get("kind") in ("hinge", "slide") for j in joints.values()):
        return out + ["the model has no moving part (a.joint in its build script: a hinge or a slide)"]
    if "Root" in groups:
        out.append("a group is named Root: the game names the model's own root part so")
    by_group = {}
    for jn, j in joints.items():
        if not isinstance(j, dict) or j.get("kind") not in ("hinge", "slide", "fixed") or not isinstance(j.get("group"), str):
            out.append(f"joint {jn}: it is {{\"group\", \"kind\": hinge | slide | fixed, ...}}")
            continue
        by_group.setdefault(j["group"], []).append(jn)
    for g, names in by_group.items():
        if len(names) > 1:
            out.append(f"{g}: {len(names)} joints move this one part ({', '.join(sorted(names))}) - one part, one joint")
    moving = {j["group"]: (jn, j) for jn, j in joints.items()
              if isinstance(j, dict) and isinstance(j.get("group"), str) and j.get("kind") in ("hinge", "slide")}
    for g, (jn, j) in moving.items():
        grp = groups.get(g)
        if not isinstance(grp, dict) or not _vec(grp.get("size_studs")) or not _vec(grp.get("center")) or min(grp["size_studs"]) <= 0:
            out.append(f"{g}: joint {jn} moves a group the model does not have (with its size_studs and center)")
            continue
        par = j.get("parent")
        if par is not None and not isinstance(par, str):
            out.append(f"{g}: joint {jn}: its parent is a group's name")
            continue
        if par not in (None, "main") and par not in groups:
            out.append(f"{g}: joint {jn} hangs on '{par}', which is not a part of the model - a moving part hangs on "
                       "another part (moving or fixed) or on the model itself (parent \"main\")")
        elif (par not in (None, "main") and par not in moving
              and (not isinstance(groups[par], dict) or not _vec(groups[par].get("size_studs"))
                   or not _vec(groups[par].get("center")))):
            out.append(f"{g}: joint {jn} hangs on '{par}', a part with no size_studs and center")
        kind = j["kind"]
        if (not _vec(j.get("axis")) or float(np.linalg.norm(j["axis"])) < 1e-6 or not _vec(j.get("pivot"))
                or any(isinstance(j.get(k), bool) or not isinstance(j.get(k), (int, float)) or not math.isfinite(j.get(k))
                       for k in ("min", "max"))
                or not j["min"] < j["max"]):
            out.append(f"{g}: joint {jn} ({kind}) needs an axis, a pivot and a range min below max (from rest)")
        elif kind == "hinge" and (j["min"] < -360 * HINGE_TURNS or j["max"] > 360 * HINGE_TURNS):
            out.append(f"{g}: joint {jn}: a hinge's range lies inside {-360 * HINGE_TURNS} to {360 * HINGE_TURNS} degrees "
                       f"({HINGE_TURNS} turns either way)")
    fixed = _fixed_of(joints)
    for g in moving:                                         # no loops: every moving part leads to the model
        chain, cur = set(), g
        while isinstance(cur, str) and cur != "main" and cur in groups and cur not in chain:
            chain.add(cur)
            cur = _hangs_on(cur, moving, fixed)
        if isinstance(cur, str) and cur in chain:
            out.append(f"{g}: its parents run in a loop")
    return out


def _fixed_of(joints):
    """a built model's FIXED joints by their group -> {group: (joint name, joint)}"""
    return {j["group"]: (jn, j) for jn, j in (joints or {}).items()
            if isinstance(j, dict) and j.get("kind") == "fixed" and isinstance(j.get("group"), str)}


def _hangs_on(g, moving, fixed):
    """the group a group hangs on as src/kit/Models.luau spawns it: a jointed group (moving or fixed) its joint's
    parent; a plain group (no joint) is welded to the root -> a group's name, or "main" (the model's own root)"""
    j = moving.get(g, fixed.get(g, (None, None)))[1]
    p = j.get("parent") if isinstance(j, dict) else None
    return p if isinstance(p, str) and p != "main" else "main"


def _wrap(d):
    """degrees -> the same turn in (-180, 180]"""
    d = (float(d) + 180.0) % 360.0 - 180.0
    return 180.0 if d == -180.0 else d


def _joint_frame(axis):
    """the turn of a spawned joint's frame, as src/kit/Models.luau builds it: X the joint's axis -> 3x3 (columns)"""
    x = np.array(axis, np.float32)                           # (Roblox's Vector3 is 32-bit: the same side of 0.95 as the game)
    x = (x / np.linalg.norm(x)).astype(np.float32)
    up = np.array([0.0, 1.0, 0.0]) if abs(float(x[1])) < 0.95 else np.array([1.0, 0.0, 0.0])
    x = x.astype(float)
    x = x / np.linalg.norm(x)
    z = np.cross(x, up)
    z = z / np.linalg.norm(z)
    y = np.cross(z, x)
    y = y / np.linalg.norm(y)
    return np.stack([x, y, z], axis=1)


def _cf_turned(pos, rot):
    return [round(float(v), 6) for v in pos] + [round(float(v), 9) for v in np.asarray(rot).reshape(9)]


def joints_hash(rig):
    """what a clip depends on in a rig: its parts' joints and their ranges"""
    import hashlib
    return hashlib.sha256(json.dumps([rig["root"], rig["joints"], rig["limits"]], sort_keys=True).encode("utf-8")).hexdigest()


def stale(manifest_path, props_path):
    """the clips a build left (its <prop>.props.json) against the model as it is built NOW -> None, or why they are
    stale. Only what a clip depends on is compared (the joints and their ranges), not the whole manifest"""
    with open(props_path, encoding="utf-8") as fh:
        props = json.load(fh)
    with open(manifest_path, encoding="utf-8") as fh:
        m = json.load(fh)
    rig = from_model(m, root=props.get("root") or "Root")
    if props.get("joints_sha256") != joints_hash(rig):
        return (f"{props.get('prop')}: the model's joints are not the ones its {len(props.get('built') or [])} clip(s) were "
                "built on (a part renamed, an axis turned, a range changed) - build the clips again: a clip made for other "
                "joints turns a part the wrong way or not at all")
    return None


def stale_all(keep_root, models_root):
    """every prop whose clips were built on a 3D-lane model (<keep_root>/<Prop>/<prop>.props.json, "from_model")
    against that model as it is built now (<models_root>/<Prop>.manifest.json) -> [why], one a stale prop. A prop
    whose model is gone is stale too: its clips have nothing to play on"""
    out = []
    if not os.path.isdir(keep_root):
        return out
    for prop in sorted(os.listdir(keep_root)):
        props = os.path.join(keep_root, prop, f"{prop.lower()}.props.json")
        if not os.path.isfile(props):
            continue
        try:
            with open(props, encoding="utf-8") as fh:
                rec = json.load(fh)
        except (OSError, ValueError):
            out.append(f"{prop}: its record of what was built ({props}) cannot be read - build its clips again")
            continue
        if not isinstance(rec, dict) or not rec.get("from_model") or not rec.get("built"):
            continue
        man = os.path.join(models_root, f"{prop}.manifest.json")
        if not os.path.isfile(man):
            out.append(f"{prop}: its {len(rec['built'])} clip(s) were built on a model that is no longer built ({man})")
            continue
        try:
            why = stale(man, props)
        except (OSError, ValueError, KeyError, TypeError) as e:
            why = f"{prop}: its clips cannot be checked against the model ({e})"
        if why:
            out.append(why)
    return out


def from_model(m, today=None, root="Root"):
    """a built model's manifest -> the rig of the model src/kit/Models.luau spawns from it (raises ValueError naming
    the first problem). Parts: the root (the model's origin: "Root" for Models.spawn, "Handle" for Models.tool, which
    renames it) and every MOVING group; a group that does not move is welded to the root and is no part of the rig"""
    if root not in ("Root", "Handle"):
        raise ValueError("the root of a spawned model is Root (Models.spawn) or Handle (Models.tool)")
    if isinstance(m, dict) and isinstance(m.get("groups"), dict) and root in m["groups"]:
        raise ValueError(f"a group is named {root}: the game names the model's own root part so")
    bad = model_problems(m)
    if bad:
        raise ValueError(bad[0] + (f" (+{len(bad) - 1} more)" if len(bad) > 1 else ""))
    groups = m["groups"]
    moving = {j["group"]: (jn, j) for jn, j in m["joints"].items() if j.get("kind") in ("hinge", "slide")}
    fixed = _fixed_of(m["joints"])

    def up(g):                                               # (Models.spawn: a name that is no part is the root)
        p = _hangs_on(g, moving, fixed)
        return p if p != "main" and p in groups else root
    need = set(moving)                                       # the moving parts and every fixed part they hang on
    for g in list(moving):
        cur = up(g)
        while cur != root and cur not in need:
            need.add(cur)
            cur = up(cur)
    for g in sorted(need - set(moving)):                    # (a fixed part a fixed part hangs on: checked here)
        if not isinstance(groups[g], dict) or not _vec(groups[g].get("size_studs")) or not _vec(groups[g].get("center")):
            raise ValueError(f"{g}: a moving part hangs on it (through its joints), and it has no size_studs and center")
    order, left, placed = [], sorted(need), {root}
    parent_of = {g: up(g) for g in need}
    while left:
        for g in list(left):
            if parent_of[g] in placed:
                order.append(g)
                placed.add(g)
                left.remove(g)
    centre = {root: np.zeros(3), **{g: np.array(groups[g]["center"], float) for g in need}}
    joints, limits = {}, {}
    for g in order:
        if g not in moving:                                  # a fixed part: welded where it was built
            joints[g] = {"c0": _cf(centre[g] - centre[parent_of[g]]), "c1": _cf(np.zeros(3)),
                         "joint": fixed[g][0] if g in fixed else g, "parent": parent_of[g], "welded": True}
            limits[g] = {"kind": "fixed"}
            continue
        jn, j = moving[g]
        rot, piv = _joint_frame(j["axis"]), np.array(j["pivot"], float)
        joints[g] = {"c0": _cf_turned(piv - centre[parent_of[g]], rot), "c1": _cf_turned(piv - centre[g], rot),
                     "joint": jn, "parent": parent_of[g]}
        ax = np.array(j["axis"], float)                      # (a clip's frames are in the parent's space at rest: clip.py)
        limits[g] = {"kind": j["kind"], "axis": [round(float(v), 6) for v in ax / np.linalg.norm(ax)],
                     "min": float(j["min"]), "max": float(j["max"])}
    sizes = {root: [0.2, 0.2, 0.2], **{g: [float(v) for v in groups[g]["size_studs"]] for g in need}}
    return {"schema": 1, "rig": m["asset"], "kind": "prop", "root": root, "order": order, "jointType": "Motor6D",
            "hipHeight": 0, "classes": {n: "Part" for n in sizes}, "sizes": sizes,
            "rest": {n: _cf(centre[n]) for n in sizes}, "joints": joints, "limits": limits,
            "source": {"date": today or datetime.date.today().isoformat(), "tool": "kit/anim/prop_rig.py from_model",
                       "from": "a built model's manifest (the joints src/kit/Models.luau spawns)",
                       "build_id": m.get("build_id")}}


def _turn(q, axis):
    """a joint's turn as (degrees about `axis`, degrees off it)"""
    q = np.asarray(q, float)
    q = q / max(float(np.linalg.norm(q)), 1e-12)
    if q[3] < 0:
        q = -q
    total = 2.0 * math.degrees(math.acos(max(-1.0, min(1.0, float(q[3])))))
    if axis is None:
        return 0.0, total
    along = float(np.dot(q[:3], axis))
    about = 2.0 * math.degrees(math.atan2(along, float(q[3])))
    rest = q[:3] - along * np.asarray(axis, float)           # what turns it about anything else
    return about, 2.0 * math.degrees(math.asin(min(1.0, float(np.linalg.norm(rest)))))


def check_clip(clip, rig):
    """a clip against the prop's joints -> [faults]: {part, frame, what} for each part's WORST fault of each kind"""
    lim = rig.get("limits") if isinstance(rig.get("limits"), dict) else {}
    faults = []
    n = len(clip.get("times") or [])
    if clip.get("rig") != rig.get("rig"):
        return [{"part": "the clip", "frame": 0, "what": f"is made for the rig {clip.get('rig')}, not for {rig.get('rig')}", "past": 1e9}]
    for part, jd in (clip.get("joints") or {}).items():
        frames = jd.get("frames") if isinstance(jd, dict) else None
        if not frames:
            continue
        if part == rig.get("root") or part not in lim:
            if part != rig.get("root"):
                faults.append({"part": part, "frame": 0, "what": "is not a part of this prop"})
                continue
            rule = {"kind": "fixed"}                         # the root stands still
        else:
            rule = lim[part]
        if len(frames) != n:
            faults.append({"part": part, "frame": 0, "what": f"has {len(frames)} frame(s) and the clip {n}"})
            continue
        axis = np.array(rule["axis"], float) if rule["kind"] != "fixed" else None
        bad = next((i for i, f in enumerate(frames) if not _vec(f, 7) or abs(float(np.linalg.norm(f[:4])) - 1.0) > 1e-3), None)
        if bad is not None:
            faults.append({"part": part, "frame": bad, "past": 1e9,
                           "what": "has a frame that is not a turn and a place (7 numbers, the first four a unit quaternion)"})
            continue
        free = rule["kind"] == "hinge" and rule["min"] == -180 and rule["max"] == 180      # it spins freely
        still = "it is the prop's root: it stands still" if part == rig.get("root") else "it is fixed to its parent"
        worst = {}
        turns = None
        if rule["kind"] == "hinge":
            # the turn about the hinge frame by frame, UNWRAPPED (a wheel past a half turn reads 190, not -170); a
            # clip keyed in degrees (one number a key: kit/anim/prop_clip.luau) carries them as "turn", held here to
            # its frames, and read as they were keyed (a wheel keyed from 400 starts at 400)
            raw = [_turn(f[:4], axis)[0] for f in frames]
            told = jd.get("turn")
            if told is not None:
                if (not isinstance(told, list) or len(told) != n
                        or not all(not isinstance(t, bool) and isinstance(t, (int, float)) and math.isfinite(t) for t in told)):
                    faults.append({"part": part, "frame": 0, "past": 1e9,
                                   "what": f"has a turn track that is not one number of degrees a frame ({n})"})
                    continue
                gap = [abs(_wrap(float(t) - r)) for t, r in zip(told, raw)]
                if max(gap) > TURN_AGREE:
                    i = int(np.argmax(gap))
                    faults.append({"part": part, "frame": i, "past": round(max(gap), 3),
                                   "what": f"says it turns to {told[i]:g} deg (its turn track) but its frame turns to {raw[i]:.1f}"})
                    continue
                turns = [float(t) for t in told]
            else:
                # a frame says its turn only within a half turn: the first one is put by whole turns where the
                # range is (a hinge running 200 to 300 posed at 250 reads 250, not -110)
                first = raw[0]
                if not free:
                    ks = [k for k in range(-HINGE_TURNS - 1, HINGE_TURNS + 2)
                          if rule["min"] - OVER <= first + 360 * k <= rule["max"] + OVER]
                    if ks and 0 not in ks:
                        first += 360 * min(ks, key=abs)
                turns = [first]
                for a, b in zip(raw, raw[1:]):
                    turns.append(turns[-1] + _wrap(b - a))
            for i in range(1, n):
                step = abs(turns[i] - turns[i - 1])
                if step - HALF > 0 and step - HALF > worst.get("step", (0.0,))[0]:
                    worst["step"] = (step - HALF, i, f"turns {step:.0f} deg between two frames - past a half turn the engine "
                                     "takes the short way round: key it slower or at a higher fps")
        for i, f in enumerate(frames):
            about, off = _turn(f[:4], axis if rule["kind"] == "hinge" else None)
            if turns is not None:
                about = turns[i]
            p = np.array(f[4:7], float)
            if rule["kind"] == "hinge":
                over = 0.0 if free else max(rule["min"] - about, about - rule["max"], 0.0)
                cand = (("range", over - OVER, f"turns to {about:.0f} deg; its hinge runs {rule['min']:g} to {rule['max']:g}"),
                        ("twist", off - TWIST, f"twists {off:.1f} deg off its hinge"),
                        ("slip", float(np.linalg.norm(p)) - SLIP, f"slides {float(np.linalg.norm(p)):.2f} studs off its hinge"))
            elif rule["kind"] == "slide":
                along = float(np.dot(p, axis))
                side = float(np.linalg.norm(p - along * axis))
                over = max(rule["min"] - along, along - rule["max"], 0.0)
                cand = (("range", over - OVER_SLIDE, f"slides to {along:.2f} studs; its runner goes {rule['min']:g} to {rule['max']:g}"),
                        ("slip", side - SLIP, f"leaves its runner by {side:.2f} studs"),
                        ("twist", off - TWIST, f"turns {off:.1f} deg (a sliding part does not turn)"))
            else:
                cand = (("twist", off - TWIST, f"turns {off:.1f} deg ({still})"),
                        ("slip", float(np.linalg.norm(p)) - SLIP, f"moves {float(np.linalg.norm(p)):.2f} studs ({still})"))
            for kind, past, what in cand:
                if past > 0 and past > worst.get(kind, (0.0,))[0]:
                    worst[kind] = (past, i, what)
        for kind in ("range", "step", "twist", "slip"):
            if kind in worst:
                faults.append({"part": part, "frame": worst[kind][1], "what": worst[kind][2], "past": round(worst[kind][0], 3)})
    if isinstance(clip.get("root"), list) and any(float(np.linalg.norm(np.array(f[4:7], float))) > SLIP for f in clip["root"] if _vec(f, 7)):
        faults.append({"part": "the whole prop", "frame": 0, "past": 1.0,
                       "what": "travels (the clip carries a root track): a prop's clip moves its parts, the game moves the prop"})
    return faults


def words(faults, name, fps=60.0):
    f = max(faults, key=lambda x: (x["what"].startswith("turns to") or x["what"].startswith("slides to"), x.get("past", 0.0)))
    return (f"{f['part']} {f['what']} at frame {f['frame']} ({f['frame'] / fps:.2f} s)"
            + (f" (+{len(faults) - 1} more fault(s))" if len(faults) > 1 else ""))


def gate(clip, rig):
    """what the build's motion gates add for a clip on a prop's rig (kit/anim/metrics.py) -> (reading or None, the
    problem or None)"""
    if not isinstance(rig, dict) or rig.get("kind") != "prop":
        return None, None
    try:
        faults = check_clip(clip, rig)
    except (ValueError, KeyError, IndexError, TypeError) as e:
        return {"error": str(e)}, f"the prop's clip could not be held to its joints ({type(e).__name__}: {e})"
    if not faults:
        return {"faults": []}, None
    return {"faults": faults}, (words(faults, str(clip.get("name")), float(clip.get("fps") or 60))
                                + " - a prop's part moves only as its joint allows: fix the keys, or the prop file's range")


def go(prop_path, spec_paths, out, keep=None, lune="lune", root="Root", name=None):
    """the whole way -> {"prop", "rig", "built": [{name, model, clip, spec}], "refused": [{spec, why}]}.
    out   gets ONLY the models the game plays (<Clip>.model.json): it is a folder of the game's tree
    keep  gets what the kit keeps beside them: the rig, each clip, the manifest (<prop>.props.json); default <out>
          itself (a fixture; the kit command gives build/animations/props/<Prop>)
    Every model and clip the LAST build of this prop left is removed first (the manifest says which), so a spec that
    is renamed, broken or refused now leaves nothing of an earlier build behind. Two specs of one name are both
    refused. The work is done in a temporary folder of its own. Raises ValueError for a prop file that is not a prop,
    or when lune is not there"""
    import hashlib
    import shutil
    import subprocess
    import tempfile
    if not shutil.which(lune):
        raise ValueError(f"`{lune}` is not on this machine's path: the kit's compiler cannot be run")
    with open(prop_path, encoding="utf-8") as fh:
        spec = json.load(fh)
    rig = from_model(spec, root=root) if is_model(spec) else build(spec)
    if name and rig["rig"] != name:
        raise ValueError(f"the file is the prop {rig['rig']}, not {name}: a prop's specs name its rig, so the two must agree")
    name = rig["rig"]
    keep = keep or out
    os.makedirs(out, exist_ok=True)
    os.makedirs(keep, exist_ok=True)
    manifest_path = os.path.join(keep, f"{name.lower()}.props.json")
    if os.path.isfile(manifest_path):                         # what the last build left: gone before this one starts
        try:
            with open(manifest_path, encoding="utf-8") as fh:
                last = json.load(fh)
        except ValueError:
            last = {}
        for b in last.get("built") or [] if isinstance(last, dict) else []:
            for k in ("model", "clip"):
                p = b.get(k) if isinstance(b, dict) else None
                if isinstance(p, str) and os.path.isfile(p) and os.path.basename(p).endswith((".model.json", ".clip.json")):
                    os.remove(p)
    work = tempfile.mkdtemp(prefix="kit_prop_")
    try:
        rigs = os.path.join(work, "rigs")
        os.makedirs(rigs)
        rig_file = os.path.join(rigs, f"{name.lower()}.json")
        with open(rig_file, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(rig, fh, indent=1)
        kept_rig = os.path.join(keep, f"{name.lower()}.rig.json")
        shutil.copyfile(rig_file, kept_rig)
        here = os.path.dirname(os.path.abspath(__file__))
        read, refused = [], []
        for sp in spec_paths:
            try:
                with open(sp, encoding="utf-8") as fh:
                    ks = json.load(fh)
            except (OSError, ValueError) as e:
                refused.append({"spec": sp, "why": f"it cannot be read ({e})"})
                continue
            stem = ks.get("name") if isinstance(ks, dict) else None
            if not isinstance(stem, str) or not stem.isidentifier():
                refused.append({"spec": sp, "why": "it has no name (one word)"})
                continue
            read.append((sp, stem))
        names = [stem for _, stem in read]
        built = []
        for sp, stem in read:
            if names.count(stem) > 1:
                refused.append({"spec": sp, "why": f"{stem}: {names.count(stem)} specs carry this name - one clip, one name"})
                continue
            made = os.path.join(work, "made", stem)
            r = subprocess.run([lune, "run", os.path.join(here, "prop_clip.luau"), rigs, sp, made], capture_output=True,
                               text=True, encoding="utf-8")
            line = (r.stdout or "").strip().splitlines()[-1] if (r.stdout or "").strip() else ""
            try:
                v = json.loads(line)
            except ValueError:
                v = {"status": "fail", "summary": f"the compiler gave no verdict ({(r.stderr or r.stdout or '').strip()[-200:]})"}
            if r.returncode != 0 or v.get("status") != "pass":
                refused.append({"spec": sp, "why": str(v.get("summary"))})
                continue
            with open(v["clip"], encoding="utf-8") as fh:
                clip = json.load(fh)
            _, problem = gate(clip, rig)
            if problem:
                refused.append({"spec": sp, "why": f"{stem}: {problem}"})
                continue
            final_model, final_clip = os.path.join(out, f"{stem}.model.json"), os.path.join(keep, f"{stem}.clip.json")
            shutil.copyfile(v["clip"], final_clip)
            shutil.copyfile(v["model"], final_model)
            with open(sp, "rb") as fh:
                sha = hashlib.sha256(fh.read()).hexdigest()
            built.append({"name": stem, "model": final_model.replace(os.sep, "/"), "clip": final_clip.replace(os.sep, "/"),
                          "spec": sp.replace(os.sep, "/"), "spec_sha256": sha})
    finally:
        shutil.rmtree(work, ignore_errors=True)
    with open(prop_path, "rb") as fh:
        prop_sha = hashlib.sha256(fh.read()).hexdigest()
    manifest = {"schema": 1, "prop": name, "rig": kept_rig.replace(os.sep, "/"), "prop_sha256": prop_sha,
                "root": rig["root"], "joints_sha256": joints_hash(rig), "from_model": is_model(spec), "built": built,
                "refused": refused}
    with open(manifest_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(manifest, fh, indent=1)
    return manifest


def flag(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if len(argv) >= 3 and argv[0] == "stale-all":
        bad = stale_all(argv[1], argv[2])
        if bad:
            return emit("fail", f"{len(bad)} prop(s) carry clips built on other joints - {bad[0]}",
                        "lune run kit anim prop <Prop> --model   (builds every clip again, each held to the joints)", stale=bad)
        return emit("pass", "every prop's clips were built on the joints its model has now", "none - proceed")
    if len(argv) < 2 or argv[0] not in ("make", "clip", "go", "stale"):
        print(__doc__)
        return 2
    if argv[0] == "stale":
        props = flag(argv, "--props")
        if not props or not os.path.isfile(props):
            return emit("pass", f"prop {argv[1]}: no clips were built on it yet", "none - proceed")
        try:
            why = stale(argv[1], props)
        except (OSError, ValueError, KeyError, TypeError) as e:
            return emit("fail", f"prop {argv[1]}: its clips cannot be checked against the model ({e})", "lune run kit anim prop <Prop> --model")
        if why:
            return emit("fail", why, "lune run kit anim prop <Prop> --model   (builds every clip again, each held to the joints)")
        return emit("pass", f"prop {argv[1]}: its clips were built on the joints the model has now", "none - proceed")
    if argv[0] == "go":
        out = flag(argv, "--out")
        specs = []
        for a in argv[2:]:
            if a.startswith("--"):
                break
            specs.append(a)
        if not out or not specs:
            return emit("fail", "prop go: <prop.json> <spec.json>... --out <dir>", "lune run kit anim prop <Prop>")
        try:
            m = go(argv[1], specs, out, flag(argv, "--keep"), flag(argv, "--lune", "lune"),
                   "Handle" if "--tool" in argv else "Root", flag(argv, "--name"))
        except (OSError, ValueError, KeyError, TypeError) as e:
            return emit("fail", f"prop {argv[1]}: it is not a prop the kit can rig ({e})",
                        "fix the prop file: every part but the root has a parent and a pivot where the two touch")
        if m["refused"]:
            first = m["refused"][0]
            return emit("fail", f"prop {m['prop']}: {len(m['refused'])} of {len(specs)} clip(s) NOT built - {first['why']}",
                        "fix the keys of the part named (or the joint's range in the prop file if the prop really moves "
                        "that far), then build it again: a clip that breaks a joint leaves no model", **m)
        return emit("pass", f"prop {m['prop']}: its rig and {len(m['built'])} clip(s) built, each held to the prop's joints -> "
                            + ", ".join(b["model"] for b in m["built"]),
                    "none - the game plays each model on the prop's own joints (an AnimationController on the prop)", **m)
    try:
        with open(argv[1], encoding="utf-8") as fh:
            data = json.load(fh)
        if argv[0] == "make":
            out = flag(argv, "--out")
            if not out:
                return emit("fail", "prop rig: name where the rig goes (--out <rig.json>)", "python kit/anim/prop_rig.py make <prop.json> --out <rig.json>")
            bad = problems(data)
            if bad:
                return emit("fail", f"prop rig: {argv[1]} is not a prop - {bad[0]}" + (f" (+{len(bad) - 1} more)" if len(bad) > 1 else ""),
                            "fix the prop file: every part but the root has a parent and a pivot where the two touch", problems=bad)
            rig = build(data)
            if os.path.basename(out) != f"{rig['rig'].lower()}.json":
                return emit("fail", f"prop rig: the rig of {rig['rig']} is the file {rig['rig'].lower()}.json (the kit finds a rig by "
                                    f"that name), not {os.path.basename(out)}", "name the file after the prop, in lower case")
            os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
            with open(out, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(rig, fh, indent=1)
                fh.write("\n")
            kinds = [rig["limits"][n]["kind"] for n in rig["order"]]
            return emit("pass", f"prop rig {rig['rig']}: {len(rig['order']) + 1} part(s), {kinds.count('hinge')} hinge(s), "
                                f"{kinds.count('slide')} slide(s), {kinds.count('fixed')} fixed -> {out.replace(os.sep, '/')}",
                        "none - a keyframe spec animates it by naming the rig; its clips are held to these joints", rig=out.replace(os.sep, "/"))
        rig_path = flag(argv, "--rig")
        if not rig_path:
            return emit("fail", "prop clip: name the prop's rig (--rig <rig.json>)", "python kit/anim/prop_rig.py clip <clip.json> --rig <rig.json>")
        with open(rig_path, encoding="utf-8") as fh:
            rig = json.load(fh)
        if not isinstance(rig, dict) or rig.get("kind") != "prop":
            return emit("fail", f"prop clip: {rig_path} is not a prop's rig", "python kit/anim/prop_rig.py make <prop.json> --out <rig.json>")
        held, problem = gate(data, rig)
    except (OSError, ValueError, KeyError, IndexError, TypeError) as e:
        return emit("fail", f"prop rig: it could not be read or made ({type(e).__name__}: {e})", "python kit/anim/prop_rig.py")
    name = str(data.get("name"))
    if problem:
        return emit("fail", f"prop clip {name}: {problem}", "fix the keys of the part named, or widen the joint's range in the prop file "
                                                    "if the prop really opens that far", faults=held.get("faults"))
    return emit("pass", f"prop clip {name}: every part moves only as its joint allows ({len(rig.get('limits') or {})} joint(s))",
                "none - proceed")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
