"""THE REFERENCES, SOLVED TOGETHER (the owner's limitations, D-R01: "Reference constraints remain fragmented ...
trace, section and form constraints are separate declarations rather than one confidence-weighted reconstruction
solve. Combine calibrated views, landmarks, sections ... and uncertainty; hold out views and flag
contradictions"; the 3D methods audit, stage L).

What a model's references SAY about its overall proportions arrives from different places - a sourced size in
millimetres (the pack: published, measured, a wiki), a traced outline's own proportion (its height over its
length), the size the script aims at - each checked alone against the build, none against the others. So a trace
of a 4:1 object beside sourced sizes of a 3:1 object made a build that could satisfy neither, and nothing said
which of the two was the odd one out.

Here every such statement is a CLAIM with a tolerance (how far its kind can be trusted), and they are solved as
one weighted least-squares fit of the three sizes (in logarithms: a proportion is then a difference). Each claim
is then HELD OUT in turn: the others predict what it should say, and a claim far outside its own tolerance from
that prediction is a CONTRADICTION, named. Pure numpy.

  claim: {"name", "kind": "size", "axis", "value" (mm), "tol"}  |  {"name", "kind": "ratio", "num", "den",
          "value", "tol"}       axes: "length", "height", "width"
"""

import math

import numpy as np

AXES = ("length", "height", "width")
# how far a claim of each kind can be off before it counts against it (a share of its value)
TOL = {"high": 0.02, "medium": 0.05, "low": 0.10, "unsourced": 0.25, "trace": 0.04, "target": 0.25}
APART = 2.5      # a held-out claim this many joint tolerances from what the others predict: a contradiction
DETERMINED = 1e-6


def _tol(name, trust):
    if trust not in TOL:
        raise ValueError(f"claim {name}: trust={trust!r} - one of {', '.join(sorted(TOL))}")
    return TOL[trust]


def size(name, axis, mm, trust):
    if axis not in AXES:
        raise ValueError(f"claim {name}: axis {axis!r} - one of {', '.join(AXES)}")
    if not float(mm) > 0:
        raise ValueError(f"claim {name}: {mm!r} mm - a size over 0")
    return {"name": str(name), "kind": "size", "axis": axis, "value": float(mm), "tol": _tol(name, trust)}


def ratio(name, num, den, value, trust="trace"):
    if num not in AXES or den not in AXES or num == den:
        raise ValueError(f"claim {name}: a proportion of two different axes of {', '.join(AXES)}")
    if not float(value) > 0:
        raise ValueError(f"claim {name}: {value!r} - a proportion over 0")
    return {"name": str(name), "kind": "ratio", "num": num, "den": den, "value": float(value),
            "tol": _tol(name, trust)}


def _row(claim):
    r = np.zeros(3)
    if claim["kind"] == "size":
        r[AXES.index(claim["axis"])] = 1.0
    else:
        r[AXES.index(claim["num"])], r[AXES.index(claim["den"])] = 1.0, -1.0
    return r


def _fit(claims):
    """-> (the three sizes' logarithms, min-norm where the claims leave one free; the claims' rows; weights)"""
    if not claims:
        return np.zeros(3), np.zeros((0, 3)), np.zeros(0)
    a = np.array([_row(c) for c in claims])
    b = np.array([math.log(c["value"]) for c in claims])
    w = np.array([1.0 / c["tol"] for c in claims])
    x = np.linalg.lstsq(a * w[:, None], b * w, rcond=None)[0]
    return x, a, w


def _says(a, w, row):
    """do these claims fix what `row` asks about? (row lies in the space their rows span)"""
    if not len(a):
        return False
    aw = a * w[:, None]
    back = row @ np.linalg.pinv(aw) @ aw
    return float(np.linalg.norm(back - row)) < DETERMINED


def solve(claims):
    """the sizes all the claims agree on best -> {"sizes": {axis: mm or None (nothing fixes it)}, "ratios": {(num,
    den) as "height/length": value or None}, "off": [each claim's distance from the fit, a share of its value]}"""
    x, a, w = _fit(claims)
    sizes = {}
    for i, axis in enumerate(AXES):
        row = np.zeros(3)
        row[i] = 1.0
        sizes[axis] = round(float(math.exp(x[i])), 4) if _says(a, w, row) else None
    ratios = {}
    for num in AXES:
        for den in AXES:
            if num != den:
                row = _row({"kind": "ratio", "num": num, "den": den})
                ratios[f"{num}/{den}"] = (round(float(math.exp(row @ x)), 5) if _says(a, w, row) else None)
    off = [abs(math.exp(float(_row(c) @ x) - math.log(c["value"])) - 1.0) for c in claims]
    return {"sizes": sizes, "ratios": ratios, "off": [round(o, 4) for o in off]}


def held_out(claims):
    """each claim against what THE OTHERS predict for it -> [{"name", "says", "others": the prediction or None
    (the others do not fix it: nothing to hold it against), "apart": a share, "sigmas": how far apart, counted in
    what the claim AND the prediction can be trusted to together, "within": that joint tolerance}] in the
    claims' order. (The review: scored against the claim's own tolerance alone, a maker's size predicted only
    from loose sources was blamed for their looseness.)"""
    out = []
    for i, c in enumerate(claims):
        rest = claims[:i] + claims[i + 1:]
        x, a, w = _fit(rest)
        row = _row(c)
        if not _says(a, w, row):
            out.append({"name": c["name"], "says": c["value"], "others": None, "apart": None, "sigmas": None,
                        "within": None})
            continue
        aw = a * w[:, None]
        spread = float(row @ np.linalg.pinv(aw.T @ aw) @ row)      # the prediction's own uncertainty (log, squared)
        both = math.sqrt(c["tol"] ** 2 + max(spread, 0.0))
        log = math.log(c["value"]) - float(row @ x)
        pred = float(math.exp(row @ x))
        out.append({"name": c["name"], "says": c["value"], "others": round(pred, 5),
                    "apart": round(abs(c["value"] / pred - 1.0), 4), "sigmas": round(abs(log) / both, 2),
                    "within": round(both, 4)})
    return out


TIE = 0.05       # two claims scored within this share of each other are equally to blame


def _said(h, c):
    what = (f"{c['axis']} {h['says']:g} mm" if c["kind"] == "size"
            else f"{c['num']} is {h['says']:.3g} of the {c['den']}")
    other = (f"{h['others']:g} mm" if c["kind"] == "size" else f"{h['others']:.3g}")
    return (f"{c['name']} says {what}; the other references together say {other} "
            f"({h['apart'] * 100:.0f}% apart, where the two can be trusted to {h['within'] * 100:.0f}%)")


def contradictions(claims):
    """the claims that do not fit the others -> [sentences], worst first. The worst claim is named and TAKEN OUT,
    and the rest looked at again, until what is left agrees: with a majority against it only the odd claim is
    named. Claims equally to blame (two alone that disagree; a ring of three where each is "wrong" by the other
    two) are ALL named, the least trusted first, and the look stops there: which is wrong is for a person."""
    left, out = list(claims), []
    while len(left) > 1:
        rows = [(h, c) for h, c in zip(held_out(left), left) if h["sigmas"] is not None and h["sigmas"] > APART]
        if not rows:
            break
        top = max(h["sigmas"] for h, _c in rows)
        tied = [(h, c) for h, c in rows if h["sigmas"] >= top * (1.0 - TIE)]
        tied.sort(key=lambda hc: (-hc[1]["tol"], -hc[0]["sigmas"]))
        out += [_said(h, c) for h, c in tied]
        if len(tied) > 1:
            break
        left = [c for c in left if c is not tied[0][1]]
    return out


def build_off(solved, built, tol=0.05):
    """the BUILT model against what the references agree on -> [sentences]. built: {axis: mm}. The sizes where
    the references fix them; where they fix none (proportions only), the proportions - one fault said once."""
    out = []
    for axis, want in solved["sizes"].items():
        if want is None or not built.get(axis):
            continue
        if abs(built[axis] / want - 1.0) > tol:
            out.append(f"its {axis} is {built[axis]:.4g} mm; the references agree on {want:.4g} "
                       f"({abs(built[axis] / want - 1.0) * 100:.0f}% off)")
    if any(v is not None for v in solved["sizes"].values()):
        return out
    for key, want in sorted(solved["ratios"].items()):
        num, den = key.split("/")
        if want is None or AXES.index(num) < AXES.index(den) or not built.get(num) or not built.get(den):
            continue
        got = built[num] / built[den]
        if abs(got / want - 1.0) > tol:
            out.append(f"its {num} is {got:.3g} of its {den}; the references agree on {want:.3g} "
                       f"({abs(got / want - 1.0) * 100:.0f}% off)")
    return out
