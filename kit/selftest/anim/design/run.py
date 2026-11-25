"""run.py — the attack set design's selftest cases (kit selftest; kit/anim/set_design.py, the animation studio route's
A1), on a string of cuts the owner loved (kit/selftest/anim/faults/loved/Katana1Kesa, Katana2GyakuKesa, Katana3Makko:
read only; a cut made again is a COPY in this run's own folder).

    python kit/selftest/anim/design/run.py good        the loved katana string as a design: whole, no two attacks
                                                       cousins, its keys are its design (direction, frames), the
                                                       page is drawn; a move of the set is held until the owner's
                                                       yes to the design, free after it, held again once the design
                                                       changed
    python kit/selftest/anim/design/run.py cousins     the same string with its third attack replaced by the first
                                                       cut made again (every key turned 8 degrees, the grip moved
                                                       0.2 studs): the design must name the two COUSINS (this case
                                                       FAILS, naming them)
    python kit/selftest/anim/design/run.py undesigned  a move of a set whose design the owner never approved: it
                                                       must not be made (this case FAILS, saying the set comes first)
    python kit/selftest/anim/design/run.py broken      the kesa straight into the makko in a set linked by pose (the
                                                       loved string runs kesa, gyaku-kesa, makko): the kesa ends 145
                                                       degrees from where the makko starts - the string BREAKS (this
                                                       case FAILS, naming the two attacks and the joint)

Prints one JSON line {schema, status, summary, next_action}; everything is written under build/selftest/ in a folder
of this run's own, removed at the end.
"""
import contextlib
import io
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import set_design as SD  # noqa: E402

LOVED = os.path.join(ROOT, "kit", "selftest", "anim", "faults", "loved")
SET = "SelftestString"


def call(argv):
    said = io.StringIO()
    with contextlib.redirect_stdout(said):
        code = SD.main(argv)
    return code, json.loads(said.getvalue().strip().splitlines()[-1])


def out(status, summary, next_action):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action}))
    return 0 if status == "pass" else 1


def attack(name, cut, body, frames, nxt, move, intent="proper"):
    return {"name": name, "cut": cut, "height": "mid", "body": body, "intent": intent,
            "frames": {"windup": frames[0], "active": frames[1], "recovery": frames[2]},
            "ends": "the blade low on the far side, the weight forward", "next": nxt, "move": move}


def main(case):
    run = os.path.join(os.environ.get("KIT_BUILD", os.path.join(ROOT, "build")), "selftest", f"anim_design_{os.getpid()}")
    shutil.rmtree(run, ignore_errors=True)
    designs = os.path.join(run, "anims", "designs")
    os.makedirs(designs)
    at = ["--designs", designs]
    kesa, gyaku, makko = (os.path.join(LOVED, f"{n}.move.json") for n in ("Katana1Kesa", "Katana2GyakuKesa", "Katana3Makko"))
    try:
        design = {"schema": 1, "set": SET, "weapon": "katana", "links": "pose",
                  "attacks": [attack("Katana1Kesa", "left", "step_in", (26, 1, 24), ["Katana2GyakuKesa"], kesa),
                              attack("Katana2GyakuKesa", "right", "plant", (24, 1, 24), ["Katana3Makko"], gyaku),
                              attack("Katana3Makko", "down", "lunge", (28, 1, 21), [], makko, "aggressive")]}
        if case == "cousins":
            with open(kesa, encoding="utf-8") as fh:
                again = json.load(fh)
            for k in again["keys"]:
                k["yaw"] = float(k.get("yaw", 0.0)) + 8.0
                if "grip" in k:
                    k["grip"] = [k["grip"][0] + 0.2, k["grip"][1] + 0.2, k["grip"][2]]
            path = os.path.join(run, "KesaAgain.move.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(again, fh)
            design["attacks"][2] = attack("KesaAgain", "left", "lunge", (26, 1, 24), [], path)
            design["attacks"][2]["height"] = "low"            # (designed as another attack: only its keys give it away)
            design["attacks"][1]["next"] = ["KesaAgain"]
            design["links"] = "blend"                         # (this case is about cousins: the game blends its links)
        if case == "broken":
            design["attacks"] = [design["attacks"][0], design["attacks"][2]]
            design["attacks"][0]["next"] = ["Katana3Makko"]
        SD.save_json(SD.design_path(designs, SET), design)
        png = os.path.join(run, "design.png")
        code, v = call(["page", SET, "--out", png, *at])
        if case in ("cousins", "broken"):
            return out("pass" if code == 0 else "fail", v["summary"], v["next_action"])
        if case == "undesigned":
            code, v = call(["lock", "Katana2GyakuKesa", *at])
            return out("pass" if code == 0 else "fail", v["summary"], v["next_action"])
        wrong = []
        if code != 0 or v["problems"] or v["state"] != "waiting":
            wrong.append(f"the loved string's design did not pass as whole and waiting ({v['summary']})")
        if not os.path.isfile(png) or os.path.getsize(png) < 20000:
            wrong.append("its page was not drawn")
        if not any("the string's link" in n for n in v.get("notes") or []):
            wrong.append("the string's links were not said")
        code0, held = call(["lock", "Katana2GyakuKesa", *at])
        # a record typed by hand (his words and the id, but no page he saw) must free nothing
        SD.save_json(SD.record_path(designs, SET), {"approved": {"id": v["id"], "by": "owner", "words": "yes"}, "history": []})
        codeh, typed = call(["lock", "Katana2GyakuKesa", *at])
        os.remove(SD.record_path(designs, SET))
        code1, yes = call(["approve", SET, "yes, that string", "--by", "owner", "--id", v["id"], "--page", png, *at])
        code2, free = call(["lock", "Katana2GyakuKesa", *at])
        design["attacks"][1]["body"] = "spin"                 # the design changed after his yes
        SD.save_json(SD.design_path(designs, SET), design)
        code3, stale = call(["lock", "Katana2GyakuKesa", *at])
        if code0 == 0:
            wrong.append("a move of the set was free before the design had his yes")
        if codeh == 0:
            wrong.append("a record typed by hand, with no page he saw, freed a move of the set")
        if code1 != 0 or code2 != 0:
            wrong.append(f"his yes to the design did not free its move ({yes['summary']} / {free['summary']})")
        if code3 == 0 or "was to design" not in stale["summary"]:
            wrong.append(f"a design changed after his yes still freed its move ({stale['summary']})")
        if wrong:
            return out("fail", "design selftest: " + "; ".join(wrong), "kit/anim/set_design.py")
        return out("pass", "design selftest: the loved katana string is whole, no two of its attacks cousins, its keys are its "
                           "design; its move was held until the owner's yes to the page of the design (a record typed by "
                           "hand freed nothing), free after it, held again once the design changed", "none - proceed")
    finally:
        shutil.rmtree(run, ignore_errors=True)


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("good", "cousins", "undesigned", "broken"):
        print(__doc__)
        sys.exit(2)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1]))
