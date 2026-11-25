"""setup.py — fetch the VETTED vision models into the model cache, each file verified (system python).

    python kit/vision/setup.py [--tier core|vision|gen|all] [model ...] [--check [--quick]] [--list]

HARDWARE TIERS (the release blueprint's Part III): every entry of kit/vision/models.json names its tier, and each tier
includes the ones below it -
    core    (the default)  the lightweight vision core: cut-outs, depth, edges, similarity, upscaling - ~2.4 GB, runs on
                           the CPU (KIT_FORCE_CPU=1) or any 4 GB GPU
    vision                 + the local VLM, relief depth/normals, albedo, SDXL lighting, FLUX.2 concepts and the gated
                           SAM 3 - ~44.6 GB more, a 12 GB CUDA GPU and 16 GB of RAM
    gen                    + qwen-image-edit and its native runner sd-cpp - ~24.5 GB more (the 3D generators' own
                           environments are set up from kit/gen/README.md)
    all                    every entry, the on_demand extras too (clap-general, the sound search)
Naming models fetches exactly those (any tier). A gated entry (sam3: HF_TOKEN) that a TIER would fetch is skipped
with a note when HF_TOKEN is not set - only a model asked for BY NAME fails without its token. An entry with "os"
(sd-cpp: a Windows build) is skipped elsewhere, with a note. --list prints the tiers and their sizes.

Every file comes from the URL pinned in kit/vision/models.json (a commit, never a moving branch), is written to
<file>.part and kept ONLY if its byte size and hash match the manifest (sha256 for the weights, the git blob sha1 for
small files): a download that fails its pin is deleted. A file already in the cache that fails its pin is reported BAD
and replaced only by a download that verifies (kit/vision/run.py refuses to load it either way). --check verifies what
is there and downloads nothing; --quick checks presence and size only (no hashing: what `kit doctor` uses). An unknown
model name is an error, never a vacuous pass.
Cache: KIT_MODELS, else ~/.cache/roblox-kit/models (outside every project: one copy for all of them).
A "tool" entry (a native program: sd-cpp) goes to KIT_TOOLS, else ~/.cache/roblox-kit/tools, and its "unzip" files
are unpacked there after they verify (every path inside checked first: nothing absolute, nothing outside the folder).
An interrupted download resumes from its .part file; the whole file is still checked against its pin.
Anonymous HTTPS only: free, no login. A new model or version is vetted first (VETLOG.md), then pinned here.
"""

import hashlib
import http.client
import json
import os
import shutil
import sys
import time
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(HERE, "models.json")
TIERS = ["core", "vision", "gen"]  # each includes the ones before it; "all" adds the on_demand extras
OS_NAME = "windows" if sys.platform.startswith("win") else "macos" if sys.platform == "darwin" else "linux"


def selected(man, tier, wanted):
    """the entries a run covers -> (names, skipped notes). Named models: exactly those. Else a tier and the tiers below
    it (on_demand extras only with "all"); an entry kept to another OS is skipped with a note."""
    names, notes = [], []
    if wanted:
        return list(wanted), notes
    top = len(TIERS) - 1 if tier == "all" else TIERS.index(tier)
    for name, m in man["models"].items():
        t = m.get("tier", "core")
        if t not in TIERS or TIERS.index(t) > top or (m.get("on_demand") and tier != "all"):
            continue
        if m.get("os") and OS_NAME not in m["os"]:
            notes.append(f"{name}: built for {', '.join(m['os'])} only - skipped on {OS_NAME}")
            continue
        names.append(name)
    return names, notes


def tier_sizes(man):
    """{tier: bytes} over every entry (on_demand extras under their own tier, flagged)"""
    out = {}
    for name, m in man["models"].items():
        key = m.get("tier", "core") + (" (on_demand)" if m.get("on_demand") else "")
        out.setdefault(key, [0, []])
        out[key][0] += sum(f.get("size", 0) for f in m["files"])
        out[key][1].append(name)
    return out


def cache_dir():
    return os.environ.get("KIT_MODELS") or os.path.join(os.path.expanduser("~"), ".cache", "roblox-kit", "models")


def tools_dir():
    return os.environ.get("KIT_TOOLS") or os.path.join(os.path.expanduser("~"), ".cache", "roblox-kit", "tools")


def entry_dir(name, m):
    """where a manifest entry's files live: a tool under the tools cache, a model under the model cache"""
    return os.path.join(tools_dir() if m.get("tool") else cache_dir(), name)


def unzip_safe(zpath, folder):
    """unpack a verified zip into `folder`; refuses the whole zip if any path is absolute or climbs out (..).
    Returns the number of files written. A marker beside the zip records which pinned zip was unpacked."""
    marker = zpath + ".unpacked"
    with zipfile.ZipFile(zpath) as z:
        names = z.namelist()
        root = os.path.realpath(folder)
        for n in names:
            target = os.path.realpath(os.path.join(folder, n))
            if os.path.isabs(n) or n.startswith(("/", "\\")) or ".." in n.replace("\\", "/").split("/") \
                    or os.path.commonpath([root, target]) != root:
                raise ValueError(f"{os.path.basename(zpath)}: unsafe path inside the zip ({n!r}) — nothing unpacked")
        z.extractall(folder)
    with open(marker, "w", encoding="utf-8") as fh:
        fh.write(str(os.path.getsize(zpath)))
    return len(names)


def file_ok(path, f):
    """size + hash exactly as pinned"""
    if not os.path.isfile(path) or os.path.getsize(path) != f["size"]:
        return False
    if "sha256" in f:
        h = hashlib.sha256()
    else:
        h = hashlib.sha1()
        h.update(b"blob %d\0" % f["size"])  # git's blob hash: what the repo tree publishes
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest() == (f.get("sha256") or f["git_sha1"])


def download_hf(url, dst, token=None):
    """a BIG Hugging Face file through huggingface_hub when it is installed (parallel transfer with hf_xet: many times
    the single-stream speed — 23 GB took hours one stream at a time). The same pinned URL (repo, commit, path); the pin
    still checks the whole file. False when the package is missing (the caller falls back to `download`)."""
    try:
        from huggingface_hub import hf_hub_download  # noqa: PLC0415
    except ImportError:
        return False
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    org, repo, _resolve, rev, path = url[len("https://huggingface.co/"):].split("/", 4)
    staging = dst + ".hf"
    local = hf_hub_download(f"{org}/{repo}", path, revision=rev, local_dir=staging, token=token or False)
    os.replace(local, dst)
    shutil.rmtree(staging, ignore_errors=True)
    return True


def download(url, dst, token=None, size=None):
    """`token`: a GATED model's Hugging Face token, read from the environment by the caller — sent only to
    huggingface.co, never printed or written anywhere. A connection that drops part-way is resumed (an HTTP Range
    request for the rest, up to 8 tries): Python's http.client just stops reading when a server closes early, so a
    multi-GB file used to arrive short and fail its pin (2026-10-06: a 5.1 GB and a 2.5 GB file). The caller still
    checks the size and hash."""
    headers = {"User-Agent": "roblox-kit-vision/1"}
    if token and url.startswith("https://huggingface.co/"):
        headers["Authorization"] = f"Bearer {token}"
    with open(dst, "wb"):
        pass
    for attempt in range(8):
        have = os.path.getsize(dst)
        if size is not None and have >= size:
            return
        if attempt and size is None:
            return  # (no size to resume towards: one pass, as before)
        req = urllib.request.Request(url, headers={**headers, **({"Range": f"bytes={have}-"} if have else {})})
        try:
            with urllib.request.urlopen(req, timeout=120) as r, open(dst, "r+b") as out:
                out.seek(have if r.status == 206 else 0)  # (a server that ignores the range sends it all again)
                out.truncate()
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    out.write(chunk)
        except OSError:
            if attempt == 7:
                raise


def main(argv):
    check = "--check" in argv
    quick = "--quick" in argv
    tier = "core"
    args = list(argv)
    if "--tier" in args:
        i = args.index("--tier")
        tier = args[i + 1] if i + 1 < len(args) else ""
        del args[i:i + 2]
    wanted = [a for a in args if not a.startswith("--")]
    with open(MANIFEST, encoding="utf-8") as fh:
        man = json.load(fh)
    if "--list" in argv:
        rows = tier_sizes(man)
        for key in sorted(rows, key=lambda k: (TIERS.index(k.split(" ")[0]), k)):
            size, names = rows[key]
            print(f"{key:20} {size / 1e9:7.2f} GB  {', '.join(names)}")
        print(json.dumps({"schema": 1, "status": "pass", "summary": "vision tiers: core (default), vision, gen, all",
                          "next_action": "lune run kit vision setup --tier <core|vision|gen|all>"}))
        return 0
    if tier not in TIERS + ["all"]:
        print(json.dumps({"schema": 1, "status": "fail", "summary": f"vision setup: unknown tier {tier!r}",
                          "next_action": "use --tier core (default), vision, gen or all (lune run kit vision setup --list)"}))
        return 1
    root = cache_dir()
    unknown = [w for w in wanted if w not in man["models"]]
    if unknown:
        print(json.dumps({"schema": 1, "status": "fail", "summary": f"vision setup: unknown model(s) {', '.join(unknown)}",
                          "next_action": f"use one of: {', '.join(man['models'])} (or a --tier)"}))
        return 1
    names, notes = selected(man, tier, wanted)
    done, bad, missing = [], [], []
    for name in names:
        m = man["models"][name]
        folder = entry_dir(name, m)
        if m.get("gated") and not os.environ.get("HF_TOKEN") and name not in wanted:
            # (a TIER never fails on a gated model: it is skipped and said - named, it is fetched or it fails)
            notes.append(f"{name}: gated - skipped (request access on huggingface.co and set HF_TOKEN, then "
                         f"`kit vision setup {name}`; until then the free SAM 2.1 point/box prompts stand in)")
            continue
        if m.get("tool"):
            root = tools_dir() if root == cache_dir() and wanted == [name] else f"{root} + {tools_dir()}"
        os.makedirs(folder, exist_ok=True)
        for f in m["files"]:
            path = os.path.join(folder, f["path"])
            if quick and check:
                if os.path.isfile(path) and os.path.getsize(path) == f["size"]:
                    done.append(f"{name}/{f['path']}")
                else:
                    (bad if os.path.exists(path) else missing).append(f"{name}/{f['path']}")
                continue
            if file_ok(path, f):
                if f.get("unzip") and not check and not os.path.isfile(path + ".unpacked"):
                    try:
                        print(f"unpacked {name}/{f['path']} ({unzip_safe(path, folder)} files)", flush=True)
                    except (ValueError, zipfile.BadZipFile) as e:
                        bad.append(f"{name}/{f['path']}: {e}")
                        continue
                done.append(f"{name}/{f['path']}")
                continue
            if check:
                (bad if os.path.exists(path) else missing).append(f"{name}/{f['path']}")
                continue
            part = path + ".part"
            os.makedirs(os.path.dirname(path), exist_ok=True)  # (a model's files can sit in sub-folders: unet/, vae/)
            token = os.environ.get("HF_TOKEN") if m.get("gated") else None
            if m.get("gated") and not token:
                bad.append(f"{name}/{f['path']}: gated — the owner requests access on huggingface.co and sets HF_TOKEN")
                continue
            if f["size"] >= 1 << 30 and f["url"].startswith("https://huggingface.co/") and not os.path.isfile(part):
                try:  # a BIG file: huggingface_hub's parallel transfer first; the plain download resumes what it left
                    download_hf(f["url"], part, token)
                except Exception as e:  # noqa: BLE001 — the plain download below takes over
                    print(f"huggingface_hub download stopped ({type(e).__name__}): plain download", flush=True)
            if not (os.path.isfile(part) and os.path.getsize(part) >= f["size"]):
                try:
                    download(f["url"], part, token, f["size"])
                except (OSError, http.client.HTTPException) as e:
                    bad.append(f"{name}/{f['path']}: download failed ({e}) — re-run to resume")
                continue
            if file_ok(part, f):
                os.replace(part, path)
                print(f"verified {name}/{f['path']} ({f['size']:,} bytes)", flush=True)
                if f.get("unzip"):
                    try:
                        print(f"unpacked {name}/{f['path']} ({unzip_safe(path, folder)} files)", flush=True)
                    except (ValueError, zipfile.BadZipFile) as e:
                        bad.append(f"{name}/{f['path']}: {e}")
                        continue
                done.append(f"{name}/{f['path']}")
            else:
                os.remove(part)
                bad.append(f"{name}/{f['path']}: size or hash does not match the vetted pin — deleted")
    ok = not bad and not missing
    for n in notes:
        print(f"note: {n}", flush=True)
    scope = f"{', '.join(wanted)}" if wanted else f"tier {tier}"
    nxt = {"core": "vision", "vision": "gen"}.get(tier) if not wanted else None
    print(json.dumps({
        "schema": 1, "status": "pass" if ok else "fail",
        "summary": f"vision models ({scope}): {len(done)} file(s) {'present' if quick else 'verified'} in {root}"
                   + (f"; {len(missing)} missing" if missing else "") + (f"; {len(bad)} BAD" if bad else "")
                   + (f"; {len(notes)} skipped (see notes)" if notes else ""),
        "next_action": (f"none - proceed (the next tier: lune run kit vision setup --tier {nxt}; sizes: --list)"
                        if ok and nxt else "none - proceed") if ok else (
            f"{'; '.join(bad[:3])} - never use a file that fails its pin" if bad
            else f"lune run kit vision setup{'' if wanted or tier == 'core' else ' --tier ' + tier}"
                 f"{' ' + ' '.join(wanted) if wanted else ''}   (downloads the vetted, pinned files)"),
        "tier": None if wanted else tier, "cache": root, "verified": done, "missing": missing, "bad": bad,
        "skipped": notes}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
