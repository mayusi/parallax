"""proc_react.py — a PHYSICAL HIT REACTION built from its move dossier (mission 04-anim, the second action: the head
hook). The dossier's build names the base idle (a kit clip, e.g. BrawlerIdle: a fighter hit in stance), the hit (part,
direction, speed, spin, time) and the body's stiffness; MuJoCo (proc_physics.react) makes the reaction - the body
tracks its idle, takes the impulse, recovers - layered on the idle as the with-hit minus without-hit difference; the
feet are re-planted; the Hit event sits at the impact. The owner rated this route 'semi realistic, good job' (6/10,
2026-10-14); the dossier calibrates its size to the loved R6 reactions (react_measure.py, statistics only).
    python kit/anim/proc_react.py <dossier> [--out <clip.json>]"""
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import clip as C  # noqa: E402
import proc_director as DR  # noqa: E402
import proc_dossier as DS  # noqa: E402
import proc_kick as PK  # noqa: E402
import proc_physics as PH  # noqa: E402


def base_clip(name, seconds):
    """the base idle (built by `kit anim <name>`), looped to `seconds`"""
    path = next((p for p in (os.path.join("build", "animations", f"{name}.clip.json"),
                             os.path.join("build", "animations", f"{name}.r6.clip.json")) if os.path.isfile(p)), None)
    if path is None:
        raise SystemExit(f"no built base clip '{name}': lune run kit anim {name}")
    c = json.load(open(path, encoding="utf-8"))
    fps = c.get("fps", 60)
    n0, n = len(c["times"]), int(round(seconds * fps))
    out = copy.deepcopy(c)
    for j in out["joints"]:
        fr = c["joints"][j]["frames"]
        out["joints"][j]["frames"] = [fr[i % n0] for i in range(n)]
    out["times"] = [round(i / fps, 6) for i in range(n)]
    out["loop"] = False
    out.pop("events", None)
    out.pop("root", None)
    return out


HIT_KEYS = ("part", "dir", "speed", "spin", "t", "dur")


def build(d, hit=None, body=None, sim=None, name=None):
    """-> (clip, the build used). hit: a candidate's own head-hit parameters (else the dossier's); body: its own
    body push (the hook's force reaching the torso; else the dossier's `body_hit`, if any)"""
    b = dict(d["build"])
    if sim:
        b["sim"] = {**(b.get("sim") or {}), **sim}
    h = {**b["hit"], **(hit or {})}
    bh = {**b["body_hit"], **(body or {})} if b.get("body_hit") or body else None
    hits = [{k: h[k] for k in HIT_KEYS if k in h}]
    if bh:
        hits.append({k: {**h, **bh}[k] for k in HIT_KEYS if k in {**h, **bh}})
    base = base_clip(b["base"], b.get("seconds", 2.4))
    c, _ = PH.react(base, hits, w_joint=float(h.get("w_joint", 14.0)), neck_deg=b.get("neck_deg"), **(b.get("sim") or {}))
    c = DR.pin_feet(c, PK.slide_ranges())
    # the Hit at the impact, settled on the head's snap the way the engine judges it: 0..3 whole frames after the
    # nearest speed peak, on the clip's own time grid (proc_kick: the rounding that put Hits 3.002 frames late)
    c["events"] = [{"t": float(h["t"]), "name": "Hit", "by": h["part"]}]
    ev = (C.metrics(c, C.load_rig("r6")).get("events") or [{}])[0]
    if ev.get("peak_t") is not None:
        pkf = int(round(float(ev["peak_t"]) * 60))
        f = min(max(int(round(float(h["t"]) * 60)), pkf), pkf + 3, len(c["times"]) - 1)
        c["events"][0]["t"] = float(c["times"][f])
    c["name"] = name or d["name"]
    c["dossier"] = d["name"]
    import clip_beats as CB                                  # (its own beats: the blow and the settle after it, j6x7)
    t_hit = float(c["events"][0]["t"])
    c["beats"] = CB.from_keys([(0.0, "before"), (t_hit, "hit"), (min(t_hit + 2 / 60, float(c["times"][-1])), "recover")],
                              float(c["times"][-1]))
    b["hit"] = h
    if bh:
        b["body_hit"] = bh
    return c, b


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    a = sys.argv[1:]
    d = DS.require(a[0])
    c, b = build(d)
    out = a[a.index("--out") + 1] if "--out" in a else os.path.join("build", "candidates", f"{d['name']}.base.clip.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(c, open(out, "w", encoding="utf-8"))
    r = DS.check(c, {**d, "build": b})
    m = C.metrics(c, C.load_rig("r6"))
    fails = [k for k, v in r["checks"].items() if not v["pass"]]
    print(json.dumps({"schema": 1, "status": "pass" if not fails and not m.get("problems") else "fail",
                      "summary": f"{d['name']}: built from {b['base']} + a {b['hit']['part']} hit -> {out}; dossier "
                                 + ("all checks pass" if not fails else f"fails {fails}")
                                 + (f"; engine {m['problems'][:2]}" if m.get("problems") else ""),
                      "next_action": f"python kit/anim/dossier_verify.py {out} --dossier {d['name']}"}))
