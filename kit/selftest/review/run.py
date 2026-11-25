"""run.py — the review page's selftest cases (kit selftest), on the fixture pieces of reviewpage.py.

    python kit/selftest/review/run.py approve   a model sheet that waits is approved BY A CLICK: passes only when the
                                                record in the fixture's locks file is the owner's, for the sheet's own
                                                id, the page reads it back as approved, and the project's own
                                                board/locks.json is byte for byte what it was
    python kit/selftest/review/run.py notoken   a write WITHOUT the page's token: must be refused (this case FAILS,
                                                naming the refusal - a page that took it would pass, and be caught)
    python kit/selftest/review/run.py effect    an effect's beat chart and style sheet approved BY A CLICK: passes
                                                only when the chart's approval is in the fixture's own chart for the
                                                plan the page showed, the style record names the PICTURES he saw (the
                                                sheet's id and its "drawn"), the page reads both back as approved, and
                                                the project's own files hold no record of the fixture's effect
    python kit/selftest/review/run.py redrawn   his yes to a style sheet, then the same preset recorded and drawn
                                                AGAIN, then a click for the OLD pictures: must be refused and his
                                                record left as it was (this case FAILS, naming the refusal - a page
                                                that took the click would pass, and be caught)

Prints one JSON line {schema, status, summary, next_action}.
"""

import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import reviewpage as P  # noqa: E402


def out(status, summary, next_action):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action}))
    return 0 if status == "pass" else 1


def sheet(case):
    said = P.fixture()
    real = open(os.path.join("board", "locks.json"), "rb").read() if os.path.isfile(os.path.join("board", "locks.json")) else b""
    page = P.sheetgun()
    try:
        if not page.token:
            return out("fail", "review page: it did not come up (no page, no token)", "lune run kit review sheetgun --models ... by hand")
        first = page.review()["stages"][0]
        if case == "notoken":
            status, answer = page.act({"stage": "sheet", "action": "approve", "words": "must not be recorded"}, token=False)
            wrote = json.load(open(P.LOCKS, encoding="utf-8")).get("stages")
            if status == 403 and not wrote:
                return out("fail", f"review page: a write without the page's token was refused ({answer.get('error')})",
                           "nothing to do: this is the refusal the case is for")
            return out("pass", f"review page: a write without the page's token was TAKEN (status {status}, stages {wrote})",
                       "kit/lib/localpage.luau writeProblem: the token check is gone")
        if first["state"] != "waiting":
            return out("fail", f"review page: the fixture's sheet is {first['state']}, not waiting ({first['says']}; {said[-200:]})",
                       f"python kit/tools/sheet.py sheetgun --root {P.PROJ.replace(os.sep, '/')}")
        status, answer = page.act({"stage": "sheet", "action": "approve", "words": "yes, this is the gun"})
        sheet_id = json.load(open(os.path.join(P.PROJ, "assets", "models", "sheetgun.sheet.json"), encoding="utf-8"))["id"]
        rec = (((json.load(open(P.LOCKS, encoding="utf-8")).get("stages") or {}).get("3d") or {}).get("sheetgun") or {}).get("sheet") or {}
        after = page.review()["stages"][0]
        now = open(os.path.join("board", "locks.json"), "rb").read() if os.path.isfile(os.path.join("board", "locks.json")) else b""
        wrong = []
        if status != 200:
            wrong.append(f"the click was refused: {answer.get('message') or answer.get('error')}")
        if (rec.get("by"), rec.get("id"), rec.get("words")) != ("owner", sheet_id, "yes, this is the gun"):
            wrong.append(f"the record is not the owner's yes for this sheet: {rec}")
        if after["state"] != "approved":
            wrong.append(f"the page reads the sheet back as {after['state']}")
        if now != real:
            wrong.append("the project's own board/locks.json changed")
        if wrong:
            return out("fail", "review page: " + "; ".join(wrong), "kit/cmd/review.luau, kit/lib/review.luau, kit/cmd/approve.luau")
        return out("pass", "review page: a sheet approved by a click is the owner's record for that sheet's id, read back as "
                   "approved; the project's own locks are untouched", "none")
    finally:
        page.stop()
        P.done()


def style_record():
    data = json.load(open(P.VFXLOCKS, encoding="utf-8"))
    return (((data.get("stages") or {}).get("vfx") or {}).get(P.FX) or {}).get("style") or {}


def own_record():
    """what the PROJECT's own files hold of the fixture's effect (there must be nothing)"""
    try:
        data = json.load(open(os.path.join("board", "locks.json"), encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    found = [k for k in ("stages", "approvals", "waivers", "proposals") if P.FX in ((data.get(k) or {}).get("vfx") or {})]
    if os.path.isfile(os.path.join("assets", "effects", "refs_measured", P.FXSET + ".chart.json")):
        found.append("its chart")
    return found


def effect(case):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        return out("fail", "review selftest: ffmpeg / ffprobe not on PATH", "install ffmpeg (vetted) or put it on PATH")
    chart, drawn = P.vfx_fixture()
    page = P.effect()
    fix = "kit/cmd/review.luau, kit/lib/review.luau, kit/cmd/approve.luau, kit/vfx/chart.py, kit/vfx/stylesheet.py"
    try:
        if not page.token:
            return out("fail", "review page: it did not come up for the effect (no page, no token)",
                       f"lune run kit review {P.FX} --lane vfx --effects ... --locks ... by hand")
        first = {s["key"]: s for s in page.review()["stages"]}
        waiting = [k for k in ("chart", "style") if first[k]["state"] != "waiting"]
        if waiting:
            return out("fail", f"review page: the fixture's {' and '.join(waiting)} do(es) not wait for a yes "
                       f"({first[waiting[0]]['says']}; chart: {chart.get('summary')}; sheet: {drawn.get('summary')})", fix)
        seen, looked = first["style"]["seen"], first["style"]["expect"]    # what a click names; what the command is told
        status, answer = page.act({"stage": "style", "action": "approve", "words": "yes, these read"})
        if status != 200:
            return out("fail", f"review page: the click on the style sheet was refused: {answer.get('message') or answer.get('error')}", fix)
        rec = style_record()
        if case == "redrawn":
            P.record(brighter=True)                             # a texture changed; the preset's own file did not
            again = P.draw_sheet()
            now = page.stage("style")
            status, answer = page.act({"stage": "style", "action": "approve", "words": "yes", "seen": seen})
            kept = style_record()
            # (409 with "stale": the refusal for what was looked at - not the 409 of a click still being recorded)
            if (again.get("status") == "pass" and now["state"] == "changed" and status == 409
                    and answer.get("stale") is True and kept == rec):
                return out("fail", "review page: a click for pictures that are no longer there was refused "
                           f"(the sheet reads '{now['state']}', his record still names the pictures he saw)",
                           "nothing to do: this is the refusal the case is for")
            return out("pass", f"review page: a click for the OLD pictures was TAKEN or the sheet does not read changed "
                       f"(redraw {again.get('status')}, state {now['state']}, status {status}, stale {answer.get('stale')}, record {kept})",
                       "kit/lib/lanelocks.luau holds, kit/lib/review.luau stageOf / fresh: the pictures are not compared")
        plan = first["chart"]["expect"]
        status, answer = page.act({"stage": "chart", "action": "approve", "words": "yes, this timing"})
        approved = json.load(open(P.CHART, encoding="utf-8")).get("approved") or {}
        after = {s["key"]: s for s in page.review()["stages"]}
        wrong = []
        if status != 200:
            wrong.append(f"the click on the chart was refused: {answer.get('message') or answer.get('error')}")
        if (approved.get("by"), approved.get("plan"), approved.get("words")) != ("owner", plan, "yes, this timing"):
            wrong.append(f"the fixture's chart does not hold the owner's yes for the plan the page showed: {approved}")
        if (rec.get("by"), f"style:{rec.get('id')}:{rec.get('drawn')}") != ("owner", looked):
            wrong.append(f"the style record does not name the pictures the page showed ({looked}): {rec}")
        for key in ("chart", "style"):
            if after[key]["state"] != "approved":
                wrong.append(f"the page reads the {key} back as {after[key]['state']}")
        if own_record():
            wrong.append(f"the project's own files hold a record of the fixture's effect: {own_record()}")
        if wrong:
            return out("fail", "review page: " + "; ".join(wrong), fix)
        return out("pass", "review page: an effect's chart is approved in the folder the page read, for the plan it showed; its "
                   "style sheet's record names the pictures he saw; both read back approved; the project's own files are untouched",
                   "none")
    finally:
        page.stop()
        P.vfx_done()


def main(argv):
    case = argv[0] if argv else "approve"
    if not P.lune():
        return out("fail", "review selftest: lune not found", "rokit install")
    os.chdir(P.ROOT)
    return effect(case) if case in ("effect", "redrawn") else sheet(case)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
