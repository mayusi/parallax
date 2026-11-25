"""A HAIR CARD BENT ALONG A FLOW (the owner's method lists: "hair cards"; the 3D methods audit, H: "a flat strip is
built; a card bent along a flow line is not").

A hair card is a narrow strip that carries a picture of many strands in its alpha: one card reads as a lock of a
hundred hairs. A real groom lays each card ALONG the hair's flow - from the root, over the head, down the back -
twisting and narrowing as it goes, and the strand picture runs along it: its top at the root, its bottom at the tip.
Laid flat in one plane, a picture on a bent card smears; here every point of the card knows where it is ON the card
(along: 0 at the root, 1 at the tip; across: 0 to 1), and the cut-out reads the picture there.

Pure numpy: the ribbon's points, its card coordinates and its faces. rbx.Asset.card builds the part."""

import numpy as np

MAX_TURN = 150.0   # degrees: a flow that doubles back sharper than this between two of its samples is refused


def _catmull(points, per):
    """a smooth line through `points` (a centripetal-free uniform Catmull-Rom), `per` samples between two points"""
    p = np.asarray(points, np.float64)
    ext = np.vstack([2 * p[0] - p[1], p, 2 * p[-1] - p[-2]])
    out = []
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        for k in range(per):
            t = k / per
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(p[-1])
    return np.array(out)


def _resample(line, count):
    """`count` + 1 points spread evenly by length along a polyline -> (points, their share of the length 0..1)"""
    seg = np.linalg.norm(np.diff(line, axis=0), axis=1)
    run = np.concatenate([[0.0], np.cumsum(seg)])
    total = float(run[-1])
    if total <= 0:
        raise ValueError("card: its flow has no length (its points lie on one place)")
    want = np.linspace(0.0, total, count + 1)
    out = np.stack([np.interp(want, run, line[:, k]) for k in range(3)], axis=1)
    return out, want / total


def _turn(v, axis, deg):
    """v turned about a unit axis by degrees (Rodrigues)"""
    t = np.radians(deg)
    return v * np.cos(t) + np.cross(axis, v) * np.sin(t) + axis * float(axis @ v) * (1 - np.cos(t))


def ribbon(points, width, taper=0.3, facing=None, twist=0.0, cup=0.0, segments=None, across=2):
    """the card's geometry -> (verts (N, 3), card (N, 2): (across 0..1, along 0..1 from the root), faces [quads],
    length). points: the flow from root to tip (2 at least, studs); width: across at the root (studs); taper: the
    tip's width as a share of the root's (0 = a point, 1 = as wide); facing: the way the card's face looks at the
    root (default: the front, -Z, or up when the flow runs along Z); twist: degrees it turns about the flow from root
    to tip; cup: how far its middle bows toward its face, as a share of its width (a lock's curl across);
    segments: rows along it (default 3 a point of the flow, at least 4); across: columns (2: a middle line to cup)"""
    p = np.asarray(points, np.float64)
    if p.ndim != 2 or p.shape[1] != 3 or len(p) < 2:
        raise ValueError("card: along= is the flow from root to tip - two (x, y, z) points at least")
    if not float(width) > 0:
        raise ValueError(f"card: width={width!r} - studs across at the root, over 0")
    if not 0.0 <= float(taper) <= 1.0:
        raise ValueError(f"card: taper={taper!r} - the tip's width as a share of the root's, 0 to 1")
    across = int(across)
    if not 1 <= across <= 8:
        raise ValueError("card: across= 1 to 8 columns")
    segs = int(segments) if segments else max(4, 3 * (len(p) - 1))
    if not 1 <= segs <= 128:
        raise ValueError("card: segments= 1 to 128 rows along it")
    line = _catmull(p, 8) if len(p) > 2 else p
    pts, s = _resample(line, segs)
    tan = np.gradient(pts, axis=0)
    tan /= np.maximum(np.linalg.norm(tan, axis=1, keepdims=True), 1e-12)
    bend = np.degrees(np.arccos(np.clip((tan[1:] * tan[:-1]).sum(1), -1, 1)))
    if float(bend.max(initial=0.0)) > MAX_TURN:
        raise ValueError(f"card: its flow doubles back ({bend.max():.0f} degrees between two rows) - a card runs "
                         "one way: two cards, or more points to round the turn")
    if facing is None:
        facing = (0.0, 1.0, 0.0) if abs(tan[0][2]) > 0.9 else (0.0, 0.0, -1.0)
    f = np.asarray(facing, np.float64)
    side = np.cross(tan[0], f)
    if np.linalg.norm(side) < 1e-6:
        raise ValueError("card: facing= runs along its flow at the root - the face must look across it")
    side /= np.linalg.norm(side)
    sides = [side]
    for i in range(1, len(pts)):   # (carried along the flow without turning about it: parallel transport)
        sd = sides[-1] - tan[i] * float(sides[-1] @ tan[i])
        n_ = np.linalg.norm(sd)
        sides.append(sd / n_ if n_ > 1e-9 else sides[-1])
    verts, card = [], []
    for i, (c, t_, sd, si) in enumerate(zip(pts, tan, sides, s)):
        sd = _turn(sd, t_, float(twist) * si)
        nrm = np.cross(sd, t_)
        w = float(width) * (1.0 - (1.0 - float(taper)) * si)
        for j in range(across + 1):
            a = j / across - 0.5
            bow = float(cup) * w * (1.0 - (2 * a) ** 2)
            verts.append(c + sd * a * w + nrm * bow)
            card.append((j / across, si))
    verts, card = np.array(verts), np.array(card)
    faces = []   # (a point at the tip - taper 0 - leaves its row's corners on one place: the builder welds them)
    for i in range(segs):
        for j in range(across):
            a0, a1 = i * (across + 1) + j, (i + 1) * (across + 1) + j
            faces.append((a0, a0 + 1, a1 + 1, a1))
    length = float(np.linalg.norm(np.diff(pts, axis=0), axis=1).sum())
    return verts, card, faces, length


def frame():
    """the frame a card's picture is laid in, in its CARD coordinates (across, 1 - along, 0) - rbx_cutout.frame_of's
    shape: the picture fills the card, its top at the root"""
    return (np.zeros(3), np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0]), 1.0, 1.0)


def card_points(card):
    """card coordinates (N, 2) -> the points the cut-out reads the picture at (N, 3): (across, 1 - along, 0)"""
    c = np.asarray(card, np.float64)
    return np.stack([c[:, 0], 1.0 - c[:, 1], np.zeros(len(c))], axis=1)
