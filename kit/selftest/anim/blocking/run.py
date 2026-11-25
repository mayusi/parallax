"""run.py — the blocking stage's selftest cases (kit selftest; kit/anim/blocking.py, the animation studio route's A2),
on a cut the owner loved (kit/selftest/anim/faults/loved/Katana1Kesa.move.json, read only: a changed pose is a COPY of
it in this run's own folder).

    python kit/selftest/anim/blocking/run.py good      the whole round: the six key poses held at the move's timing;
                                                       the owner's note on pose 3 is OPEN while the pose is as he saw
                                                       it (a second make does not lose it), ANSWERED once that pose
                                                       turned 15 degrees; his yes then holds for exactly those poses
    python kit/selftest/anim/blocking/run.py open      a note given and the pose left as it was: asked whether the
                                                       blocking is approved, the kit must say NO and quote the note
                                                       (this case FAILS, naming it)
    python kit/selftest/anim/blocking/run.py stale     his yes, then a key pose turned 15 degrees: the yes must be
                                                       STALE and name the pose and the limb (this case FAILS)
    python kit/selftest/anim/blocking/run.py proposal  a yes nobody said was the owner's is no approval (FAILS)
    python kit/selftest/anim/blocking/run.py kept      the FINISHED clip held to the poses he approved (A4): the clip
                                                       built from the approved keys keeps all six to 0 degrees, and
                                                       a move with no approved blocking is held to nothing
    python kit/selftest/anim/blocking/run.py drift     the finished clip of the move with pose 3's key turned 15
                                                       degrees after his yes: it must be named - the pose, the limb,
                                                       how far (this case FAILS, naming it)
    python kit/selftest/anim/blocking/run.py lock      POSES FIRST, MOTION AFTER (the lock): a move on the frozen
                                                       list of those made before the rule is never asked; the new
                                                       move is free once the owner said yes to its poses as they
                                                       are; a pose turned 15 degrees after that yes holds it again;
                                                       a record typed by hand (no poses, not his) frees nothing
    python kit/selftest/anim/blocking/run.py locked    a move made after the rule whose key poses nobody showed
                                                       the owner: it must not be made (this case FAILS, saying how
                                                       to show him)

Prints one JSON line {schema, status, summary, next_action}; everything is written under build/selftest/ in a folder
of this run's own, removed at the end.
"""
import contextlib
import copy
import io
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import blocking as B  # noqa: E402

LOVED = os.path.join(ROOT, "kit", "selftest", "anim", "faults", "loved", "Katana1Kesa.move.json")
NAME = "SelftestBlocking"


def call(argv):
    said = io.StringIO()
    with contextlib.redirect_stdout(said):
        code = B.main(argv)
    return code, json.loads(said.getvalue().strip().splitlines()[-1])


def out(status, summary, next_action):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action}))
    return 0 if status == "pass" else 1


def main(case):
    run = os.path.join(os.environ.get("KIT_BUILD", os.path.join(ROOT, "build")), "selftest", f"anim_blocking_{os.getpid()}")
    shutil.rmtree(run, ignore_errors=True)
    os.makedirs(run)
    where = ["--out", os.path.join(run, "out"), "--anims", os.path.join(run, "anims")]
    with open(LOVED, encoding="utf-8") as fh:
        move = json.load(fh)
    turned = copy.deepcopy(move)
    turned["keys"][2]["yaw"] = float(turned["keys"][2].get("yaw", 0.0)) + 15.0     # pose 3, in a copy
    paths = {}
    for tag, m in (("as_loved", move), ("pose3_turned", turned)):
        paths[tag] = os.path.join(run, f"{tag}.move.json")
        with open(paths[tag], "w", encoding="utf-8") as fh:
            json.dump(m, fh)

    def make(tag):
        return call(["make", NAME, "--from-move", paths[tag], *where])
    try:
        code, v = make("as_loved")
        if code != 0 or v.get("state") != "waiting" or "6 key pose(s) held" not in v["summary"]:
            return out("fail", f"blocking selftest: the loved cut's blocking was not made as six held poses ({v['summary']})",
                       "kit/anim/blocking.py make")
        if case == "proposal":
            code, v = call(["approve", NAME, "looks right to me", *where])
            return out("pass" if code == 0 else "fail", v["summary"], v["next_action"])
        if case == "open":
            call(["note", NAME, "3", "lower, wider", "--by", "owner", *where])
            make("as_loved")
            code, v = call(["state", NAME, "--need", "approved", *where])
            return out("pass" if code == 0 else "fail", v["summary"], v["next_action"])
        if case == "stale":
            call(["approve", NAME, "yes, those poses", "--by", "owner", "--id", v["id"], *where])
            make("pose3_turned")
            code, v = call(["state", NAME, "--need", "approved", *where])
            return out("pass" if code == 0 else "fail", v["summary"], v["next_action"])
        if case in ("lock", "locked"):
            anims = os.path.join(run, "anims")
            at = ["--anims", anims]
            new = f"{NAME}=move={paths['as_loved']}"
            code, first = call(["lock", new, *at])
            if case == "locked":
                return out("pass" if code == 0 else "fail", first["summary"], first["next_action"])
            # a record typed by hand: an "approval" with no poses that nobody said was his
            os.makedirs(os.path.join(anims, "blocks"), exist_ok=True)
            with open(os.path.join(anims, "blocks", "SelftestTyped.blocking.json"), "w", encoding="utf-8") as fh:
                json.dump({"approved": {"source": "clip", "poses": []}, "notes": [], "history": []}, fh)
            codeh, typed = call(["lock", f"SelftestTyped=move={paths['as_loved']}", *at])
            call(["approve", NAME, "yes, those poses", "--by", "owner", "--id", v["id"], *where])
            codey, yes = call(["lock", new, *at])
            codet, late = call(["lock", f"{NAME}=move={paths['pose3_turned']}", *at])
            # the frozen list of the moves made before the rule: only a move file that is there when it is frozen
            with open(os.path.join(anims, "SelftestOld.move.json"), "w", encoding="utf-8") as fh:
                json.dump(move, fh)
            call(["freeze", *at])
            codeb, old = call(["lock", f"SelftestOld=move={paths['as_loved']}", *at])
            codel, still = call(["lock", f"SelftestLater=move={paths['as_loved']}", *at])
            wrong = []
            if code == 0:
                wrong.append("a move nobody showed him was free to be made")
            if codeh == 0:
                wrong.append(f"a record typed by hand freed a move ({typed['summary']})")
            if codey != 0:
                wrong.append(f"his yes to the poses as they are did not free the move ({yes['summary']})")
            if codet == 0 or "pose 3" not in late["summary"]:
                wrong.append(f"a pose turned 15 degrees after his yes did not hold the move again ({late['summary']})")
            if codeb != 0:
                wrong.append(f"a move made before the rule was held ({old['summary']})")
            if codel == 0:
                wrong.append("a move that is not on the frozen list was free without his yes")
            if wrong:
                return out("fail", "blocking selftest (the lock): " + "; ".join(wrong), "kit/anim/blocking.py lock")
            return out("pass", "blocking selftest (the lock): the new move was held until the owner's yes to its six poses, "
                               "then free; held again once pose 3 turned after that yes; a record typed by hand freed "
                               "nothing; the move on the frozen list was never asked, one added after it was",
                       "none - proceed")
        if case in ("kept", "drift"):
            import strike as S
            clips = {}
            for tag, mv in (("as_loved", move), ("pose3_turned", turned)):
                gen = copy.deepcopy(mv)
                gen.pop("step", None)
                clips[tag] = os.path.join(run, f"{tag}.clip.json")
                with open(clips[tag], "w", encoding="utf-8") as fh:
                    json.dump(S.generate(gen)[0], fh)
            anims = ["--anims", os.path.join(run, "anims")]
            code0, none = call(["kept", NAME, "--clip", clips["as_loved"], *anims])       # before his yes: held to nothing
            call(["approve", NAME, "yes, those poses", "--by", "owner", "--id", v["id"], *where])
            if case == "drift":
                code, v = call(["kept", NAME, "--clip", clips["pose3_turned"], *anims])
                return out("pass" if code == 0 else "fail", v["summary"], v["next_action"])
            code, v = call(["kept", NAME, "--clip", clips["as_loved"], *anims])
            if code0 != 0 or none.get("state") != "none" or code != 0 or v.get("state") != "kept":
                return out("fail", f"blocking selftest: an unchanged clip is not kept, or a move without his yes was held to "
                                   f"something ({none['summary']} / {v['summary']})", "blocking.kept")
            if max(r["deg"] for r in v["rows"]) > 0.05:
                return out("fail", f"blocking selftest: a clip rebuilt from the approved keys is off its poses ({v['summary']})", "blocking.kept")
            return out("pass", f"blocking selftest: {v['summary']}; before his yes: {none['summary']}", "none - proceed")
        # good: the whole round
        code, v = call(["note", NAME, "3", "lower, wider", "--by", "owner", *where])
        if code != 0:
            return out("fail", f"blocking selftest: the note was refused ({v['summary']})", "kit/anim/blocking.py note")
        call(["note", NAME, "5", "the finish is too high", "--by", "owner", *where])
        code, v = make("as_loved")
        if v.get("state") != "notes open":
            return out("fail", f"blocking selftest: a note on an unchanged pose is '{v.get('state')}', not open", "blocking.settle")
        code, v = make("pose3_turned")
        with open(os.path.join(run, "out", "blocking.json"), encoding="utf-8") as fh:
            m = json.load(fh)
        note, carried = m["notes"][0], m["notes"][1]
        if note["state"] != "answered" or "turned" not in note["answered"]["changed"]:
            return out("fail", f"blocking selftest: pose 3 turned 15 degrees and its note is '{note['state']}'", "blocking.settle")
        # pose 5 moved too (the generator carries pose 3's change into it), but nobody touched its key: NOT answered
        if v.get("state") != "notes open" or carried["state"] != "open" or not carried.get("carried"):
            return out("fail", f"blocking selftest: the note on pose 5 is '{carried['state']}' after ONLY pose 3's key changed "
                               "(a pose carried along by another's change answers nothing)", "blocking.settle")
        code, v = call(["approve", NAME, "yes, those poses", "--by", "owner", "--id", m["id"], *where])
        code2, s = call(["state", NAME, "--need", "approved", *where])
        code3, again = make("pose3_turned")
        if code != 0 or code2 != 0 or again.get("state") != "approved":
            return out("fail", f"blocking selftest: the owner's yes did not hold on unchanged poses ({s['summary']})", "blocking.approve")
        return out("pass", "blocking selftest: six poses held; the note on pose 3 open while the pose stood, answered when it "
                           f"turned ({note['answered']['changed']}); the note on pose 5 still open (it only changed with pose 3); "
                           "the owner's yes holds for those poses", "none - proceed")
    finally:
        shutil.rmtree(run, ignore_errors=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "good"))
