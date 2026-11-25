"""cad_check.py — every code-CAD part of an asset in SECONDS, without a build (kit cad check).

    python kit/tools/cad_check.py <asset> [--only Part,Part] [--jobs 6] [--no-fillet] [--look] [--zoom cx,cy,cz,size]

A build is minutes (Blender, bakes, renders, checks); a CAD part is seconds. Debugging a part's CAD inside full builds
cost the Silverballer most of its 3 hours. This runs the asset's build script WITHOUT Blender — a stand-in `rbx`
records each a.cad(...) call and does nothing else — then runs every recorded part through cad_run.py in the cad env,
in parallel, and says per part: solid or not, volume, faces, open edges, fillets it had to reduce, or the CAD error
with its line (a crash too: run with -X faulthandler). Fix the CAD here; build only when every part is green.
Only a.cad parts are checked (boxes, cylinders, tubes, imports are Blender's and cannot fail this way).
A part's fillet_mm= is run here exactly as the build runs it (cad_run --fillet, the crash-safe fillet search): this
check once skipped it and passed the single-action revolver's frame, which build 5's 0.8 mm fillet then broke (not a
valid solid, 2026-11-11). A fillet search can take minutes; --no-fillet checks the shape only, in seconds, and its
verdict says which parts' fillets it did not check.
--look: and DRAW each checked part (Blender, ~5 s a part): four sides in build/cad/<asset>_<Part>.png — see a fin, a
step or a fillet that did not take without a build (--zoom: a box, centre and size in the part's mm).
One JSON verdict line; the per-part lines above it.
"""

import concurrent.futures as cf
import contextlib
import io
import json
import os
import re
import runpy
import subprocess
import sys
import tempfile
import time
import types

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
_KIT = os.path.join(REPO, "kit")
if _KIT not in sys.path:
    sys.path.insert(0, _KIT)
from blender_path import find_blender  # noqa: E402


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def _arg(argv, flag, default=None):
    return argv[argv.index(flag) + 1] if flag in argv and argv.index(flag) + 1 < len(argv) else default


def cad_python():
    env = os.environ.get("CAD")
    if env:
        return env
    home = os.path.expanduser("~")
    for c in (os.path.join(home, ".cache", "roblox-kit", "envs", "cad", "Scripts", "python.exe"),
              os.path.join(home, ".cache", "roblox-kit", "envs", "cad", "bin", "python")):
        if os.path.isfile(c):
            return c
    return None


class _Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def row_ok(said):
    """a part is green when its code ran, left a closed solid that OpenCASCADE calls valid (the build's cad_solid gate
    fails "not valid": revolver build 5's frame came back status pass, 1 solid, 0 open edges and valid false), and its
    mesh holds that solid's own volume (cad_run's volume_untrue: a solid that disagrees with itself tears open on the
    build's import, however closed it looks here)"""
    return (said.get("status") == "pass" and said.get("solids", 1) >= 1 and said.get("open_edges", 0) == 0
            and said.get("valid", True) is not False and not said.get("volume_untrue"))


def record(script):
    """run a build script with a stand-in rbx -> [(name, code path or text, params, tol, angle, fillet_mm or None)]"""
    calls = []

    class Asset:
        def __init__(self, *a, **k):
            self.name = a[0] if a else k.get("name", "asset")

        # (rbx.Asset.cad's own signature, so a script's positional arguments land where the build puts them)
        def cad(self, name, code, mat=None, pos=None, rot=None, group="main", params=None, tol=0.05, angle=12.0,
                round_mm=None, edge_roles=None, fillet_mm=None, low=None, **_k):
            calls.append((name, code, dict(params or {}), tol, angle, float(fillet_mm) if fillet_mm else None))

        def seat(self, part, pos, *_a, **_k):
            # (a.seat measures a surface in Blender; here only its shape matters: (centre, thickness))
            return tuple(pos), 0.001

        def maker(self, name, folder=None):
            # (the maker's language is pure data: the real parser, so lang["radius_mm"] reads as in the build)
            sys.path.insert(0, os.path.join(REPO, "kit", "tools"))
            import design  # noqa: PLC0415

            path = os.path.join(folder or os.path.join(design.models_root(), "makers"), f"{name}.md")
            mk = design.check_maker(path)[2]
            return {k: v for k, v in mk.items() if k != "sections"}

        def scatter_relief(self, *_a, **_k):
            # (rays in Blender; here a part-like record its callers may read)
            return {"kit_relief_features": 0}

        def __getattr__(self, attr):
            if attr in ("mirror", "floaters", "internal", "group"):
                return lambda *a, **k: _Ctx()
            return lambda *a, **k: None

    stub = types.ModuleType("rbx")
    stub.Asset = Asset
    stub.REPO = REPO
    stub.BUILD = os.path.join(REPO, os.environ.get("KIT_BUILD", "build"))
    stub.__getattr__ = lambda attr: (lambda *a, **k: {})  # rbx.finish(...), rbx.real(...): material dicts
    sys.path.insert(0, os.path.join(REPO, "kit", "blender"))
    import rbx_profile  # noqa: PLC0415  (pure Python: the real outline operations, as rbx.profile)

    stub.profile = rbx_profile
    saved = sys.modules.get("rbx")
    sys.modules["rbx"] = stub
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            runpy.run_path(script, run_name="kit_cad_check")
    finally:
        if saved is not None:
            sys.modules["rbx"] = saved
        else:
            sys.modules.pop("rbx", None)
    return calls


def run_one(py, call, out_dir, fillet=True):
    """one recorded part through cad_run.py, as a.cad runs it (its fillet_mm too, unless fillet=False: --no-fillet)
    -> (name, code path, cad_run's verdict + seconds and, when it was run, fillet_mm)"""
    name, code, params, tol, angle, fillet_mm = call
    fillet_mm = fillet_mm if fillet else None
    path = code if isinstance(code, str) and code.endswith(".py") and os.path.isfile(code) else None
    if path is None:  # inline code: a file of its own, as a.cad writes it
        path = os.path.join(out_dir, f"{name}.py")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(code)
    npz = os.path.join(out_dir, f"{name}.npz")
    t0 = time.time()
    r = subprocess.run([py, "-X", "faulthandler", os.path.join(REPO, "kit", "tools", "cad_run.py"), path, "--out", npz,
                        "--tol", str(float(tol)), "--angle", str(float(angle)), "--params", json.dumps(params)]
                       + (["--fillet", str(float(fillet_mm))] if fillet_mm else []),
                       capture_output=True, text=True, cwd=REPO, timeout=3600 if fillet_mm else 900)
    said = None
    for line in reversed((r.stdout or "").splitlines()):
        if line.startswith("{"):
            try:
                said = json.loads(line)
                break
            except ValueError:
                pass
    if said is None:
        at = re.findall(r'File "[^"]*' + re.escape(os.path.basename(path)) + r'", line (\d+)', r.stderr or "")
        said = {"status": "fail", "summary": f"CRASHED (exit {r.returncode})" + (f" at line {at[0]}" if at else "")
                + " - OpenCASCADE died inside an operation: most often a fillet bigger than a small feature"}
    said["seconds"] = round(time.time() - t0, 1)
    if fillet_mm:
        said["fillet_mm"] = fillet_mm
    return name, os.path.relpath(path, REPO).replace("\\", "/"), said


def blender():
    return find_blender()


def look(asset, rows, out_dir, zoom):
    """draw each ok part from four sides -> {part: sheet path}"""
    from PIL import Image  # noqa: PLC0415

    exe = blender()
    if not exe:
        return {}
    dest = os.path.join(REPO, os.environ.get("KIT_BUILD", "build"), "cad")
    os.makedirs(dest, exist_ok=True)
    sheets = {}
    for r in rows:
        npz = os.path.join(out_dir, f"{r['part']}.npz")
        if not r["ok"] or not os.path.isfile(npz):
            continue
        tmp = os.path.join(out_dir, f"{r['part']}_look.png")
        cmd = [exe, "-b", "--factory-startup", "--python", os.path.join(REPO, "kit", "tools", "cad_look.py"), "--",
               tmp, npz] + (["--zoom", zoom] if zoom else [])
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        line = [ln for ln in (res.stdout or "").splitlines() if ln.startswith("CAD_LOOK ")]
        if not line:
            tail = [ln for ln in ((res.stdout or "") + (res.stderr or "")).splitlines() if ln.strip()][-4:]
            print(f"  look {r['part']}: FAILED - " + " | ".join(tail)[:400])
            continue
        tiles = [Image.open(f).convert("RGB") for f in line[0][len("CAD_LOOK "):].split("|")]
        w, h = tiles[0].size
        sheet = Image.new("RGB", (2 * w, 2 * h))
        for k, tl in enumerate(tiles):
            sheet.paste(tl, ((k % 2) * w, (k // 2) * h))
        path = os.path.join(dest, f"{asset}_{r['part']}.png")
        sheet.save(path)
        sheets[r["part"]] = os.path.relpath(path, REPO).replace("\\", "/")
    return sheets


def game_root(argv):
    """the game the command is for (--game <Name> > env KIT_GAME > games/.active, as kit/lib/config.luau routes every
    path), relative to the repo; "" = the project root. A SampleRegion piece once came back "no build script" here"""
    game = _arg(argv, "--game") or os.environ.get("KIT_GAME")
    act = os.path.join(REPO, "games", ".active")
    if not game and os.path.isfile(act):
        game = open(act, encoding="utf-8").read().strip()
    if game and game.lower() != "none" and os.path.isdir(os.path.join(REPO, "games", game)):
        return os.path.join("games", game)
    return ""


def main(argv):
    if not argv:
        return emit("fail", "cad check: give the asset", "lune run kit cad check <asset> [--only Part,Part]")
    asset = argv[0]
    root = game_root(argv)
    if root and not os.environ.get("KIT_BUILD"):
        os.environ["KIT_BUILD"] = os.path.join(root, "build")
    rel = os.path.join(root, "assets", "models", f"build_{asset}.py").replace("\\", "/")
    script = os.path.join(REPO, rel)
    if not os.path.isfile(script):
        return emit("fail", f"cad check: no {rel}", "check the asset's name (and --game <Name> for a game's piece)")
    py = cad_python()
    if py is None:
        return emit("fail", "cad check: the cad environment is not installed", "lune run kit tools setup cad")
    t0 = time.time()
    try:
        calls = record(script)
    except Exception as e:  # noqa: BLE001 — the build script's own error, said plainly
        return emit("fail", f"cad check: the build script failed before its parts: {type(e).__name__}: {e}",
                    f"fix {rel} (it runs here without Blender: plain Python before a.build())")
    only = set(filter(None, (_arg(argv, "--only", "") or "").split(",")))
    seen, todo = set(), []
    for c in calls:
        if c[0] not in seen and (not only or c[0] in only):
            seen.add(c[0])
            todo.append(c)
    if not todo:
        return emit("pass", f"cad check: {asset} has no a.cad parts" + (f" named {', '.join(sorted(only))}" if only else ""),
                    "nothing to check")
    out_dir = tempfile.mkdtemp(prefix=f"kit_cad_{asset}_")
    jobs = int(_arg(argv, "--jobs", str(min(8, os.cpu_count() or 4))))
    fillet = "--no-fillet" not in argv
    asked = {c[0]: c[5] for c in todo if c[5]}   # the parts whose a.cad asks a fillet_mm
    rows = []
    with cf.ThreadPoolExecutor(jobs) as ex:
        for name, path, said in ex.map(lambda c: run_one(py, c, out_dir, fillet), todo):
            reduced = said.get("fillets_reduced") or []
            ok = row_ok(said)
            note = ("; fillets reduced: " + ", ".join("->".join(str(v) for v in e) for e in reduced[:4])
                    + (f" (+{len(reduced) - 4})" if len(reduced) > 4 else "")) if reduced else ""
            if name in asked:
                note += (f"; filleted {asked[name]} mm as the build does" if fillet
                         else f"; its {asked[name]} mm fillet NOT checked (--no-fillet)")
            if said.get("status") == "pass" and said.get("valid") is False:
                note += " — NOT A VALID SOLID (OpenCASCADE): the build's cad_solid gate fails it"
                said["summary"] = "not a valid solid (OpenCASCADE)" + (
                    f" after its {asked[name]} mm fillet" if fillet and name in asked else "")
            line = (f"  {'ok  ' if ok else 'FAIL'} {name}: "
                    + (f"{said.get('solids')} solid(s), {said.get('volume_mm3')} mm3, {said.get('faces')} faces, "
                       f"open edges {said.get('open_edges')}{note}"
                       + (f" — {said['volume_untrue']}" if said.get("volume_untrue") else "")
                       if said.get("status") == "pass"
                       else str(said.get("summary", "?")) + note) + f" ({said['seconds']} s)")
            print(line)
            rows.append({"part": name, "code": path, "ok": ok, "summary": said.get("summary"),
                         "fillets_reduced": reduced, "open_edges": said.get("open_edges"),
                         **({"fillet_mm": asked[name], "fillet_checked": fillet} if name in asked else {})})
    bad = [r for r in rows if not r["ok"]]
    sheets = look(asset, rows, out_dir, _arg(argv, "--zoom")) if "--look" in argv else {}
    for r in rows:
        if r["part"] in sheets:
            r["look"] = sheets[r["part"]]
            print(f"  look {r['part']}: {sheets[r['part']]} (right, left / front-left below, rear-right above)")
    secs = round(time.time() - t0, 1)
    if bad:
        return emit("fail", f"cad check: {len(bad)} of {len(rows)} CAD part(s) fail ({secs} s): "
                    + "; ".join(f"{r['part']}: {r['summary']}" for r in bad[:3]),
                    "fix those parts' CAD (the line is named) and run this again - no build until every part is ok",
                    parts=rows)
    soft = [r for r in rows if r["fillets_reduced"]]
    unchecked = [r["part"] for r in rows if r.get("fillet_checked") is False]
    return emit("pass", f"cad check: all {len(rows)} CAD part(s) of {asset} are closed solids ({secs} s)"
                + (f"; {len(soft)} took smaller fillets than asked ({', '.join(r['part'] for r in soft[:4])})" if soft
                   else "")
                + (f"; {len(unchecked)} part(s)' fillets NOT checked (--no-fillet: {', '.join(unchecked[:4])}) - "
                   "the build runs them" if unchecked else ""),
                (f"run it once without --no-fillet before the build (the fillets of {', '.join(unchecked[:4])}), "
                 "then " if unchecked else "")
                + (f"LOOK at {', '.join(sorted(sheets.values())[:3])}, then " if sheets else "")
                + f"lune run kit watch {asset} --geo (every check through a persistent Blender; or once: kit asset "
                f"{asset} --geo), "
                f"the full build only at the stage's end (lune run kit plan {asset})", parts=rows)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
