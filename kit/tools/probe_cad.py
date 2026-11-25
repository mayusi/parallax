"""probe_cad.py — does the CAD stack work? (run in the cad env)

    <env>/python kit/tools/probe_cad.py [--keep <folder>]

The test part: a 40 x 30 x 20 mm box, its four upright edges rounded (r 3), a 10 mm hole straight through, the
hole's top edge chamfered 1 mm. Built twice when build123d imports — with build123d and with OpenCASCADE itself
(OCP: what build123d runs on) — else with OCP only. Each part is exported to STL and GLB, read back, and its volume
compared with the volume worked out by hand:
    24000 - 4 x (9 - 9 pi / 4) x 20 (the rounded corners) - pi x 25 x 20 (the hole) - 2 pi x (5 + 1/3) x 0.5 (the
    chamfer ring) = 22257.93 mm3
The files go to a temporary folder (deleted) unless --keep. One JSON verdict line.
"""

import json
import math
import os
import struct
import sys
import tempfile
import time

EXPECTED_MM3 = 24000 - 4 * (9 - 9 * math.pi / 4) * 20 - math.pi * 25 * 20 - 2 * math.pi * (5 + 1 / 3) * 0.5
TOLERANCE_MM3 = 0.5


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}),
          flush=True)
    return 0 if status == "pass" else 1


def stl_triangles(path):
    """triangle count of an STL file, binary or ASCII"""
    with open(path, "rb") as fh:
        data = fh.read()
    if len(data) >= 84:
        n = struct.unpack_from("<I", data, 80)[0]
        if 84 + 50 * n == len(data):
            return n
    return data.count(b"facet normal")


def glb_triangles(path):
    """triangle count of a binary glTF: the index accessors of every triangle primitive"""
    with open(path, "rb") as fh:
        data = fh.read()
    magic, _version, _length = struct.unpack_from("<III", data, 0)
    if magic != 0x46546C67:  # b"glTF"
        raise ValueError(f"{path} is not a binary glTF")
    chunk_len, chunk_type = struct.unpack_from("<II", data, 12)
    if chunk_type != 0x4E4F534A:  # b"JSON"
        raise ValueError(f"{path}: the first chunk is not JSON")
    doc = json.loads(data[20:20 + chunk_len])
    tris = 0
    for mesh in doc.get("meshes", []):
        for prim in mesh.get("primitives", []):
            if prim.get("mode", 4) != 4:
                continue
            if "indices" in prim:
                tris += doc["accessors"][prim["indices"]]["count"] // 3
            else:
                tris += doc["accessors"][prim["attributes"]["POSITION"]]["count"] // 3
    return tris


def with_ocp(folder):
    """the test part with OpenCASCADE's own API (OCP)"""
    from OCP.BRep import BRep_Tool  # noqa: PLC0415
    from OCP.BRepAdaptor import BRepAdaptor_Curve  # noqa: PLC0415
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut  # noqa: PLC0415
    from OCP.BRepFilletAPI import BRepFilletAPI_MakeChamfer, BRepFilletAPI_MakeFillet  # noqa: PLC0415
    from OCP.BRepGProp import BRepGProp  # noqa: PLC0415
    from OCP.BRepMesh import BRepMesh_IncrementalMesh  # noqa: PLC0415
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder  # noqa: PLC0415
    from OCP.GeomAbs import GeomAbs_Circle, GeomAbs_Line  # noqa: PLC0415
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt  # noqa: PLC0415
    from OCP.GProp import GProp_GProps  # noqa: PLC0415
    from OCP.Message import Message_ProgressRange  # noqa: PLC0415
    from OCP.RWGltf import RWGltf_CafWriter  # noqa: PLC0415
    from OCP.StlAPI import StlAPI_Writer  # noqa: PLC0415
    from OCP.TCollection import TCollection_AsciiString, TCollection_ExtendedString  # noqa: PLC0415
    from OCP.collections import (  # noqa: PLC0415
        IndexedDataMap_TCollection_AsciiString_TCollection_AsciiString as Meta)
    from OCP.TDocStd import TDocStd_Document  # noqa: PLC0415
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE  # noqa: PLC0415
    from OCP.TopExp import TopExp_Explorer  # noqa: PLC0415
    from OCP.TopLoc import TopLoc_Location  # noqa: PLC0415
    from OCP.TopoDS import TopoDS  # noqa: PLC0415
    from OCP.XCAFDoc import XCAFDoc_DocumentTool  # noqa: PLC0415

    def edges(shape):
        ex = TopExp_Explorer(shape, TopAbs_EDGE)
        while ex.More():
            yield TopoDS.Edge(ex.Current())
            ex.Next()

    shape = BRepPrimAPI_MakeBox(gp_Pnt(-20, -15, -10), 40, 30, 20).Shape()
    fil = BRepFilletAPI_MakeFillet(shape)
    for e in edges(shape):
        c = BRepAdaptor_Curve(e)
        if c.GetType() == GeomAbs_Line and abs(abs(c.Line().Direction().Z()) - 1) < 1e-9:
            fil.Add(3.0, e)
    shape = fil.Shape()
    hole = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, -11), gp_Dir(0, 0, 1)), 5, 22).Shape()
    shape = BRepAlgoAPI_Cut(shape, hole).Shape()
    cham = BRepFilletAPI_MakeChamfer(shape)
    for e in edges(shape):
        c = BRepAdaptor_Curve(e)
        if c.GetType() == GeomAbs_Circle and abs(c.Circle().Radius() - 5) < 1e-6 and c.Circle().Location().Z() > 9.9:
            cham.Add(1.0, e)
    shape = cham.Shape()
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    BRepMesh_IncrementalMesh(shape, 0.01, False, 0.1, True)
    stl = os.path.join(folder, "probe_ocp.stl")
    StlAPI_Writer().Write(shape, stl)
    glb = os.path.join(folder, "probe_ocp.glb")
    doc = TDocStd_Document(TCollection_ExtendedString("probe"))
    XCAFDoc_DocumentTool.ShapeTool_s(doc.Main()).AddShape(shape)
    RWGltf_CafWriter(TCollection_AsciiString(glb), True).Perform(doc, Meta(), Message_ProgressRange())
    mesh_tris = 0
    loc = TopLoc_Location()
    ex = TopExp_Explorer(shape, TopAbs_FACE)
    while ex.More():
        t = BRep_Tool.Triangulation_s(TopoDS.Face(ex.Current()), loc)
        mesh_tris += t.NbTriangles() if t is not None else 0
        ex.Next()
    return {"volume": props.Mass(), "mesh_triangles": mesh_tris, "stl": stl, "glb": glb}


def with_build123d(folder):
    """the same part, written as build123d code"""
    from build123d import (  # noqa: PLC0415
        Axis, Box, BuildPart, Cylinder, GeomType, Mode, chamfer, export_gltf, export_stl, fillet)

    with BuildPart() as p:
        Box(40, 30, 20)
        fillet(p.edges().filter_by(Axis.Z), radius=3)
        Cylinder(5, 22, mode=Mode.SUBTRACT)
        chamfer(p.edges().filter_by(GeomType.CIRCLE).sort_by(Axis.Z)[-1], length=1)
    part = p.part
    stl, glb = os.path.join(folder, "probe_b3d.stl"), os.path.join(folder, "probe_b3d.glb")
    export_stl(part, stl)
    export_gltf(part, glb, binary=True)
    return {"volume": part.volume, "stl": stl, "glb": glb}


def check(name, r):
    r["stl_triangles"] = stl_triangles(r["stl"])
    r["glb_triangles"] = glb_triangles(r["glb"])
    r["volume_error"] = abs(r["volume"] - EXPECTED_MM3)
    ok = r["volume_error"] <= TOLERANCE_MM3 and r["stl_triangles"] > 0 and r["glb_triangles"] > 0
    r["stl"], r["glb"] = os.path.basename(r["stl"]), os.path.basename(r["glb"])
    return ok, (f"{name}: volume {r['volume']:.2f} mm3 (by hand {EXPECTED_MM3:.2f}), STL {r['stl_triangles']} "
                f"triangles, GLB {r['glb_triangles']}")


def main(argv):
    keep = argv[argv.index("--keep") + 1] if "--keep" in argv else None
    t0 = time.time()
    try:
        import OCP  # noqa: PLC0415

        ocp_version = getattr(OCP, "__version__", "?")
    except ImportError as e:
        return emit("fail", f"cad: OpenCASCADE (OCP) does not import ({e})", "lune run kit tools setup cad")
    tmp = None
    if keep:
        os.makedirs(keep, exist_ok=True)
        folder = keep
    else:
        tmp = tempfile.TemporaryDirectory(prefix="kit-cad-probe-")
        folder = tmp.name
    lines, ok = [], True
    try:
        good, line = check("OCP", with_ocp(folder))
        ok = ok and good
        lines.append(line)
        b3d_error = None
        try:
            import build123d  # noqa: PLC0415

            b3d_version = getattr(build123d, "__version__", "?")
        except ImportError as e:
            b3d_version, b3d_error = None, f"{type(e).__name__}: {e}"
        if b3d_version:
            good, line = check("build123d", with_build123d(folder))
            ok = ok and good
            lines.append(line)
    finally:
        if tmp:
            tmp.cleanup()
    took = time.time() - t0
    if not ok:
        return emit("fail", "cad: the test part came out wrong — " + "; ".join(lines),
                    "report it with the versions: OCP " + ocp_version, lines=lines)
    if b3d_error:
        return emit("fail", f"cad: OpenCASCADE {ocp_version} works ({lines[0]}, {took:.1f} s) but build123d does "
                            f"not import ({b3d_error})",
                    "build123d's own dependencies are not installed: lune run kit tools setup cad (once they are "
                    "pinned in kit/tools/pins/cad.txt)", lines=lines, ocp=ocp_version, build123d_error=b3d_error)
    return emit("pass", f"cad: build123d {b3d_version} on OpenCASCADE {ocp_version} — " + "; ".join(lines)
                + f" ({took:.1f} s)", "none — proceed", lines=lines, ocp=ocp_version, build123d=b3d_version)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
