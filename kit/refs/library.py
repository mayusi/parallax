"""library.py — REFERENCE MODELS: find, download and vet detailed 3D models of a real object — every side, every
cross-section, every part, which no photo gives — to MEASURE and trace from (kit refs measure).

    python kit/refs/library.py find "<object>" [--n 12] [--licenses cc0,by,by-sa] [--min-faces 20000]
    python kit/refs/library.py get <sketchfab uid>
    python kit/refs/library.py get --url <https://...glb|.gltf.zip> --license cc0 --title "<what it is>" [--author ..]

Sources: Sketchfab's Creative Commons library (api.sketchfab.com Data API v3: searching needs no account; a download
needs the owner's personal API token in the SKETCHFAB_API_TOKEN environment variable — read from the environment,
sent only to api.sketchfab.com, never printed or written anywhere) and direct CC0 files (the Smithsonian's 3D scans,
3d.si.edu: no account). Only licences that allow use AND changes are kept: CC0 and CC BY / BY-SA (attribution
recorded); never NC, ND, Standard or Editorial.

SAFETY — what can go wrong with a downloaded model, and what this does about it:
  - a 3D file is DATA, but a .blend can carry Python that runs when opened -> only glTF (.glb, or .gltf + .bin + images
    from a zip) is accepted; never .blend, never anything executable (.exe .bat .cmd .ps1 .py .js .dll .scr .vbs ...)
  - a zip can write outside its folder ("zip slip") or explode in size -> every member's path is checked (no absolute
    path, no "..", no drive letter), only model / texture extensions are extracted, size and count are capped
  - a file can lie about its type -> the .glb's header must read "glTF" version 2 with a JSON chunk; a glTF that points
    at files OUTSIDE its folder or at web URLs is refused
  - a download can be huge -> streamed with a byte cap (400 MB)
  - a "free" model can be someone else's art re-uploaded (ripped game assets are common) -> the licence and author are
    recorded; library models are REFERENCES to measure and trace, never shipped in a game
  - the files go to ~/.cache/roblox-kit/library/<id>/ (outside the repo), with model.json: title, author, licence,
    licence URL, attribution text, source page, retrieval date, face count, sha256
One JSON verdict line at the end.
"""

import datetime
import hashlib
import json
import os
import re
import struct
import sys
import urllib.parse
import urllib.request
import zipfile

API = "https://api.sketchfab.com/v3"
UA = os.environ.get("KIT_REFS_UA") or "roblox-kit-refs/1.0 (local reference library for a Roblox content kit)"
CACHE = os.path.join(os.path.expanduser("~"), ".cache", "roblox-kit", "library")
MAX_BYTES = 400 * 1024 * 1024
MAX_UNZIPPED = 600 * 1024 * 1024
MAX_MEMBERS = 3000
KEEP_EXT = {".glb", ".gltf", ".bin", ".png", ".jpg", ".jpeg", ".webp", ".ktx2", ".txt", ".md"}
OK_LABELS = {"cc0": ("cc0", "public domain"), "by": ("cc attribution",), "by-sa": ("cc attribution-sharealike",)}
BAD_WORDS = ("noncommercial", "non-commercial", "nonderiv", "noderiv", "standard", "editorial")
# polyhaven.org = its asset FILE host (dl.polyhaven.org), one file by its link: the live API (api.polyhaven.com) is
# never automated — its terms ask tools built on live data for a revenue share (VETLOG 2026-10-07)
OK_HOSTS = ("sketchfab.com", "amazonaws.com", "si.edu", "smithsonian.museum", "polyhaven.org")


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra},
                     ensure_ascii=True))
    return 0 if status == "pass" else 1


def _arg(argv, flag, default=None):
    return argv[argv.index(flag) + 1] if flag in argv and argv.index(flag) + 1 < len(argv) else default


def licence_ok(label, allowed=("cc0", "by", "by-sa")):
    """a Sketchfab licence label -> its short name if usable, else None"""
    low = (label or "").strip().lower()
    if not low or any(w in low.replace(" ", "") or w in low for w in BAD_WORDS):
        return None
    for short in allowed:
        if any(low == want or low.startswith(want + " ") for want in OK_LABELS.get(short, ())):
            return short
    if "cc0" in allowed and ("cc0" in low or "public domain" in low):
        return "cc0"
    return None


def _host_ok(url):
    h = (urllib.parse.urlparse(url).hostname or "").lower()
    return urllib.parse.urlparse(url).scheme == "https" and any(h == d or h.endswith("." + d) for d in OK_HOSTS)


def _token():
    """The owner's Sketchfab key: this process's environment, else (Windows) the User environment — set after the app
    started, a new variable reaches only new processes. A pasted example's <brackets>, quotes or spaces are stripped
    (the owner's first key was saved as '<key>'). Never printed."""
    tok = os.environ.get("SKETCHFAB_API_TOKEN")
    if not tok and os.name == "nt":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                tok = winreg.QueryValueEx(k, "SKETCHFAB_API_TOKEN")[0]
        except OSError:
            tok = None
    return (tok or "").strip().strip("<>\"'").strip() or None


def polite(open_fn, tries=5):
    """a web call that waits when the server says "too many requests" (HTTP 429 / 503): its Retry-After, else 2, 4, 8,
    16 s — the APIs are free and shared; never hammer them"""
    import time  # noqa: PLC0415
    import urllib.error  # noqa: PLC0415

    for k in range(tries):
        try:
            return open_fn()
        except urllib.error.HTTPError as e:
            if e.code not in (429, 503) or k == tries - 1:
                raise
            wait = e.headers.get("Retry-After") if e.headers else None
            time.sleep(min(60.0, float(wait)) if wait and wait.replace(".", "", 1).isdigit() else 2.0 ** (k + 1))
    return None


def _get_json(url, token=None):
    hdr = {"User-Agent": UA}
    if token:
        hdr["Authorization"] = f"Token {token}"

    def go():
        with urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=60) as r:
            return json.load(r)

    return polite(go)


def _download(url, path):
    """stream url -> path, capped; -> (bytes, sha256)"""
    if not _host_ok(url):
        raise ValueError(f"refusing a download from {urllib.parse.urlparse(url).hostname} (not an allowed host)")
    h, n = hashlib.sha256(), 0
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=120) as r, \
            open(path, "wb") as fh:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            n += len(chunk)
            if n > MAX_BYTES:
                raise ValueError(f"over the {MAX_BYTES >> 20} MB cap")
            h.update(chunk)
            fh.write(chunk)
    return n, h.hexdigest()


def check_glb(path):
    """the .glb's header and JSON chunk -> (ok, why). Refuses external / web URIs."""
    with open(path, "rb") as fh:
        head = fh.read(20)
        if len(head) < 20:
            return False, "too short for a .glb"
        magic, version, _length, clen, ctype = struct.unpack("<4sIIII", head)
        if magic != b"glTF" or version != 2 or ctype != 0x4E4F534A:
            return False, "not a glTF 2 binary (bad header)"
        doc = json.loads(fh.read(clen).decode("utf-8"))
    return check_gltf_doc(doc)


def check_gltf_doc(doc):
    for key in ("buffers", "images"):
        for item in doc.get(key, []) or []:
            uri = item.get("uri")
            if not uri or uri.startswith("data:"):
                continue
            low = uri.lower()
            if "://" in low or low.startswith(("/", "\\")) or ".." in uri.replace("\\", "/").split("/") \
                    or re.match(r"^[a-z]:", low):
                return False, f"points outside its folder: {uri[:60]}"
    return True, "glTF 2, self-contained"


def safe_unzip(zpath, dest):
    """extract only model / texture files, inside dest, capped -> (kept, skipped)"""
    kept, skipped, total = [], [], 0
    with zipfile.ZipFile(zpath) as z:
        infos = z.infolist()
        if len(infos) > MAX_MEMBERS:
            raise ValueError(f"{len(infos)} files in the archive (cap {MAX_MEMBERS})")
        for info in infos:
            name = info.filename.replace("\\", "/")
            if info.is_dir():
                continue
            parts = name.split("/")
            if name.startswith("/") or ".." in parts or re.match(r"^[A-Za-z]:", name):
                skipped.append(f"{name} (unsafe path)")
                continue
            if os.path.splitext(name)[1].lower() not in KEEP_EXT:
                skipped.append(f"{name} (not a model / texture file)")
                continue
            total += info.file_size
            if total > MAX_UNZIPPED:
                raise ValueError(f"over {MAX_UNZIPPED >> 20} MB unpacked")
            target = os.path.normpath(os.path.join(dest, *parts))
            if not target.startswith(os.path.normpath(dest) + os.sep):
                skipped.append(f"{name} (outside the folder)")
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with z.open(info) as src, open(target, "wb") as out:
                out.write(src.read())
            kept.append(os.path.relpath(target, dest).replace("\\", "/"))
    return kept, skipped


def search(q, n=12, allowed=("cc0", "by", "by-sa"), min_faces=0, pages_max=5):
    """Sketchfab's downloadable models for q with a usable licence (no account needed) -> rows, most liked first"""
    params = {"type": "models", "q": q, "downloadable": "true", "count": 24, "sort_by": "-likeCount"}
    rows, url, pages = [], f"{API}/search?{urllib.parse.urlencode(params)}", 0
    while url and len(rows) < n and pages < pages_max:
        d = _get_json(url)
        pages += 1
        for m in d.get("results", []):
            lic = (m.get("license") or {}).get("label") if isinstance(m.get("license"), dict) else m.get("license")
            short = licence_ok(lic, allowed)
            if not short or not m.get("isDownloadable") or (m.get("faceCount") or 0) < min_faces:
                continue
            rows.append({"uid": m.get("uid"), "title": m.get("name"), "author": (m.get("user") or {}).get("username"),
                         "licence": short, "licence_label": lic, "faces": m.get("faceCount"),
                         "page": m.get("viewerUrl"), "likes": m.get("likeCount")})
            if len(rows) >= n:
                break
        url = d.get("next")
    return rows


def cmd_find(argv):
    if not argv or argv[0].startswith("--"):
        return emit("fail", "library find: give what to look for", 'lune run kit library find "colt 1911"')
    q = argv[0]
    n = int(_arg(argv, "--n", "12"))
    allowed = tuple(_arg(argv, "--licenses", "cc0,by,by-sa").split(","))
    min_faces = int(_arg(argv, "--min-faces", "0"))
    rows = search(q, n, allowed, min_faces)
    slug = re.sub(r"[^a-z0-9]+", "_", q.lower()).strip("_")[:40]
    out = os.path.join(os.environ.get("KIT_BUILD", "build"), "library", slug)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "candidates.json"), "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=1)
    lines = [f"  {i + 1}. {r['uid']}  {r['title'][:46]:<46} {r['faces'] or 0:>8} faces  {r['licence']:<5} by {r['author']}"
             for i, r in enumerate(rows)]
    if not rows:
        return emit("fail", f"library find: no downloadable CC0 / BY / BY-SA model of '{q}'", "try other words",
                    rows=[])
    return emit("pass", f"library find: {len(rows)} downloadable model(s) of '{q}' (licences {', '.join(allowed)})",
                f"pick the most detailed REAL one (faces, a real make, not a game rip): lune run kit library get <uid> "
                f"(needs SKETCHFAB_API_TOKEN in the environment); the list: {out}/candidates.json", rows=lines)


def _store(meta, folder):
    meta["retrieved"] = datetime.date.today().isoformat()
    with open(os.path.join(folder, "model.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1)


def cmd_get(argv):
    url = _arg(argv, "--url")
    if url:
        return get_url(url, argv)
    if not argv or argv[0].startswith("--"):
        return emit("fail", "library get: give a Sketchfab uid (kit library find) or --url", "lune run kit library get <uid>")
    uid = argv[0]
    if not re.fullmatch(r"[0-9a-f]{32}", uid):
        return emit("fail", f"library get: '{uid[:40]}' is not a Sketchfab uid (32 hex digits)", "kit library find")
    token = _token()
    if not token:
        return emit("fail", "library get: SKETCHFAB_API_TOKEN is not set in the environment",
                    "the OWNER sets it (Sketchfab > Settings > Password & API): PowerShell "
                    "[Environment]::SetEnvironmentVariable('SKETCHFAB_API_TOKEN','PASTE_KEY_HERE','User') "
                    "(the key alone, no brackets). Never paste a token into a chat")
    info = _get_json(f"{API}/models/{uid}")
    lic = (info.get("license") or {}).get("label") if isinstance(info.get("license"), dict) else info.get("license")
    short = licence_ok(lic)
    if not short:
        return emit("fail", f"library get: '{info.get('name')}' is licensed '{lic}' — not usable (CC0 / BY / BY-SA "
                    "only)", "pick another")
    links = _get_json(f"{API}/models/{uid}/download", token=token)
    folder = os.path.join(CACHE, uid)
    os.makedirs(folder, exist_ok=True)
    fmt = "glb" if "glb" in links else "gltf" if "gltf" in links else None
    if not fmt:
        return emit("fail", f"library get: no glTF download offered (only {', '.join(links)})", "pick another")
    if fmt == "glb":
        path = os.path.join(folder, "model.glb")
        size, sha = _download(links["glb"]["url"], path)
        ok, why = check_glb(path)
        kept, skipped = ["model.glb"], []
    else:
        zpath = os.path.join(folder, "download.zip")
        size, sha = _download(links["gltf"]["url"], zpath)
        kept, skipped = safe_unzip(zpath, os.path.join(folder, "gltf"))
        os.remove(zpath)
        gl = [k for k in kept if k.endswith(".gltf")]
        if not gl:
            return emit("fail", "library get: the archive held no .gltf", "pick another", skipped=skipped[:10])
        path = os.path.join(folder, "gltf", gl[0])
        with open(path, encoding="utf-8") as fh:
            ok, why = check_gltf_doc(json.load(fh))
    if not ok:
        return emit("fail", f"library get: refused — {why}", "pick another model")
    author = (info.get("user") or {}).get("username")
    meta = {"source": "sketchfab", "uid": uid, "title": info.get("name"), "author": author,
            "author_page": (info.get("user") or {}).get("profileUrl"), "licence": short, "licence_label": lic,
            "licence_url": (info.get("license") or {}).get("url") if isinstance(info.get("license"), dict) else None,
            "page": info.get("viewerUrl"), "faces": info.get("faceCount"), "file": os.path.relpath(path, folder),
            "bytes": size, "sha256": sha, "format": fmt, "kept": kept[:50], "skipped": skipped[:50],
            "attribution": f"\"{info.get('name')}\" by {author} ({info.get('viewerUrl')}), {lic}",
            "use": "REFERENCE ONLY (measure / trace) — never shipped in a game"}
    _store(meta, folder)
    return emit("pass", f"library get: '{info.get('name')}' ({short}, {info.get('faceCount')} faces, {size >> 20} MB) "
                f"-> {path}", f"measure it at its REAL size: lune run kit refs measure \"{path}\" --name <name> "
                "--length-mm <its real overall length>", path=path.replace("\\", "/"), skipped=len(skipped))


def get_url(url, argv):
    lic = _arg(argv, "--license")
    title = _arg(argv, "--title")
    if lic not in ("cc0", "by", "by-sa") or not title:
        return emit("fail", "library get --url: give --license cc0|by|by-sa (from the source page) and --title",
                    "check the licence on the source page first")
    if not _host_ok(url):
        return emit("fail", f"library get --url: {urllib.parse.urlparse(url).hostname} is not an allowed host "
                    f"({', '.join(OK_HOSTS)})", "only the listed sources")
    key = hashlib.sha1(url.encode()).hexdigest()[:16]
    folder = os.path.join(CACHE, key)
    os.makedirs(folder, exist_ok=True)
    ext = os.path.splitext(urllib.parse.urlparse(url).path)[1].lower()
    if ext == ".glb":
        path = os.path.join(folder, "model.glb")
        size, sha = _download(url, path)
        ok, why = check_glb(path)
        kept, skipped = ["model.glb"], []
    elif ext == ".zip":
        zpath = os.path.join(folder, "download.zip")
        size, sha = _download(url, zpath)
        kept, skipped = safe_unzip(zpath, os.path.join(folder, "files"))
        os.remove(zpath)
        gl = [k for k in kept if k.endswith((".gltf", ".glb"))]
        if not gl:
            return emit("fail", "library get --url: no .gltf / .glb in the archive", "pick another", skipped=skipped[:10])
        path = os.path.join(folder, "files", gl[0])
        if path.endswith(".glb"):
            ok, why = check_glb(path)
        else:
            with open(path, encoding="utf-8") as fh:
                ok, why = check_gltf_doc(json.load(fh))
    else:
        return emit("fail", f"library get --url: only .glb or a .zip of glTF ({ext or 'no extension'})", "find the glTF")
    if not ok:
        return emit("fail", f"library get --url: refused — {why}", "pick another")
    _store({"source": urllib.parse.urlparse(url).hostname, "url": url, "title": title,
            "author": _arg(argv, "--author"), "licence": lic, "file": os.path.relpath(path, folder), "bytes": size,
            "sha256": sha, "kept": kept[:50], "skipped": skipped[:50],
            "use": "REFERENCE ONLY (measure / trace) — never shipped in a game"}, folder)
    return emit("pass", f"library get: '{title}' ({lic}, {size >> 20} MB) -> {path}",
                f"lune run kit refs measure \"{path}\" --name <name> --length-mm <its real length>",
                path=path.replace("\\", "/"))


def main(argv):
    if not argv:
        return emit("fail", "library: needs find | get", 'lune run kit library find "colt 1911"')
    cmd, rest = argv[0], argv[1:]
    try:
        if cmd == "find":
            return cmd_find(rest)
        if cmd == "get":
            return cmd_get(rest)
    except Exception as e:  # noqa: BLE001 — said plainly, never with the token
        msg = str(e)
        tok = _token()
        if tok:
            msg = msg.replace(tok, "<token>")
        return emit("fail", f"library {cmd}: {type(e).__name__}: {msg[:200]}", "check the network / the uid; retry")
    return emit("fail", f"library: unknown '{cmd}' (find | get)", 'lune run kit library find "colt 1911"')


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
