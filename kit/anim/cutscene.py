"""cutscene.py — a CUTSCENE of several R6 actors from a worded script (the "animate anything on R6" plan's final test,
2026-10-12). Every pose on screen is human-made R6 motion from the library (kit/anim/motion_lib.py); the script only
DIRECTS: who does what (in words), where they stand, when they teleport, who gets hit, where the camera looks.

    python kit/anim/cutscene.py make <script.json>      -> _artifacts/r6lib/cutscenes/<name>/ (scene.json, frames,
                                                            <name>.mp4 + <name>.gif, one sheet .png)
    python kit/anim/cutscene.py make <script.json> --game <dir>  -> <dir>/Cutscenes.luau: the GAME timeline
        (`lune run kit anim cutscene <script> --timeline`; src/kit/Cutscene.play(name, anchor, cast) plays it on real
        R6 bodies with the kit's own clips - library clips are not in the game and play as idle)
Script:
  {"name": "...", "actors": {"hero": {"pos": [x, z], "yaw": deg, "look": "shadow"}, "victim": {"pos": [0, 0], "look": "noob",
                             "idle": "idle"}},
   "beats": [ {"do": "idle", "seconds": 1.0},
              {"do": "act", "actor": "victim", "say": "confused", "seconds": 1.2, "turn": 120},
              {"do": "strike", "by": "hero", "on": "victim", "from": 180, "dist": 3.0, "say": "m1 combo punch",
               "react": "hit reaction", "push": 1.5, "launch": 0, "spin": 40, "hitstop": 5, "teleport": true},
              {"do": "vanish", "actor": "hero"}, {"do": "appear", "actor": "hero", "pos": [x, z], "face": "victim",
               "say": "idle"} ]}
  "from" = the side the attacker comes from, degrees around the target relative to the TARGET's facing (0 = in front,
  180 = behind, 90 = its right). "say" picks the best loved, game-safe library clip for the words (or "id" pins one);
  a strike's Hit = that clip's measured fastest-hand moment. Roblox axes: +Y up, -Z forward; yaw 0 faces -Z.
  The kit's OWN clips (2026-10-24): "clip": "<Name>" on act / strike (build/animations/<Name>.clip.json - its Hit event
  is the hit), "react_clip": "<Name>" (+ "react_from": "<marker>": the reaction starts at that marker, the way the game
  plays it) and "counter": {"react_clip": "<Name>", "push": 1.2} on a strike = a PARRY: the attacker freezes at the
  contact and takes the counter reaction when the defender's clip reaches its own Hit. A clip that carries a sword
  (strike.py `sword`) gives its actor a blade, held in the right hand between clips."""
import copy
import json
import math
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import clip as C  # noqa: E402
import derive as D  # noqa: E402
import motion_lib as ML  # noqa: E402

FPS = 60
OUT = os.path.join(ML.LIB, "cutscenes")
JOINTS = ["Torso", "Head", "Right Arm", "Left Arm", "Right Leg", "Left Leg"]
REST = [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]


def yaw_to(src, dst):
    """the yaw (deg) that faces from src to dst ([x, z] on the floor; yaw 0 faces -Z)"""
    return math.degrees(math.atan2(-(dst[0] - src[0]), -(dst[1] - src[1])))


def fwd(yaw):
    a = math.radians(yaw)
    return np.array([-math.sin(a), -math.cos(a)])


def quat_y(deg):
    a = math.radians(deg)
    return [0.0, math.sin(a / 2), 0.0, math.cos(a / 2)]


def pick(say=None, cid=None, kind=None, kit=None):
    if kit:
        path = os.path.join(os.environ.get("KIT_BUILD", "build"), "animations", f"{kit}.clip.json")
        c = json.load(open(path, encoding="utf-8"))
        if int(round(float(c.get("fps") or 30))) != FPS:
            n0 = len(c["times"])
            D.op_retime(c, duration=float(c["times"][-1]), fps=FPS)
            n1 = len(c["times"])
            idx = [min(n0 - 1, int(round(i * (n0 - 1) / max(1, n1 - 1)))) for i in range(n1)]
            sw = c.get("sword")                                # (retime moves the joints only: the blade + root too)
            for k in ("tip", "grip_path", "edge"):
                if isinstance(sw, dict) and isinstance(sw.get(k), list) and len(sw[k]) == n0:
                    sw[k] = [sw[k][i] for i in idx]
            if isinstance(c.get("root"), list) and len(c["root"]) == n0:
                c["root"] = [c["root"][i] for i in idx]
        hit = next((float(e["t"]) for e in c.get("events") or [] if e.get("name") == "Hit"), float(c["times"][-1]) * 0.4)
        return c, {"id": kit, "name": kit, "kit": True, "facts": {"strike": {"at_s": hit}}}
    cat = ML.load()
    if cid:
        r = next(x for x in cat if x["id"] == cid)
    else:
        res = ML.find(say, k=8, kind=kind) or ML.find(say, k=8)
        if not res:
            raise ValueError(f"no library clip for '{say}'")
        r = res[0][1]
    c = json.load(open(os.path.join(ML.LIB, "clips", f"{r['id']}.clip.json"), encoding="utf-8"))
    if int(round(float(c.get("fps") or 30))) != FPS:
        D.op_retime(c, duration=float(c["times"][-1]), fps=FPS)
    return c, r


_RIG = None


def arm_mat(pose):
    """the Right Arm's 4x4 in character space for a pose {joint: frame}"""
    global _RIG
    _RIG = _RIG or C.load_rig("r6")
    tr = {j: (C.quat_mat(pose[j][:4]), np.asarray(pose[j][4:7], float)) for j in JOINTS if j in pose}
    return C.fk(_RIG, tr)["Right Arm"]


def frames_of(c):
    n = len(c["times"])
    out = [{j: list(c["joints"][j]["frames"][i]) if j in c["joints"] else list(REST) for j in JOINTS} for i in range(n)]
    # a clip with a SWORD (strike.py): the blade's grip / tip / edge in the RIGHT ARM's frame, per pose - the actor
    # carries it through crossfades and holds the last one in hand through clips without a sword (idles)
    sw = c.get("sword") or {}
    tips, grips, edges = sw.get("tip") or [], sw.get("grip_path") or [], sw.get("edge") or []
    if len(tips) == n and len(grips) == n:
        for i, p in enumerate(out):
            inv = np.linalg.inv(arm_mat(p))
            g = (inv @ np.r_[np.asarray(grips[i], float), 1.0])[:3]
            t = (inv @ np.r_[np.asarray(tips[i], float), 1.0])[:3]
            e = (inv[:3, :3] @ np.asarray(edges[i], float)).tolist() if len(edges) == n else None
            p["_sword"] = {"g": g.tolist(), "t": t.tolist(), "e": e, "kind": sw.get("kind"),
                           "length": sw.get("length"), "grip": sw.get("grip")}
    return out


def blend(a, b, w):
    out = {}
    s = (b.get("_sword") if w >= 0.5 else a.get("_sword")) or a.get("_sword") or b.get("_sword")
    if s:
        out["_sword"] = s
    for j in JOINTS:
        qa, qb = np.asarray(a[j][:4]), np.asarray(b[j][:4])
        out[j] = list(C.slerp(qa, qb, w)) + list(np.asarray(a[j][4:7]) * (1 - w) + np.asarray(b[j][4:7]) * w)
    return out


class Actor:
    def __init__(self, name, spec):
        self.name = name
        self.look = spec.get("look", "noob")
        self.poses = []          # per frame {joint: frame}
        self.root = []           # per frame [x, y, z, yaw]  (Roblox world, the HumanoidRootPart)
        self.visible = []
        self.pos = np.array([float(spec.get("pos", [0, 0])[0]), 0.0, float(spec.get("pos", [0, 0])[1])])
        self.yaw = float(spec.get("yaw", 0.0))
        self.shown = spec.get("visible", True)
        self.idle, _ = pick(spec.get("idle", "idle"), kind="idle")
        self.idle_frames = frames_of(self.idle)
        self.phase = 0
        self.hold = False        # True: between beats the actor keeps its last pose (in the air, knocked down)
        self.used = [_["name"]]
        # what plays when, for the GAME (the timeline): {"f": first frame, "clip": name | "@idle" | "@hold",
        # "from": seconds into the clip, "n": frames, "fade": frames, "kit": a game clip}
        self.log = []

    def n(self):
        return len(self.poses)

    def _push(self, pose):
        self.poses.append(pose)
        self.root.append([float(self.pos[0]), float(self.pos[1]), float(self.pos[2]), float(self.yaw)])
        self.visible.append(bool(self.shown))

    def idle_until(self, frame):
        if self.n() < frame:
            kind = "@hold" if self.hold and self.poses else "@idle"
            last = self.log[-1] if self.log else None
            if not (last and last["clip"] == kind):
                self.log.append({"f": self.n(), "clip": kind})
        while self.n() < frame:
            if self.hold and self.poses:
                self._push(self.poses[-1])
                continue
            p = self.idle_frames[self.phase % len(self.idle_frames)]
            self.phase += 1
            if self.poses and self.phase < 2:
                p = blend(self.poses[-1], p, 0.5)
            self._push(p)

    def play(self, frames, fade=6, start=None, root_fn=None, src=None):
        """append frames (crossfaded from the current pose over `fade` frames); root_fn(i, n) may move the root;
        src = (clip name, seconds into it, a game clip?) for the timeline"""
        if start is not None:
            self.idle_until(start)
        if src:
            self.log.append({"f": self.n(), "clip": src[0], "from": round(float(src[1]), 4), "n": len(frames),
                             "fade": fade, "kit": bool(src[2])})
        last = self.poses[-1] if self.poses else frames[0]
        for i, p in enumerate(frames):
            if i < fade:
                p = blend(last, p, (i + 1) / (fade + 1))
            if root_fn:
                root_fn(i, len(frames))
            self._push(p)
        self.phase = 0


def end_effector_world(actor, frame, rig):
    """world positions of both hands and feet of an actor at a frame (Roblox studs)"""
    pose = actor.poses[frame]
    x, y, z, yaw = actor.root[frame]
    c = {"name": "probe", "rig": "R6", "fps": FPS, "times": [0.0], "joints": {j: {"frames": [pose[j]]} for j in JOINTS}}
    W = C.world_frames(c, rig)[0]
    a = math.radians(yaw)
    R = np.array([[math.cos(a), 0, math.sin(a)], [0, 1, 0], [-math.sin(a), 0, math.cos(a)]])
    out = {}
    for part in ("Right Arm", "Left Arm", "Right Leg", "Left Leg"):
        p = np.asarray(W[part]) @ np.array([0, -1, 0, 1.0])
        out[part] = R @ p[:3] + np.array([x, y, z])
    torso = R @ np.asarray(W["Torso"])[:3, 3] + np.array([x, y, z])
    return out, torso


def contact_distance(pose, rig, height=0.0, skin=0.55):
    """how far in front of its target an attacker must stand so the limb that reaches furthest forward at the Hit lands
    on the target's body surface (the torso is 1 stud deep: half of it + a little skin) - measured on the clip's own
    pose, so a jab, a lunge kick and a slam each get their own spacing"""
    c = {"name": "probe", "rig": "R6", "fps": FPS, "times": [0.0], "joints": {j: {"frames": [pose[j]]} for j in JOINTS}}
    W = C.world_frames(c, rig)[0]
    best = 0.0
    for part in ("Right Arm", "Left Arm", "Right Leg", "Left Leg"):
        p = np.asarray(W[part]) @ np.array([0, -1, 0, 1.0])
        if height > 0 or p[1] > -2.2:                     # a planted foot is not a strike
            best = max(best, float(-p[2]))
    sw = pose.get("_sword")
    if sw:
        # a SWORD cuts with its blade, not the hands: the cutting zone (70 % along it, the monouchi of a katana) lands
        # on the target - spaced by the hands, two swordsmen stood body to body (the first KatanaDuel render)
        M = arm_mat(pose)
        g = (M @ np.r_[sw["g"], 1.0])[:3]
        t = (M @ np.r_[sw["t"], 1.0])[:3]
        best = max(best, float(-(g + 0.7 * (t - g))[2]))
    return max(2.2, best + skin)                        # never inside the target, whatever the pose


def make(script):
    rig = C.load_rig("r6")
    actors = {k: Actor(k, v) for k, v in script["actors"].items()}
    fx, hits, shots = [], [], []
    t = 0                                                      # the scene's current frame

    def sync(frame):
        for a in actors.values():
            a.idle_until(frame)

    for bi, b in enumerate(script["beats"]):
        do = b["do"]
        if do == "idle":
            t += int(round(float(b.get("seconds", 1.0)) * FPS))
            sync(t)
            shots.append({"from": t - int(round(float(b.get("seconds", 1.0)) * FPS)), "to": t, "kind": b.get("shot", "wide")})
        elif do == "act":
            a = actors[b["actor"]]
            c, r = pick(b.get("say"), b.get("id"), b.get("kind"))
            a.used.append(r["name"])
            if b.get("trim"):
                D.op_trim(c, start=float(b["trim"][0]), end=float(b["trim"][1]) if b["trim"][1] else None)
            fr = frames_of(c)
            if b.get("seconds"):
                fr = fr[: int(round(float(b["seconds"]) * FPS))]
            turn = float(b.get("turn", 0.0))
            y0 = a.yaw
            a.play(fr, fade=int(b.get("fade", 8)), start=t,
                   src=(r["name"], float(b["trim"][0]) if b.get("trim") else 0.0, r.get("kit")),
                   root_fn=(lambda i, n, a=a, y0=y0, turn=turn: setattr(a, "yaw", y0 + turn * D.smooth(min(1.0, i / max(1, n * 0.7)))))
                   if turn else None)
            t0, t = t, a.n()
            sync(t)
            shots.append({"from": t0, "to": t, "kind": b.get("shot", "on"), "actor": b["actor"]})
        elif do == "vanish":
            a = actors[b["actor"]]
            sync(t)
            fx.append({"type": "afterimage", "actor": a.name, "frame": max(0, t - 1), "frames": 14})
            fx.append({"type": "flash", "pos": [float(a.pos[0]), 1.0, float(a.pos[2])], "frame": t, "frames": 5, "size": 0.9})
            a.shown = False
        elif do == "appear":
            a = actors[b["actor"]]
            sync(t)
            a.pos = np.array([float(b["pos"][0]), 0.0, float(b["pos"][1])])
            if b.get("face"):
                o = actors[b["face"]]
                a.yaw = yaw_to(a.pos[[0, 2]], o.pos[[0, 2]])
            a.shown = True
            fx.append({"type": "flash", "pos": [float(a.pos[0]), 1.0, float(a.pos[2])], "frame": t, "frames": 5, "size": 0.9})
            if b.get("say"):
                c, r = pick(b["say"], b.get("id"), b.get("kind"))
                a.used.append(r["name"])
                fr = frames_of(c)[: int(round(float(b.get("seconds", 1.0)) * FPS))]
                a.play(fr, fade=0, start=t, src=(r["name"], 0.0, r.get("kit")))
                t0, t = t, a.n()
                sync(t)
                shots.append({"from": t0, "to": t, "kind": b.get("shot", "on"), "actor": a.name})
        elif do == "strike":
            hero, vic = actors[b["by"]], actors[b["on"]]
            c, r = pick(b.get("say"), b.get("id"), b.get("kind"), kit=b.get("clip"))
            hero.used.append(r["name"])
            hit_s = float(b["hit"]) if "hit" in b else float((r["facts"].get("strike") or {}).get("at_s", c["times"][-1] * 0.4))
            lead = float(b.get("lead", 0.22))                  # seconds from the arrival to the hit
            start_s = max(0.0, hit_s - lead)
            D.op_trim(c, start=start_s, end=min(c["times"][-1], hit_s + float(b.get("follow", 0.45))))
            fr = frames_of(c)
            hit_i = int(round((hit_s - start_s) * FPS))
            sync(t)
            # where the attacker arrives: around the target, relative to the target's facing
            side = math.radians(vic.yaw + float(b.get("from", 0.0)))
            d = b.get("dist", "auto")
            if d == "auto":
                d = contact_distance(fr[min(hit_i, len(fr) - 1)], rig, float(b.get("height", 0.0)))
            arrive = vic.pos + np.array([-math.sin(side) * d, float(b.get("height", 0.0)), -math.cos(side) * d])
            if b.get("teleport", True) and hero.shown and hero.n():
                fx.append({"type": "afterimage", "actor": hero.name, "frame": max(0, t - 1), "frames": 14})
                fx.append({"type": "flash", "pos": [float(hero.pos[0]), 1.0, float(hero.pos[2])], "frame": t, "frames": 5, "size": 0.9})
            hero.pos = arrive
            hero.yaw = yaw_to(arrive[[0, 2]], vic.pos[[0, 2]]) + float(b.get("aim", 0.0))
            hero.shown = True
            gap = int(b.get("gap", 3))                          # frames unseen between leaving and arriving
            hero.shown = False
            hero.idle_until(t + gap)
            hero.shown = True
            fx.append({"type": "streak", "pos": [float(arrive[0]), float(arrive[1]), float(arrive[2])], "frame": t + gap, "frames": 6})
            hit_frame = t + gap + hit_i
            hero.play(fr, fade=0, start=t + gap, src=(r["name"], start_s, r.get("kit")))
            # the target: whatever it was doing until the Hit, then the reaction, pushed and spun by the blow
            vic.idle_until(hit_frame)
            rc, rr = pick(b.get("react", "hit reaction"), b.get("react_id"), None, kit=b.get("react_clip"))
            vic.used.append(rr["name"])
            rf = frames_of(rc)
            mark = {}
            for e in rc.get("events") or []:                   # (the FIRST of each marker, as pick() reads the Hit)
                if isinstance(e, dict) and "t" in e:
                    mark.setdefault(e.get("name"), float(e["t"]))
            if b.get("react_from") in mark:                    # started AT its marker, as the game plays it
                rf = rf[int(round(mark[b["react_from"]] * FPS)):]
            if b.get("react_seconds"):
                rf = rf[: int(round(float(b["react_seconds"]) * FPS))]
            push_dir = fwd(hero.yaw)
            push, launch, spin = float(b.get("push", 1.2)), float(b.get("launch", 0.0)), float(b.get("spin", 35.0))
            p0, y0 = vic.pos.copy(), vic.yaw
            slam = bool(b.get("slam"))
            air = int(round(float(b.get("air", 0.9)) * FPS)) if (launch or slam) else 0
            if (launch or slam) and len(rf) < air:
                rf = rf + [rf[-1]] * (air - len(rf))
            sgn = 1.0 if ((y0 - hero.yaw + 540) % 360 - 180) > 0 else -1.0

            def vroot(i, n, vic=vic, p0=p0, y0=y0):
                u = min(1.0, i / 14.0)
                e = 1 - (1 - u) ** 3                            # a shove: fast out, slowing
                off = np.array([push_dir[0], 0.0, push_dir[1]]) * push * e
                if slam:
                    v = min(1.0, i / max(1, air))
                    off = np.array([push_dir[0], 0.0, push_dir[1]]) * push * v
                    off[1] = -p0[1] * v * v                    # falls from where it hung, accelerating
                elif launch:
                    v = min(1.0, i / max(1, air))
                    off = np.array([push_dir[0], 0.0, push_dir[1]]) * push * v
                    off[1] = launch * 4 * v * (1 - v) if b.get("land", True) else launch * math.sin(v * math.pi / 2)
                vic.pos = p0 + off
                vic.yaw = y0 + sgn * spin * e

            vic.hold = False
            vic.play(rf, fade=2, start=hit_frame, root_fn=vroot,
                     src=(rr["name"], mark.get(b.get("react_from"), 0.0) if b.get("react_from") in mark else 0.0,
                          rr.get("kit")))
            vic.hold = bool(b.get("hold", launch and not b.get("land", True)))
            co = b.get("counter")
            parried = isinstance(co, dict) and "Hit" in mark and mark["Hit"] > mark.get(b.get("react_from"), 0.0)
            if parried:
                # a PARRY: the attacker is stopped dead at the contact (held there, stunned) and takes the counter
                # when the defender's clip reaches its own Hit
                cf = hit_frame + int(round((mark["Hit"] - mark.get(b.get("react_from"), 0.0)) * FPS))
                del hero.poses[hit_frame + 1:], hero.root[hit_frame + 1:], hero.visible[hit_frame + 1:]
                if hero.log and hero.log[-1].get("n"):          # (the strike stops dead at the contact)
                    hero.log[-1]["n"] = min(hero.log[-1]["n"], hit_frame + 1 - hero.log[-1]["f"])
                hero.hold = True
                hero.idle_until(cf)
                hero.hold = False
                cc, cr = pick("hit reaction", None, None, kit=co.get("react_clip"))
                hero.used.append(cr["name"])
                cmark = {}
                for e in cc.get("events") or []:
                    if isinstance(e, dict) and "t" in e:
                        cmark.setdefault(e.get("name"), float(e["t"]))
                cff = frames_of(cc)[int(round(cmark.get("Hit", 0.0) * FPS)):]
                hp0, hy0 = hero.pos.copy(), hero.yaw
                back = -fwd(hero.yaw)

                def hroot(i, n, hero=hero, hp0=hp0, back=back, push=float(co.get("push", 1.2))):
                    u = min(1.0, i / 14.0)
                    hero.pos = hp0 + np.array([back[0], 0.0, back[1]]) * push * (1 - (1 - u) ** 3)

                hero.play(cff, fade=2, start=cf, root_fn=hroot, src=(cr["name"], cmark.get("Hit", 0.0), cr.get("kit")))
                fx.append({"type": "impact", "pos": [float(hero.pos[0]), float(hero.pos[1]) + 0.6, float(hero.pos[2])],
                           "frame": cf, "frames": 8, "size": float(co.get("impact", 1.0)), "by": vic.name, "on": hero.name})
                hits.append({"frame": cf, "hold": int(co.get("hitstop", 5)), "shake": float(co.get("shake", 1.0))})
            if b.get("vanish_after"):
                fx.append({"type": "afterimage", "actor": hero.name, "frame": hero.n() - 1, "frames": 14})
                fx.append({"type": "flash", "pos": [float(hero.pos[0]), float(hero.pos[1]) + 1.0, float(hero.pos[2])], "frame": hero.n(), "frames": 5, "size": 0.9})
                hero.shown = False
            fx_w, torso = end_effector_world(hero, hit_frame, rig) if hit_frame < hero.n() else ({}, vic.pos + [0, 1, 0])
            vt = vic.pos.copy()
            vt[1] += 0.5
            contact = min(fx_w.values(), key=lambda p: float(np.linalg.norm(p - (p0 + [0, 0.5, 0])))) if fx_w else vt
            fx.append({"type": "impact", "pos": [float(v) for v in contact], "frame": hit_frame, "frames": 8,
                       "size": float(b.get("impact", 1.0)), "by": hero.name, "on": vic.name,
                       "parry": bool(parried)})
            hits.append({"frame": hit_frame, "hold": int(b.get("hitstop", 4)), "shake": float(b.get("shake", 1.0))})
            t0 = t
            t = max(hero.n(), vic.n())
            sync(t)
            shots.append({"from": t0, "to": t, "kind": b.get("shot", "fight"), "a": hero.name, "b": vic.name,
                          "side": float(b.get("cam", 75.0))})
        else:
            raise ValueError(f"beat {bi}: unknown do '{do}'")
    sync(t)
    return actors, fx, hits, shots, t


def apply_hitstop(actors, fx, hits, shots, total):
    """freeze every actor for `hold` frames at each Hit (the impact reads as weight) -> a global frame map"""
    order = []
    for f in range(total):
        order.append(f)
        for h in hits:
            if h["frame"] == f:
                order += [f] * h["hold"]
    remap = {}
    for i, f in enumerate(order):
        remap.setdefault(f, i)
    for a in actors.values():
        a.poses = [a.poses[f] for f in order]
        a.root = [a.root[f] for f in order]
        a.visible = [a.visible[f] for f in order]
        for e in getattr(a, "log", []):                       # (a segment's track time is unchanged: the game
            e["f"] = remap.get(e["f"], e["f"])                #  freezes its tracks through each hit-stop)
    for e in fx:
        e["frame"] = remap.get(e["frame"], e["frame"])
    for h in hits:
        h["frame"] = remap[h["frame"]]
    for s in shots:
        s["from"], s["to"] = remap.get(s["from"], 0), remap.get(min(s["to"], total - 1), len(order) - 1)
    return len(order)


def torso_tracks(clips, rig):
    """each actor's Torso world position per frame (Roblox studs, the root track composed in) - the camera aims at
    the BODIES, not the roots (a knockdown clip puts the torso 2.5 studs under its root)"""
    out = {}
    for nm, c in clips.items():
        out[nm] = np.array([np.asarray(w["Torso"])[:3, 3] for w in C.world_frames(c, rig)])
    return out


def camera(actors, shots, hits, total, torso, seed=3, near=5.5, cut_deg=30.0, ease=12, same_subject=3.0):
    """one camera position + target per frame (Roblox world). Each shot keeps ONE viewing direction (chosen at its
    start: across the line between the fighters, or off the actor's facing), pushes in slowly, cuts at the next shot
    (or eases into it when the view changes less than `cut_deg` on the same subject); shake after each Hit; never
    closer than `near` studs to any visible body"""
    rng = np.random.default_rng(seed)
    cams = [None] * total
    names = list(actors)
    vis = {nm: actors[nm].visible for nm in names}

    def facing(nm, f):
        yaw = math.radians(actors[nm].root[f][3])
        return np.array([-math.sin(yaw), 0.0, -math.cos(yaw)]), np.array([math.cos(yaw), 0.0, -math.sin(yaw)])

    for s in shots:
        a0, a1 = s["from"], min(total, max(s["from"] + 1, s["to"]))
        if a0 >= total:
            continue
        if s["kind"] == "fight":
            A, Bn = s["a"], s["b"]
            seen = [f for f in range(a0, a1) if vis[A][f]]
            f_ref = seen[min(len(seen) - 1, 6)] if seen else a0
            line = torso[Bn][f_ref] - torso[A][f_ref]
            line[1] = 0
            ln = float(np.linalg.norm(line))
            if ln < 0.8:
                fw, _ = facing(Bn, f_ref)
                line, ln = -fw, 1.0
            line = line / ln
            perp = np.array([-line[2], 0.0, line[0]])
            side = math.radians(s.get("side", 75.0))
            dirv = perp * math.sin(side) + line * math.cos(side)
            for f in range(a0, a1):
                u = (f - a0) / max(1, a1 - a0)
                # a hidden attacker (the frames of its teleport gap) is framed where it is next seen in the shot: the
                # two-shot holds still instead of snapping to the target alone for 3 frames and back (a jump cut)
                fa = f if vis[A][f] else min(seen, key=lambda g: (g < f, abs(g - f))) if seen else None
                bodies = [torso[Bn][f]] + ([torso[A][fa]] if fa is not None else [])
                mid = np.mean(bodies, axis=0)
                spread = float(np.ptp(np.array(bodies)[:, [0, 2]], axis=0).max()) if len(bodies) > 1 else 0.0
                dist = 9.0 - 1.2 * u + 0.4 * spread
                cams[f] = (mid + dirv * dist + [0, 2.0, 0], mid + [0, 0.3, 0])
        else:
            nm = s.get("actor") or names[-1]
            fw, rt = facing(nm, a0)
            for f in range(a0, a1):
                u = (f - a0) / max(1, a1 - a0)
                p = torso[nm][f]
                if s["kind"] == "wide":
                    pts = np.array([torso[k][f] for k in names if vis[k][f]] or [p])
                    centre = pts.mean(0)
                    spread = float(np.ptp(pts[:, [0, 2]], axis=0).max()) if len(pts) > 1 else 0.0
                    cams[f] = (centre + (fw * 0.8 + rt * 0.6) * (13 + spread * 0.6 - 2 * u) + [0, 4.5, 0], centre + [0, 0.3, 0])
                else:
                    cams[f] = (p + (fw * 0.9 + rt * 0.45) * (8.5 - 1.2 * u) + [0, 1.8, 0], p + [0, 0.4, 0])
    # the 30-DEGREE RULE: a cut must change the view by >= cut_deg or it reads as a jump cut (the duel's strikes at
    # sides 70 / 60 / 75 lurched 1-1.8 studs at each new beat) - a next shot that close CONTINUES the last one instead,
    # easing from where the camera was over `ease` frames
    def view(f):
        d = np.asarray(cams[f][0], float) - np.asarray(cams[f][1], float)
        d[1] = 0
        n = float(np.linalg.norm(d))
        return d / n if n > 1e-6 else d

    cuts = set()                                              # the frames a new shot CUTS in (the game snaps there)
    for s in shots:
        a0 = s["from"]
        a1 = min(total, max(a0 + 1, s["to"]))
        if a0 <= 0 or a0 >= total or cams[a0 - 1] is None or cams[a0] is None:
            continue
        if math.degrees(math.acos(max(-1.0, min(1.0, float(view(a0 - 1) @ view(a0)))))) >= cut_deg:
            cuts.add(a0)
            continue
        # (only on the SAME subject: a next shot aimed elsewhere - another pair across the arena - is a cut, never a
        # 12-frame fly-through; review 2026-10-24)
        if float(np.linalg.norm(np.asarray(cams[a0][1], float) - np.asarray(cams[a0 - 1][1], float))) > same_subject:
            cuts.add(a0)
            continue
        held = (np.asarray(cams[a0 - 1][0], float), np.asarray(cams[a0 - 1][1], float))
        n = min(ease, max(1, (a1 - a0) // 2))               # (a short shot still arrives at its own framing)
        for k in range(n):
            w = D.smooth((k + 1) / (n + 1))
            loc, tgt = cams[a0 + k]
            cams[a0 + k] = (held[0] + (np.asarray(loc) - held[0]) * w, held[1] + (np.asarray(tgt) - held[1]) * w)
    for f in range(total):
        if cams[f] is None:
            cams[f] = cams[f - 1] if f else (np.array([0, 5, 14.0]), np.zeros(3))
        loc, tgt = cams[f]
        for nm in names:                                     # never inside / on top of a body
            if not vis[nm][f]:
                continue
            d = loc - torso[nm][f]
            dn = float(np.linalg.norm(d))
            if dn < near:
                back = loc - tgt
                back = back / max(float(np.linalg.norm(back)), 1e-6)
                loc = loc + back * (near - dn + 0.5)
        loc = np.array(loc, float)
        loc[1] = max(loc[1], -1.5)                            # above the floor (3 studs under the root)
        cams[f] = (loc, tgt)
    for h in hits:
        for k in range(10):
            f = h["frame"] + k
            if f < total:
                amp = 0.35 * h["shake"] * (1 - k / 10)
                loc, tgt = cams[f]
                j = rng.normal(0, amp, 3)
                cams[f] = (loc + j, tgt + j * 0.4)
    return [dict({"loc": [float(v) for v in l], "target": [float(v) for v in t_]}, **({"cut": True} if f in cuts else {}))
            for f, (l, t_) in enumerate(cams)]


def rel_path(path):
    """a path as the repo sees it (relative to where the kit runs, forward slashes): the same in every checkout"""
    try:
        return os.path.relpath(os.path.abspath(path)).replace(os.sep, "/")
    except ValueError:                                         # (another drive: keep it as given)
        return path.replace(os.sep, "/")


def build(script_path, render=True, size=(960, 540), every=1):
    script = json.load(open(script_path, encoding="utf-8"))
    name = script.get("name", "Cutscene")
    odir = os.path.join(OUT, name)
    os.makedirs(odir, exist_ok=True)
    actors, fx, hits, shots, total = make(script)
    total = apply_hitstop(actors, fx, hits, shots, total)
    clips, cdata = {}, {}
    for a in actors.values():
        c = {"schema": 1, "name": f"{name}_{a.name}", "rig": "R6", "fps": FPS, "loop": False,
             "times": [round(i / FPS, 6) for i in range(total)],
             "joints": {j: {"frames": [p[j] for p in a.poses]} for j in JOINTS},
             "root": [quat_y(r[3]) + [r[0], r[1], r[2]] for r in a.root]}
        sw = [p.get("_sword") for p in a.poses]
        if any(sw):
            first = next(x for x in sw if x)
            held, last = [], first
            for x in sw:                                       # held in hand between clips without a sword
                last = x or last
                held.append(last)
            tips, grips, edges = [], [], []
            for p, x in zip(a.poses, held):
                M = arm_mat(p)
                grips.append([float(v) for v in (M @ np.r_[x["g"], 1.0])[:3]])
                tips.append([float(v) for v in (M @ np.r_[x["t"], 1.0])[:3]])
                if x.get("e") is not None:
                    edges.append([float(v) for v in M[:3, :3] @ np.asarray(x["e"], float)])
            c["sword"] = {"tip": tips, "grip_path": grips, "kind": first.get("kind") or "katana",
                          "length": first.get("length") or 3.6, "grip": first.get("grip") or 0.5}
            if len(edges) == len(tips):
                c["sword"]["edge"] = edges
        path = os.path.join(odir, f"{a.name}.clip.json")
        json.dump(c, open(path, "w", encoding="utf-8"))
        cdata[a.name] = c
        clips[a.name] = {"clip": path, "look": a.look, "visible": a.visible, "used": a.used, "plays": a.log}
    cams = camera(actors, shots, hits, total, torso_tracks(cdata, C.load_rig("r6")))
    scene = {"name": name, "fps": FPS, "frames": total, "actors": clips, "fx": fx, "hits": hits, "camera": cams,
             "size": list(size), "out": odir, "every": every, "script": rel_path(script_path)}
    sp = os.path.join(odir, "scene.json")
    json.dump(scene, open(sp, "w", encoding="utf-8"))
    if not render:
        return scene, None
    p = subprocess.run([ML.BLENDER, "-b", os.environ.get("PARALLAX_R6_RIG") or "assets/rigs/R6_IK.blend", "--disable-autoexec", "--python-exit-code", "2", "-P",
                        os.path.join("kit", "anim", "cutscene_r6.py"), "--", sp], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    last = [ln for ln in p.stdout.splitlines() if ln.startswith("{")]
    res = json.loads(last[-1]) if last else {"status": "fail", "summary": (p.stderr or p.stdout)[-1500:]}
    return scene, res


def timeline(scene, every_s=1 / 30):
    """the scene as the GAME plays it (src/kit/Cutscene.luau): per actor what plays when (the kit's own clips, by name,
    from a point in them; "@idle" / "@hold" between), its root path ("x y z yaw" rows, yaw in radians, every `every_s`;
    space = the cutscene's own: the runtime puts it on an anchor CFrame), when it is hidden (a teleport's gap) and when
    its root JUMPS; the camera's keys in the same space and when it CUTS, the hit-stops (seconds of freeze) and the
    effects (impacts, flashes) as events"""
    fps = scene["fps"]
    step = max(1, int(round(every_s * fps)))
    out = {"fps": round(fps / step, 3), "duration": round(scene["frames"] / fps, 4), "actors": {}, "camera": [],
           "hits": sorted(({"t": round(h["frame"] / fps, 4), "hold": round(h["hold"] / fps, 4)} for h in scene["hits"]),
                          key=lambda h: h["t"]),
           "events": []}
    for nm, a in scene["actors"].items():
        c = json.load(open(a["clip"], encoding="utf-8"))
        rows = []
        for r in c["root"][::step]:
            yaw = 2 * math.atan2(r[1], r[3])
            rows.append(f"{r[4]:.3f} {r[5]:.3f} {r[6]:.3f} {yaw:.4f}")
        hidden, st = [], None
        for i, v in enumerate(list(a["visible"]) + [True]):
            if not v and st is None:
                st = i
            elif v and st is not None:
                hidden.append([round(st / fps, 4), round(i / fps, 4)])
                st = None
        # the TELEPORTS, marked (the game snaps there, never slides): a root move over 0.5 studs in one 60 fps frame
        # (30 studs/s - a shove peaks near 0.35), or any move next to a hidden frame (review 2026-10-24: the duel's
        # 1.7-1.8 stud teleports slid under a distance rule)
        vis, jumps = list(a["visible"]), []
        for f in range(1, len(c["root"])):
            d = math.hypot(c["root"][f][4] - c["root"][f - 1][4], c["root"][f][6] - c["root"][f - 1][6])
            near_gap = not vis[min(f, len(vis) - 1)] or not vis[min(f - 1, len(vis) - 1)]
            if d > 0.5 or (d > 0.05 and near_gap):
                jumps.append(round(f / fps, 4))
        plays = []
        for e in a.get("plays") or []:
            p = {"t": round(e["f"] / fps, 4), "clip": e["clip"]}
            if not e["clip"].startswith("@"):
                p.update({"from": e["from"], "len": round(e["n"] / fps, 4), "fade": round(e["fade"] / fps, 4),
                          "kit": e["kit"]})
            plays.append(p)
        out["actors"][nm] = {"look": a["look"], "plays": plays, "root": rows, "hidden": hidden, "jumps": jumps}
    out["cuts"] = [round(f / fps, 4) for f, k in enumerate(scene["camera"]) if k.get("cut")]
    for f in range(0, scene["frames"], step):
        k = scene["camera"][f]
        out["camera"].append({"t": round(f / fps, 4), "loc": [round(v, 3) for v in k["loc"]],
                              "target": [round(v, 3) for v in k["target"]]})
    for e in scene["fx"]:
        if e.get("type") in ("impact", "flash", "streak"):
            ev = {"t": round(e["frame"] / fps, 4), "type": e["type"]}
            if e.get("pos") is not None:
                ev["pos"] = [round(float(v), 3) for v in e["pos"]]
            for k in ("by", "on", "parry"):                    # (who struck whom: the game's Hit event names them)
                if e.get(k) is not None:
                    ev[k] = e[k]
            if e.get("size") is not None:
                ev["size"] = round(float(e["size"]), 3)
            out["events"].append(ev)
    out["events"].sort(key=lambda e: e["t"])
    # what it was BUILT FROM (kit anim's verify compares: a changed clip or script makes it stale) - the script's
    # bytes (line endings normalised: a Windows checkout is not a change) and each game clip's length + events, the
    # fields KitAnimations.Meta carries for it
    src = {"clips": {}}
    if scene.get("script") and os.path.isfile(scene["script"]):
        import hashlib
        raw = open(scene["script"], "rb").read().replace(b"\r\n", b"\n")
        src["script"] = {"path": scene["script"], "sha256": hashlib.sha256(raw).hexdigest()}
    for a in out["actors"].values():
        for p in a["plays"]:
            if p.get("kit") and p["clip"] not in src["clips"]:
                cp = os.path.join(os.environ.get("KIT_BUILD", "build"), "animations", f"{p['clip']}.clip.json")
                if os.path.isfile(cp):
                    c = json.load(open(cp, encoding="utf-8"))
                    src["clips"][p["clip"]] = {
                        "duration": round(float(c.get("duration") or c["times"][-1]), 4),
                        "events": [[e.get("name"), round(float(e["t"]), 4)] for e in c.get("events") or []
                                   if isinstance(e, dict) and "t" in e]}
    out["sources"] = src
    return out


def write_game(scene, out_dir):
    """the timeline into <out_dir>/Cutscenes.luau (ReplicatedStorage.KitAnimations.Cutscenes: every game cutscene by
    name), keeping the other cutscenes already in it"""
    path = os.path.join(out_dir, "Cutscenes.luau")
    allc = {}
    if os.path.isfile(path):
        import re
        text = open(path, encoding="utf-8").read()
        m = re.search(r"JSONDecode\(\[(=+)\[", text)
        j = text.rfind(f"]{m.group(1)}]") if m else -1
        if m and j > m.end():
            try:
                allc = json.loads(text[m.end():j])
            except ValueError:
                allc = {}
    allc[scene["name"]] = timeline(scene)
    os.makedirs(out_dir, exist_ok=True)
    body = json.dumps(allc, indent=1, sort_keys=True)
    eq = 2                                                     # a long-string level whose closer the JSON never holds
    while f"]{'=' * eq}]" in body:                             # (a name with "]==]" in it cannot end the string early)
        eq += 1
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("-- generated by `lune run kit anim cutscene <script> --timeline`: every cutscene's timeline for "
                 "src/kit/Cutscene. Never edit.\n")
        fh.write(f'return game:GetService("HttpService"):JSONDecode([{"=" * eq}[')
        fh.write(body)
        fh.write(f"]{'=' * eq}])\n")
    return path


def sheet(odir, name, cols=6, width=1920):
    """every rendered frame of a preview (--every N) in one picture: <name>.sheet.png"""
    from PIL import Image
    fdir = os.path.join(odir, "frames")
    files = sorted(os.listdir(fdir))
    if not files:
        return None
    ims = [Image.open(os.path.join(fdir, f)).convert("RGB") for f in files]
    w = width // cols
    h = int(ims[0].height * w / ims[0].width)
    rows = (len(ims) + cols - 1) // cols
    out = Image.new("RGB", (w * cols, h * rows), (10, 10, 12))
    for i, im in enumerate(ims):
        out.paste(im.resize((w, h)), ((i % cols) * w, (i // cols) * h))
    path = os.path.join(odir, f"{name}.sheet.png")
    out.save(path)
    return path


def encode(odir, name, fps=FPS):
    frames = os.path.join(odir, "frames", "%05d.png")
    mp4 = os.path.join(odir, f"{name}.mp4")
    gif = os.path.join(odir, f"{name}.gif")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps), "-i", frames, "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-crf", "18", mp4], check=False)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", mp4, "-vf",
                    "fps=24,scale=480:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96[p];[b][p]paletteuse=dither=bayer",
                    gif], check=False)
    return (mp4 if os.path.isfile(mp4) else None), (gif if os.path.isfile(gif) else None)


def main(argv):
    if argv[:1] != ["make"] or len(argv) < 2:
        print(__doc__)
        return 2
    every = int(argv[argv.index("--every") + 1]) if "--every" in argv else 1
    game = argv[argv.index("--game") + 1] if "--game" in argv else None
    scene, res = build(argv[1], render="--plan" not in argv and not game, every=every)
    name = scene["name"]
    used = {k: v["used"] for k, v in scene["actors"].items()}
    if game:
        path = write_game(scene, game)
        tl = timeline(scene)
        lib = sorted({p["clip"] for a in tl["actors"].values() for p in a["plays"]
                      if not p["clip"].startswith("@") and not p.get("kit")})
        n = sum(len(a["plays"]) for a in tl["actors"].values())
        ML.emit("pass", f"cutscene {name}: timeline -> {path} ({tl['duration']:.1f} s, {len(tl['actors'])} actors, "
                f"{n} plays, {len(tl['hits'])} hit-stops, {len(tl['camera'])} camera keys)"
                + (f"; library clips the game does not have (played as idle): {', '.join(lib)}" if lib else ""),
                f"play it in game: Cutscene.play(\"{name}\", anchor, {{{', '.join(f'{k} = <Model>' for k in tl['actors'])}}})")
        return 0
    if res is None:
        ML.emit("pass", f"cutscene {name}: planned {scene['frames']} frames ({scene['frames'] / FPS:.1f} s), {len(scene['hits'])} hits, clips {used}", "drop --plan to render")
        return 0
    if res.get("status") != "pass":
        ML.emit("fail", f"cutscene {name}: render failed - {res.get('summary')}", "read the Blender output")
        return 1
    if every > 1:
        sh = sheet(scene["out"], name)
        ML.emit("pass", f"cutscene {name}: preview every {every} frames -> {sh}; {res.get('summary')}", "look at the sheet, then render without --every")
        return 0
    mp4, gif = encode(scene["out"], name)
    ML.emit("pass", f"cutscene {name}: {scene['frames']} frames ({scene['frames'] / FPS:.1f} s), {len(scene['hits'])} hits; {res.get('summary')}; video {mp4}, gif {gif}; clips {used}",
            "watch the video; change a beat's words to swap a move")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
