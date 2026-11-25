"""rbx_cycle.py — a mechanism's ACTION CYCLE: the joints moving TOGETHER, as the real action moves them, keyed on the
.blend's timeline (the owner presses play in Blender and watches it work) and checked for collisions frame by frame.

Declared in the build script (rbx.Asset.cycle): keys = [(frame, {joint name: value, ...}), ...] - each joint
interpolated between ITS OWN keys (eased in and out: a real part starts and stops), held before its first key and
after its last; a joint never keyed stays at rest. One joint's keys can lead or lag another's - that is the coupling
(a revolver's hand turns the cylinder only while the hammer is past half-cock; the bolt drops before the turn and
rises into the next notch before it ends).

Why (the owner, 2026-11-10, on the 3D pipeline: "It's really bad at making hero weapons ... especially with detail
and proper mechanisms"): a.joint only checked each joint ALONE at five stops of its travel and drew a schematic;
nothing ever moved in the .blend he judges, and two parts that each clear alone can still meet when they move
together (a cylinder turning while its stop is still up in the notch).

  frames(keys, joints)            -> {frame: {group: value}}
  check(objs, joints, per_frame)  -> problems: a moving group driving into another past what touched at rest
  key(objs, joints, per_frame, scene, fps, marks) -> keyframes on the moving groups' objects + timeline markers
  clear(objs, rest)               -> the animation taken off again (the build's later checks pose by matrix)
"""

import math

import bpy

import rbx_mech
import rbx_travel

PIECES = 8        # each frame-to-frame move is first walked in this many pieces (a hinge's arc as its chords)
PER_FRAME = 512   # ... and then cut into this many at most (past it the cycle is said to be checked coarsely)


def _value(j, v):
    return j["max"] if v == "max" else j["min"] if v == "min" else float(v)


def frames(keys, joints, step=1):
    """keys [(frame, {joint name: value})] -> {frame: {group: value}} from the first key's frame to the last"""
    if not keys:
        raise ValueError("cycle: no keys - give [(frame, {joint name: value}), ...]")
    by_name = {j["name"]: g for g, j in joints.items()}
    per = {}
    for f, vals in keys:
        for nm, v in vals.items():
            g = by_name.get(nm)
            if g is None:
                raise ValueError(f"cycle: no joint named {nm!r} (the joints: {', '.join(sorted(by_name))})")
            j = joints[g]
            if j["kind"] == "fixed":
                raise ValueError(f"cycle: {nm} is a fixed joint - it rides on its parent and has no value")
            val = _value(j, v)
            lo, hi = min(j["min"], j["max"]), max(j["min"], j["max"])
            if not lo - 1e-6 <= val <= hi + 1e-6:
                raise ValueError(f"cycle: {nm} = {val:g} at frame {f} is outside its travel [{lo:g}, {hi:g}]")
            per.setdefault(g, []).append((int(f), val))
    f0 = min(int(f) for f, _ in keys)
    f1 = max(int(f) for f, _ in keys)
    out = {}
    for f in range(f0, f1 + 1, max(1, int(step))):
        vals = {}
        for g, ks in per.items():
            ks = sorted(ks)
            if f <= ks[0][0]:
                v = ks[0][1]
            elif f >= ks[-1][0]:
                v = ks[-1][1]
            else:
                v = ks[-1][1]
                for (fa, va), (fb, vb) in zip(ks, ks[1:]):
                    if fa <= f <= fb:
                        t = (f - fa) / (fb - fa) if fb > fa else 1.0
                        t = t * t * (3.0 - 2.0 * t)          # eased: a part starts and stops
                        v = va + (vb - va) * t
                        break
            vals[g] = v
        out[f] = vals
    return out


def pose_all(objs, joints, rest, vals):
    """every group back to rest, then each joint's move, deepest first (a child turns about its REST pivot and its
    parent's move carries it: M_parent @ M_child @ rest - the order rbx.Asset._pose_as_pictured uses)"""
    for k, o in objs.items():
        o.matrix_world = rest[k].copy()
    for g, v in sorted(vals.items(), key=lambda gv: -len(rbx_mech._chain(joints, gv[0]))):
        if g not in joints or joints[g]["kind"] == "fixed":
            continue
        m = rbx_mech.pose(joints[g], v)
        for k, o in objs.items():
            if g in rbx_mech._chain(joints, k):
                o.matrix_world = m @ o.matrix_world
    bpy.context.view_layer.update()


def moving_groups(objs, joints):
    return [k for k in objs if any(joints[g]["kind"] != "fixed" for g in rbx_mech._chain(joints, k) if g in joints)]


def _corners(o):
    m = o.matrix_world
    return [tuple(m @ type(m.translation)(c)) for c in o.bound_box]


def poses(objs, joints, per_frame, rest, movers, every=2):
    """the poses of a timeline to check: chosen by how far the parts MOVE (his D-R05: "coordinated cycles ...
    remain sampled too" - a wheel turned half round between two sampled frames passed a pin in its way unseen).
    Every frame-to-frame move is walked in pieces no longer than the mover's step (rbx_travel.step_for: half its
    own smallest depth), and a pose is checked before any mover has gone further than its step since the last
    one; every `every`-th frame and the last are checked as before.
    -> ([(frame - a fraction between two frames, {group: value})], the furthest a mover went between two
    checked poses against its own step (studs), None or the mover that went over its step: the check is coarse)"""
    fs = sorted(per_frame)
    if not fs:
        return [], 0.0, False
    diag = max((o.dimensions.length for o in objs.values()), default=1.0)
    steps = {}
    for g in movers:
        thin = [d for d in objs[g].dimensions if d > 1e-9]
        steps[g] = rbx_travel.step_for(min(thin) if thin else diag, diag)

    def at(vals):
        pose_all(objs, joints, rest, vals)
        return {g: _corners(objs[g]) for g in movers}

    def far(a, b):
        return {g: max(math.dist(p, q) for p, q in zip(a[g], b[g])) for g in movers}

    def mix(va, vb, t):
        return {g: va.get(g, 0.0) + (vb.get(g, 0.0) - va.get(g, 0.0)) * t for g in set(va) | set(vb)}

    cands, moves, must = [(fs[0], dict(per_frame[fs[0]]))], [], {0}
    was = at(per_frame[fs[0]])
    for k, (fa, fb) in enumerate(zip(fs, fs[1:]), 1):
        va, vb = per_frame[fa], per_frame[fb]
        if all(abs(va.get(g, 0.0) - vb.get(g, 0.0)) < 1e-9 for g in set(va) | set(vb)):
            n = 1                                      # (held: nothing moves)
        else:
            # how far over this one frame? walked in PIECES first (a full turn's chord is nothing), then cut as
            # fine as the thinnest mover's step asks
            trial, total = was, {g: 0.0 for g in movers}
            for i in range(1, PIECES + 1):
                now = at(mix(va, vb, i / PIECES))
                for g, d in far(trial, now).items():
                    total[g] += d
                trial = now
            n = max(1, min(PER_FRAME, max(int(math.ceil(total[g] / steps[g] - 1e-9)) for g in movers)
                           if movers else 1))
        for i in range(1, n + 1):
            vals = mix(va, vb, i / n) if i < n else dict(vb)
            now = at(vals)
            moves.append(far(was, now))
            was = now
            cands.append((fa + (fb - fa) * i / n, vals))
        if k % max(1, int(every)) == 0 or fb == fs[-1]:
            must.add(len(cands) - 1)
    picked, _scale, _wide = rbx_travel.walk(moves, must, steps)
    # how far each mover REALLY went between two checked poses, against its own step (the review: a move capped
    # per frame, or a walk widened to fit, was reported as the step it was meant to keep)
    worst, gap, who, acc, at = 0.0, 0.0, None, {}, set(picked)
    for i, m in enumerate(moves, 1):
        for g, d in m.items():
            acc[g] = acc.get(g, 0.0) + d
        if i in at:
            for g, d in acc.items():
                if d / steps[g] > worst:
                    worst, gap, who = d / steps[g], d, g
            acc = {}
    coarse = worst > 1.25      # (a quarter over a step: chords against arcs, and the cut's rounding)
    return [cands[i] for i in picked], gap, (who if coarse else None)


def check(objs, joints, per_frame, every=2):
    """the poses `poses` picks (by how far the parts move; every `every`-th frame and the last among them): does a
    moving group drive into another group past what touched at rest? (the rule rbx_mech.interference uses: more
    than 8 colliding triangle pairs AND a third more than at rest; springs never count) -> (problems, facts)"""
    rest = {g: o.matrix_world.copy() for g, o in objs.items()}
    movers = moving_groups(objs, joints)
    trees = {g: rbx_mech._tree(o) for g, o in objs.items()}
    base = {}
    for g in movers:
        for h in objs:
            if h != g:
                base[(g, h)] = len(rbx_mech._hard(trees[g].overlap(trees[h]), objs[g], objs[h]))
    # the depth test the per-joint check also runs (a few big triangles never make 8 colliding pairs: two boxes
    # passing through each other read "clear" by the pair count alone): points of a mover's surface deeper than
    # tol inside another group's solid, against how many already were at rest; a coarser grid than the per-joint
    # check's (a cycle poses every mover at every sampled frame)
    diag = max((o.dimensions.length for o in objs.values()), default=1.0)
    spacing, tol, memo = diag * 0.005, diag * 0.0015, {}
    skips = {g: set(rbx_mech._chain(joints, g)) | {k for k in objs if g in rbx_mech._chain(joints, k)} for g in movers}
    rest_pen = {g: {h: v[0] for h, v in rbx_mech.penetration(objs, g, skips[g], spacing, tol, memo).items()}
                for g in movers}
    fs = sorted(per_frame)
    problems, worst, seen, last = [], {}, set(), None
    sample, gap, coarse = [], 0.0, False
    try:
        sample, gap, coarse = poses(objs, joints, per_frame, rest, movers, every)
        for f, vals in sample:
            key_now = tuple(sorted((g, round(v, 4)) for g, v in vals.items()))
            if key_now == last:      # (a held pose - every joint where the last sampled frame had it - is checked)
                continue
            last = key_now
            pose_all(objs, joints, rest, vals)
            for g in movers:
                for h, (n, mid, who) in rbx_mech.penetration(objs, g, skips[g], spacing, tol, memo).items():
                    b = rest_pen[g].get(h, 0)
                    if n >= 3 and n > b * 1.34 + 2:
                        key = tuple(sorted((g, h)))
                        if key not in worst or n > worst[key][0]:
                            worst[key] = (n, f, b, (who or "").replace(" in ", " into "), mid)
            now = {g: rbx_mech._tree(objs[g]) for g in movers}
            for g in movers:
                for h in objs:
                    if h == g or (h, g, f) in seen:      # (a pair of two movers is tested once a frame)
                        continue
                    other = now.get(h) or trees[h]
                    pairs = rbx_mech._hard(now[g].overlap(other), objs[g], objs[h])
                    n, b = len(pairs), base.get((g, h), 0)
                    if n > max(8, b * 1.34):
                        key = tuple(sorted((g, h)))
                        if key not in worst or n > worst[key][0]:
                            parts = rbx_mech._pair_parts(pairs, objs[g], objs[h])
                            who = ", ".join(f"{a} into {z}" for (a, z), c in sorted(parts.items(), key=lambda t: -t[1])[:2])
                            worst[key] = (n, f, b, who, rbx_mech._where(pairs, objs[h]))
                    seen.add((g, h, f))
    finally:
        for k, o in objs.items():
            o.matrix_world = rest[k]
        bpy.context.view_layer.update()
    for (g, h), (n, f, b, who, at) in sorted(worst.items(), key=lambda t: -t[1][0]):
        problems.append(f"at frame {round(f, 2):g} '{g}' drives into '{h}' ({n} colliding triangle pairs or surface points inside, "
                        f"{b} at rest"
                        f"{': ' + who if who else ''}{f'; around {at}' if at else ''}) - change the keys (lead or lag "
                        "one joint), cut clearance, or move the part")
    facts = {"frames": [fs[0], fs[-1]] if fs else [], "sampled": len(sample), "moving": sorted(movers),
             "collisions": len(problems), "gap": round(gap, 4)}
    if coarse:   # (said, never silent: a mover went further between two poses than its own step)
        facts["coarse"], facts["coarse_of"] = round(gap, 4), f"'{coarse}' moved that far between two checked poses"
    return problems, facts


def key(objs, joints, per_frame, scene, fps=24, marks=None):
    """keyframes on every moving group's object for every frame (LINEAR between them: the easing is in the values),
    the scene's range and fps, markers naming the steps -> the rest matrices (to clear() after the save)"""
    rest = {g: o.matrix_world.copy() for g, o in objs.items()}
    movers = moving_groups(objs, joints)
    for g in movers:
        o = objs[g]
        o.rotation_mode = "QUATERNION"
    for f in sorted(per_frame):
        pose_all(objs, joints, rest, per_frame[f])
        for g in movers:
            o = objs[g]
            o.keyframe_insert("location", frame=f)
            o.keyframe_insert("rotation_quaternion", frame=f)
    for g in movers:
        ad = objs[g].animation_data
        if ad and ad.action:
            fcurves = getattr(ad.action, "fcurves", None)
            if fcurves is None:   # (Blender 4.4+: an action's curves live in its layers / channelbags)
                fcurves = [fc for layer in ad.action.layers for strip in layer.strips
                           for bag in strip.channelbags for fc in bag.fcurves]
            for fc in fcurves:
                for kp in fc.keyframe_points:
                    kp.interpolation = "LINEAR"
    fs = sorted(per_frame)
    scene.frame_start, scene.frame_end = fs[0], fs[-1]
    scene.render.fps = int(fps)
    for name, f in (marks or {}).items():
        scene.timeline_markers.new(str(name), frame=int(f))
    scene.frame_set(fs[0])
    return rest


def clear(objs, rest, scene=None):
    """the keyframes off again and every group back at rest (after the .blend is saved: the build's later checks
    and renders pose the groups by matrix, which an action would overwrite on a frame change)"""
    for g, o in objs.items():
        if o.animation_data:
            o.animation_data_clear()
        if g in rest:
            o.matrix_world = rest[g]
    if scene is not None:
        for m in list(scene.timeline_markers):
            scene.timeline_markers.remove(m)
    bpy.context.view_layer.update()


def trigger_pull(objs, joints, mm_per_stud=None):
    """a trigger is PULLED: at its full travel the lowest point of its blade moves BACK toward the grip (the kit's +Z;
    the front is -Z). The revolver's build 4 swung its trigger 4 mm toward the muzzle at the shot (a hinge's +8 degrees
    about +X turns what hangs below the pivot FORWARD) - the owner, 2026-11-11: "imagine you actually try to shoot it
    with that type of trigger, it didn't work out". -> problems (one per trigger joint that moves the wrong way)"""
    import re  # noqa: PLC0415

    out = []
    for g, j in joints.items():
        if j["kind"] != "hinge" or not re.search(r"trigger", str(j["name"]), re.IGNORECASE) or g not in objs:
            continue
        o = objs[g]
        mw = o.matrix_world
        pts = [mw @ v.co for v in o.data.vertices]
        if not pts:
            continue
        low = min(pts, key=lambda p: p.z)                   # (Blender z = the kit's up)
        end = j["max"] if abs(j["max"]) >= abs(j["min"]) else j["min"]
        moved = rbx_mech.pose(j, end) @ low
        back = (-moved.y) - (-low.y)                         # (Blender -y = the kit's +Z = toward the BACK)
        if back <= 0:
            unit, k = ("mm", mm_per_stud) if mm_per_stud else ("studs", 1.0)
            out.append(f"{j['name']}: at its full travel ({end:g} deg) the blade's tip moves {abs(back) * k:.1f} {unit} "
                       "toward the MUZZLE - a trigger is pulled BACK toward the grip: flip its axis (or the sign of its "
                       "travel)")
    return out
