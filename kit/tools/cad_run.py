"""cad_run.py — one build123d part -> the triangles a.cad() places (run in the cad env: lune run kit tools setup cad)

    <cad env>/python kit/tools/cad_run.py <code.py> --out <file.npz> [--tol 0.05] [--angle 12] [--params <json>]
        [--fillet <mm>]   (every hard edge rounded in CAD after the code: fillet_auto)
        [--chamfer <mm>]  (every hard edge cut back as one chamfer: the high-and-low route's low, chamfer_auto)

<code.py> builds the part with build123d — its names are already there, as after `from build123d import *` — and
leaves it in `part` (a Part, Solid or Compound, or the BuildPart context itself; `result` works too), in MILLIMETRES,
in the kit's axes: x right, y up, z back (the front is -Z). Measured numbers come in as `P`: a dict from --params
({} when not given). (a.cad's inline code is written to a .py file under build/cad first.)
The part is tessellated to `tol` mm (the surface's distance from the triangles) and `angle` degrees (between
neighbouring facets: a fillet gets enough of them to shade round) and written to <out>:
    verts (n, 3) float64 mm, tris (m, 3) int32 — each B-rep face's own vertices (the kit welds them)
One JSON verdict line: the solid's volume (mm3), area (mm2), bounding box (mm), how many solids and faces, whether
OpenCASCADE calls it valid, the triangle count and the seconds taken.

Kit helpers are there too, for parts built FROM TRACED PROFILES (kit refs profiles: real outlines have small
features a fixed radius cannot follow):
    clean_profile(r)          in a BuildSketch: specks and notches under 2r gone, every corner rounded to r (an opening
                              then a closing of the sketch) — a traced outline made machinable
    fillet_soft(edges, r)     fillet(edges, r), and when OpenCASCADE cannot, the largest of 0.75r / 0.5r / 0.35r that it
                              can; the verdict lists every one it had to reduce ("fillets_reduced") — never silently
    fillet_each(edges, r)     the same ONE EDGE AT A TIME (each found again by its midpoint after the last change):
                              when the set as a whole is refused, most of it still gets rounded
    hard_edges(part, deg=30)  the edges where two faces meet at a CORNER (normals more than deg apart): the ones a real
                              part has broken — fillet_each(hard_edges(part), 0.2) rounds what is still sharp and leaves
                              a fillet's own tangent seams alone (the sharp_edges gate measures the same thing)
And the REAL PARTS of kit/tools/cad_parts.py — screw("M3-0.5", 10, head="socket"), nut, pin(d, length),
roll_pin(d, length), spring(mean_d, wire_d, length, coils), clearance("M3"): down to the screws, at ISO sizes.
"""

import json
import math
import os
import runpy
import sys
import time
import traceback


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}),
          flush=True)
    return 0 if status == "pass" else 1


def open_edges(verts, tris, weld=1e-6):
    """edges used by one triangle only, once the vertices are welded (each B-rep face comes with its own copies)"""
    import numpy as np  # noqa: PLC0415

    if not tris:
        return -1
    v = np.array([(p.X, p.Y, p.Z) for p in verts], dtype=np.float64)
    _, inv = np.unique(np.round(v / weld).astype(np.int64), axis=0, return_inverse=True)
    t = inv.ravel()[np.array(tris, dtype=np.int64)]
    t = t[(t[:, 0] != t[:, 1]) & (t[:, 1] != t[:, 2]) & (t[:, 0] != t[:, 2])]
    e = np.sort(np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]]), axis=1)
    _, counts = np.unique(e, axis=0, return_counts=True)
    return int((counts == 1).sum())


def mesh_faces(part, tol, angle, min_size=None):
    """the part meshed with an ABSOLUTE tolerance: tol mm off the true surface at most (build123d's own tessellate
    meshes RELATIVE to each edge's size — a 50 mm cylinder 'to 0.05' came out 15-sided, 1.1 mm off; only the angle kept
    curves round),
    and a face OpenCASCADE could not mesh is left out and named, not a crash (the Glock frame's 0.4 mm fillet piece at
    the dust cover's front). -> (verts, tris, the faces left unmeshed, normals): normals = each vertex's TRUE surface
    normal there (the B-rep face's own, outward): a high-and-low route's high shades with them, never with normals
    guessed from its triangles (face-area weighting swung them on the long thin triangles of a fillet or a cone: the
    car rim's bore ring and lug-hole seats baked wavy, rework 6ebz)"""
    from OCP.BRep import BRep_Tool  # noqa: PLC0415
    try:
        from OCP.BRepLib import BRepLib_ToolTriangulatedShape  # noqa: PLC0415
    except ImportError:   # (an older OCP: no exact normals, the mesh's own shading as before)
        BRepLib_ToolTriangulatedShape = None
    from OCP.BRepMesh import BRepMesh_IncrementalMesh  # noqa: PLC0415
    from OCP.IMeshTools import IMeshTools_Parameters  # noqa: PLC0415
    from OCP.TopAbs import TopAbs_Orientation  # noqa: PLC0415
    from OCP.TopLoc import TopLoc_Location  # noqa: PLC0415

    prm = IMeshTools_Parameters()
    prm.Deflection, prm.Angle, prm.Relative, prm.InParallel = tol, math.radians(angle), False, True
    # no element under 1.5 tol: left free, the mesher strewed needle triangles (the Glock frame's smoothed walls and
    # fillets: 17,579 under the validator's zero-area line — cleaned on import, they tore 791 open edges); with it: 0
    prm.MinSize = 1.5 * tol if min_size is None else min_size   # (tessellate retries without it: see there)
    prm.ControlSurfaceDeflection = True
    BRepMesh_IncrementalMesh(part.wrapped, prm)
    verts, tris, missing, normals = [], [], [], []
    for face in part.faces():
        loc = TopLoc_Location()
        poly = BRep_Tool.Triangulation_s(face.wrapped, loc)
        if poly is None:
            missing.append(face)
            continue
        trsf = loc.Transformation()
        rev = face.wrapped.Orientation() == TopAbs_Orientation.TopAbs_REVERSED
        has_n = False
        if BRepLib_ToolTriangulatedShape is not None:
            try:   # (the surface's own normal at every node; turned out of a REVERSED face)
                BRepLib_ToolTriangulatedShape.ComputeNormals_s(face.wrapped, poly)
                has_n = poly.HasNormals()
            except Exception:  # noqa: BLE001 — no exact normals for this face: zeros (its shading is the mesh's)
                has_n = False
        off = len(verts)
        sgn = -1.0 if rev else 1.0
        for i in range(1, poly.NbNodes() + 1):
            p = poly.Node(i).Transformed(trsf)
            verts.append(build123d_vector(p.X(), p.Y(), p.Z()))
            if has_n:
                d = poly.Normal(i).Transformed(trsf)
                normals.append((sgn * d.X(), sgn * d.Y(), sgn * d.Z()))
            else:
                normals.append((0.0, 0.0, 0.0))
        for t in poly.Triangles():
            a, b, c = t.Value(1) + off - 1, t.Value(2) + off - 1, t.Value(3) + off - 1
            tris.append((a, c, b) if rev else (a, b, c))
    return verts, tris, missing, normals


def fill_small_holes(verts, tris, max_loop=96, max_span=3.0, weld=1e-6):
    """close the SMALL holes OpenCASCADE's mesher leaves where curved faces meet at a sliver (the Glock frame: one
    1 x 1.4 mm crack of 12-36 open edges at every tolerance — the retries fell back to a 4x coarser mesh that read as
    faceted): each loop of open edges is fanned shut, wound against its neighbours, when it is small — 12 points or
    fewer, or no more than max_span mm across (up to max_loop points). -> (tris, loops filled, open edges left)"""
    import numpy as np  # noqa: PLC0415

    if not tris:
        return tris, 0, -1
    v = np.array([(p.X, p.Y, p.Z) for p in verts], dtype=np.float64)
    _, inv = np.unique(np.round(v / weld).astype(np.int64), axis=0, return_inverse=True)
    inv = inv.ravel()
    rep = {}
    for i, w in enumerate(inv.tolist()):
        rep.setdefault(w, i)  # (one original vertex stands for each welded point)
    t = inv[np.array(tris, dtype=np.int64)]
    directed = set()
    for a, b, c in t.tolist():
        if a != b and b != c and a != c:
            directed.update(((a, b), (b, c), (c, a)))
    nxt = {}
    for a, b in directed:
        if (b, a) not in directed:  # a boundary: no face runs back along it
            if a in nxt:
                nxt[a] = None  # (two boundary edges leave one point: not a simple hole — left alone)
            else:
                nxt[a] = b
    out, filled, seen = list(tris), 0, set()
    for start in list(nxt):
        if start in seen or nxt.get(start) is None:
            continue
        loop, cur = [], start
        while cur is not None and cur not in seen and len(loop) <= max_loop:
            seen.add(cur)
            loop.append(cur)
            cur = nxt.get(cur)
        if cur != start or not 3 <= len(loop) <= max_loop:
            continue
        if len(loop) > 12:   # (a longer loop only when it is small: a crack, never an opening)
            pts = v[[rep[k] for k in loop]]
            if float(np.linalg.norm(pts.max(axis=0) - pts.min(axis=0))) > max_span:
                continue
        for k in range(1, len(loop) - 1):  # (the fan runs back along the boundary: (b, a) where faces have (a, b))
            out.append((rep[loop[0]], rep[loop[k + 1]], rep[loop[k]]))
        filled += 1
    return out, filled, open_edges(verts, out)


def build123d_vector(x, y, z):
    import build123d  # noqa: PLC0415

    return build123d.Vector(x, y, z)


def mesh_volume(verts, tris):
    """the signed volume a closed triangle mesh encloses (mm3)"""
    import numpy as np  # noqa: PLC0415

    if not tris:
        return 0.0
    v = np.array([(p.X, p.Y, p.Z) for p in verts], dtype=np.float64)
    t = np.array(tris, dtype=np.int64)
    a, b, c = v[t[:, 0]], v[t[:, 1]], v[t[:, 2]]
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)


def volume_allowed(area, volume, tol):
    """how far a chordal mesh may honestly fall short of its solid's volume: about area x tol (a 0.5 mm spring wire
    loses several percent at any tolerance), at least 0.5%"""
    return max(0.005, area * tol / volume) if volume > 0 else 1.0


# how far past what chords can lose a CLOSED mesh may still be off before the solid itself is called wrong: OpenCASCADE's
# deflection is no strict bound on lofted B-spline faces (the ARP grip: 0.94-0.99% against 0.60-0.65%, closed and
# right); the broken ones are far past it (the Glock frame: 9.5% against 1.4%; a garbage trigger BRep: 100%)
ROUNDED_LOW = [0]   # the corners rounded() rounded on a high-and-low route's LOW (facts low_rounded: its rounds are geometry)
LOW_ROUND_STEP = 30.0   # rounded() on the LOW: a corner's round in steps of at most this many degrees (its points at
                        # equal turns: 32 at most between chords, under the low's 35-degree smoothing). A smaller step
                        # does not stop the creases OpenCASCADE makes when it meshes neighbouring thin bands of a revolve
                        # with different counts round the axis (fans of twisted triangles: the rim's lip at 0.3 mm) - an
                        # angle limit on the low, which gives every band the same count, does (low={"angle": ...})
UNTRUE_FACTOR = 3.0
UNTRUE_FLOOR = 0.02


def volume_truth(vol_err, allowed, closed=True):
    """None when the mesh holds its solid's volume, else what is wrong: no tessellation came within UNTRUE_FACTOR x
    what chords can lose (and at least UNTRUE_FLOOR) — the SOLID disagrees with itself (a kinked outline, a
    self-intersecting fillet: the Glock's frame, 9.5%, a smoothed strap joined to its trace at a kink, 2026-10-10).
    Its mesh is the finest try, strewn with needles that the build's import dissolves: open edges in the build while
    this part said 0. Only a CLOSED mesh is judged: one with holes or unmeshed faces is off by its holes (said
    already as open edges / unmeshed faces), not by a wrong solid."""
    if not closed or vol_err <= max(UNTRUE_FACTOR * allowed, UNTRUE_FLOOR):
        return None
    return (f"its mesh is {vol_err:.1%} off the solid's own volume (chords lose at most {allowed:.1%}): the SOLID is "
            "wrong — a kinked outline or a self-intersecting fillet; it tears open on import. Bisect your last CAD / "
            "outline change by this number")


def tessellate(part, tol, angle):
    """mesh_faces, retried until the mesh is CLOSED and TRUE: OpenCASCADE can leave a face unmeshed or open (a small
    fillet round a hole, measured on the Silverballer's ring hammer: 43 open edges at any weld), and the minimum
    element size that stops needle triangles can stop it refining a big curved face — the Glock grip's side came out
    in chords up to 2 mm inside the true surface (the mesh 79.6 cm3 for a 94.8 cm3 solid: the magazine read as buried
    in the frame). Each try is checked against the solid's own volume (within what chords at tol can lose: area x
    tol, at least 0.5%); the first closed, true one is kept.
    -> (verts, tris, the (tol, angle) used, open edges, the faces still unmeshed, holes filled, volume error, the
    minimum element size used, the vertices' true surface normals)"""
    from OCP.BRepTools import BRepTools  # noqa: PLC0415

    # the minimum element size stepped DOWN before the tolerance is touched: the largest that still meshes true keeps
    # the fewest needles (thousands of them, cleaned on import, tore springs open); finer tolerances come last — a
    # mesh finer than asked is triangles under the validator's zero-area line, not quality
    tries = [(tol, angle, 1.5 * tol), (tol, angle, 0.75 * tol), (tol, angle, 0.35 * tol), (tol, angle, 0.0),
             (tol * 0.5, angle * 0.75, 0.75 * tol), (tol * 2.0, angle, 3.0 * tol), (tol * 4.0, angle * 1.5, 6.0 * tol)]
    solid = len(part.solids()) > 0
    true_vol = float(part.volume) if solid else 0.0
    # a chordal mesh sits up to tol inside a curved surface: it may honestly lose about area x tol (a 0.5 mm spring wire
    # loses several percent at any tolerance); more than that is a face meshed wrong
    allowed = volume_allowed(float(part.area), true_vol, tol) if solid else 1.0
    best = None
    for t_, a_, ms_ in tries:
        BRepTools.Clean_s(part.wrapped)  # (a shape keeps its last mesh: without this every try returns the same one)
        verts, tris, missing, normals = mesh_faces(part, t_, a_, ms_)
        holes = open_edges(verts, tris)
        filled = 0
        if holes > 0 and not missing and solid:  # (small holes at a sliver: fanned shut, said)
            tris, filled, holes = fill_small_holes(verts, tris)
        vol_err = abs(mesh_volume(verts, tris) - true_vol) / true_vol if solid and true_vol > 0 and tris else 0.0
        rank = (len(missing), holes if holes >= 0 else 10 ** 9, 0 if vol_err <= allowed else 1, vol_err)
        if best is None or rank < best[5]:
            best = (verts, tris, (t_, a_), holes, missing, rank, filled, vol_err, ms_, normals)
        if (holes == 0 and not missing and vol_err <= allowed) or not solid:  # (a surface handed over is open by nature)
            break
    return best[:5] + best[6:10]


def _wire_points(wire, step):
    """a closed wire walked in order as (x, y) points: every vertex (its corners) kept, and points every `step` mm
    along each edge between them"""
    segs = []
    for e in wire.order_edges():
        n = max(1, math.ceil(e.length / step))
        segs.append([e.position_at(i / n) for i in range(n + 1)])
    if len(segs) > 1:  # (an edge can run against the wire: chain each one on from where the last ended)
        if min((segs[0][0] - p).length for p in (segs[1][0], segs[1][-1])) < \
                min((segs[0][-1] - p).length for p in (segs[1][0], segs[1][-1])):
            segs[0].reverse()
    pts = list(segs[0])
    for seg in segs[1:]:
        if (seg[-1] - pts[-1]).length < (seg[0] - pts[-1]).length:
            seg = seg[::-1]
        pts.extend(seg[1:])
    return [(p.X, p.Y) for p in pts]



LADDER = (1.0, 0.8, 0.64, 0.5, 0.4, 0.32, 0.25, 0.2, 0.16, 0.12, 0.08, 0.05)


def hard_edges_of(shape, deg=30.0):
    """the edges where two faces meet at a CORNER (normals more than `deg` apart along the edge)"""
    import build123d  # noqa: PLC0415
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE  # noqa: PLC0415
    from OCP.TopExp import TopExp  # noqa: PLC0415
    from OCP.TopoDS import TopoDS  # noqa: PLC0415

    try:
        from OCP.collections import (  # noqa: PLC0415
            IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher as Owners,
        )
    except ImportError:
        from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape as Owners  # noqa: PLC0415
    to_face = getattr(TopoDS, "Face_s", None) or TopoDS.Face
    shape = getattr(shape, "part", shape)
    owners = Owners()
    TopExp.MapShapesAndAncestors_s(shape.wrapped, TopAbs_EDGE, TopAbs_FACE, owners)
    lim = math.cos(math.radians(deg))
    out = []
    for e in shape.edges():
        i = owners.FindIndex(e.wrapped)
        if not i:
            continue
        faces = [build123d.Face(to_face(f)) for f in owners.FindFromIndex(i)]
        if len(faces) != 2 or faces[0].wrapped.IsSame(faces[1].wrapped):
            continue
        for t in (0.25, 0.5, 0.75):
            p = e.position_at(t)
            if faces[0].normal_at(p).dot(faces[1].normal_at(p)) < lim:
                out.append(e)
                break
    return out


def _key(e):
    c = e.center()
    return f"{c.X:.4f},{c.Y:.4f},{c.Z:.4f}"


def fillet_child(brep_in, brep_out, state_path, r, deg=30.0):
    """the crash-safe fillet pass (run as a child: --fillet-child): every hard edge as close to r as it fits —
    all at once if taken, else each edge's own largest radius (probed alone, a ladder down from r), applied in
    groups biggest first. The state file records each probe's result and the edge being tried BEFORE each call, so a
    native crash loses only that one try (the parent marks it 0 and starts this again)"""
    import build123d  # noqa: PLC0415

    def save(st):
        with open(state_path + ".tmp", "w", encoding="utf-8") as fh:
            json.dump(st, fh)
        os.replace(state_path + ".tmp", state_path)
    try:
        with open(state_path, encoding="utf-8") as fh:
            st = json.load(fh)
    except (OSError, ValueError):
        st = {"probe": {}, "trying": None, "whole": None, "applied": {}, "group_bad": []}
    shape = build123d.import_brep(brep_in)
    edges = hard_edges_of(shape, deg)
    if not edges:
        build123d.export_brep(shape, brep_out)
        save(st)
        return 0
    if st.get("whole") is None:   # (the asked radius on every edge at once)
        st["trying"] = "whole"
        save(st)
        try:
            out = build123d.fillet(edges, r)
            ok = bool(out.is_valid)
        except Exception:  # noqa: BLE001
            ok = False
        st["whole"] = ok
        st["trying"] = None
        save(st)
        if ok:
            st["applied"] = {str(round(r, 4)): len(edges)}
            save(st)
            build123d.export_brep(out, brep_out)
            return 0
    for e in edges:   # each edge's own largest radius, alone
        k = _key(e)
        if k in st["probe"]:
            continue
        # the largest ladder step that takes, by BISECTION (a radius that fits means every smaller one does: ~4
        # tries an edge, not 12 — a traced frame has 100+ hard edges)
        lo, hi, got = 0, len(LADDER) - 1, 0.0
        while lo <= hi:
            mid = (lo + hi) // 2
            st["trying"] = [k, LADDER[mid]]
            save(st)
            try:
                ok = bool(build123d.fillet([e], r * LADDER[mid]).is_valid)
            except Exception:  # noqa: BLE001
                ok = False
            if ok:
                got, hi = r * LADDER[mid], mid - 1
            else:
                lo = mid + 1
        st["probe"][k] = got
        st["trying"] = None
        save(st)
    groups = {}
    for k, rr in st["probe"].items():
        if rr > 0:
            groups.setdefault(round(rr, 4), []).append([float(v) for v in k.split(",")])
    cur = shape
    for rr in sorted(groups, reverse=True):
        tag = str(rr)
        if tag in st["applied"] or tag in st["group_bad"]:
            continue
        now = hard_edges_of(cur, deg)
        pick = []
        for c in groups[rr]:
            if not now:
                break
            e2 = min(now, key=lambda e_: (e_.center() - build123d.Vector(*c)).length)
            if (e2.center() - build123d.Vector(*c)).length < max(0.5 * rr, 0.05) and e2 not in pick:
                pick.append(e2)
        if not pick:
            continue
        group_ok = False
        if tag not in st["group_bad"]:
            st["trying"] = ["group", tag]
            save(st)
            try:
                nxt = build123d.fillet(pick, rr)
                if nxt.is_valid:
                    cur, group_ok = nxt, True
                    st["applied"][tag] = st["applied"].get(tag, 0) + len(pick)
                    build123d.export_brep(cur, brep_in + ".partial")   # (a crash later keeps what took)
                else:
                    st["group_bad"].append(tag)
            except Exception:  # noqa: BLE001
                st["group_bad"].append(tag)
            st["trying"] = None
            save(st)
        if group_ok:
            continue
        # the group refused together: each of its edges ALONE, at its radius, then smaller
        for c in groups[rr]:
            ek = f"{c[0]:.4f},{c[1]:.4f},{c[2]:.4f}"
            if ek in st.setdefault("edge_done", {}):
                continue
            now = hard_edges_of(cur, deg)
            if not now:
                break
            e2 = min(now, key=lambda e_: (e_.center() - build123d.Vector(*c)).length)
            if (e2.center() - build123d.Vector(*c)).length >= max(0.5 * rr, 0.05):
                st["edge_done"][ek] = 0.0
                continue
            got = 0.0
            for f in (1.0, 0.7, 0.5):
                st["trying"] = ["edge", ek, f]
                save(st)
                try:
                    nxt = build123d.fillet([e2], rr * f)
                    if nxt.is_valid:
                        cur, got = nxt, rr * f
                        build123d.export_brep(cur, brep_in + ".partial")
                        break
                except Exception:  # noqa: BLE001, S112
                    continue
            st["edge_done"][ek] = got
            if got > 0:
                t2 = str(round(got, 4))
                st["applied"][t2] = st["applied"].get(t2, 0) + 1
            st["trying"] = None
            save(st)
    build123d.export_brep(cur, brep_out)
    return 0


def fillet_safe(part, r, workdir, attempts=24):
    """run fillet_child in a child process until it finishes, marking the try that crashed it each time ->
    (the filleted part or the input, {radius: edges}, notes)"""
    import subprocess  # noqa: PLC0415

    import build123d  # noqa: PLC0415

    base = os.path.join(workdir, "fillet_in.brep")
    out = os.path.join(workdir, "fillet_out.brep")
    state = os.path.join(workdir, "fillet_state.json")
    build123d.export_brep(part, base)
    notes = []
    for _ in range(attempts):
        if os.path.isfile(out):
            os.remove(out)
        rc = subprocess.run([sys.executable, os.path.abspath(__file__), "--fillet-child", base, out, state, str(r)],
                            capture_output=True, text=True, timeout=1800).returncode
        if rc == 0 and os.path.isfile(out):
            with open(state, encoding="utf-8") as fh:
                st = json.load(fh)
            got = build123d.import_brep(out)
            sharp = sum(1 for v in st["probe"].values() if v <= 0) + sum(1 for v in st.get("edge_done", {}).values()
                                                                          if v <= 0)
            if sharp:
                notes.append(["fillet_auto", round(r, 3), f"{sharp} edge(s) left sharp: no radius took"])
            return got, {float(k): v for k, v in st["applied"].items()}, notes
        try:
            with open(state, encoding="utf-8") as fh:
                st = json.load(fh)
        except (OSError, ValueError):
            break
        t = st.get("trying")
        if t == "whole":
            st["whole"] = False
        elif isinstance(t, list) and t and t[0] == "group":
            st["group_bad"].append(t[1])
        elif isinstance(t, list) and t and t[0] == "edge":
            st.setdefault("edge_done", {})[t[1]] = 0.0
        elif isinstance(t, list) and t:
            st["probe"][t[0]] = 0.0     # (this edge crashed OpenCASCADE: left sharp)
        st["trying"] = None
        notes.append(["fillet_auto", "crash", str(t)])
        with open(state, "w", encoding="utf-8") as fh:
            json.dump(st, fh)
    partial = base + ".partial"
    if os.path.isfile(partial):
        return build123d.import_brep(partial), {}, notes + [["fillet_auto", "gave up after crashes: partial"]]
    return part, {}, notes + [["fillet_auto", "gave up after crashes: no fillet"]]

def _arg(argv, flag, default):
    return argv[argv.index(flag) + 1] if flag in argv and argv.index(flag) + 1 < len(argv) else default


def main(argv):
    if argv[:1] == ["--fillet-child"]:   # (the crash-safe fillet pass's child: fillet_safe starts it)
        return fillet_child(argv[1], argv[2], argv[3], float(argv[4]))
    if not argv or "--out" not in argv:
        return emit("fail", "cad_run: needs <code.py> --out <file.npz>",
                    "called by a.cad() in a build script — see kit/skills/parallax-3d/SKILL.md (code CAD)")
    src, out = argv[0], _arg(argv, "--out", None)
    tol, angle = float(_arg(argv, "--tol", "0.05")), float(_arg(argv, "--angle", "12"))
    params = json.loads(_arg(argv, "--params", "{}"))
    t0 = time.time()
    try:
        import build123d
        import numpy as np
    except ImportError as e:
        return emit("fail", f"cad_run: the cad env cannot import {e.name}", "lune run kit tools setup cad")
    names = {k: getattr(build123d, k) for k in getattr(build123d, "__all__", []) if hasattr(build123d, k)}
    reduced = []

    def clean_profile(r):
        ctx = build123d.BuildSketch._get_context()
        start = ctx.sketch_local  # (its OWN coordinates: the global copy, put back, landed mirrored on a side
        # plane — the Glock's trigger guard, upside down behind the gun)
        for k in (1.0, 0.5, 0.25):
            try:
                for amount in (-r * k, 2 * r * k, -r * k):
                    build123d.offset(amount=amount, kind=build123d.Kind.ARC, mode=build123d.Mode.REPLACE)
                if k < 1.0:
                    reduced.append(["clean_profile", round(r, 3), round(r * k, 3)])
                return
            except Exception:  # noqa: BLE001 — a neck under 2r: the shrink split it; put it back, try smaller
                getattr(build123d, "insert", build123d.add)(start, mode=build123d.Mode.REPLACE)
        reduced.append(["clean_profile", round(r, 3), 0.0])  # (left as traced: said, never silently)

    def smooth_profile(corner_deg=35.0, step=0.4, tol=0.08):
        """the sketch's outline and its holes RE-FIT as smooth walls (cad_parts.outline per wire: a curve per run
        between its corners, the corners kept) — the last step of a sketch built from traced polygons, after the
        booleans, INSTEAD of clean_profile: extruded, a polygon has a facet at every traced point, clean_profile adds a
        0.05 mm arc at each (rounded tighter than any fillet), and no fillet takes a wall of those (the Glock's frame:
        every edge refused, even alone)"""
        import cad_parts  # noqa: PLC0415

        ctx = build123d.BuildSketch._get_context()
        start = ctx.sketch_local
        try:
            faces = []
            for f in start.faces():
                outer = cad_parts.outline(_wire_points(f.outer_wire(), step), corner_deg, tol).outer_wire()
                inner = [cad_parts.outline(_wire_points(w, step), corner_deg, tol).outer_wire()
                         for w in f.inner_wires()]
                faces.append(build123d.Face(outer, inner))
            getattr(build123d, "insert", build123d.add)(faces, mode=build123d.Mode.REPLACE)
        except Exception:  # noqa: BLE001 — left as it was: said, never silently
            getattr(build123d, "insert", build123d.add)(start, mode=build123d.Mode.REPLACE)
            reduced.append(["smooth_profile", 0.0])

    def fillet_soft(edges, r):
        edges = list(edges)
        if not edges:
            return None
        for k in (1.0, 0.75, 0.5, 0.35):
            try:
                got = build123d.fillet(edges, r * k)
            except Exception:  # noqa: BLE001, S112 — OpenCASCADE refused this radius: the next one down
                continue
            if k < 1.0:
                reduced.append([round(r, 3), round(r * k, 3)])
            return got
        reduced.append([round(r, 3), 0.0])
        return None

    def hard_edges(shape=None, deg=30.0):
        """the edges where two faces meet at a CORNER (their normals more than `deg` apart along the edge) — the
        edges a real part has broken; a fillet's own seams (tangent) and a round face's seam are left out.
        shape: a part (default: the BuildPart being built)"""
        from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE  # noqa: PLC0415
        from OCP.TopExp import TopExp  # noqa: PLC0415
        from OCP.TopoDS import TopoDS  # noqa: PLC0415

        try:  # (the kernel's own collections, OCP 7.8+ — build123d 0.13; earlier OCP: TopTools)
            from OCP.collections import (  # noqa: PLC0415
                IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher as Owners,
            )
        except ImportError:
            from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape as Owners  # noqa: PLC0415
        to_face = getattr(TopoDS, "Face_s", None) or TopoDS.Face

        if shape is None:
            shape = build123d.BuildPart._get_context().part
        shape = getattr(shape, "part", shape)
        owners = Owners()
        TopExp.MapShapesAndAncestors_s(shape.wrapped, TopAbs_EDGE, TopAbs_FACE, owners)
        lim = math.cos(math.radians(deg))
        out = []
        for e in shape.edges():
            i = owners.FindIndex(e.wrapped)
            if not i:
                continue
            faces = [build123d.Face(to_face(f)) for f in owners.FindFromIndex(i)]
            if len(faces) != 2 or faces[0].wrapped.IsSame(faces[1].wrapped):
                continue  # (an open edge, or a round face's own seam)
            for t in (0.25, 0.5, 0.75):  # (the angle can change along a curved edge: a slot's lip on a dome)
                p = e.position_at(t)
                if faces[0].normal_at(p).dot(faces[1].normal_at(p)) < lim:
                    out.append(e)
                    break
        return out

    def fillet_each(edges, r):
        edges = list(edges)
        if not edges:
            return 0
        if fillet_soft(edges, r) is not None:
            return len(edges)  # (the whole set took a radius: done, said in fillets_reduced if smaller)
        reduced.pop()  # (the set was refused outright: one edge at a time instead)
        ctx = build123d.BuildPart._get_context()
        done = 0
        for c in [e.center() for e in edges]:
            cur = min(ctx.part.edges(), key=lambda e: (e.center() - c).length)
            if (cur.center() - c).length > 1.5 * r:
                reduced.append([round(r, 3), "skipped: rounded into a neighbour"])
                continue
            if fillet_soft([cur], r) is not None:
                done += 1
        return done


    def chamfer_auto(shape, d, deg=30.0, ladder=(1.0, 0.75, 0.5, 0.35)):
        """the HIGH-AND-LOW route's LOW (a.cad with fillet_mm on Asset(low=...)): every edge its high rounds (sharper
        than `deg`) cut back as ONE chamfer about d mm wide - the high's round then bakes onto a 45-degree face, not
        into a two-texel band on a 90-degree corner (the car rim's wavy, sawtoothed edge highlights: rework 6ebz).
        All at once if OpenCASCADE takes it, else each edge alone, as wide as it takes -> (the shape, {size: edges});
        edges left sharp are said in fillets_reduced"""
        shape = getattr(shape, "part", shape)
        edges = hard_edges(shape, deg)
        if not edges:
            return shape, {}
        for k in ladder:
            try:
                out = build123d.chamfer(edges, d * k)
                if out.is_valid:
                    return out, {round(d * k, 3): len(edges)}
            except Exception:  # noqa: BLE001, S112 — refused as a set at this size: smaller, then one by one
                continue
        cur, done = shape, {}
        for e0 in edges:
            c0 = e0.center()
            for k in ladder:
                try:
                    now = hard_edges(cur, deg)
                    e = min(now, key=lambda e_: (e_.center() - c0).length) if now else None
                    if e is None or (e.center() - c0).length > max(d, 0.05):
                        break
                    nxt = build123d.chamfer([e], d * k)
                    if nxt.is_valid:
                        cur = nxt
                        done[round(d * k, 3)] = done.get(round(d * k, 3), 0) + 1
                        break
                except Exception:  # noqa: BLE001, S112
                    continue
        left = len(edges) - sum(done.values())
        if left:
            reduced.append(["chamfer_auto", round(d, 3), f"{left} edge(s) left sharp: no chamfer took"])
        return cur, done

    def rounded(pts, r, n=4, sharp_only=None, low_turn=30.0):
        """a closed 2D profile's corners rounded (a quadratic arc, n segments, cut back r or 40% of the shorter side)
        - rounds IN the profile, so a revolve gets real round edges at a cone-band's triangle cost (OpenCASCADE's own
        fillets on a 467 mm revolve tessellate to ~95,000-500,000 triangles). sharp_only=deg: only the corners
        turning more than deg. Building the LOW of the high-and-low route (P["low"]): each corner turning more than 30
        degrees gets the same round in as few segments as keep every step at LOW_ROUND_STEP (30) degrees or under (a
        90-degree corner: 3) - the round is geometry, shaded smooth by its own normals inside one UV island; a normal-mapped round on a
        sharp low corner was a 2-5 texel band that stair-stepped and wobbled along every facet (rework 6ebz).
        low_turn: on the low, only corners turning more than this are rounded (60: the right angles only - a part seen
        from afar, or hidden in use, keeps its gentler corners sharp, their rounds baked). On that route the points
        sit at EQUAL turns along the arc (evenly spaced in t they turned 11/34/34/11 degrees at a right angle and 47 in
        the middle at 120: a hard edge inside the round), and the HIGH (P["kit_high"]) takes a step of 6 degrees at
        most - its B-rep normals shade each step flat, and the bake copied coarse steps. Without the route: as ever."""
        import math as _m  # noqa: PLC0415

        low, high = bool(params.get("low")), bool(params.get("kit_high"))
        out, m = [], len(pts)
        for i in range(m):
            p0, p1, p2 = pts[i - 1], pts[i], pts[(i + 1) % m]
            ax, ay, bx, by = p1[0] - p0[0], p1[1] - p0[1], p2[0] - p1[0], p2[1] - p1[1]
            la, lb = _m.hypot(ax, ay), _m.hypot(bx, by)
            turn = _m.degrees(_m.acos(max(-1.0, min(1.0, (ax * bx + ay * by) / max(la * lb, 1e-12)))))
            if (sharp_only is not None and turn <= sharp_only) or (low and turn <= max(30.0, float(low_turn))):
                out.append(p1)
                continue
            n_ = (max(1, int(_m.ceil(turn / LOW_ROUND_STEP - 1e-9))) if low
                  else max(int(n), int(_m.ceil(turn / 6.0 - 1e-9))) if high else int(n))
            dd = min(r, 0.4 * la, 0.4 * lb)
            t1 = (p1[0] - ax / la * dd, p1[1] - ay / la * dd)
            t2 = (p1[0] + bx / lb * dd, p1[1] + by / lb * dd)
            u, w = (p1[0] - t1[0], p1[1] - t1[1]), (t2[0] - p1[0], t2[1] - p1[1])   # (the tangent: (1-t) u + t w)
            a0, sw = _m.atan2(u[1], u[0]), (1.0 if u[0] * w[1] - u[1] * w[0] >= 0 else -1.0)
            for k in range(n_ + 1):
                t = k / n_
                if (low or high) and 0 < k < n_:   # (the t where the tangent has turned k/n of the corner)
                    e = (_m.cos(a0 + sw * _m.radians(turn) * k / n_), _m.sin(a0 + sw * _m.radians(turn) * k / n_))
                    cu, cw = u[0] * e[1] - u[1] * e[0], w[0] * e[1] - w[1] * e[0]
                    t = cu / (cu - cw) if abs(cu - cw) > 1e-12 else t
                out.append(((1 - t) ** 2 * t1[0] + 2 * (1 - t) * t * p1[0] + t * t * t2[0],
                            (1 - t) ** 2 * t1[1] + 2 * (1 - t) * t * p1[1] + t * t * t2[1]))
            if low:
                ROUNDED_LOW[0] += 1
        return out

    def fillet_auto(shape, r, deg=30.0, ladder=(1.0, 0.8, 0.64, 0.5, 0.4, 0.32, 0.25, 0.2, 0.16, 0.12, 0.08, 0.05)):
        """EVERY hard edge of `shape` rounded in CAD, each as close to r as it fits — the asked radius on all at
        once if OpenCASCADE takes it; else each edge's own largest radius (a ladder down from r, tried on the edge
        alone) and the edges filleted in groups, biggest first (a 3 mm round on the long edges, 0.5 mm round a
        0.6 mm tip). Lines + arcs meeting TANGENT (kit refs redraw) take fillets a fitted spline refuses.
        -> (the rounded shape, {radius: edges}) — every edge left sharp is said in fillets_reduced"""
        shape = getattr(shape, "part", shape)
        edges = hard_edges(shape, deg)
        if not edges:
            return shape, {}
        try:
            out = build123d.fillet(edges, r)
            if out.is_valid:
                return out, {round(r, 3): len(edges)}
        except Exception:  # noqa: BLE001 — refused as a set: per edge below
            pass
        best = {}
        for e in edges:
            for k in ladder:
                try:
                    if build123d.fillet([e], r * k).is_valid:
                        best[e] = r * k
                        break
                except Exception:  # noqa: BLE001, S112
                    continue
        groups = {}
        for e, rr in best.items():
            groups.setdefault(round(rr, 4), []).append(e.center())
        sharp = len(edges) - len(best)
        if sharp:
            reduced.append(["fillet_auto", round(r, 3), f"{sharp} edge(s) left sharp: no radius took"])
        done = {}
        cur = shape
        for rr in sorted(groups, reverse=True):
            cents = groups[rr]
            now = hard_edges(cur, deg)
            pick = []
            for c in cents:
                e2 = min(now, key=lambda e_: (e_.center() - c).length) if now else None
                if e2 is not None and (e2.center() - c).length < max(0.5 * rr, 0.05) and e2 not in pick:
                    pick.append(e2)
            if not pick:
                continue
            try:
                nxt = build123d.fillet(pick, rr)
                if nxt.is_valid:
                    cur, done[rr] = nxt, len(pick)
                    continue
            except Exception:  # noqa: BLE001 — the group refused together: each alone
                pass
            for e2 in pick:
                for k in (1.0, 0.7, 0.5):
                    try:
                        nxt = build123d.fillet([min(hard_edges(cur, deg), key=lambda e_: (e_.center() - e2.center()).length)], rr * k)
                        if nxt.is_valid:
                            cur = nxt
                            done[round(rr * k, 4)] = done.get(round(rr * k, 4), 0) + 1
                            break
                    except Exception:  # noqa: BLE001, S112
                        continue
        if done and max(done) < r - 1e-6:
            reduced.append(["fillet_auto", round(r, 3), {str(k): v for k, v in sorted(done.items(), reverse=True)}])
        return cur, done

    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import cad_parts  # noqa: PLC0415  (screws, nuts, pins, roll pins, springs, clearance holes)

        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "blender"))
        import rbx_profile  # noqa: PLC0415  (the build scripts' outline operations: rbx.profile)

        ns = runpy.run_path(src, init_globals={**names, "P": dict(params), "clean_profile": clean_profile,
                                               "smooth_profile": smooth_profile,
                                               "fillet_soft": fillet_soft, "fillet_each": fillet_each,
                                               "hard_edges": hard_edges, "fillet_auto": fillet_auto,
                                               "chamfer_auto": chamfer_auto, "rounded": rounded,
                                               "profile": rbx_profile, **cad_parts.HELPERS},
                            run_name="__cad__")
    except Exception as e:  # noqa: BLE001 — the CAD code's own error, said plainly
        where = [f for f in traceback.extract_tb(e.__traceback__) if f.filename == src]
        line = f" (line {where[-1].lineno})" if where else ""
        return emit("fail", f"cad_run: the CAD code failed{line}: {type(e).__name__}: {e}",
                    "fix the code; build123d docs: https://build123d.readthedocs.io")
    part = ns.get("part", ns.get("result"))
    if part is not None and not isinstance(part, build123d.Shape) and hasattr(part, "part"):
        part = part.part  # a `with BuildPart() as part:` context: its result
    if not isinstance(part, build123d.Shape):
        return emit("fail", "cad_run: the code left no `part` (a build123d Part / Solid / Compound)",
                    "end the code with: part = <your shape>  (or build it in `with BuildPart() as part:`)")
    fillet_done = None
    if float(_arg(argv, "--fillet", "0") or 0) > 0:   # (a.cad fillet_mm=: every hard edge rounded in CAD, crash-safe)
        import tempfile  # noqa: PLC0415

        with tempfile.TemporaryDirectory(prefix="kit_fillet_") as wd:
            part, fillet_done, notes = fillet_safe(part, float(_arg(argv, "--fillet", "0")), wd)
        reduced.extend(notes)
    chamfer_done = None
    if float(_arg(argv, "--chamfer", "0") or 0) > 0:   # (the high-and-low route's low: the high's rounds as chamfers)
        part, chamfer_done = chamfer_auto(part, float(_arg(argv, "--chamfer", "0")))
    verts, tris, (tol_used, angle_used), holes, unmeshed, holes_filled, vol_err, min_size, normals =         tessellate(part, tol, angle)
    if not tris:
        return emit("fail", "cad_run: the part has no surface to tessellate", "check that the code builds a solid")
    np.savez(out, verts=np.array([(p.X, p.Y, p.Z) for p in verts], dtype=np.float64),
             tris=np.array(tris, dtype=np.int32),
             normals=np.array(normals, dtype=np.float32).reshape(-1, 3))   # (each vertex's true surface normal)
    bb = part.bounding_box()
    untrue = volume_truth(vol_err, volume_allowed(float(part.area), float(part.volume), tol),
                          closed=holes == 0 and not unmeshed) if part.solids() and float(part.volume) > 0 else None
    facts = {"volume_mm3": round(float(part.volume), 3), "area_mm2": round(float(part.area), 3),
             "bbox_mm": [[round(bb.min.X, 4), round(bb.min.Y, 4), round(bb.min.Z, 4)],
                         [round(bb.max.X, 4), round(bb.max.Y, 4), round(bb.max.Z, 4)]],
             "solids": len(part.solids()), "faces": len(part.faces()), "valid": bool(part.is_valid),
             "triangles": len(tris), "tol_mm": tol, "angle_deg": angle, "open_edges": holes,
             **({"retessellated": [tol_used, angle_used]} if (tol_used, angle_used) != (tol, angle) else {}),
             **({"fillets_reduced": reduced} if reduced else {}),
             **({"fillet_auto": {str(k): v for k, v in sorted(fillet_done.items(), reverse=True)}}
                if fillet_done is not None else {}),
             **({"chamfer_auto": {str(k): v for k, v in sorted(chamfer_done.items(), reverse=True)}}
                if chamfer_done is not None else {}),
             **({"holes_filled": holes_filled} if holes_filled else {}),
             **({"low_rounded": ROUNDED_LOW[0]} if ROUNDED_LOW[0] else {}),
             "mesh_volume_error": round(vol_err, 5), "min_size_mm": round(min_size, 4),
             **({"volume_untrue": untrue} if untrue else {}),
             **({"unmeshed_faces": [{"at_mm": [round(f.center().X, 2), round(f.center().Y, 2), round(f.center().Z, 2)],
                                     "area_mm2": round(float(f.area), 3), "kind": f.geom_type.name}
                                    for f in unmeshed[:8]]} if unmeshed else {}),
             "build123d": build123d.__version__,
             "seconds": round(time.time() - t0, 2)}
    hole = (f"; {len(unmeshed)} face(s) OpenCASCADE could not mesh (a hole: unmeshed_faces says where — usually a "
            f"tiny fillet piece; leave that edge out of the fillet)") if unmeshed else ""
    untrue_ = f"; {untrue}" if untrue else ""
    return emit("pass", f"cad_run: {facts['solids']} solid(s), {facts['faces']} faces, {facts['volume_mm3']} mm3, "
                f"{facts['triangles']} triangles ({facts['seconds']} s){hole}{untrue_}", "none — a.cad places it",
                **facts)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
