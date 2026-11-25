"""proc_r6.py — PROCEDURAL R6 animation (Overgrowth-style, after David Rosen, GDC 2014 "An Indie Approach to Procedural
Animation"; owner brief 2026-10-13). An action is 2-4 KEY POSES (mined from the owner's loved R6 clips); everything
between them is spring physics, with every parameter EXPLICIT (so it can be fitted to loved clips, never hand-guessed):

  springs   every joint chases the current key pose with Daniel Holden's EXACT damped spring ("Spring-It-On",
            theorangeduck.com): per joint a HALFLIFE (s) and a damping RATIO (1 = critically damped, < 1 = overshoot),
            applied to the rotation-vector offset of the joint from its goal (and linearly to limb slides / the Torso
            offset). Exact = frame-rate independent, never unstable
  overlap   the torso LEADS; head and arms chase their key in CHARACTER space against the torso as it was DELAY
            seconds ago (per joint) - a torso turn drags them late, then they catch up
  momentum  the torso pitches with the body's forward velocity (lean gain, deg per stud/s) + its own acceleration
  foot IK   stances: feet PLANTED where the first key puts them (each leg turned on the shortest arc, twist kept, and slid
            inside the loved slide range); gaits: soles only kept out of the floor (the torso is lifted where needed)

params (all explicit, defaults = the first hand-tuned smoke test):
  {"halflife": {joint: s}, "ratio": {joint: zeta}, "delay": {joint: s}, "lean_v": deg per stud/s, "lean_a": gain,
   "stiff_scale": strikes' halflife divisor, "follow": {joint: 0..1} (interp="hermite": 0 tracks the key curve exactly,
   1 = full spring follow-through past each turnaround; default 1)}
A key = {"pose": {joint: [qx,qy,qz,qw,px,py,pz]}, "t": seconds, "stiff": >1 snaps faster}.
    sim(keys, seconds, params, ...) -> an R6 clip (60 fps, character-space joint frames, the kit's clip format)"""
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import clip as C  # noqa: E402

JOINTS = ["Torso", "Head", "Right Arm", "Left Arm", "Right Leg", "Left Leg"]
OVERLAP = ("Head", "Right Arm", "Left Arm")
FPS = 60
FLOOR = -3.0
LN2 = math.log(2.0)


def default_params():
    """the first (hand-tuned) smoke test, expressed as halflife / ratio: k = 160..320, zeta 0.7..0.95"""
    hl = lambda k, z: (4 * LN2) / (2 * z * math.sqrt(k))                                     # noqa: E731  (d = 2 zeta sqrt k)
    base = {"Torso": (160.0, 0.9), "Head": (110.0, 0.85), "Right Arm": (240.0, 0.7), "Left Arm": (240.0, 0.7),
            "Right Leg": (320.0, 0.95), "Left Leg": (320.0, 0.95)}
    return {"halflife": {j: hl(*v) for j, v in base.items()}, "ratio": {j: v[1] for j, v in base.items()},
            "delay": {j: 0.0 for j in OVERLAP}, "lean_v": 0.3, "lean_a": 0.05, "stiff_scale": 1.0, "follow": {}}


# ---------------------------------------------------------------- quaternion helpers (x, y, z, w), vectorised
def q_mul(a, b):
    ax, ay, az, aw = a[..., 0], a[..., 1], a[..., 2], a[..., 3]
    bx, by, bz, bw = b[..., 0], b[..., 1], b[..., 2], b[..., 3]
    return np.stack([aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
                     aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz], -1)


def q_inv(q):
    return q * np.array([-1.0, -1.0, -1.0, 1.0])


def q_exp(v):
    a = np.linalg.norm(v, axis=-1, keepdims=True)
    s = np.where(a > 1e-9, np.sin(a / 2) / np.maximum(a, 1e-12), 0.5)
    return np.concatenate([v * s, np.cos(a / 2)], -1)


def q_log(q):
    q = q * np.where(q[..., 3:4] < 0, -1.0, 1.0)
    n = np.linalg.norm(q[..., :3], axis=-1, keepdims=True)
    a = 2 * np.arctan2(n, q[..., 3:4])
    return q[..., :3] * np.where(n > 1e-9, a / np.maximum(n, 1e-12), 2.0)


def q_rot(q, v):
    return q_mul(q_mul(q, np.concatenate([v, np.zeros(v.shape[:-1] + (1,))], -1)), q_inv(q))[..., :3]


# ---------------------------------------------------------------- Holden's exact spring
def spring_exact(x, v, halflife, ratio, dt):
    """the exact damped spring toward 0 (Holden, Spring-It-On): x, v arrays; halflife (s) sets the damping
    d = 4 ln2 / halflife, the ratio zeta the stiffness s = (d / (2 zeta))^2. Returns (x, v) after dt"""
    d = 4.0 * LN2 / max(halflife, 1e-4)
    zeta = max(ratio, 1e-3)
    s = (d / (2.0 * zeta)) ** 2
    y = d / 2.0
    e = math.exp(-y * dt)
    disc = s - y * y
    if abs(disc) < 1e-5:                                   # critically damped
        j0, j1 = x, v + x * y
        return j1 * dt * e + j0 * e, -y * j0 * e - y * j1 * dt * e + j1 * e
    if disc > 0:                                           # under-damped: a little overshoot
        w = math.sqrt(disc)
        a, b = x, (v + y * x) / w
        cw, sw = math.cos(w * dt), math.sin(w * dt)
        xn = e * (a * cw + b * sw)
        vn = e * ((-y * a + w * b) * cw + (-y * b - w * a) * sw)
        return xn, vn
    y0 = (d + math.sqrt(d * d - 4 * s)) / 2.0              # over-damped
    y1 = (d - math.sqrt(d * d - 4 * s)) / 2.0
    j1 = (-y0 * x - v) / (y1 - y0)
    j0 = x - j1
    e0, e1 = math.exp(-y0 * dt), math.exp(-y1 * dt)
    return j0 * e0 + j1 * e1, -y0 * j0 * e0 - y1 * j1 * e1


# ---------------------------------------------------------------- legs
_RIG = None


def _rig():
    global _RIG
    if _RIG is None:
        r = C.load_rig("r6")
        pivot = {p: np.asarray(r["joints"][p]["c0"][:3], float) for p in ("Right Leg", "Left Leg")}
        vloc = {p: np.array([0.0, -1.0, 0.0]) - np.asarray(r["joints"][p]["c1"][:3], float) for p in ("Right Leg", "Left Leg")}
        _RIG = (pivot, vloc)
    return _RIG


def sole_char(qt, pt, ql, pl, leg):
    pivot, vloc = _rig()
    return pt + q_rot(qt, pivot[leg] + pl + q_rot(ql, vloc[leg]))


def leg_ik(qt, pt, ql, pl, leg, goal_c, lo, hi):
    pivot, vloc = _rig()
    g = q_rot(q_inv(qt), goal_c - pt) - pivot[leg]
    cur = q_rot(ql, vloc[leg]) + pl
    a, b = cur / np.linalg.norm(cur), g / max(np.linalg.norm(g), 1e-9)
    ax = np.cross(a, b)
    ang = math.atan2(np.linalg.norm(ax), float(a @ b))
    turn = q_exp(ax / max(np.linalg.norm(ax), 1e-12) * ang) if np.linalg.norm(ax) > 1e-9 else np.array([0, 0, 0, 1.0])
    reach = float(np.linalg.norm(vloc[leg]))
    return q_mul(turn, ql), np.clip(b * (np.linalg.norm(g) - reach), lo, hi)


# ---------------------------------------------------------------- the key curve (interp="hermite")
def _q_mean(Q):
    """hemisphere-aligned normalised mean of quaternions [n, 4]"""
    Q = np.array(Q, float)
    Q = np.where((Q @ Q[0])[:, None] < 0, -Q, Q)
    m = Q.mean(0)
    return m / np.linalg.norm(m)


def key_curve(K, loop, period):
    """a smooth goal through the keys: per joint, rotations as rotation vectors about the joint's MEAN key rotation
    (log space), cubic Hermite with non-uniform Catmull-Rom slopes; a channel's slope is 0 where it turns around (an
    extreme eases in and out, a breakdown flows through - Blender's auto-clamped handles); cyclic for a loop.
    -> sample(t) -> (q [6,4], p [6,3])"""
    pts = [k for k in K if not (loop and k["t"] >= period - 1e-9)] if loop else K
    T = np.array([k["t"] for k in pts])
    mean = np.array([_q_mean([k["q"][j] for k in pts]) for j in range(6)])
    V = np.array([[q_log(q_mul(k["q"][j], q_inv(mean[j]))) for j in range(6)] for k in pts])   # [K, 6, 3]
    # UNWRAPPED along the keys: a joint whose keys sweep past 180 deg from its mean (a sword arm, 2026-11-05) wrapped
    # +pi -> -pi in log space and the curve went the long way round for a frame (a 424 studs/s blade flip); a body
    # keyed through several whole turns (a drill spin) folded back into one. Each key takes the log vector
    # v + 2 pi k v/|v| (k whole: the same rotation) whose length matches the key before's length ALONG this key's axis
    # (nearest-by-distance picked a key one whole turn off when the axis tilted a little 30 radians into a spin: the
    # body whipped 6,000 deg/s at the drill's stop)
    for i in range(1, len(pts)):
        for j in range(6):
            a = float(np.linalg.norm(V[i, j]))
            if a > 1e-9:
                ax = V[i, j] / a
                k = round((float(V[i - 1, j] @ ax) - a) / (2 * math.pi))
                V[i, j] = ax * (a + 2 * math.pi * k)
    Pz = np.array([k["p"] for k in pts])                                                          # [K, 6, 3]
    n = len(pts)

    def slopes(X):
        M = np.zeros_like(X)
        for i in range(n):
            if not loop and (i == 0 or i == n - 1):
                continue                                    # a one-shot starts and ends at rest
            ip, inx = (i - 1) % n, (i + 1) % n
            dtp = (T[i] - T[ip]) % period if loop else T[i] - T[ip]
            dtn = (T[inx] - T[i]) % period if loop else T[inx] - T[i]
            dtp, dtn = max(dtp, 1e-6), max(dtn, 1e-6)
            rp, rn = (X[i] - X[ip]) / dtp, (X[inx] - X[i]) / dtn
            m = (dtn * rp + dtp * rn) / (dtp + dtn)
            # Fritsch-Carlson: |slope| <= 3 x the smaller neighbouring slope. Without it a fast rise into a long hold
            # carried its full speed into the hold (the non-uniform weighting favours the long side) and the curve
            # bulged far past both keys (a watch arm keyed at chest height swung above the head)
            lim = 3.0 * np.minimum(np.abs(rp), np.abs(rn))
            m = np.clip(m, -lim, lim)
            M[i] = np.where(rp * rn <= 0, 0.0, m)
        return M

    MV, MP = slopes(V), slopes(Pz)

    def herm(X, Mx, i, u, dt):
        u2, u3 = u * u, u * u * u
        return ((2 * u3 - 3 * u2 + 1) * X[i] + (u3 - 2 * u2 + u) * dt * Mx[i]
                + (-2 * u3 + 3 * u2) * X[(i + 1) % n] + (u3 - u2) * dt * Mx[(i + 1) % n])

    def sample(t):
        if loop:
            t = t % period
            i = int(np.searchsorted(T, t, side="right")) - 1
            i %= n
            dt = ((T[(i + 1) % n] - T[i]) % period) or period
            u = ((t - T[i]) % period) / dt
        else:
            if t <= T[0]:
                i, u, dt = 0, 0.0, 1.0
            elif t >= T[-1]:
                return np.array([q_mul(q_exp(V[-1, j]), mean[j]) for j in range(6)]), Pz[-1].copy()
            else:
                i = int(np.searchsorted(T, t, side="right")) - 1
                dt = T[i + 1] - T[i]
                u = (t - T[i]) / dt
        v = herm(V, MV, i, u, dt)
        return np.array([q_mul(q_exp(v[j]), mean[j]) for j in range(6)]), herm(Pz, MP, i, u, dt)
    return sample


# ---------------------------------------------------------------- the simulation
def sim(keys, seconds, params=None, *, loop=False, plant=True, velocity=0.0, settle=None, name="proc", slide_range=None,
        interp="step"):
    """keys: [{"pose", "t", "stiff"}] sorted by t (a loop's period = the last key's t);
    plant: True / False, or the legs to pin (e.g. ("Left Leg",) - a kick plants only its support leg); velocity: forward speed (studs/s) for the momentum lean;
    settle: seconds simulated first (a loop then starts in its steady state);
    interp: "step" - the goal jumps to each key at its t and the springs chase it (they round the poses off: the run's
            legs reached 74 % of the picked swing, 8-9 frames late);
            "hermite" - the goal is a smooth curve through the keys (key_curve) and the springs TRACK it (Holden's
            tracking spring: fed the goal's velocity too), so the poses land on time and the springs only smooth the
            switches and add the settle / overshoot"""
    P = default_params()
    if params:
        for k, v in params.items():
            P[k] = {**P[k], **v} if isinstance(v, dict) else v
    lo_hi = slide_range or {leg: (np.full(3, -0.6), np.full(3, 0.6)) for leg in ("Right Leg", "Left Leg")}
    dt = 1.0 / FPS
    pre = settle or 0.0
    n = int(round((seconds + pre) * FPS)) + 1
    K = [{"q": np.array([k["pose"][j][:4] for j in JOINTS], float), "p": np.array([k["pose"][j][4:7] for j in JOINTS], float),
          "t": float(k["t"]), "stiff": float(k.get("stiff", 1.0))} for k in keys]
    q = K[0]["q"].copy()
    p = K[0]["p"].copy()
    xr = np.zeros((6, 3))                                  # rotation offsets from the goal (rotation vectors)
    vr = np.zeros((6, 3))
    xp = np.zeros((6, 3))
    vp = np.zeros((6, 3))
    hist = []                                              # the torso's character-space turn, for the overlap delay
    plant_at = {leg: sole_char(K[0]["q"][0], K[0]["p"][0], K[0]["q"][JOINTS.index(leg)], K[0]["p"][JOINTS.index(leg)], leg)
                for leg in ("Right Leg", "Left Leg")}
    for leg in plant_at:
        plant_at[leg][1] = FLOOR
    period = K[-1]["t"] if loop else None
    curve = key_curve(K, loop, period) if interp == "hermite" else None
    g_prev = {}                                            # last frame's goal per joint (rotation) / ("p", jn) (slide)
    gd_prev = {}                                           # last frame's goal velocity, same keys
    follow = P.get("follow") or {}
    out_q, out_p = [], []
    prev_vz = 0.0
    torso_world = q[0].copy()
    child_world = {j: q_mul(q[0], q[JOINTS.index(j)]) for j in OVERLAP}
    for i in range(n):
        t = i * dt - pre
        tk = (t % period) if loop and period else t
        cur = K[0]
        for k in K:
            if tk >= k["t"] - 1e-9:
                cur = k
        sc = max(1.0, cur["stiff"]) * P["stiff_scale"] if cur["stiff"] > 1.0 else 1.0
        kq, kp = curve(tk) if curve else (cur["q"], cur["p"])
        # torso: spring to its key + momentum lean (forward speed / acceleration pitch the top forward)
        acc = (vp[0, 2] - prev_vz) / dt
        prev_vz = vp[0, 2]
        lean = math.radians(-P["lean_v"] * velocity + P["lean_a"] * acc)
        goal = {0: q_mul(q_exp(np.array([lean, 0.0, 0.0])), kq[0])}

        def track(key, g, x_state, v_state):
            """one tracking-spring step: the offset from last frame's goal, its velocity relative to the goal's
            velocity, advanced exactly, re-applied to this frame's goal. (step mode: the goal's velocity is 0)
            follow (hermite): how much of the goal's change of velocity the joint resists - 0 tracks the curve
            exactly, 1 lets every turnaround swing the spring past the pose (follow-through / overshoot)"""
            gp = g_prev.get(key, g) if curve else g
            gd = q_log(q_mul(g, q_inv(gp))) / dt if curve and key in g_prev else np.zeros(3)
            g_prev[key] = g
            gdp = gd_prev.get(key, gd)
            gd_prev[key] = gd
            v_off = v_state - gd if not curve else v_state - gdp + follow.get(JOINTS[key], 1.0) * (gdp - gd)
            xn, vn = spring_exact(q_log(q_mul(x_state, q_inv(gp))), v_off, hl, zt, dt)
            return q_mul(q_exp(xn), g), vn + gd

        for jn, j in enumerate(JOINTS):
            hl = P["halflife"][j] / (sc if j != "Torso" else max(1.0, sc * 0.6))
            zt = P["ratio"][j]
            if j in OVERLAP:
                d = int(round(P["delay"].get(j, 0.0) * FPS))
                tq = hist[-1 - d] if d and len(hist) > d else torso_world
                g = q_mul(tq, kq[jn])                      # chase the key against the torso as it WAS
                child_world[j], vr[jn] = track(jn, g, child_world[j], vr[jn])
                q[jn] = q_mul(q_inv(torso_world), child_world[j])
            else:
                g = goal.get(jn, kq[jn])
                q[jn], vr[jn] = track(jn, g, q[jn], vr[jn])
                if jn == 0:
                    torso_world = q[0].copy()
                    hist.append(torso_world)
            gpp = g_prev.get(("p", jn), kp[jn]) if curve else kp[jn]
            gpd = (kp[jn] - gpp) / dt if curve else np.zeros(3)
            g_prev[("p", jn)] = kp[jn].copy()
            gpdp = gd_prev.get(("p", jn), gpd)
            gd_prev[("p", jn)] = gpd
            vpo = vp[jn] - gpd if not curve else vp[jn] - gpdp + follow.get(j, 1.0) * (gpdp - gpd)
            xpn, vpn = spring_exact(p[jn] - gpp, vpo, hl, zt, dt)
            p[jn] = kp[jn] + xpn
            vp[jn] = vpn + gpd
        legs = {}
        for leg in ("Right Leg", "Left Leg"):
            jn = JOINTS.index(leg)
            ql, pl = q[jn].copy(), p[jn].copy()
            if plant is True or (plant and leg in plant):
                ql, pl = leg_ik(q[0], p[0], ql, pl, leg, plant_at[leg], *lo_hi[leg])
            legs[leg] = (ql, pl)
        pt = p[0].copy()
        if plant is not True:                             # a free leg must not go through the floor
            dig = max(FLOOR - sole_char(q[0], pt, legs[leg][0], legs[leg][1], leg)[1] for leg in legs)
            if dig > 0:
                pt[1] += dig
        if i * dt >= pre - 1e-9:
            fq, fp = q.copy(), p.copy()
            fp[0] = pt
            for leg, (ql, pl) in legs.items():
                fq[JOINTS.index(leg)], fp[JOINTS.index(leg)] = ql, pl
            out_q.append(fq)
            out_p.append(fp)
    Q, Pp = np.array(out_q), np.array(out_p)
    T = len(Q)
    return {"schema": 1, "name": name, "rig": "R6", "fps": FPS, "loop": bool(loop), "priority": "Action",
            "times": [round(i / FPS, 6) for i in range(T)], "events": [],
            "joints": {j: {"frames": [list(map(float, Q[i, k])) + list(map(float, Pp[i, k])) for i in range(T)]} for k, j in enumerate(JOINTS)},
            "source": {"kind": "proc_r6", "keys": len(keys)}}
