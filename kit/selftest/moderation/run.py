"""run.py - the moderation gate's self-test runner (`kit selftest`): draws the fixtures (draw_blood.py) into a temp
folder and screens one with kit/tools/mod_gate.py, printing a content verdict.
  pool / splat  - must be HELD (status fail: "held: ... blood-red")
  ember         - must PASS (a fire puff's colours are not blood)
Usage: python -I kit/selftest/moderation/run.py <pool|splat|ember>. Never "fix" this file to make a gate pass."""

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))


def main(case):
    tmp = tempfile.mkdtemp(prefix="kit_modgate_")
    subprocess.run([sys.executable, "-I", os.path.join(HERE, "draw_blood.py"), tmp], check=True, capture_output=True)
    png = os.path.join(tmp, f"{case}.png")
    out = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "kit", "tools", "mod_gate.py"), png],
                         capture_output=True, text=True)
    lines = [ln for ln in out.stdout.splitlines() if ln.startswith("{")]
    if not lines:
        print(json.dumps({"status": "fail", "summary": f"the image check gave no verdict: {out.stderr[-300:]}"}))
        return 1
    r = json.loads(lines[-1])["images"][0]
    if r["flagged"]:
        print(json.dumps({"status": "fail", "summary": f"held: {case}.png - {r['why']}", "crimson": r["crimson"]}))
        return 1
    print(json.dumps({"status": "pass", "summary": f"clean: {case}.png blood-red {r['crimson']:.0%}",
                      "crimson": r["crimson"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "pool"))
