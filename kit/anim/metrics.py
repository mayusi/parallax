"""metrics.py — `python kit/anim/metrics.py build/animations/<Name>.clip.json`: the clip's motion measured over time
(kit/anim/clip.py) -> <Name>.metrics.json beside it, and the verdict line `kit anim` reads: fail when a gate bites
(a Hit off the fastest frame, a planted foot sliding, a one-frame snap, a loop that ends elsewhere, a part under the
ground, a weapon out of both hands with no toss declared - kit/anim/in_hand.py), with the fix in next_action.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clip as C  # noqa: E402


def main(argv):
    if not argv:
        print(json.dumps({"status": "fail", "summary": "metrics: no clip given",
                          "next_action": "python kit/anim/metrics.py build/animations/<Name>.clip.json"}))
        return 1
    path = argv[0]
    clip = C.load_clip(path)
    rig = C.load_rig(clip["rig"])
    m = C.metrics(clip, rig)
    # THE WEAPON IN A HAND AT EVERY FRAME (kit/anim/in_hand.py; the owner's method lists 2026-11-13, attachment
    # sockets): the weapon out of both hands with no toss declared by the clip's events is a problem of the clip
    import in_hand as IH
    held, loose = IH.gate(clip)
    if held is not None:
        m["in_hand"] = held
    if loose:
        m["problems"].append(loose)
    # A PATH DRAWN FOR THE BLADE (kit/anim/blade_path.py): a clip whose source states a blade_path is held to it
    import blade_path as BP
    drawn, missed = BP.gate(clip)
    if drawn is not None:
        m["blade_path"] = drawn
    if missed:
        m["problems"].append(missed)
    # ... AND FOR A HAND OR A FOOT (a kick's foot, a fist): a source that states "paths" is held to each of them
    drawn, missed = BP.gate_paths(clip)
    if drawn is not None:
        m["paths"] = drawn
    if missed:
        m["problems"].append(missed)
    # NOTHING PASSES THROUGH THE BODY (kit/anim/collide.py; the owner's limitations list 2026-11-15, A-R05): the weapon,
    # the hands and the feet, swept between frames, against the body's blocks; a declared contact is not judged
    import collide as CO
    through, passed = CO.gate(clip)
    if through is not None:
        m["collide"] = through
    if passed:
        m["problems"].append(passed)
    # WHERE THE STRIKE MEETS ITS TARGET (kit/anim/contact.py; the owner's limitations list 2026-11-15, A-R06): every
    # contact the geometry sees, with its confidence; a Hit the BUILD placed at a speed peak is held to it
    import contact as CT
    meets, missed_target = CT.gate(clip)
    if meets is not None:
        m["contact"] = meets
    if missed_target:
        m["problems"].append(missed_target)
    # ONE FINISHING CONTRACT (kit/anim/finish.py; the owner's limitations list 2026-11-15, A-R09): the same numbers for
    # every route's clip, and a clip that asks for a finish its route did not apply is a problem
    import finish as FN
    finished, unfinished = FN.gate(clip)
    if finished is not None:
        m["finish"] = finished
    if unfinished:
        m["problems"].append(unfinished)
    # THE STRIKE AS THE PLAYER'S CAMERA SEES IT (kit/anim/camera_read.py; the owner's older list, AN-36): how much of
    # the strike is seen to move from behind and from 45 degrees to either side - a reading, never a failure
    import camera_read as CR
    seen, _ = CR.gate(clip)
    if seen is not None:
        m["camera"] = seen
    # A JOINT THAT TURNS FASTER THAN THE FRAMES CAN CARRY (kit/anim/fast_turns.py): over 90 degrees between two frames
    # the way round is not defined - a swing of two big steps side by side, which the pop gate does not see
    import fast_turns as FT
    turned, too_fast = FT.gate(clip)
    if turned is not None:
        m["fast_turns"] = turned
    if too_fast:
        m["problems"].append(too_fast)
    # AN OBJECT HANDED BETWEEN PARENTS (kit/anim/handoff.py; LIMITATIONS_FIXES_V3 Stage D): a clip that carries a
    # handoff plan is held to it - the hand reaches what it takes, a socket is arrived at, a toss lands in its catch
    import handoff as HO
    handed, dropped = HO.gate(clip, rig)
    if handed is not None:
        m["handoff"] = handed
    if dropped:
        m["problems"].append(dropped)
    # WHAT THE RIG CHANGE LOST (kit/anim/fold_loss.py; the owner's older list, AN-19 / AN-21): an R6 fold with its R15
    # source beside it is read against it - hands, feet, pelvis; over the bar it fails, what no R6 can keep is said
    import fold_loss as FL
    lost, too_far = FL.gate(clip, path)
    if lost is not None:
        m["fold"] = lost
    if too_far:
        m["problems"].append(too_far)
    # A PROP's parts move only as its joints allow (kit/anim/prop_rig.py): a clip on a prop's rig is held to them
    import prop_rig as PR
    joints, broken = PR.gate(clip, rig)
    if joints is not None:
        # (the gates above are a CHARACTER's: feet that slide, a Hit on a limb, a part under the ground. On a prop
        # they take its lowest part for a foot - a drawer sliding its own length "slides a planted foot")
        m["character_gates_not_for_a_prop"] = list(m["problems"])
        m["problems"] = []
        m["prop"] = joints
    if broken:
        m["problems"].append(broken)
    base = path[:-len(".clip.json")] if path.endswith(".clip.json") else os.path.splitext(path)[0]
    out = base + ".metrics.json"
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(m, fh, indent=1)
    problems = m["problems"]
    status = "pass" if not problems else "fail"
    if status == "pass":
        summary = C.summary(m)
        nxt = None
    else:
        summary = f"{m['name']}: {problems[0]}" + (f" (+{len(problems) - 1} more in {os.path.basename(out)})" if len(problems) > 1 else "")
        nxt = problems[0]
    verdict = {"schema": 1, "status": status, "summary": summary, "file": out.replace(chr(92), "/")}
    if nxt:
        verdict["next_action"] = nxt
    print(json.dumps(verdict))
    return 0 if status == "pass" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
