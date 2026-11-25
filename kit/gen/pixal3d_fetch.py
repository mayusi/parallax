"""pixal3d_fetch.py — fetch and verify what `kit gen views` runs on (the owner approved these exact files, 2026-10-06).

    <envs/trellis2>/Scripts/python.exe kit/gen/pixal3d_fetch.py           # weights (~22 GB) + the NAF checkpoint
    <envs/trellis2>/Scripts/python.exe kit/gen/pixal3d_fetch.py --check   # re-hash what is here against the pins

- Pixal3D's multi-view networks from huggingface.co/TencentARC/Pixal3D at a PINNED revision: every file is checked
  against the Hub's own sha256 and size at that revision, then recorded in ~/.cache/roblox-kit/models/pixal3d/pins.json
  (the runner checks sizes against it before every run).
- Its three decoders are byte-identical to TRELLIS.2's (same sha256 on the Hub): when the verified TRELLIS.2 copy is
  here and re-hashes to that sha256 it is HARD-LINKED (no second download, no second copy on disk).
- NAF's checkpoint (naf_release.pth) from the valeoai/NAF GitHub release: size and the release's sha256 digest.
No token is needed (neither repository is gated).
"""

import hashlib
import json
import os
import sys
import urllib.request

MODELS = os.environ.get("KIT_MODELS") or os.path.join(os.path.expanduser("~"), ".cache", "roblox-kit", "models")
ROOT = os.path.join(MODELS, "pixal3d")
REPO, REVISION = "TencentARC/Pixal3D", "b0cb2e1b794cab9aa0ac38a95d794a4d9337437f"
_NETS = ["ss_flow_img_dit_1_3B_64_bf16_mv", "slat_flow_img2shape_dit_1_3B_512_bf16_mv",
         "slat_flow_img2shape_dit_1_3B_1024_bf16_mv", "slat_flow_imgshape2tex_dit_1_3B_1024_bf16_mv"]
_DECODERS = {  # Pixal3D name -> the TRELLIS.2 copy it may be linked from (kit/gen/fetch.py fetched + pinned those)
    "ss_dec_conv3d_16l8_fp16": "microsoft/TRELLIS-image-large/ckpts/ss_dec_conv3d_16l8_fp16.safetensors",
    "shape_dec_next_dc_f16c32_fp16": "microsoft/TRELLIS.2-4B/ckpts/shape_dec_next_dc_f16c32_fp16.safetensors",
    "tex_dec_next_dc_f16c32_fp16": "microsoft/TRELLIS.2-4B/ckpts/tex_dec_next_dc_f16c32_fp16.safetensors",
}
FILES = ["pipeline_mv.json"] + [f"ckpts/{n}.{e}" for n in _NETS + list(_DECODERS) for e in ("json", "safetensors")]
NAF = {"name": "naf_release.pth", "size": 2664431,
       "sha256": "c096c1ab2217a5c3ac136365f721685e2201379cb69d509cfb0261183847c98f",
       "url": "https://github.com/valeoai/NAF/releases/download/model/naf_release.pth"}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 24), b""):
            h.update(chunk)
    return h.hexdigest()


def _trellis2_copy(key):
    """the verified TRELLIS.2 file for a pins.json key (kit/gen/fetch.py layout), or None"""
    t2 = os.path.join(MODELS, "trellis2")
    pins_path = os.path.join(t2, "pins.json")
    if not os.path.isfile(pins_path):
        return None, None
    with open(pins_path, encoding="utf-8") as fh:
        pin = json.load(fh).get(key)
    path = os.path.join(t2, key.split("/", 2)[1], key.split("/", 2)[2])
    return (path, pin) if pin and os.path.isfile(path) else (None, None)


def fetch_weights(pins):
    from huggingface_hub import HfApi, hf_hub_download  # noqa: PLC0415

    info = HfApi().model_info(REPO, revision=REVISION, files_metadata=True)
    meta = {s.rfilename: s for s in info.siblings}
    local_dir, bad = os.path.join(ROOT, "Pixal3D"), 0
    for name in FILES:
        s = meta[name]
        local = os.path.join(local_dir, name)
        decoder = os.path.splitext(os.path.basename(name))[0]
        how = "downloaded"
        if name.endswith(".safetensors") and decoder in _DECODERS and not os.path.isfile(local):
            src, pin = _trellis2_copy(_DECODERS[decoder])
            if src and s.lfs and pin["sha256"] == s.lfs.sha256 and sha256(src) == s.lfs.sha256:
                os.makedirs(os.path.dirname(local), exist_ok=True)
                os.link(src, local)  # same bytes, same volume: a second name for the verified file
                how = "hard link to the verified TRELLIS.2 copy"
        if not os.path.isfile(local):
            local = hf_hub_download(REPO, name, revision=REVISION, local_dir=local_dir)
        elif how == "downloaded":
            how = "already here"
        size, digest = os.path.getsize(local), sha256(local)
        ok = size == s.size and (s.lfs is None or (digest == s.lfs.sha256 and size == s.lfs.size))
        bad += not ok
        pins[f"{REPO}/{name}"] = {"commit": REVISION, "size": size, "sha256": digest, "how": how}
        print(("OK  " if ok else "BAD ") + f"{REPO}/{name} {size} bytes ({how})", flush=True)
    return bad


def fetch_naf(pins):
    dest = os.path.join(ROOT, "naf", NAF["name"])
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if not os.path.isfile(dest):
        tmp = dest + ".part"
        with urllib.request.urlopen(NAF["url"], timeout=60) as r, open(tmp, "wb") as fh:  # noqa: S310 (fixed https URL)
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                fh.write(chunk)
        os.replace(tmp, dest)
    size, digest = os.path.getsize(dest), sha256(dest)
    ok = size == NAF["size"] and digest == NAF["sha256"]
    pins["valeoai/NAF/" + NAF["name"]] = {"commit": "release:model", "size": size, "sha256": digest,
                                          "how": "GitHub release asset"}
    print(("OK  " if ok else "BAD ") + f"valeoai/NAF/{NAF['name']} {size} bytes", flush=True)
    return int(not ok)


def check(pins):
    bad = 0
    for key, pin in pins.items():
        path = (os.path.join(ROOT, "naf", key.split("/")[-1]) if key.startswith("valeoai/")
                else os.path.join(ROOT, "Pixal3D", key.split("/", 2)[2]))
        ok = os.path.isfile(path) and os.path.getsize(path) == pin["size"] and sha256(path) == pin["sha256"]
        bad += not ok
        print(("OK  " if ok else "BAD ") + key, flush=True)
    return bad


def main(argv):
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    pins_path = os.path.join(ROOT, "pins.json")
    pins = json.load(open(pins_path, encoding="utf-8")) if os.path.isfile(pins_path) else {}
    if "--check" in argv:
        bad = check(pins) if pins else 1
    else:
        os.makedirs(ROOT, exist_ok=True)
        bad = fetch_weights(pins) + fetch_naf(pins)
        with open(pins_path, "w", encoding="utf-8") as fh:
            json.dump(pins, fh, indent=1)
    print(json.dumps({"schema": 1, "status": "pass" if not bad else "fail",
                      "summary": f"pixal3d fetch: {'every file verified' if not bad else f'{bad} file(s) failed'} "
                                 f"({ROOT})",
                      "next_action": "lune run kit gen views <name> --view side=<rgba.png> --view front=<rgba.png>"
                      if not bad else "delete the BAD file(s) and fetch again; if it repeats, report it"}))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
