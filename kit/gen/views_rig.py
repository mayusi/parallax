"""views_rig.py — the kit's standard views as cameras, for generators that take posed views (kit gen views, Pixal3D).

Roblox space: x right, y up, the model's FRONT faces -Z. The views are the ones the kit measures with
(kit/blender/rbx_precision.py VIEWS: the direction from the model's centre to the camera):

    view   camera at   looks along   picture right        picture up
    front  -Z          +Z            -X (model's left)    +Y
    side   +X          -X            -Z (front on RIGHT)  +Y      (as kit trace and the side camera see it)
    back   +Z          -Z            +X                   +Y
    top    +Y          -Y            +X                   -Z (front at the TOP of the picture)

Every picture is a cut-out of ONE object. The rig re-frames each the same way (so the pictures may come in any
size or crop): the silhouette's box is the object's extent across that view (exact for an orthographic chart view),
the extents of the three axes are fitted from all the views' aspect ratios (log least squares, the disagreement
kept per view), the object is normalised to a longest side of 1 (the unit box generators work in), and each picture
is scaled to that size and centred in a square canvas whose half-width at the object's centre is HALF units.
Cameras: a pinhole at distance HALF / tan(fov / 2) looking at the centre. Orthographic chart views are approximated
by a narrow lens far away (ORTHO_FOV: a +-0.5 deep object is drawn within +-1.6 % of orthographic); photos and
renders use Pixal3D's own example rig (20 deg, distance 3.119).

Pixal3D's world (Blender/NeRF transforms.json: Z up, a camera looks along its -Z with +Y up): its MAIN view must sit
at (0, -d, 0) looking +Y. world_rotation(main) turns Roblox space so the chosen main view lands exactly there, and
glb_to_roblox(main) turns its exported GLB back into Roblox space (for main = front it is Pixal3D's own fixed turn).
"""

import math

import numpy as np

HALF = 0.55  # visible half-width at the object's centre (the unit-box object fills 91 %: Pixal3D's example rig)
PERSPECTIVE_FOV = 20.0  # degrees: Pixal3D's example rig
ORTHO_FOV = 2.0  # degrees: a chart drawing, approximated by a long lens far away
VIEWS = {"front": (0, 0, -1), "side": (1, 0, 0), "back": (0, 0, 1), "top": (0, 1, 0)}
UP = {"front": (0, 1, 0), "side": (0, 1, 0), "back": (0, 1, 0), "top": (0, 0, -1)}
ORDER = ("front", "side", "back", "top")
MAIN_PREFERENCE = ("front", "side", "back")  # a level view: the object stands upright in it, as in training


def basis(view):
    """(right, up, back) unit vectors of a view's camera in Roblox space; the camera looks along -back"""
    back = np.array(VIEWS[view], float)
    up = np.array(UP[view], float)
    return np.cross(up, back), up, back


def axes(view):
    """(axis shown left-right, axis shown up-down) as indices 0 = x, 1 = y, 2 = z"""
    right, up, _ = basis(view)
    return int(np.argmax(np.abs(right))), int(np.argmax(np.abs(up)))


def distance(fov_deg):
    return HALF / math.tan(math.radians(fov_deg) / 2)


def fit_extents(sizes):
    """{view: (width_px, height_px) of its silhouette box} -> (extents (3,) with max 1, {view: disagreement %}).
    Raises ValueError when the views do not show all three axes."""
    rows, rhs, seen = [], [], set()
    for view, (w, h) in sizes.items():
        i, j = axes(view)
        row = np.zeros(3)
        row[i], row[j] = 1.0, -1.0
        rows.append(row)
        rhs.append(math.log(w / h))
        seen |= {i, j}
    if seen != {0, 1, 2} or np.linalg.matrix_rank(np.array(rows)) < 2:
        missing = [("x", "y", "z")[k] for k in range(3) if k not in seen]
        raise ValueError(f"the views do not show the object's {', '.join(missing) or 'depth'}: give a side view and a "
                         "front (or back / top) view")
    a = np.vstack([np.array(rows), np.ones((1, 3))])  # gauge: the logs sum to 0 (scale is fixed below)
    sol = np.linalg.lstsq(a, np.array(rhs + [0.0]), rcond=None)[0]
    ext = np.exp(sol)
    ext /= ext.max()
    off = {}
    for (view, (w, h)), row in zip(sizes.items(), rows):
        pred = math.exp(float(row @ sol))
        off[view] = round(100.0 * (w / h / pred - 1.0), 2)
    return ext, off


def frame_scale(view, size, ext, res):
    """how much to scale a view's cut-out (its silhouette box `size` in px) so the object has its fitted extents in
    a res x res canvas: one factor for both directions (the picture keeps its own proportions)"""
    i, j = axes(view)
    s = (res / 2) / HALF  # canvas pixels per unit at the object's centre
    w, h = size
    return math.sqrt((ext[i] * s / w) * (ext[j] * s / h))


def world_rotation(main):
    """3x3: Roblox space -> Pixal3D's world, with the main view's camera at (0, -d, 0), right +X, up +Z"""
    r, u, b = basis(main)
    target = np.array([[1.0, 0, 0], [0, 0, 1.0], [0, -1.0, 0]]).T  # columns: where right, up, back must go
    return target @ np.stack([r, u, b], 1).T


def c2w(view, main, fov_deg):
    """the view's camera-to-world 4x4 in Pixal3D's world (columns: right, up, back, position)"""
    rot = world_rotation(main)
    r, u, b = basis(view)
    m = np.eye(4)
    m[:3, 0], m[:3, 1], m[:3, 2] = rot @ r, rot @ u, rot @ b
    m[:3, 3] = rot @ (b * distance(fov_deg))
    return m


def glb_to_roblox(main):
    """4x4: the GLB TRELLIS.2 / Pixal3D's o_voxel export writes (its (x, z, -y) of the voxel grid) -> Roblox space.
    The grid sits in Pixal3D's world as (x, -z, y) (its ProjGrid), so the GLB is diag(1, -1, -1) of that world."""
    m = np.eye(4)
    m[:3, :3] = world_rotation(main).T @ np.diag([1.0, -1.0, -1.0])
    return m


def project(points, view, fov_deg, res):
    """Roblox-space points -> (pixel x right, pixel y down, depth) in the view's res x res picture (edge coordinates:
    the picture's centre is res / 2), the camera at the view's distance looking at the origin"""
    r, u, b = basis(view)
    p = np.asarray(points, float) - b * distance(fov_deg)
    x, y, z = p @ r, p @ u, p @ b  # camera space: the scene is at negative z
    f = (res / 2) / math.tan(math.radians(fov_deg) / 2)
    depth = -z
    return np.stack([res / 2 + f * x / depth, res / 2 - f * y / depth, depth], -1)


def transforms(views, main, fov_deg):
    """Pixal3D's transforms.json for the views (main first): {view: file name}"""
    order = [main] + [v for v in ORDER if v in views and v != main]
    return {"camera_angle_x": math.radians(fov_deg), "mesh_scale": 1.0,
            "frames": [{"file_path": views[v], "name": v, "transform_matrix": c2w(v, main, fov_deg).round(9).tolist()}
                       for v in order]}


def choose_main(views):
    for v in MAIN_PREFERENCE:
        if v in views:
            return v
    raise ValueError("give at least one level view (front, side or back): the top view cannot lead")
