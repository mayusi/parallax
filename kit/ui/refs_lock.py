"""refs_lock.py — the UI quality lock: a NEW screen compiles only on real references (the quality locks, 2026-10-21).

    python kit/ui/refs_lock.py --specs assets/ui [--refs assets/ui/refs] <Screen> [<Screen> ...]

The kit (`kit ui`, `kit verify`) calls it for the screens made after the locks (board/locks.json "grandfathered" lists
the older ones). Each screen passes the same refs lock `kit ui plan` shows for hero screens (refsdb.gate: >= 2 real
stills of its kind and screen type at >= 1080p, or the owner's quoted waiver of the 1080p rule), whatever its quality:
a screen built from no picture is the AI-slop route the owner rejected. One JSON line: status, summary, next_action and
screens {name: {ok, detail, todo}}.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import direct  # noqa: E402  (the creative-direction lock)
import plan  # noqa: E402  (infer_kind: the compiler's HUD-or-menu rule)
import refsdb  # noqa: E402


def check(name, specs, refs_root):
    """(ok, detail, todo) for one screen spec."""
    path = os.path.join(specs, f"{name}.json")
    try:
        with open(path, encoding="utf-8") as fh:
            spec = json.load(fh)
    except (OSError, ValueError) as e:
        return False, f"cannot read {path}: {e}", f"fix {path}"
    ident_name = spec.get("identity")
    ident = None
    if ident_name:
        ipath = os.path.join(specs, "identities", f"{ident_name}.json")
        try:
            with open(ipath, encoding="utf-8") as fh:
                ident = json.load(fh)
        except (OSError, ValueError):
            ident = None
    kind = spec.get("kind") or plan.infer_kind(spec)
    ok, detail, todo = refsdb.gate(ident_name, refs_root, ident, kind, spec.get("screen_type"))
    if not ok:
        return ok, detail, todo
    # and the look itself was CHOSEN (v8, 2026-10-24): an identity made after the director comes from a direction the
    # owner picked on a board (older ones exempt: kit/ui/direct_exempt.json or the project's grandfathered list).
    # Checked after the refs so each lock's own selftest exercises it alone.
    dok, ddetail, dtodo = direct.direction_lock(ident_name, os.path.join(specs, "identities", f"{ident_name}.json"))
    return (ok, detail, todo) if dok else (dok, ddetail, dtodo)


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="+")
    ap.add_argument("--specs", default="assets/ui")
    ap.add_argument("--refs", default=None, help="default: <specs>/refs")
    a = ap.parse_args(argv)
    refs_root = (a.refs or os.path.join(a.specs, "refs")).replace("\\", "/")
    screens = {}
    for name in a.names:
        ok, detail, todo = check(name, a.specs, refs_root)
        screens[name] = {"ok": ok, "detail": detail, "todo": todo}
    bad = [n for n, s in screens.items() if not s["ok"]]
    print(json.dumps({
        "status": "fail" if bad else "pass",
        "summary": f"ui refs lock: {len(screens) - len(bad)}/{len(screens)} new screen(s) built on real references",
        "next_action": screens[bad[0]]["todo"] if bad else "",
        "screens": screens,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
