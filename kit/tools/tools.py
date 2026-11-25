"""tools.py — the kit's pinned tools: install them, and say which are ready (kit python; `lune run kit tools ...`).

    python kit/tools/tools.py doctor [--deep]
    python kit/tools/tools.py setup [kit-python|mitsuba|cad ...] [--check]

Every tool was vetted and approved by the owner (VETLOG.md). Its wheels are pinned with their sha256 in
kit/tools/pins/<env>.txt; setup runs pip with --no-deps --require-hashes --only-binary=:all:, so only the pinned files
are fetched, only wheels (no build script runs), each checked against its hash — a dependency that is not pinned is
never fetched. kit-python is the kit's own python (this one: the vision stack's torch is here); mitsuba and cad each
get their own environment, ~/.cache/roblox-kit/envs/<name> (Python 3.11), made by setup when missing.
doctor: each tool ready / missing, with the command that fixes it. --deep also runs each one on a tiny test (mitsuba:
a forward AND a backward render on the GPU, skipped while the GPU is busy; cad: a filleted box with a chamfered hole,
exported to STL and GLB, its volume checked by hand).
"""

import importlib
import importlib.metadata
import json
import os
import re
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
VISION = os.path.join(ROOT, "kit", "vision")
GPU_BUSY_MIB = 3000  # the GPU is shared: a deep GPU test waits for a quieter moment above this much in use

ENVS = ("kit-python", "mitsuba", "cad")
# environments that also see the kit python's own packages (numpy, scipy, ipython, ...): only their extra wheels are pinned
SYSTEM_SITE = ("cad",)
TOOLS = [
    {"name": "vectorize", "env": "kit-python", "packages": ["vtracer"], "modules": ["vtracer"], "licence": "MIT",
     "use": "lune run kit vision vectorize <image>"},
    {"name": "upscale", "env": "kit-python", "packages": ["spandrel"], "modules": ["torch", "spandrel"],
     "weights": ["realesrgan-x4plus", "realesr-general-x4v3"], "licence": "BSD-3-Clause weights, MIT spandrel",
     "use": "lune run kit vision upscale <image> [--x 2|4]"},
    {"name": "mitsuba", "env": "mitsuba", "packages": ["mitsuba", "drjit"], "modules": ["mitsuba"],
     "variant": "cuda_ad_rgb", "probe": "probe_mitsuba.py", "gpu": True, "licence": "BSD-3-Clause",
     "use": "Run.tool(\"mitsuba\"): kit/tools/probe_mitsuba.py"},
    {"name": "cad", "env": "cad", "packages": ["build123d", "cadquery-ocp-novtk"], "modules": ["OCP", "build123d"],
     "probe": "probe_cad.py", "licence": "Apache-2.0", "use": "Run.tool(\"cad\"): kit/tools/probe_cad.py"},
]


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def canon(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def pins(env):
    """kit/tools/pins/<env>.txt -> {canonical name: version} (comments and blank lines skipped)"""
    out = {}
    with open(os.path.join(HERE, "pins", f"{env}.txt"), encoding="utf-8") as fh:
        for line in fh:
            m = re.match(r"^\s*([A-Za-z0-9_.\-]+)==([^\s;]+)\s+--hash=sha256:[0-9a-f]{64}\s*$", line)
            if m:
                out[canon(m.group(1))] = m.group(2)
            elif line.strip() and not line.lstrip().startswith("#"):
                raise ValueError(f"pins/{env}.txt: not 'name==version --hash=sha256:<64 hex>': {line.strip()}")
    return out


def env_python(env):
    """the python of an environment: the kit's own for kit-python; else <ENV> (an override, as Run.tool reads it),
    else ~/.cache/roblox-kit/envs/<env>"""
    if env == "kit-python":
        return sys.executable
    override = os.environ.get(env.upper())
    if override:
        return override
    base = os.path.join(os.path.expanduser("~"), ".cache", "roblox-kit", "envs", env)
    for p in (os.path.join(base, "Scripts", "python.exe"), os.path.join(base, "bin", "python")):
        if os.path.isfile(p):
            return p
    return None


def versions_and_imports(names, modules, variant=None):
    """in THIS python: {name: version or None, "__import__": None or the first import error}"""
    out = {}
    for n in names:
        try:
            out[n] = importlib.metadata.version(n)
        except importlib.metadata.PackageNotFoundError:
            out[n] = None
    try:
        for mod in modules:
            m = importlib.import_module(mod)
            if variant and variant not in m.variants():
                raise RuntimeError(f"no {variant} variant (has: {', '.join(m.variants())})")
        out["__import__"] = None
    except Exception as e:  # noqa: BLE001 — reported, never hidden
        out["__import__"] = f"{type(e).__name__}: {e}"
    return out


def installed(env, names, modules, variant=None):
    """versions_and_imports in the env's python (None: no environment)"""
    py = env_python(env)
    if py is None:
        return None
    if env == "kit-python":
        sys.path.insert(0, VISION)
        import upscale  # noqa: PLC0415

        upscale._einops_placeholder()  # (spandrel's package imports einops; upscale.py says why a stand-in is fine)
        return versions_and_imports(names, modules, variant)
    args = [py, os.path.abspath(__file__), "_probe", ",".join(names), ",".join(modules), variant or ""]
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=180)
        return json.loads(r.stdout.strip().splitlines()[-1])
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired) as e:
        return {"__import__": f"the environment's python did not answer ({type(e).__name__})"}


def weights_ok(names):
    """-> problems with the pinned weight files (kit/vision/models.json)"""
    if not names:
        return []
    sys.path.insert(0, VISION)
    import setup as vision_setup  # noqa: PLC0415

    with open(vision_setup.MANIFEST, encoding="utf-8") as fh:
        man = json.load(fh)["models"]
    bad = []
    for name in names:
        for f in man[name]["files"]:
            p = os.path.join(vision_setup.cache_dir(), name, f["path"])
            if not os.path.isfile(p):
                bad.append(f"{name}/{f['path']} missing")
            elif not vision_setup.file_ok(p, f):
                bad.append(f"{name}/{f['path']} does NOT match its pin")
    return bad


def gpu():
    """(MiB used, MiB total, driver) or None"""
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total,driver_version",
                            "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=30)
        used, total, driver = [v.strip() for v in r.stdout.strip().splitlines()[0].split(",")]
        return int(used), int(total), driver
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return None


def verdict(cmd, timeout=300):
    """a script's JSON verdict line; a hang is cut off at `timeout` s and says what it printed last"""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=ROOT)
    except subprocess.TimeoutExpired as e:
        said = e.stdout.decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        last = said.strip().splitlines()[-1] if said.strip() else "nothing"
        return {"status": "fail", "summary": f"HUNG: no answer in {timeout} s (last line: {last})"}
    lines = [ln for ln in r.stdout.splitlines() if ln.startswith("{")]
    if lines:
        return json.loads(lines[-1])
    return {"status": "fail", "summary": "crashed: " + ((r.stderr or "").strip().splitlines() or ["?"])[-1]}


def deep_test(tool):
    """each tool on a tiny job, in a temporary folder (upscale: the fast model, on the CPU)"""
    if tool["env"] != "kit-python":
        return verdict([env_python(tool["env"]), os.path.join(HERE, tool["probe"])])
    from PIL import Image, ImageDraw  # noqa: PLC0415

    with tempfile.TemporaryDirectory(prefix="kit-tools-") as tmp:
        pic = os.path.join(tmp, "probe.png")
        img = Image.new("RGBA", (48, 48), (255, 255, 255, 0))
        ImageDraw.Draw(img).line((6, 40, 42, 8), fill=(20, 20, 20, 255), width=3)
        img.save(pic)
        if tool["name"] == "vectorize":
            return verdict([sys.executable, os.path.join(VISION, "vectorize.py"), pic,
                            "-o", os.path.join(tmp, "o.svg")])
        return verdict([sys.executable, os.path.join(VISION, "upscale.py"), pic,
                        "-o", os.path.join(tmp, "o.png"), "--fast", "--cpu"])


def check(tool, deep):
    """-> {name, env, status: ready|missing|failed, detail, fix, licence, use}"""
    env = tool["env"]
    row = {"name": tool["name"], "env": env, "licence": tool["licence"], "use": tool["use"]}
    fix_env = f"lune run kit tools setup {env}"
    try:
        pinned = pins(env)
    except (OSError, ValueError) as e:
        return {**row, "status": "failed", "detail": str(e), "fix": "restore kit/tools/pins/ from git"}
    want = {n: v for n, v in pinned.items() if n in {canon(p) for p in tool["packages"]}}
    have = installed(env, list(want), tool["modules"], tool.get("variant"))
    if have is None:
        return {**row, "status": "missing", "detail": f"no environment ~/.cache/roblox-kit/envs/{env}", "fix": fix_env}
    wrong = [f"{n} {have.get(n) or 'missing'} (pinned {v})" for n, v in want.items() if have.get(n) != v]
    if wrong:
        return {**row, "status": "missing", "detail": "; ".join(wrong), "fix": fix_env}
    if have.get("__import__"):
        detail = f"installed as pinned, but: {have['__import__']}"
        if deep and tool.get("probe") and not tool.get("gpu"):  # (what does work, said too: cad's OCP part)
            detail += f"; deep test: {deep_test(tool).get('summary')}"
        return {**row, "status": "failed", "detail": detail,
                "fix": tool.get("pending") or "a dependency the pins do not hold yet — see kit/gen/README.md "
                                              "(Tools); a new one is vetted and approved by the owner first"}
    bad = weights_ok(tool.get("weights", []))
    if bad:
        return {**row, "status": "missing", "detail": "; ".join(bad),
                "fix": "lune run kit vision setup " + " ".join(tool["weights"])}
    detail = ", ".join(f"{n} {v}" for n, v in want.items())
    if deep:
        if tool.get("gpu"):
            g = gpu()
            if g and g[0] > GPU_BUSY_MIB:
                return {**row, "status": "ready", "fix": "",
                        "detail": f"{detail}; deep test SKIPPED: the GPU is busy ({g[0]} MiB in use)"}
            if g:
                detail += f"; NVIDIA driver {g[2]}"
        t0 = time.time()
        r = deep_test(tool)
        if r.get("status") != "pass":
            return {**row, "status": "failed", "detail": f"{detail}; deep test: {r.get('summary')}",
                    "fix": r.get("next_action") or "read the deep test's summary"}
        detail += f"; deep test passed ({time.time() - t0:.1f} s): {r.get('summary')}"
    return {**row, "status": "ready", "detail": detail, "fix": ""}


def doctor(argv):
    deep = "--deep" in argv
    rows = [check(t, deep) for t in TOOLS]
    bad = [r for r in rows if r["status"] != "ready"]
    summary = "tools: " + ", ".join(f"{r['name']} {r['status']}" for r in rows) + (" (deep tests run)" if deep else "")
    if bad:
        return emit("fail", summary, f"{bad[0]['name']}: {bad[0]['fix']}", tools=rows)
    return emit("pass", summary, "none — proceed" if deep else
                "none — proceed (lune run kit tools doctor --deep also runs each one on a tiny test)", tools=rows)


def make_env(env):
    """a Python 3.11 venv at ~/.cache/roblox-kit/envs/<env> (the pinned wheels are cp311)"""
    target = os.path.join(os.path.expanduser("~"), ".cache", "roblox-kit", "envs", env)
    if sys.version_info[:2] == (3, 11):
        cmd = [sys.executable, "-m", "venv", target]
    elif os.name == "nt":
        cmd = ["py", "-3.11", "-m", "venv", target]
    else:
        cmd = ["python3.11", "-m", "venv", target]
    subprocess.run(cmd + (["--system-site-packages"] if env in SYSTEM_SITE else []), check=True, timeout=600)
    return env_python(env)


def see_system_site(env):
    """an environment made before it was in SYSTEM_SITE: turn its pyvenv.cfg's include-system-site-packages on"""
    cfg = os.path.join(os.path.expanduser("~"), ".cache", "roblox-kit", "envs", env, "pyvenv.cfg")
    if env not in SYSTEM_SITE or not os.path.isfile(cfg):
        return
    with open(cfg, encoding="utf-8") as fh:
        text = fh.read()
    fixed = re.sub(r"(?m)^include-system-site-packages\s*=\s*false\s*$", "include-system-site-packages = true", text)
    if fixed != text:
        with open(cfg, "w", encoding="utf-8") as fh:
            fh.write(fixed)


def setup(argv):
    check_only = "--check" in argv
    wanted = [a for a in argv if not a.startswith("--")] or list(ENVS)
    unknown = [w for w in wanted if w not in ENVS]
    if unknown:
        return emit("fail", f"tools setup: unknown environment(s) {', '.join(unknown)}",
                    f"use one of: {', '.join(ENVS)} (or none for all)")
    done, bad = [], []
    for env in wanted:
        want = pins(env)
        py = env_python(env)
        if py is None and not check_only:
            try:
                py = make_env(env)
            except (OSError, subprocess.SubprocessError) as e:
                bad.append(f"{env}: could not make its environment ({e}) — it needs Python 3.11 (py -3.11)")
                continue
        if py is None:
            bad.append(f"{env}: no environment")
            continue
        if not check_only:
            see_system_site(env)
            r = subprocess.run([py, "-m", "pip", "install", "--no-deps", "--require-hashes", "--only-binary=:all:",
                                "--disable-pip-version-check", "-r", os.path.join(HERE, "pins", f"{env}.txt")],
                               capture_output=True, text=True, timeout=3600)
            if r.returncode != 0:
                bad.append(f"{env}: pip failed — " + ((r.stderr or "").strip().splitlines() or ["?"])[-1])
                continue
        have = installed(env, list(want), []) or {}
        wrong = [f"{env}: {n} {have.get(n) or 'missing'} (pinned {v})" for n, v in want.items() if have.get(n) != v]
        if wrong:
            bad.extend(wrong)
        else:
            done.append(f"{env} ({len(want)} pinned)")
    title = "tools setup --check" if check_only else "tools setup"
    if bad:
        return emit("fail", f"{title}: {', '.join(done) or 'nothing'} as pinned; {len(bad)} problem(s): {bad[0]}",
                    "lune run kit tools setup " + " ".join(wanted) if check_only else f"fix: {bad[0]}",
                    done=done, bad=bad)
    return emit("pass", f"{title}: {', '.join(done)} as pinned", "lune run kit tools doctor", done=done, bad=bad)


def main(argv):
    if argv and argv[0] == "_probe":  # (run by installed() inside another environment's python)
        names, modules = [n for n in argv[1].split(",") if n], [m for m in argv[2].split(",") if m]
        print(json.dumps(versions_and_imports(names, modules, argv[3] if len(argv) > 3 and argv[3] else None)))
        return 0
    if not argv or argv[0] not in ("doctor", "setup"):
        return emit("fail", "tools: needs doctor [--deep] | setup [kit-python|mitsuba|cad] [--check]",
                    "lune run kit tools doctor")
    return doctor(argv[1:]) if argv[0] == "doctor" else setup(argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
