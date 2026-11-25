"""run.py — the MAP CHECK's selftest cases (kit selftest): rbx.Asset._uv_check / kit/blender/rbx_uvcheck.py, on
parts whose faces are given their places on the map by hand (kit/selftest/blender/check_repair_cases.py, run once
in Blender).

    python kit/selftest/uvcheck/run.py crossed    two faces given one piece of the map: the `uv_overlap` check
                                                  must say so (this case FAILS, naming the share painted twice - a
                                                  check that passed it would be caught)
    python kit/selftest/uvcheck/run.py stacked    a copy the unwrap's own record lays on its original: meant, not said
    python kit/selftest/uvcheck/run.py piled      two faces on the very same place and NO such record (a front
                                                  unwrapped onto its back): said like any other two (FAILS)
    python kit/selftest/uvcheck/run.py built      the REAL build of kit/selftest/blender/build_repair.py: its verdict
                                                  must carry the map check of its group (passes only then - a
                                                  build that no longer checks its map is caught)
    python kit/selftest/uvcheck/run.py long       a face four times as long as the square piece of map it has:
                                                  the `uv_stretch` check must say so (this case FAILS)
    python kit/selftest/uvcheck/run.py apart      two faces each with its own piece of the map: neither is said

Prints one JSON line {schema, status, summary, next_action}. Never "fix" this file.
"""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "tools"))
import cad_check  # noqa: E402

PART = {"crossed": "Crossed", "stacked": "Stacked", "piled": "Piled", "long": "Long", "apart": "Apart"}


def built(blender, env):
    r = subprocess.run([blender, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                        os.path.join(ROOT, "kit", "selftest", "blender", "build_repair.py"), "--", "--no-preview"],
                       cwd=ROOT, capture_output=True, text=True, timeout=1800, env=env, encoding="utf-8",
                       errors="replace")
    line = next((x for x in reversed(r.stdout.splitlines()) if x.startswith("{") and '"status"' in x), None)
    if not line:
        return out("error", "map check: the fixture's build gave no verdict: " + (r.stderr or r.stdout)[-300:],
                   "build kit/selftest/blender/build_repair.py in Blender by hand")
    verdict = json.loads(line)
    facts = ((verdict.get("facts") or {}).get("uv_check") or {}).get("main")
    named = {c.get("name") for c in ((verdict.get("groups") or {}).get("main") or {}).get("checks") or []}
    if not facts or not {"uv_overlap", "uv_stretch"} <= named:
        return out("fail", "map check: the build never checked its map (no uv_check in its facts, or no "
                           "uv_overlap / uv_stretch among its group's checks)",
                   "rbx.Asset.build no longer calls _uv_check after the bake")
    return out("pass", f"map check: the build checked its map - {facts['overlap'] * 100:.2f}% painted twice, "
                       f"{facts['stretched'] * 100:.1f}% stretched", "nothing to do")


def out(status, summary, next_action):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action}))
    return 0 if status == "pass" else 1


def main(case):
    if case not in PART and case != "built":
        return out("error", f"map check selftest: unknown case {case!r}", " | ".join([*PART, "built"]))
    blender = cad_check.blender()
    if not blender or not os.path.isfile(blender):
        return out("skip", "map check: Blender was not found", "install Blender or set BLENDER")
    env = dict(os.environ, KIT_GAME="none",
               KIT_BUILD=os.environ.get("KIT_BUILD") or os.path.join("build", "selftest", "uvcheck"))
    if case == "built":
        return built(blender, env)
    r = subprocess.run([blender, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                        os.path.join(ROOT, "kit", "selftest", "blender", "check_repair_cases.py"), "--",
                        "--no-preview"], cwd=ROOT, capture_output=True, text=True, timeout=900, env=env,
                       encoding="utf-8", errors="replace")
    line = next((x for x in r.stdout.splitlines() if x.startswith("REPAIR_CASES ")), None)
    if r.returncode != 0 or not line:
        return out("error", "map check: the probe did not answer: " + (r.stderr or r.stdout)[-300:],
                   "run kit/selftest/blender/check_repair_cases.py in Blender by hand")
    got = json.loads(line.split(" ", 1)[1])["uv"][PART[case]]
    facts, checks = got["facts"], got["checks"]
    if not checks["uv_overlap"][0]:
        return out("fail", f"map check: {facts['overlap'] * 100:.1f}% of {PART[case]}'s map is painted twice "
                           f"({facts['overlap_faces']} faces lie on each other)",
                   "give each face its own place on the map")
    if not checks["uv_stretch"][0]:
        return out("fail", f"map check: {facts['stretched'] * 100:.0f}% of {PART[case]}'s surface has texels "
                           f"{facts['stretch_p50']:g}x longer than wide", "more seams, or its own uvs=")
    return out("pass", f"map check: {PART[case]}'s map has nothing painted twice ({facts['stacked']} face(s) laid "
                       "on a copy's place, meant) and no stretched texels", "nothing to do")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else ""))
