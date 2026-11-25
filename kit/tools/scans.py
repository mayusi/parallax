"""scans.py — the scanned PBR materials a.material(..., scan=) reads (ambientCG, CC0 1.0: VETLOG.md).

    python kit/tools/scans.py                 # the scans this machine has: id, real tile size, maps, source
    python kit/tools/scans.py --fetch Bark014 Rust009 ...   # fetch these exact scans (2K-JPG) — the owner's OK first
    python kit/tools/scans.py --fetch Grass004 ... --res 1K # 1K-JPG (terrain: a Roblox MaterialVariant takes 1024 px)

A scan is a DOWNLOAD: the owner approves the exact list (ids and total size) before --fetch, and the fetch is logged
in VETLOG.md. Each one is checked like this, then pinned in ~/.cache/roblox-kit/materials/pins.json (KIT_MATERIALS
overrides) — the file rbx_scans reads:
  - its download link and byte count come from ambientCG's own API (api/v2/full_json, no key, no account); every
    request and every redirect stays on https and on ambientCG's hosts (its /get link sends the file from its download
    host, acg-download.struffelproductions.com) — nothing else is ever contacted;
  - nothing is read past its size: the API's answer is capped, the zip at the byte count the API lists, each map in
    it at MAX_MAP bytes;
  - the zip lands in a fresh temp folder first; its size must equal the API's, its sha256 is recorded (an id already
    pinned must match its pin);
  - every zip entry is checked (no absolute path, no "..", no drive) and ONLY the image maps (.jpg / the .png
    preview) are extracted — the bundled .blend / .usdc / .mtlx / .tres scene files are never opened;
  - the tile's real size (ambientCG's dimensions, cm) is pinned: a.material tiles the scan at that size.
"""

import hashlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile

ROOT = os.environ.get("KIT_MATERIALS") or os.path.join(os.path.expanduser("~"), ".cache", "roblox-kit", "materials")
API = "https://ambientcg.com/api/v2/full_json"
HOSTS = ("ambientcg.com", "acg-download.struffelproductions.com")   # (the API and /get; the host /get redirects to)
RES = "2K-JPG"
MAX_API = 8_000_000      # bytes: one asset's API record
MAX_MAP = 200_000_000    # bytes: one map inside a zip (a 2K map is ~5-15 MB)
ID_RE = re.compile(r"^[A-Za-z0-9]{3,40}$")
UA = {"User-Agent": "roblox-kit-scans/1"}
MAP_EXT = (".jpg", ".png")


def _pins(root):
    path = os.path.join(root, "pins.json")
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _save_pins(root, pins):
    path = os.path.join(root, "pins.json")
    with open(path + ".tmp", "w", encoding="utf-8", newline="\n") as fh:
        json.dump(pins, fh, indent=1)
    os.replace(path + ".tmp", path)


def safe_member(name):
    """a zip entry that stays inside its folder: no absolute path, no drive, no '..' -> True"""
    n = name.replace("\\", "/")
    return bool(n) and not n.startswith("/") and ":" not in n and ".." not in n.split("/")


def map_members(names, asset_id, res=RES):
    """the zip entries to extract: <id>_<res>_<Map>.jpg and the <id>.png preview, flat (no folders) -> [name]"""
    keep = []
    for n in names:
        if not safe_member(n) or "/" in n.replace("\\", "/"):
            continue
        low = n.lower()
        if not low.endswith(MAP_EXT):
            continue
        if n.startswith(f"{asset_id}_{res}_") or n == f"{asset_id}.png":
            keep.append(n)
    return sorted(keep)


def tile_cm(asset):
    """ambientCG's real size of one repeat, cm -> [x, y] or None (0 = not listed)"""
    x, y = asset.get("dimensionX") or 0, asset.get("dimensionY") or 0
    return [x, y] if x and y else None


def allowed(url):
    """https, on one of ambientCG's hosts -> True"""
    u = urllib.parse.urlparse(url)
    return u.scheme == "https" and (u.hostname or "") in HOSTS


class _Stay(urllib.request.HTTPRedirectHandler):
    """follow a redirect only to https on ambientCG's hosts"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not allowed(newurl):
            raise ValueError(f"refused: a redirect to {newurl} (not https on {', '.join(HOSTS)})")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _get(url, timeout=120, limit=MAX_API):
    """the bytes at url (https on ambientCG's hosts, every redirect too), never more than `limit`"""
    if not allowed(url):
        raise ValueError(f"refused: {url} is not https on {', '.join(HOSTS)}")
    opener = urllib.request.build_opener(_Stay)
    with opener.open(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        blob = r.read(limit + 1)
    if len(blob) > limit:
        raise ValueError(f"refused: {url} sends more than {limit} bytes")
    return blob


def lookup(asset_id, res=RES):
    """ambientCG's record of one id -> (asset, download {fileName, size, link})"""
    if not ID_RE.match(asset_id or ""):
        raise ValueError(f"{asset_id!r}: not an ambientCG id (letters and digits)")
    q = urllib.parse.urlencode({"id": asset_id, "include": "downloadData,dimensionsData,tagData"})
    data = json.loads(_get(f"{API}?{q}"))
    hits = [a for a in data.get("foundAssets", []) if a.get("assetId") == asset_id]
    if not hits:
        raise LookupError(f"{asset_id}: not on ambientCG")
    a = hits[0]
    dls = [x for f in a.get("downloadFolders", {}).values() for c in f.get("downloadFiletypeCategories", {}).values()
           for x in c.get("downloads", []) if x.get("attribute") == res]
    if not dls:
        raise LookupError(f"{asset_id}: no {res} download")
    d = dls[0]
    if d.get("fileName") != f"{asset_id}_{res}.zip":   # (it names a file in the cache: nothing else is written)
        raise ValueError(f"{asset_id}: the API names its file {d.get('fileName')!r}, not {asset_id}_{res}.zip")
    return a, {"fileName": d["fileName"], "size": int(d["size"]), "link": d.get("downloadLink") or d["fullDownloadPath"]}


def fetch(asset_id, root=ROOT, res=RES):
    """download, check and pin one scan -> its pins.json row. A non-2K fetch is its own pin and folder,
    "<id>@1K" (a 1K terrain scan and a 2K model scan of the same id never overwrite each other)"""
    os.makedirs(root, exist_ok=True)
    pins = _pins(root)
    key = asset_id if res == RES else f"{asset_id}@{res.split('-')[0]}"
    a, d = lookup(asset_id, res)
    tmp = tempfile.mkdtemp(prefix="kit_scan_")
    try:
        blob = _get(d["link"], timeout=600, limit=d["size"])
        if len(blob) != d["size"]:
            raise ValueError(f"{asset_id}: {len(blob)} bytes, ambientCG lists {d['size']}")
        sha = hashlib.sha256(blob).hexdigest()
        if key in pins and pins[key].get("sha256") not in (None, sha):
            raise ValueError(f"{key}: sha256 {sha[:12]} differs from its pin {pins[key]['sha256'][:12]}")
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            names = z.namelist()
            bad = [n for n in names if not safe_member(n)]
            if bad:
                raise ValueError(f"{asset_id}: unsafe zip entries {bad[:3]}")
            keep = map_members(names, asset_id, res)
            big = [n for n in keep if z.getinfo(n).file_size > MAX_MAP]
            if big:
                raise ValueError(f"{asset_id}: {big[0]} unpacks to {z.getinfo(big[0]).file_size} bytes")
            if not any(n.endswith("_Color.jpg") for n in keep):
                raise ValueError(f"{asset_id}: no colour map in the zip")
            stage = os.path.join(tmp, asset_id)
            os.makedirs(stage)
            for n in keep:
                with z.open(n) as src, open(os.path.join(stage, n), "wb") as dst:
                    shutil.copyfileobj(src, dst)
        folder = os.path.join(root, key)
        if os.path.isdir(folder):
            shutil.rmtree(folder)
        shutil.move(stage, folder)
        with open(os.path.join(root, d["fileName"]), "wb") as fh:
            fh.write(blob)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    row = {"file": d["fileName"], "size": d["size"], "sha256": sha, "maps": keep, "tile_cm": tile_cm(a),
           "source": f"https://ambientcg.com/a/{asset_id}", "license": "CC0-1.0",
           "tags": [t for t in a.get("tags", []) if not t.isdigit()][:8], "method": a.get("creationMethod"),
           "res": res, "fetched": time.strftime("%Y-%m-%d")}
    pins = _pins(root)   # (re-read: another fetch may have pinned meanwhile)
    pins[key] = row
    _save_pins(root, pins)
    return row


def listing(root=ROOT):
    pins = _pins(root)
    rows = []
    for k, v in sorted(pins.items()):
        have = all(os.path.isfile(os.path.join(root, k, m)) for m in v.get("maps", []))
        rows.append({"id": k, "tile_cm": v.get("tile_cm"), "maps": len(v.get("maps", [])), "present": have,
                     "tags": v.get("tags", []), "source": v.get("source", f"https://ambientcg.com/a/{k}")})
    return rows


def main(argv):
    if argv and argv[0] == "--fetch":
        res = RES
        if "--res" in argv:
            k = argv.index("--res")
            res = f"{argv[k + 1].upper()}-JPG" if k + 1 < len(argv) else ""
            if res not in ("1K-JPG", "2K-JPG", "4K-JPG"):
                print(json.dumps({"schema": 1, "status": "fail", "summary": "scans --res: 1K, 2K or 4K",
                                  "next_action": "python kit/tools/scans.py --fetch <ids> --res 1K"}))
                return 2
            argv = argv[:k] + argv[k + 2:]
        ids = [x for x in argv[1:] if not x.startswith("-")]
        if not ids:
            print(json.dumps({"schema": 1, "status": "fail", "summary": "scans --fetch: name the ids",
                              "next_action": "python kit/tools/scans.py --fetch Bark014 Rust009 (the owner's OK on "
                                             "the exact list first)"}))
            return 2
        done, failed = [], []
        for i in ids:
            try:
                row = fetch(i, res=res)
                done.append({"id": i, "mb": round(row["size"] / 1e6, 1), "sha256": row["sha256"],
                             "tile_cm": row["tile_cm"], "maps": len(row["maps"])})
            except Exception as e:  # noqa: BLE001 — one bad id does not stop the rest; each is reported
                failed.append({"id": i, "error": str(e)})
        mb = round(sum(x["mb"] for x in done), 1)
        print(json.dumps({"schema": 1, "status": "pass" if not failed else "fail", "fetched": done, "failed": failed,
                          "summary": f"scans: {len(done)} fetched ({mb} MB, size + sha256 checked, maps only)"
                                     + (f", {len(failed)} failed" if failed else ""),
                          "next_action": "log the fetch in VETLOG.md (ids, MB, sha256 pinned in pins.json); build "
                                         'with a.material(..., scan="<id>") or a look that names it'
                          if not failed else "read the failures above"}))
        return 0 if not failed else 1
    rows = listing()
    missing = [r["id"] for r in rows if not r["present"]]
    print(json.dumps({"schema": 1, "status": "pass" if rows and not missing else "fail", "scans": rows,
                      "summary": f"scans: {len(rows)} on this machine ({ROOT})"
                                 + (f", {len(missing)} with maps missing: {', '.join(missing)}" if missing else ""),
                      "next_action": 'a.material("<name>", ..., scan="<id>") — or a look (kit materials --looks)'
                      if rows else "no scans yet: the owner approves a list, then kit materials --fetch <ids>"}))
    return 0 if rows and not missing else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
