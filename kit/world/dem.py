"""dem.py — REAL land for kit worlds: a bounding box of USGS 3DEP elevation (public domain; credit: "USGS National Map
3D Elevation Program (3DEP)"; VETLOG.md) -> a float32 GeoTIFF + a JSON sidecar the terrain designer reads.

    python kit/world/dem.py fetch --bbox <lon0,lat0,lon1,lat1> --out <file.dem.tif> [--size 512]
    python kit/world/dem.py info <file.dem.tif>
    (normally: lune run kit world dem <Name> --bbox ... ; a design then says "dem": {"file": ..., ...})

The export comes from the 3DEP ImageServer's exportImage (F32, bilinear, uncompressed TIFF: Pillow reads it, no GDAL).
Only https://elevation.nationalmap.gov is contacted; the answer is size-capped and must be a little-endian TIFF of the
asked size. The sidecar records the box, the real width / height in metres (from the latitude), the metres per
pixel, the elevation range and the credit line — so the designer can keep slopes TRUE (horizontal and vertical in
the same unit). US coverage only (3DEP); elsewhere Copernicus GLO-30 (attribution required) is the planned source.
Prints one JSON verdict line.
"""

import io
import json
import math
import os
import sys
import urllib.parse
import urllib.request

HOST = "elevation.nationalmap.gov"
EXPORT = f"https://{HOST}/arcgis/rest/services/3DEPElevation/ImageServer/exportImage"
CREDIT = "USGS National Map 3D Elevation Program (3DEP) - public domain"
MAX_BYTES = 80_000_000  # a 4096 x 4096 float32 export is 64 MB


def box_metres(lon0, lat0, lon1, lat1):
    """the box's real width (east-west) and height (north-south) in metres (a sphere is plenty at this size)"""
    r = 6371008.8
    mid = math.radians((lat0 + lat1) / 2)
    return (math.radians(abs(lon1 - lon0)) * r * math.cos(mid), math.radians(abs(lat1 - lat0)) * r)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """the service is asked at one host: an answer that sends the question elsewhere is refused BEFORE it is followed"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError(f"redirected off {HOST}: {newurl}")


def fetch(bbox, out, size):
    lon0, lat0, lon1, lat1 = bbox
    if not (-180 <= lon0 < lon1 <= 180 and -90 <= lat0 < lat1 <= 90):
        raise ValueError("bbox is lon0,lat0,lon1,lat1 with lon0 < lon1 and lat0 < lat1")
    # a square grid needs a square box: asked for size x size pixels over a box that is not square on its own grid
    # (the web map's), the service WIDENS the box about its middle until it is (measured 2026-11-15: a fresh reader
    # asked it what it covers). The heights are of that square, and so is the size written beside them - not of
    # the box as typed (before: a tall box's heights were laid on its narrow width, and every slope was too steep)
    import imagery as _im

    on = _im.ground([lon0, lat0, lon1, lat1])
    w_m = h_m = on["side_m"]
    q = {"bbox": f"{lon0},{lat0},{lon1},{lat1}", "bboxSR": "4326", "size": f"{size},{size}", "format": "tiff",
         "pixelType": "F32", "noDataInterpretation": "esriNoDataMatchAny",
         "interpolation": "RSP_BilinearInterpolation", "compression": "None", "f": "image"}
    url = EXPORT + "?" + urllib.parse.urlencode(q)
    req = urllib.request.Request(url, headers={"User-Agent": "roblox-kit (kit world dem)"})
    with urllib.request.build_opener(NoRedirect).open(req, timeout=300) as r:
        final = urllib.parse.urlparse(r.geturl())
        if final.scheme != "https" or final.hostname != HOST:
            raise ValueError(f"redirected off {HOST}: {r.geturl()}")
        data = r.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("the export is larger than the cap")
    if data[:4] != b"II*\x00":
        raise ValueError(f"not a little-endian TIFF (the service said: {data[:200]!r})")
    from PIL import Image
    import numpy as np

    im = Image.open(io.BytesIO(data))
    if im.mode != "F" or im.size != (size, size):
        raise ValueError(f"unexpected raster {im.mode} {im.size}")
    a = np.asarray(im, dtype=np.float32)
    valid = np.isfinite(a) & (a > -1000)
    if valid.mean() < 0.98:
        raise ValueError(f"{(1 - valid.mean()) * 100:.1f} % no-data cells (outside 3DEP coverage?)")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "wb") as fh:
        fh.write(data)
    meta = {"source": "USGS 3DEP ImageServer exportImage", "credit": CREDIT, "bbox": [lon0, lat0, lon1, lat1],
            "size": size, "covers": on, "width_m": round(w_m, 1), "height_m": round(h_m, 1),
            "m_per_px": [round(w_m / size, 3), round(h_m / size, 3)],
            "elevation_m": [round(float(a[valid].min()), 2), round(float(a[valid].max()), 2)]}
    with open(sidecar(out), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(meta, fh, indent=1)
    return meta


def sidecar(path):
    return os.path.splitext(path)[0] + ".json"


def load(path, n):
    """a fetched DEM -> (heights in METRES resampled to n x n [x, z] with north at -z, its sidecar)"""
    from PIL import Image
    import numpy as np

    im = Image.open(path)
    if im.mode != "F":
        im = im.convert("F")
    im = im.resize((n, n), Image.BILINEAR)
    h = np.asarray(im, dtype=np.float64).T  # image x = world x (east), image y = world z (south: north is -z)
    meta = {}
    if os.path.isfile(sidecar(path)):
        with open(sidecar(path), encoding="utf-8") as fh:
            meta = json.load(fh)
    return h, meta


def main(argv):
    if len(argv) >= 2 and argv[0] == "info":
        if not os.path.isfile(sidecar(argv[1])):
            print(json.dumps({"status": "fail", "summary": f"no sidecar for {argv[1]}", "next_action": "fetch it with kit world dem"}))
            return 1
        meta = json.load(open(sidecar(argv[1]), encoding="utf-8"))
        print(json.dumps({"status": "pass", "summary": f"{argv[1]}: {meta['width_m'] / 1000:.2f} x {meta['height_m'] / 1000:.2f} km, "
                          f"{meta['elevation_m'][0]:.0f}-{meta['elevation_m'][1]:.0f} m", "meta": meta}))
        return 0
    if not argv or argv[0] != "fetch" or "--bbox" not in argv or "--out" not in argv:
        print(json.dumps({"status": "fail", "summary": "usage: dem.py fetch --bbox lon0,lat0,lon1,lat1 --out <file.dem.tif> [--size 512]",
                          "next_action": "lune run kit world dem <Name> --bbox lon0,lat0,lon1,lat1"}))
        return 2
    bbox = [float(v) for v in argv[argv.index("--bbox") + 1].split(",")]
    out = argv[argv.index("--out") + 1]
    size = int(argv[argv.index("--size") + 1]) if "--size" in argv else 512
    if len(bbox) != 4 or not 16 <= size <= 4096:
        print(json.dumps({"status": "fail", "summary": "bbox needs 4 numbers; size 16..4096", "next_action": "fix the arguments"}))
        return 2
    try:
        meta = fetch(bbox, out, size)
    except Exception as e:  # noqa: BLE001 — one verdict line whatever went wrong
        print(json.dumps({"status": "fail", "summary": f"dem: {e}", "next_action": "check the box (US land only: 3DEP) and the network"}))
        return 1
    print(json.dumps({"status": "pass",
                      "summary": f"dem: {meta['width_m'] / 1000:.2f} x {meta['height_m'] / 1000:.2f} km at {meta['m_per_px'][0]:.1f} m/px, "
                                 f"{meta['elevation_m'][0]:.0f}-{meta['elevation_m'][1]:.0f} m -> {out}",
                      "next_action": 'use it in a design: "dem": {"file": "' + out.replace(os.sep, "/") + '", "vexag": 1, "blur": 1} '
                                     "then lune run kit world terrain <Name> --design <file>",
                      "meta": meta}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
