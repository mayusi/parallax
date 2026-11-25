"""qwen_edit.py — a picture edited by an instruction, or the same object seen from another camera, on this PC.
Qwen-Image-Edit-2511 (Apache-2.0, Q4_K_M) run by stable-diffusion.cpp (MIT); owner-approved 2026-10-06 (VETLOG.md).
`lune run kit vision angle|edit ...` routes here (system python: stdlib + Pillow; psutil for the memory numbers).

    angle <picture> --azimuth <deg> --elevation <deg> [--distance near|mid|far] [-o out.png]
          the same object from another camera (Multiple-Angles LoRA: 8 azimuths x 4 elevations x 3 distances —
          the request snaps to the nearest of its 96 poses). Azimuth 0 = the object's front, 90 = its right side,
          180 = its back, 270 = its left side; elevation -30 (below) / 0 (eye level) / 30 / 60 (looking down).
    edit <picture> --prompt "<instruction>" [-o out.png]
          e.g. "remove reflections, flat even studio light, white background"
    both: [--fast] (Lightning LoRA: 4 steps, no guidance) [--seed 1] [--steps N] [--cfg 2.5] [--res 1024]
          [--strength 0.9] (the angle LoRA's weight) [--wait <minutes>] (wait for free memory / another run)

LOW TRUST, always: the output is a GENERATED picture, not a photo and not a measurement. Use it to understand a
shape you cannot see (the back of an ornament, a clean side view of what a 3/4 render shows); never trace,
measure or colour-match from it — the kit's measuring tools read real pictures and real models only.

Offline: sd-cli reads local files only (no network flags are passed). Memory: segmented execution
(`--offload-to-cpu --max-vram -1`: the weights wait in RAM, ~1 GiB of the GPU is left free for others), ~20 GB of
RAM. One run at a time on this PC (a lock file beside sd-cli). Every file is checked against its pin in
kit/vision/models.json (size) before use; `lune run kit vision setup qwen-image-edit sd-cpp` fetches + hashes them.
"""

import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "vision"))
import setup as S  # noqa: E402  (the manifest + cache folders: one place for every pinned file)

BUILD = os.path.join(ROOT, os.environ.get("KIT_BUILD", "build"))
MODEL, TOOL = "qwen-image-edit", "sd-cpp"
NEED_RAM_GB = 22.0  # measured: see kit/gen/README.md (the weights wait in RAM during segmented execution)
NEED_VRAM_FREE_MIB = 9000  # = at most ~3 GB used by others on a 12 GB card
AZIMUTHS = {0: "front view", 45: "front-right quarter view", 90: "right side view", 135: "back-right quarter view",
            180: "back view", 225: "back-left quarter view", 270: "left side view", 315: "front-left quarter view"}
ELEVATIONS = {-30: "low-angle shot", 0: "eye-level shot", 30: "elevated shot", 60: "high-angle shot"}
DISTANCES = {"near": "close-up", "mid": "medium shot", "far": "wide shot"}
LOW_TRUST = ("LOW TRUST: a generated picture, not a measurement — use it to see a shape, never to trace, measure "
             "or colour-match")


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def _opt(argv, flag, default):
    return type(default)(argv[argv.index(flag) + 1]) if flag in argv and argv.index(flag) + 1 < len(argv) else default


def files():
    """the pinned files, each present at its pinned size (else FileNotFoundError naming the fix)"""
    with open(S.MANIFEST, encoding="utf-8") as fh:
        man = json.load(fh)["models"]
    out = {}
    for name in (MODEL, TOOL):
        m = man[name]
        folder = S.entry_dir(name, m)
        for f in m["files"]:
            p = os.path.join(folder, f["path"])
            if not os.path.isfile(p) or os.path.getsize(p) != f["size"]:
                raise FileNotFoundError(f"{name}/{f['path']} missing or not its pinned size — run: lune run kit vision "
                                        f"setup {MODEL} {TOOL}   (23.6 GB + 0.9 GB, every file hashed)")
            out[f["path"]] = p
        out[name] = folder
    exe = os.path.join(out[TOOL], "sd-cli.exe" if os.name == "nt" else "sd-cli")
    if not os.path.isfile(exe):
        raise FileNotFoundError(f"{exe} missing (the zip was not unpacked) — run: lune run kit vision setup {TOOL}")
    out["exe"] = exe
    return out


def pose(azimuth, elevation, distance):
    """the nearest of the LoRA's 96 poses: (prompt words, snapped azimuth, snapped elevation)"""
    az = int(round((azimuth % 360) / 45.0) * 45) % 360
    el = min(ELEVATIONS, key=lambda e: abs(e - elevation))
    return f"{AZIMUTHS[az]} {ELEVATIONS[el]} {DISTANCES[distance]}", az, el


def out_size(w, h, res):
    """the input's aspect at about res x res pixels, both sides multiples of 16 (the model's patch)"""
    s = math.sqrt(res * res / float(w * h))
    return max(256, int(round(w * s / 16)) * 16), max(256, int(round(h * s / 16)) * 16)


def free_memory():
    """(free RAM in GB, free VRAM in MiB or None)"""
    ram = None
    try:
        import psutil  # noqa: PLC0415

        ram = psutil.virtual_memory().available / 1e9
    except ImportError:
        pass
    vram = None
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=20)
        vram = int(r.stdout.strip().splitlines()[0])
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        pass
    return ram, vram


def _pid_alive(pid):
    try:
        import psutil  # noqa: PLC0415

        return psutil.pid_exists(pid)
    except ImportError:
        return True  # (cannot tell: treat the lock as held; it is removed when its run ends)


def acquire(lock, wait_s):
    """one run at a time on this PC; waits up to wait_s for free memory and the lock. Returns None or the reason."""
    t_end = time.time() + wait_s
    while True:
        reason = None
        if os.path.isfile(lock):
            try:
                pid = int(open(lock, encoding="utf-8").read().strip() or 0)
            except (OSError, ValueError):
                pid = 0
            if pid and _pid_alive(pid):
                reason = f"another kit vision angle/edit run is busy (pid {pid})"
            else:
                os.remove(lock)  # (a stale lock: its run is gone)
                continue
        if reason is None:
            ram, vram = free_memory()
            if ram is not None and ram < NEED_RAM_GB:
                reason = f"{ram:.1f} GB of RAM free (needs {NEED_RAM_GB:.0f})"
            elif vram is not None and vram < NEED_VRAM_FREE_MIB:
                reason = f"{vram} MiB of GPU memory free (needs {NEED_VRAM_FREE_MIB})"
        if reason is None:
            try:
                fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                continue
            with os.fdopen(fd, "w") as fh:
                fh.write(str(os.getpid()))
            return None
        if time.time() >= t_end:
            return reason
        print(f"waiting: {reason}", flush=True)
        time.sleep(60)


class Peak(threading.Thread):
    """samples the run's RAM (process tree) and the GPU's used memory until stopped"""

    def __init__(self, pid):
        super().__init__(daemon=True)
        self.pid, self.ram, self.vram, self.vram0, self.stop = pid, 0, 0, None, threading.Event()

    def _gpu_used(self):
        try:
            r = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                               capture_output=True, text=True, timeout=20)
            return int(r.stdout.strip().splitlines()[0])
        except (OSError, ValueError, IndexError, subprocess.SubprocessError):
            return None

    def run(self):
        try:
            import psutil  # noqa: PLC0415

            proc = psutil.Process(self.pid)
        except Exception:  # noqa: BLE001 — memory numbers are a report, never a failure
            proc = None
        self.vram0 = self._gpu_used()
        while not self.stop.is_set():
            if proc is not None:
                try:
                    rss = proc.memory_info().rss + sum(c.memory_info().rss for c in proc.children(recursive=True))
                    self.ram = max(self.ram, rss)
                except Exception:  # noqa: BLE001
                    pass
            g = self._gpu_used()
            if g is not None:
                self.vram = max(self.vram, g)
            self.stop.wait(1.0)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def generate(kind, src, prompt, argv, extra_record):
    from PIL import Image  # noqa: PLC0415

    try:
        f = files()
    except FileNotFoundError as e:
        return emit("fail", f"vision {kind}: {e}", str(e).split(" — ")[-1])
    fast = "--fast" in argv
    steps = _opt(argv, "--steps", 4 if fast else 20)
    cfg = _opt(argv, "--cfg", 1.0 if fast else 2.5)
    seed = _opt(argv, "--seed", 1)
    res = _opt(argv, "--res", 1024)
    im = Image.open(src)
    if im.mode in ("RGBA", "LA", "P"):  # a cut-out: its transparent background becomes plain white
        rgba = im.convert("RGBA")
        flat = Image.new("RGB", rgba.size, (255, 255, 255))
        flat.paste(rgba, mask=rgba.getchannel("A"))
        im = flat
    im = im.convert("RGB")
    W, H = out_size(im.width, im.height, res)
    loras = []
    if kind == "angle":
        loras.append(f"<lora:multiple-angles:{_opt(argv, '--strength', 0.9)}>")
    if fast:
        loras.append("<lora:lightning-4steps:1.0>")
    full_prompt = prompt + "".join(loras)
    stem = os.path.splitext(os.path.basename(src))[0]
    default_out = os.path.join(BUILD, "vision", f"{stem}.{extra_record['tag']}{'_fast' if fast else ''}.png")
    out = argv[argv.index("-o") + 1] if "-o" in argv else default_out
    out = os.path.abspath(out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    lock = os.path.join(f[TOOL], ".running")
    busy = acquire(lock, _opt(argv, "--wait", 0.0) * 60)
    if busy:
        return emit("fail", f"vision {kind}: not started — {busy}",
                    "wait, or close what holds the memory, then re-run (or add --wait 30 to wait up to 30 minutes)")
    tmp = tempfile.mkdtemp(prefix="kit_qwen_edit_")
    try:
        ref = os.path.join(tmp, "input.png")
        im.save(ref)
        cmd = [f["exe"], "--diffusion-model", f["qwen-image-edit-2511-Q4_K_M.gguf"],
               "--vae", f["qwen_image_vae.safetensors"], "--llm", f["Qwen2.5-VL-7B-Instruct.Q8_0.gguf"],
               "--llm_vision", f["Qwen2.5-VL-7B-Instruct.mmproj-Q8_0.gguf"],
               "--model-args", "qwen_image_zero_cond_t=true",  # (2511: quality degrades badly without it)
               "--offload-to-cpu", "--max-vram", "-1", "--diffusion-fa",
               "--sampling-method", "euler", "--flow-shift", "3", "--cfg-scale", str(cfg), "--steps", str(steps),
               "-W", str(W), "-H", str(H), "--seed", str(seed), "-r", ref, "-p", full_prompt, "-o", out,
               "--disable-image-metadata"]
        if loras:  # (quantised weights: LoRAs at run time — `immediately` aborts on a quantised Qwen, sd.cpp #2083)
            cmd += ["--lora-model-dir", os.path.join(f[MODEL], "loras"), "--lora-apply-mode", "at_runtime"]
        log_path = os.path.join(tmp, "sd-cli.log")
        if os.path.isfile(out):
            os.remove(out)
        t0 = time.time()
        with open(log_path, "w", encoding="utf-8", errors="replace") as log:
            p = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, cwd=tmp)
            peak = Peak(p.pid)
            peak.start()
            code = p.wait()
            peak.stop.set()
            peak.join(5)
        secs = time.time() - t0
        with open(log_path, encoding="utf-8", errors="replace") as fh:
            tail = [ln.rstrip() for ln in fh.read().splitlines() if ln.strip()][-12:]
    finally:
        if os.path.isfile(lock):
            os.remove(lock)
        shutil.rmtree(tmp, ignore_errors=True)
    if code != 0 or not os.path.isfile(out):
        return emit("fail", f"vision {kind}: sd-cli stopped (exit {code}) after {secs:.0f} s — {' | '.join(tail[-3:])}",
                    "read the log lines above; out of memory: close other GPU / RAM users and re-run",
                    log_tail=tail)
    ram_gb = round(peak.ram / 1e9, 1)
    vram_mib = peak.vram - (peak.vram0 or 0) if peak.vram else None
    src_abs = os.path.abspath(src)
    shown = os.path.relpath(src_abs, ROOT) if src_abs.startswith(ROOT) else src_abs
    record = {"kind": kind, "trust": "low", "trust_note": LOW_TRUST, "source": shown.replace("\\", "/"),
              "source_sha256": sha256(src),
              "out": out.replace("\\", "/"), "prompt": full_prompt, "seed": seed, "steps": steps, "cfg": cfg,
              "size": [W, H], "fast": fast, "seconds": round(secs, 1), "peak_ram_gb": ram_gb,
              "peak_gpu_used_mib": peak.vram or None, "gpu_used_before_mib": peak.vram0, "gpu_added_mib": vram_mib,
              "model": "Qwen-Image-Edit-2511 Q4_K_M (sd.cpp master-929-3f8527a)", **extra_record}
    with open(os.path.splitext(out)[0] + ".json", "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=1)
    mem = f"peak {ram_gb} GB RAM" + (f", GPU +{vram_mib} MiB" if vram_mib is not None else "")
    return emit("pass", f"vision {kind}: {out} ({W} x {H}, {steps} steps{' fast' if fast else ''}, {secs:.0f} s, {mem})"
                        f" — {LOW_TRUST}",
                f"look at {out} — is it still the same object (shape, parts, proportions)? If not: another --seed",
                trust="low", out=out.replace("\\", "/"), record=os.path.splitext(out)[0].replace("\\", "/") + ".json",
                seconds=round(secs, 1), peak_ram_gb=ram_gb, gpu_added_mib=vram_mib)


def cmd_angle(argv):
    src = argv[0]
    if "--azimuth" not in argv or "--elevation" not in argv:
        return emit("fail", "vision angle: needs --azimuth <deg> and --elevation <deg>",
                    "lune run kit vision angle <picture> --azimuth 90 --elevation 0 [--distance mid]")
    dist = _opt(argv, "--distance", "mid")
    if dist not in DISTANCES:
        return emit("fail", f"vision angle: --distance is near, mid or far (not {dist})",
                    "lune run kit vision angle <picture> --azimuth 90 --elevation 0 --distance mid")
    az_req, el_req = _opt(argv, "--azimuth", 0.0), _opt(argv, "--elevation", 0.0)
    words, az, el = pose(az_req, el_req, dist)
    tag = f"angle_{az}_{el}_{dist}".replace("-", "m")
    return generate("angle", src, f"<sks> {words}", argv,
                    {"tag": tag, "requested": {"azimuth": az_req, "elevation": el_req, "distance": dist},
                     "pose": {"azimuth": az, "elevation": el, "distance": dist, "words": words}})


def cmd_edit(argv):
    src = argv[0]
    prompt = _opt(argv, "--prompt", "")
    if not prompt.strip():
        return emit("fail", "vision edit: needs --prompt \"<instruction>\"",
                    'lune run kit vision edit <picture> --prompt "remove reflections, flat even studio light, '
                    'white background"')
    return generate("edit", src, prompt, argv, {"tag": "edit"})


def main(argv):
    cmds = {"angle": cmd_angle, "edit": cmd_edit}
    if not argv or argv[0] not in cmds or len(argv) < 2 or not os.path.isfile(argv[1]):
        return emit("fail", "vision angle|edit: usage: angle <picture> --azimuth <deg> --elevation <deg> | "
                            "edit <picture> --prompt \"<instruction>\" (the picture must exist)",
                    "lune run kit vision angle refs/<picture>.png --azimuth 90 --elevation 0")
    return cmds[argv[0]](argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
