"""check_graveyard_rows.py — kit plan's graveyard rules born from the owner's verdicts, each on its REAL bad example
(kit/knowledge/vault/3d/routes.md). Never "fix" this check or its lines.

  G9  - the Gjallarhorn d2's round-3 line (the owner, 2026-11-10: "the most horrible thing I've seen"): a hero's pearl
        panels traced by colour off one lit render and seated as pillows. Spared: a panel redrawn as a designed part,
        gold TRIM traced by colour and wrapped as an inlay (Scarborough Fair, owner 9/10).
  G10 - the revolver's build-4 line (the owner, 2026-11-11: "the trigger, doesn't look like it's set properly"): a hero
        trigger extruded from its outline, 5 mm thick. Spared: the trigger inflated (a.pillow), its sections crowned.

    python kit/selftest/refs/check_graveyard_rows.py --rule G9|G10            -> exit 1 when the rule refuses its bad line
    python kit/selftest/refs/check_graveyard_rows.py --rule G9|G10 --clean    -> exit 1 if it refuses a line it must spare
"""

import json
import os
import sys

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "kit", "tools"))
import plan  # noqa: E402

CASES = {
    "G9": {
        "bad": [{"name": "Pearl panels", "routes": ["code", "sculpt"],
                 "line": "3. Pearl panels | code + sculpt: every pearl area traced by colour (kit refs inlays), inflated as a "
                         "pillow riding on its host | gjallarhorn_d2_pearl inlays | pearl paint"}],
        "clean": [{"name": "Pearl panels", "routes": ["code"],
                   "line": "3. Pearl panels | code: each panel redrawn as lines + arcs between its real corners, a CAD plate "
                           "with its own edges | the reference sheet, blueprint | pearl paint"},
                  {"name": "Gold trim", "routes": ["code"],
                   "line": "4. Gold trim | code: the trim traced by colour (kit refs inlays) and wrapped onto the barrels as an "
                           "inlay | the game's orthographic renders | polished gold"}]},
    "G10": {
        "bad": [{"name": "Trigger and trigger guard", "routes": ["code"],
                 "line": "8. Trigger and trigger guard | code: a.cad trigger outline (trace) 5 mm thick, edges rounded; the "
                         "guard bow swept along the trace's centreline, its section a rounded strip | trace | case-hardened "
                         "trigger, blued guard"}],
        "clean": [{"name": "Trigger", "routes": ["code"],
                   "line": "8. Trigger | code: a.pillow inflated from the photo's trigger, its sections crowned, seated in the "
                           "frame's slot | trace, the photo's trigger rows | case-hardened"}]},
}


def _arg(argv, flag, default=None):
    return argv[argv.index(flag) + 1] if flag in argv and argv.index(flag) + 1 < len(argv) else default


def main(argv):
    rule = _arg(argv, "--rule", "G9")
    case = CASES[rule]
    rows = plan.graveyard(REPO)
    lines = case["clean"] if "--clean" in argv else case["bad"]
    hits = [(n, g["id"]) for n, g, allowed in plan.graveyard_hits(lines, "hero", rows) if not allowed]
    mine = [h for h in hits if h[1] == rule]
    said = ", ".join(f"{n} -> {i}" for n, i in hits) or "no graveyard rule"
    print(json.dumps({"schema": 1, "status": "fail" if mine else "pass",
                      "summary": (f"graveyard {rule} refuses: {said}" if mine else f"graveyard ({rule}): {said}"),
                      "next_action": "none" if not mine else f"the parts plan takes a route {rule} refuses"}))
    return 1 if mine else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
