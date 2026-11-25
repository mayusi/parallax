"""gait_curves.py — normative HUMAN gait curves, per percent of the gait cycle (0 = the right heel strikes), so the
kit's generated walk and run have a real body's timing instead of a sinusoid's: the knee absorbs at loading response
and is nearly straight at mid-stance, the heel strikes toes-up and the heel rises before toe-off, the pelvis rotates
and lists, the trunk counters, the arms swing against the legs with the elbow flexing as the arm comes forward.

The keypoints are textbook means, rounded to the degree:
  - Perry & Burnfield, "Gait Analysis: Normal and Pathological Function", 2nd ed. (2010), ch. 4-7 (hip, knee, ankle,
    pelvis, trunk, arm for a comfortable walk ~1.4 m/s; stance 62 % of the cycle, double support 2 x 12 %).
  - Winter, "Biomechanics and Motor Control of Human Movement", 4th ed. (2009), appendix A (joint angle tables).
  - Novacheck, "The biomechanics of running", Gait & Posture 7 (1998) 77-95 (distance running ~3.5 m/s: stance
    ~40 %, two flight phases, knee flexion to ~90-100 deg in swing, trunk lean, arm carriage).
The kit scales them (stride, knee peaks, style = exaggeration) rather than reading them literally; an in-place game
walk is a stylised human walk, not a measurement.

Conventions here: flexion positive. hip: thigh forward +. knee: fold +. foot: the SOLE's pitch vs the floor, toes
up +. pelvis_rot: the right side forward +. pelvis_obl: the right side up +. trunk/arm: shoulder flexion forward +,
elbow fold +. Each curve is [(percent, value)...] with the last point at 100 equal to the first (a loop).
"""

import math

WALK = {
    "support": 0.62,                                 # stance fraction per leg: 62 % -> double support 2 x 12 %
    "hip":  [(0, 30), (10, 25), (20, 16), (30, 6), (40, -4), (50, -10), (56, -9), (62, -3), (70, 12), (80, 26),
             (90, 32), (100, 30)],
    "knee": [(0, 5), (8, 15), (15, 18), (25, 13), (35, 6), (45, 5), (52, 14), (60, 38), (68, 58), (75, 62),
             (85, 42), (93, 16), (100, 5)],
    "foot": [(0, 18), (6, 8), (10, 0), (40, 0), (48, -8), (56, -24), (62, -42), (72, -14), (85, 4), (95, 14),
             (100, 18)],
    "pelvis_rot": [(0, 5), (25, 0), (50, -5), (75, 0), (100, 5)],
    "pelvis_obl": [(0, 0), (12, 4), (30, 2), (50, 0), (62, -4), (80, -2), (100, 0)],
    "arm":  [(0, -22), (25, -6), (50, 24), (75, 6), (100, -22)],          # the right arm: back at right heel strike
    "elbow": [(0, 14), (25, 20), (50, 32), (75, 22), (100, 14)],          # flexes as the arm comes forward
    "flight": 0.0,
    "lean": 2.0,                                     # trunk forward lean, degrees
}

RUN = {
    "support": 0.40,                                 # stance 40 %: two flight phases of 10 %
    "hip":  [(0, 35), (15, 20), (30, 2), (40, -14), (50, -10), (62, 10), (75, 36), (88, 46), (100, 35)],
    "knee": [(0, 22), (15, 42), (30, 26), (40, 16), (48, 34), (60, 78), (70, 100), (80, 76), (90, 36), (100, 22)],
    "foot": [(0, 6), (5, 0), (28, 0), (34, -12), (40, -34), (50, -22), (65, -6), (85, 4), (100, 6)],
    "pelvis_rot": [(0, 8), (25, 0), (50, -8), (75, 0), (100, 8)],
    "pelvis_obl": [(0, 0), (10, 6), (30, 3), (50, 0), (60, -6), (80, -3), (100, 0)],
    "arm":  [(0, -36), (25, -10), (50, 40), (75, 10), (100, -36)],
    "elbow": [(0, 80), (25, 86), (50, 96), (75, 88), (100, 80)],
    "flight": 0.18,                                  # studs the pelvis rises at the top of a flight phase
    "lean": 9.0,
}


def _slopes(xs, ys):
    """Fritsch-Carlson monotone cubic (PCHIP) slopes: no overshoot between hand-set keypoints"""
    n = len(xs)
    d = [(ys[i + 1] - ys[i]) / (xs[i + 1] - xs[i]) for i in range(n - 1)]
    m = [0.0] * n
    m[0], m[-1] = d[0], d[-1]
    for i in range(1, n - 1):
        if d[i - 1] * d[i] <= 0:
            m[i] = 0.0
        else:
            w1, w2 = 2 * (xs[i + 1] - xs[i]) + (xs[i] - xs[i - 1]), (xs[i + 1] - xs[i]) + 2 * (xs[i] - xs[i - 1])
            m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i])
    return m


def sample(points, q):
    """the curve's value at q (0..1 of the cycle, periodic): a monotone cubic through the keypoints, continued
    one keypoint past each end so the loop's slope is continuous at 0 = 100"""
    pts = sorted(points)
    xs = [pts[-2][0] - 100.0] + [x for x, _ in pts] + [pts[1][0] + 100.0]
    ys = [pts[-2][1]] + [y for _, y in pts] + [pts[1][1]]
    m = _slopes(xs, ys)
    t = (q % 1.0) * 100.0
    i = 0
    while i < len(xs) - 2 and xs[i + 1] <= t:
        i += 1
    h = xs[i + 1] - xs[i]
    s = (t - xs[i]) / h
    h00, h10, h01, h11 = 2 * s ** 3 - 3 * s ** 2 + 1, s ** 3 - 2 * s ** 2 + s, -2 * s ** 3 + 3 * s ** 2, s ** 3 - s ** 2
    return h00 * ys[i] + h10 * h * m[i] + h01 * ys[i + 1] + h11 * h * m[i + 1]


def peak(points, lo=0.0, hi=1.0, sign=1.0):
    """the curve's largest value (times sign) over a phase window, sampled finely"""
    best = -math.inf
    for k in range(201):
        q = lo + (hi - lo) * k / 200
        best = max(best, sign * sample(points, q))
    return best


def family(kind):
    """the curve set a kind draws from, and the blend between walk and run that it is"""
    if kind in ("run",):
        return RUN, 1.0
    if kind in ("jog",):
        return RUN, 0.5
    return WALK, 0.0


def blended(t):
    """the walk and run families mixed: t = 0 walk, 1 run (a jog is 0.5): keypoints sampled on a common grid"""
    if t <= 0:
        return WALK
    if t >= 1:
        return RUN
    out = {}
    for key in ("hip", "knee", "foot", "pelvis_rot", "pelvis_obl", "arm", "elbow"):
        out[key] = [(k * 2.0, (1 - t) * sample(WALK[key], k / 50.0) + t * sample(RUN[key], k / 50.0)) for k in range(51)]
    for key in ("support", "flight", "lean"):
        out[key] = (1 - t) * WALK[key] + t * RUN[key]
    return out
