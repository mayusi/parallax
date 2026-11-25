"""run.py — the METHODS LOCK's selftest cases (kit selftest): the owner, 2026-11-13 - "every method i mentioned ...
implmented into each pipeline and enforced in the terms of being used". A new piece's parts plan names the builder
call each coded part is made with (kit/blender/rbx_plan.py method_problems, asked by kit/tools/plan.py's brief
stage), and its build is held to that plan (rbx.Asset's `methods` check).

    python kit/selftest/methods/run.py typed     a NEW piece whose plan types twelve teeth as a box each, makes a
                                                 horn from a box and says only "code" for its grip: kit plan must
                                                 hold the brief (this case FAILS, naming the three - a plan stage
                                                 that let it through would pass, and be caught)
    python kit/selftest/methods/run.py planned   the same piece with its methods named (a.repeat, a.sweep, the
                                                 box-modelling calls): passes, nothing of it named
    python kit/selftest/methods/run.py old       the SAME bad plan on a piece that existed before the lock: passes
                                                 (the lock holds new pieces only)
    python kit/selftest/methods/run.py build     the REAL build (shape only) of kit/selftest/blender/
                                                 build_lock_typed.py, the lock forced on: its plan names a.repeat
                                                 for five bolts and a fence, the script types them one by one (a
                                                 hair apart, in two materials) beside a token repeat of two - the
                                                 build's own `methods` check must refuse it (this case FAILS,
                                                 naming the count and both typed groups)
    python kit/selftest/methods/run.py built     build_lock_made.py: the same model made by its methods (a.repeat
                                                 in a row, at given places) - its `methods` check passes

Each project is written to a temporary folder: nothing of the repo is read but the kit, nothing is written to it.
Prints one JSON line {schema, status, summary, next_action}. Never "fix" this file.
"""

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
sys.path.insert(0, os.path.join(ROOT, "kit", "tools"))
import cad_check  # noqa: E402
import plan as PL  # noqa: E402

BRIEF = """# cog — the brief
- what: a cog wheel with a hook (a fixture)
- end goal: master
- quality: standard
- style: realistic PBR
- view: third person
- function: none
- references: refs/cog_side.png
- ownership: the kit's own
- parts plan:
  1. Hub | code: a.cad from the side trace | side picture | steel
"""
TYPED = """  2. Teeth x12 | code: a.box each | top picture | steel
  3. Horn | code: a.box | side picture | bone
  4. Grip | code | side picture | rubber
"""
PLANNED = """  2. Teeth x12 | code: a.box in a.repeat, a ring | top picture | steel
  3. Horn | code: a.sweep of a round section, tapering | side picture | bone
  4. Grip | code: a.box, a.loop + a.inset + a.push, a.round | side picture | rubber
"""
SCRIPT = 'import rbx\na = rbx.Asset("cog")\na.build()\n'


def out(status, summary, next_action):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action}))
    return 0 if status == "pass" else 1


def brief(case):
    os.environ.pop("KIT_METHODS_LOCK", None)
    with tempfile.TemporaryDirectory() as root:
        for d in ("assets/models", "refs", ".verify", "board"):
            os.makedirs(os.path.join(root, d))
        files = {
            "assets/models/cog.brief.md": BRIEF + (PLANNED if case == "planned" else TYPED),
            "assets/models/build_cog.py": SCRIPT,
            "board/locks.json": json.dumps(
                {"grandfathered": {"3d-methods": ["assets/models/build_cog.py"] if case == "old" else []}}),
        }
        for rel, text in files.items():
            with open(os.path.join(root, rel), "w", encoding="utf-8") as fh:
                fh.write(text)
        stage = {st["key"]: st for st in PL.assess(PL.facts("cog", root))}["brief"]
    said = [m for m in stage["missing"] if m.startswith("methods: ")]
    if said:
        return out("fail", "methods lock: kit plan holds the brief - " + said[0][len("methods: "):],
                   "name each coded part's builder call in its parts plan line (reference/06, Which method for which part)")
    if case == "typed":
        return out("pass", "methods lock: a new piece's plan with typed teeth, a boxed horn and a bare 'code' was NOT held",
                   "kit/tools/plan.py's brief stage no longer asks rbx_plan.method_problems")
    asked = "methods: every coded part's line names how it is made" in stage["found"]
    if case == "planned" and not asked:
        return out("fail", "methods lock: the plan stage never asked a new piece's plan (the lock is not on for it)",
                   "kit/blender/rbx_plan.py methods_locked")
    if case == "old" and asked:
        return out("fail", "methods lock: a piece on the grandfathered list was asked as if it were new",
                   "kit/blender/rbx_plan.py methods_locked")
    return out("pass", "methods lock: " + ("every coded part's line says how it is made" if case == "planned"
                                           else "a piece that existed before the lock is not held"), "nothing to do")


def build(case):
    """the REAL build of a fixture (shape only: --geo), the lock forced on: the whole chain - the script, the
    parts as it made them, the brief beside it, the build's own `methods` check in its verdict"""
    blender = cad_check.blender()
    if not blender or not os.path.isfile(blender):
        return out("skip", "methods lock: Blender was not found", "install Blender or set BLENDER")
    script = os.path.join(ROOT, "kit", "selftest", "blender",
                          "build_lock_typed.py" if case == "build" else "build_lock_made.py")
    env = dict(os.environ, KIT_GAME="none", KIT_METHODS_LOCK="1",
               KIT_BUILD=os.environ.get("KIT_BUILD") or os.path.join("build", "selftest", "methods"))
    r = subprocess.run([blender, "-b", "--factory-startup", "--python-exit-code", "2", "-P", script, "--",
                        "--no-preview", "--geo"], cwd=ROOT, capture_output=True, text=True, timeout=900, env=env,
                       encoding="utf-8", errors="replace")
    line = next((x for x in reversed(r.stdout.splitlines()) if x.startswith("{") and '"status"' in x), None)
    if not line:
        return out("error", "methods lock: the fixture's build gave no verdict: " + (r.stderr or r.stdout)[-300:],
                   f"build {os.path.basename(script)} in Blender by hand with KIT_METHODS_LOCK=1")
    verdict = json.loads(line)
    asked = (verdict.get("facts") or {}).get("methods")   # (said by every build the lock holds, passed or not)
    if not asked:
        return out("pass" if case == "build" else "fail",
                   "methods lock: the build never asked its `methods` check (the lock was on: KIT_METHODS_LOCK=1)",
                   "rbx.Asset._plan no longer calls _methods_check")
    if not asked["ok"]:
        check = next((c for c in verdict.get("design") or [] if c.get("name") == "methods"), {})
        return out("fail", "methods lock: the build is refused - " + "; ".join(asked["value"]), check.get("fix", ""))
    if case == "build":
        return out("pass", "methods lock: a fence and five bolts typed one by one against their plan were NOT refused",
                   "rbx.Asset._typed_alike / rbx_plan.methods_check")
    return out("pass", "methods lock: the build made its alike parts by a.repeat, as many as its plan says",
               "nothing to do")


if __name__ == "__main__":
    case = sys.argv[1] if len(sys.argv) > 1 else ""
    if case in ("typed", "planned", "old"):
        sys.exit(brief(case))
    if case in ("build", "built"):
        sys.exit(build(case))
    sys.exit(out("error", f"methods lock selftest: unknown case {case!r}", "typed | planned | old | build | built"))
