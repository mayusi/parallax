"""RigRun2 key poses (an example of the research workflow, board/plans/archive/2026-10-11-anim-research.md): limbs at their
extremes with in-out eases + bottom breakdowns, the stance planted at down, contact by forward slide, flight clear, drag
offsets, non-mirrored steps. Writes assets/animations/RigRun2.pose.json; tune with a JSON of parameters as argv[1].
    python kit/anim/examples/rigrun2_keys.py '{"leg_fwd": 66, "arm_fwd": 128}' && lune run kit anim RigRun2 && lune run kit anim profile RigRun2 --vs CommunitySprint"""
import json, copy, sys
# the values RigRun2 was built with (0 profile gaps vs CommunitySprint, 2026-10-11)
P = {"leg_fwd": 66, "leg_back": -88, "arm_fwd": 128, "arm_back": -64, "compress": 0.12, "clear": 0.12, "contact_fwd": 0.75,
     "contact_y": -0.06, "limb_ease": "quad_inout", "twist_lead": 1.1, "asym_arm": 0.97, "asym_leg": 0.9, "asym_turn": 0.8}
P.update(json.loads(sys.argv[1]) if len(sys.argv) > 1 else {})
g = lambda k, d: P.get(k, d)
CYC = int(g("cycle", 36)); H = CYC // 2
def half(f0, F, B, s):
    arm_of = {"right": "left", "left": "right"}
    t = 1 if F == "right" else -1
    leg_f, leg_b = g("leg_fwd", 62) * s["leg"], g("leg_back", -74) * s["leg"]
    arm_f, arm_b = g("arm_fwd", 95) * s["arm"], g("arm_back", -45) * s["arm"]
    K = []
    # CONTACT: extremes - front leg reaching, back leg kicked up behind, arms at the ends of the pump
    K.append({"f": f0, "ease": g("limb_ease", "cubic_inout"),
              "body": {"pos": [0, g("contact_y", -0.06), 0], "lean": g("lean", 15), "turn": g("twist", 17) * s["turn"] * t, "tilt": -2 * t},
              f"{F}_leg": {"swing": leg_f, "out": 2, "twist": 0, "slide": [0, g("contact_up", 0.0), g("contact_fwd", 0.6)]},
              f"{B}_leg": {"swing": leg_b, "out": 3, "twist": 0, "slide": [0, g("kick_up", 0.4), -0.05]},
              f"{arm_of[F]}_arm": {"swing": arm_f, "out": 3, "twist": 0, "slide": [0, -g("elbow", 0.55), g("elbow", 0.55) * 0.8]},
              f"{arm_of[B]}_arm": {"swing": arm_b, "out": 6, "twist": 0, "slide": [0, -0.1, -0.12]}})
    # DOWN: weight absorbed on the front leg (it slides up into the torso), body lowest
    K.append({"f": f0 + round(H * 0.22), "ease": "sine_inout",
              "body": {"lean": g("lean", 15) + 1, "plant": F},
              f"{F}_leg": {"swing": leg_f * 0.45, "out": 2, "twist": 0, "slide": [0, g("compress", 0.28), 0.12]}})
    # PASSING: the swing leg drives through high and forward (the R6 knee), the stance leg under the hip
    K.append({"f": f0 + round(H * 0.5), "ease": "quad_inout",
              # BREAKDOWNS: both arms pass the bottom here - a 187-degree pump interpolated between its two extremes
              # takes the short way, OVER THE HEAD (RigRun2 v2's left arm windmilled; the profile caught it)
              f"{arm_of[F]}_arm": {"swing": (arm_f + arm_b) * 0.5 * 0.55, "out": 4, "twist": 0, "slide": [0, -0.25, 0.15]},
              f"{arm_of[B]}_arm": {"swing": (arm_f + arm_b) * 0.5 * 0.45, "out": 5, "twist": 0, "slide": [0, -0.2, 0.1]},
              f"{F}_leg": {"swing": -8, "out": 2, "twist": 0, "slide": [0, 0.1, 0]},
              f"{B}_leg": {"swing": 8, "out": 3, "twist": 0, "slide": [0, g("knee_drive", 0.75), g("knee_drive", 0.75) * 0.85]}})
    # FLIGHT: pushed off, both feet clear, body at the top
    K.append({"f": f0 + round(H * 0.75), "ease": "sine_inout",
              "body": {"lean": g("lean", 15) - 1, "turn": -g("twist", 17) * s["turn"] * t * g("twist_lead", 0.6), "tilt": 0,
                       "plant": "both", "clear": g("clear", 0.12)}})
    return K
keys = half(0, "right", "left", {"leg": 1.0, "arm": 1.0, "turn": 1.0}) + \
       half(H, "left", "right", {"leg": g("asym_leg", 0.94), "arm": g("asym_arm", 0.92), "turn": g("asym_turn", 0.88)})
last = copy.deepcopy(keys[0]); last["f"] = CYC
keys.append(last)
for k in keys:
    if "body" in k and k["f"] in (0, H, CYC):
        k["head"] = {"look": [0, -0.04, 1]}
spec = {"name": "RigRun2", "axes": "stage: x right, y up from the floor, z forward (root-relative)", "fps": 60, "loop": True,
        "priority": "Movement", "legs": "fk", "offsets": g("offsets", {"arms": 1, "head": 2}),
        "note": "RigRun v2, made with the research workflow (board/plans/archive/2026-10-11-anim-research.md): limbs keyed only at their extremes with cubic in-out eases (snap ~2.8 like the finished R6 runs, not a floaty sine), contacts planted by measurement, flight clear, arms opposite the legs, the drag hierarchy (arms +1 f, head +2 f), the two steps not mirrored; profiled against CommunitySprint",
        "keys": keys}
open("assets/animations/RigRun2.pose.json", "w", newline="").write(json.dumps(spec, indent=1) + "\n")
print(len(keys), "keys")
