"""run.py — the timing chart's selftest cases (kit selftest; kit/anim/timing_chart.py, the owner's method lists
2026-11-13: the chart as a command and a page of every sheet), on a cut the owner loved
(kit/selftest/anim/faults/loved/Katana1Kesa.move.json, read only).

    python kit/selftest/anim/timing/run.py good     the loved cut charted against its own move: the chart is drawn and
                                                    its reading counts what the move file says - the frames between
                                                    the keys span the clip, the Hit is on or a frame after the fastest
                                                    frame, the cut is unevenly spaced
    python kit/selftest/anim/timing/run.py wrong    the same clip charted against ANOTHER move's keys (a rejected
                                                    spin, read only): the chart must not be drawn, and say the clip
                                                    was not built from that move file (this case FAILS, naming it)

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
import strike as S  # noqa: E402
import timing_chart as TC  # noqa: E402

LOVED = os.path.join(ROOT, "kit", "selftest", "anim", "faults", "loved", "Katana1Kesa.move.json")
OTHER = os.path.join(ROOT, "kit", "selftest", "anim", "faults", "rejected", "DTDrillSpin4.move.json")


def call(argv):
    said = io.StringIO()
    with contextlib.redirect_stdout(said):
        code = TC.main(argv)
    return code, json.loads(said.getvalue().strip().splitlines()[-1])


def out(status, summary, next_action):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action}))
    return 0 if status == "pass" else 1


def main(case):
    run = os.path.join(os.environ.get("KIT_BUILD", os.path.join(ROOT, "build")), "selftest", f"anim_timing_{os.getpid()}")
    shutil.rmtree(run, ignore_errors=True)
    os.makedirs(run)
    try:
        with open(LOVED, encoding="utf-8") as fh:
            move = json.load(fh)
        clip, _ = S.generate(json.loads(json.dumps(move)))
        cp, png = os.path.join(run, "Kesa.clip.json"), os.path.join(run, "Kesa.timing.png")
        with open(cp, "w", encoding="utf-8") as fh:
            json.dump(clip, fh)
        if case == "wrong":
            code, v = call([cp, "--move", OTHER, "--out", png])
            if code != 0 and os.path.isfile(png):
                return out("pass", "timing selftest: a chart was drawn against a move that is not the clip's own",
                           "kit/anim/timing_chart.py main")
            return out("pass" if code == 0 else "fail", v["summary"], v["next_action"])
        code, v = call([cp, "--move", LOVED, "--out", png])
        if code != 0 or not os.path.isfile(png) or os.path.getsize(png) < 5000:
            return out("fail", f"timing selftest: the loved cut's chart was not drawn ({v['summary']})",
                       "kit/anim/timing_chart.py chart")
        r = v["reading"]
        wrong = []
        if sum(r["key_gaps_fr"]) != r["frames"] - 1 or len(r["key_gaps_fr"]) != len(move["keys"]) - 1:
            wrong.append(f"the frames between the keys ({r['key_gaps_fr']}) do not span the clip's {r['frames']} frames")
        if r["hit_after_peak_fr"] not in (0, 1):
            wrong.append(f"the Hit is {r['hit_after_peak_fr']} frame(s) from the fastest frame")
        if r["striker"] != "tip" or r["widest_over_mean"] <= 1.2:
            wrong.append(f"the cut's spacing reads as even ({r['widest_over_mean']}x, striker {r['striker']})")
        if r["gather_fr"] < 1 or r["quiet_after_fr"] < 1 or r["rise_fr"] + r["fall_fr"] + 1 != r["cut_fr"]:
            wrong.append("the gather / cut / quiet counts do not add up")
        if not v["next_action"].startswith("look at "):
            wrong.append("the chart's next step is not a look")
        if wrong:
            return out("fail", "timing selftest: the loved cut's reading is wrong - " + "; ".join(wrong),
                       "kit/anim/timing_chart.py read")
        return out("pass", f"timing selftest: the loved cut charted against its own move - {TC.words(r)}", "none")
    finally:
        shutil.rmtree(run, ignore_errors=True)


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("good", "wrong"):
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
