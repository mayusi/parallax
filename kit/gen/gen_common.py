"""gen_common.py — what the kit's local generators share (kit-owned code).

    import gen_common as G
    G.offline()              # every socket connection raises; Hugging Face + transformers run offline
    G.shims()                # nvdiffrast -> kit/gen/uvraster.py, xformers -> kit/gen/xops_sdpa.py
    G.pinned(root)           # every file in <root>/pins.json is there at its pinned size -> list of problems
    state = G.watch_tuning() # FlexGEMM kernel tunings during a run (a run that tuned is generated again)
    return G.emit("pass", "summary", "next action", **facts)

trellis2_run.py keeps its own copies of these (it came first); new runners (pixal3d_run.py) use this module.
"""

import hashlib
import json
import os
import socket
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(os.path.expanduser("~"), ".cache", "roblox-kit")
MODELS = os.environ.get("KIT_MODELS") or os.path.join(CACHE, "models")
SRC = os.path.join(CACHE, "src")


def _no_network(*_a, **_k):
    raise RuntimeError("kit gen runs offline: a network connection was attempted and blocked")


def offline():
    """no network from here on: Hugging Face / transformers offline, every socket connection raises"""
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1")
    socket.socket.connect = _no_network
    socket.socket.connect_ex = _no_network
    socket.socket.sendto = _no_network
    socket.create_connection = _no_network
    socket.getaddrinfo = _no_network


def shims():
    """the kit's stand-ins for two libraries the generators call but the kit never installs: nvdiffrast (NVIDIA
    licence: non-commercial only) -> uvraster.py; xformers (no compute-12.0 kernel on Windows) -> xops_sdpa.py"""
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    import uvraster  # noqa: PLC0415
    import xops_sdpa  # noqa: PLC0415

    nv = types.ModuleType("nvdiffrast")
    nv.torch = uvraster
    sys.modules["nvdiffrast"] = nv
    sys.modules["nvdiffrast.torch"] = uvraster
    xf = types.ModuleType("xformers")
    xf.ops = xops_sdpa
    sys.modules["xformers"] = xf
    sys.modules["xformers.ops"] = xops_sdpa


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}),
          flush=True)
    return 0 if status == "pass" else 1


def opt(argv, flag, default):
    """--flag value (the last one wins), cast to the default's type"""
    if flag not in argv:
        return default
    i = len(argv) - 1 - argv[::-1].index(flag)
    if i + 1 >= len(argv):
        raise ValueError(f"{flag} needs a value")
    return type(default)(argv[i + 1]) if default is not None else argv[i + 1]


def opts(argv, flag):
    """every value of a repeatable --flag value"""
    return [argv[i + 1] for i, a in enumerate(argv[:-1]) if a == flag]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pinned(root, where):
    """every file pinned in <root>/pins.json is there at its pinned size -> list of problems.
    where(key) -> the local path of a pins.json key"""
    pins_path = os.path.join(root, "pins.json")
    if not os.path.isfile(pins_path):
        return [f"no {pins_path} — the weights were never fetched"]
    with open(pins_path, encoding="utf-8") as fh:
        pins = json.load(fh)
    problems = []
    for key, pin in pins.items():
        path = where(key)
        if not os.path.isfile(path):
            problems.append(f"missing {path}")
        elif os.path.getsize(path) != pin["size"]:
            problems.append(f"{path} is {os.path.getsize(path)} bytes, pinned {pin['size']}")
    return problems


def watch_tuning():
    """FlexGEMM tunes its GPU kernels the first time it meets a problem size (cached in ~/.flex_gemm). On a 12 GB
    RTX 5070 every model generated WHILE kernels were being tuned came out with stray strands to the edge of the box
    (kit/gen/README.md) -> a counter of tunings during a run, so a run that tuned is generated again."""
    from flex_gemm.utils import autotuner as AT  # noqa: PLC0415

    state = {"tuned": 0}

    def wrap(cls, name):
        orig = getattr(cls, name)
        if getattr(orig, "_kit_counted", False):
            return

        def counted(self, *a, **k):
            before = len(self.cache)
            out = orig(self, *a, **k)
            if len(self.cache) > before:
                state["tuned"] += 1
            return out

        counted._kit_counted = True
        setattr(cls, name, counted)

    wrap(AT.TritonPersistentCacheAutotuner, "run")
    wrap(AT.PersistentCacheAutoTuner, "__call__")
    return state


def extents(v):
    """the three side lengths of a vertex set's box, sorted"""
    import numpy as np  # noqa: PLC0415

    v = np.asarray(v, dtype=np.float64)
    return sorted((v.max(0) - v.min(0)).tolist())


def dinov3_blocks(m):
    """DINOv3's transformer blocks: transformers 4 keeps them at model.layer, transformers 5 at model.model.layer
    (same blocks, same weights)"""
    return m.layer if hasattr(m, "layer") else m.model.layer


class KitCutoutDone:
    """the pictures come cut out (kit vision cutout --rgba, BiRefNet MIT): a generator's own background remover
    (RMBG-2.0, CC BY-NC) never loads"""

    def __init__(self, **_):
        pass

    def to(self, *_a, **_k):
        return self

    def cpu(self):
        return self

    def cuda(self):
        return self

    def __call__(self, image):
        raise RuntimeError("kit gen: every picture must be an RGBA cut-out (lune run kit vision cutout <img> --rgba)")
