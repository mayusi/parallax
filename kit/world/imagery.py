"""imagery.py - REAL GROUND COVER for kit worlds: an aerial picture of a bounding box (USDA NAIP through the USGS
National Map; public domain; VETLOG.md) and what it says of the ground, cell by cell (the owner's method list:
"Satellite imagery-based terrain").

    python kit/world/imagery.py fetch --bbox <lon0,lat0,lon1,lat1> --out <file.img.png> [--size 512]
    python kit/world/imagery.py info <file.img.png>
    (normally: lune run kit world imagery <Name> --bbox ... ; then kit world terrain <Name> ... --imagery <file>)

`kit world dem` brings a box's real HEIGHTS; this brings the same box's real LOOK from above, and reads it as the
painter's roles: where the picture is green the land is meadow (dark green: lush), where it is grey it is rock, brown
dirt, pale tan sand, white snow, dark and dull mud. It is a read of COLOUR, not a land-cover map: a grey roof reads as
rock and a shadow as mud, and the season the picture was flown in is the season it shows.
Only https://imagery.nationalmap.gov is contacted; the answer is size-capped and must be a PNG of the asked size that
is not blank. The sidecar records the box, its real size in metres, the metres a pixel and the credit line.
US coverage only (NAIP). Prints one JSON verdict line. The picture is for local use: it is not committed or uploaded;
only the roles read from it go into a world."""

import io
import json
import math
import os
import sys
import urllib.parse
import urllib.request

HOST = "imagery.nationalmap.gov"
EXPORT = f"https://{HOST}/arcgis/rest/services/USGSNAIPImagery/ImageServer/exportImage"
CREDIT = "USDA FSA National Agriculture Imagery Program (NAIP), via the USGS National Map - public domain"
MAX_BYTES = 40_000_000
ROLES = ("meadow", "lush", "dirt", "mud", "rock", "snow", "sand")  # (what a colour can say; cliff and scree are shapes)
WATER = "water"  # (read, and left to the land's own water: no painter's role)


def box_metres(lon0, lat0, lon1, lat1):
    """the box's real width (east-west) and height (north-south) in metres"""
    r = 6371008.8
    mid = math.radians((lat0 + lat1) / 2)
    return (math.radians(abs(lon1 - lon0)) * r * math.cos(mid), math.radians(abs(lat1 - lat0)) * r)


MERCATOR_R = 6378137.0


def mercator(lon, lat):
    """a place on the web map's own grid (EPSG 3857 / Esri 102100), metres"""
    return (MERCATOR_R * math.radians(lon), MERCATOR_R * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)))


def unmercator(x, y):
    return (math.degrees(x / MERCATOR_R), math.degrees(2 * math.atan(math.exp(y / MERCATOR_R)) - math.pi / 2))


def covered(bbox):
    """THE GROUND A BOX'S HEIGHTS REALLY COVER (measured 2026-11-15, a fresh reader's find): asked for a square grid
    over a box that is not square on the web map's grid, the elevation service widens the box about its middle
    until it is - so `kit world dem`'s heights are of THIS square, not of the box as typed. The picture is asked for
    this same square, in the same grid, so that both lie on the same ground -> (xmin, ymin, xmax, ymax), metres"""
    lon0, lat0, lon1, lat1 = bbox
    x0, y0 = mercator(lon0, lat0)
    x1, y1 = mercator(lon1, lat1)
    side = max(x1 - x0, y1 - y0)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return (cx - side / 2, cy - side / 2, cx + side / 2, cy + side / 2)


def ground(bbox):
    """what `covered` is on the ground -> {"lon": [w, e], "lat": [s, n], "side_m": its real side}"""
    x0, y0, x1, y1 = covered(bbox)
    lon_w, lat_s = unmercator(x0, y0)
    lon_e, lat_n = unmercator(x1, y1)
    side = (x1 - x0) * math.cos(math.radians((lat_s + lat_n) / 2))  # (the web map stretches by 1 / cos(latitude))
    return {"lon": [round(lon_w, 6), round(lon_e, 6)], "lat": [round(lat_s, 6), round(lat_n, 6)], "side_m": round(side, 1)}


def query(bbox, size):
    """the export's question for a box -> the URL: the picture's three colour bands, north up, over the square the
    box's heights cover (`covered`), asked in the web map's grid so that the service has nothing to widen"""
    lon0, lat0, lon1, lat1 = bbox
    if not (-180 <= lon0 < lon1 <= 180 and -85 <= lat0 < lat1 <= 85):
        raise ValueError("bbox is lon0,lat0,lon1,lat1 with lon0 < lon1 and lat0 < lat1 (latitudes within 85)")
    if not (isinstance(size, int) and 16 <= size <= 2048):
        raise ValueError("size is 16..2048")
    x0, y0, x1, y1 = covered(bbox)
    q = {"bbox": f"{x0!r},{y0!r},{x1!r},{y1!r}", "bboxSR": "102100", "imageSR": "102100", "size": f"{size},{size}",
         "format": "png", "bandIds": "0,1,2", "interpolation": "RSP_BilinearInterpolation", "f": "image"}
    return EXPORT + "?" + urllib.parse.urlencode(q)


def accept(data, size):
    """what came back, held to what was asked -> an RGB array [row, col, 3] (row 0 = north); raises ValueError"""
    from PIL import Image
    import numpy as np

    if len(data) > MAX_BYTES:
        raise ValueError("the export is larger than the cap")
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"not a PNG (the service said: {data[:200]!r})")
    im = Image.open(io.BytesIO(data))
    if im.size != (size, size):
        raise ValueError(f"unexpected picture {im.size}, asked {size} x {size}")
    alpha = np.asarray(im.convert("RGBA"))[:, :, 3]
    if (alpha < 128).mean() > 0.02:
        raise ValueError(f"{(alpha < 128).mean() * 100:.1f} % of the picture is empty (outside NAIP coverage?)")
    a = np.asarray(im.convert("RGB"), dtype=np.uint8)
    if a.std() < 2.0:
        raise ValueError("the picture is one flat colour (outside NAIP coverage?)")
    black = float((a.max(axis=2) == 0).mean())  # (where it has no flight the service may send black, not clear)
    if black > 0.02:
        raise ValueError(f"{black * 100:.1f} % of the picture is black (outside NAIP coverage?)")
    return a


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """the service is asked at one host: an answer that sends the question elsewhere is refused BEFORE it is followed"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError(f"redirected off {HOST}: {newurl}")


def ask(url):
    """the bytes the service answers with (one host, https, no redirect, under the cap)"""
    req = urllib.request.Request(url, headers={"User-Agent": "roblox-kit (kit world imagery)"})
    with urllib.request.build_opener(NoRedirect).open(req, timeout=300) as r:
        final = urllib.parse.urlparse(r.geturl())
        if final.scheme != "https" or final.hostname != HOST:
            raise ValueError(f"redirected off {HOST}: {r.geturl()}")
        return r.read(MAX_BYTES + 1)


def fetch(bbox, out, size):
    data = ask(query(bbox, size))
    a = accept(data, size)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "wb") as fh:
        fh.write(data)
    share = cover(read(a))
    on = ground(bbox)
    # (the box as asked, and the ground the picture really shows: the square the box's heights cover)
    meta = {"source": "USGS National Map NAIP ImageServer exportImage", "credit": CREDIT, "bbox": list(bbox), "size": size,
            "covers": on, "width_m": on["side_m"], "height_m": on["side_m"],
            "m_per_px": [round(on["side_m"] / size, 3), round(on["side_m"] / size, 3)], "cover": share}
    with open(sidecar(out), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(meta, fh, indent=1)
    return meta


def sidecar(path):
    return os.path.splitext(path)[0] + ".json"


def read(rgb):
    """WHAT A PICTURE SAYS OF THE GROUND: an RGB array [.., .., 3] (0..255) -> an array of the same shape of names
    (ROLES, or WATER), by colour alone. v = the brightest band 0..1, s = how coloured (0 grey .. 1 pure):
       very white (v >= 0.92, s <= 0.08)                 snow
       blue (over red by 15 %, over green), v < 0.7       water
       green (over red and blue by 4 %, s >= 0.12)        meadow; dark (v < 0.35): lush
       grey (s < 0.15), v >= 0.25                         rock
       warm (red >= green >= blue), pale (s < 0.38), v >= 0.6   sand
       dark and dull (v < 0.25, s < 0.3)                  mud
       anything else                                      dirt
    Known to be read wrong, and said: snow in shadow (dirt or water), pale granite and cloud near white (snow when
    very white), asphalt and deep shadow (mud), a muddy river (dirt or meadow), dry yellow grass (dirt)."""
    import numpy as np

    a = np.asarray(rgb, dtype=float) / 255.0
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    v = np.maximum(np.maximum(r, g), b)
    lo = np.minimum(np.minimum(r, g), b)
    s = np.where(v > 0, (v - lo) / np.maximum(v, 1e-9), 0.0)
    out = np.full(v.shape, "dirt", dtype=object)
    warm = (r >= g) & (g >= b) & (s >= 0.15) & (s < 0.38)
    out[warm & (v >= 0.6)] = "sand"
    out[(s < 0.15) & (v >= 0.25)] = "rock"
    out[(v < 0.25) & (s < 0.3)] = "mud"
    green = (g > r * 1.04) & (g > b * 1.04) & (s >= 0.12)
    out[green] = "meadow"
    out[green & (v < 0.35)] = "lush"
    out[(b > r * 1.15) & (b > g * 1.02) & (v < 0.7)] = WATER
    out[(v >= 0.92) & (s <= 0.08)] = "snow"
    return out


def cover(names):
    """the share of each name in a read -> {name: share} (only those that occur), shares rounded to a thousandth"""
    import numpy as np

    total = names.size
    return {str(k): round(float(n) / total, 3) for k, n in zip(*np.unique(names, return_counts=True))}


def load(path, n):
    """a fetched picture -> (names on an n x n grid [x, z] with north at -z, its sidecar): the same grid `dem.load`
    hands the heights back on. The picture is READ at its own size and each cell of the grid takes the name that
    covers most of it (colours are never mixed before they are read: half lush and half sand is not a meadow)"""
    from PIL import Image
    import numpy as np

    full = read(np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8))
    best, names = None, None
    for name in ROLES + (WATER,):
        mask = Image.fromarray(((full == name) * 255).astype(np.uint8), "L")
        share = np.asarray(mask.resize((n, n), Image.BOX), dtype=float)
        if best is None:
            best, names = share, np.full((n, n), name, dtype=object)
        else:
            more = share > best
            names[more] = name
            best = np.where(more, share, best)
    names = names.T  # image x = world x (east), image y = world z (north is -z)
    meta = {}
    if os.path.isfile(sidecar(path)):
        with open(sidecar(path), encoding="utf-8") as fh:
            meta = json.load(fh)
    return names, meta


def main(argv):
    if len(argv) >= 2 and argv[0] == "info":
        if not os.path.isfile(sidecar(argv[1])):
            print(json.dumps({"status": "fail", "summary": f"no sidecar for {argv[1]}", "next_action": "fetch it with kit world imagery"}))
            return 1
        meta = json.load(open(sidecar(argv[1]), encoding="utf-8"))
        print(json.dumps({"status": "pass", "summary": f"{argv[1]}: {meta['width_m'] / 1000:.2f} x {meta['height_m'] / 1000:.2f} km, "
                          f"{meta['m_per_px'][0]:.1f} m a pixel", "meta": meta}))
        return 0
    if not argv or argv[0] != "fetch" or "--bbox" not in argv or "--out" not in argv:
        print(json.dumps({"status": "fail", "summary": "usage: imagery.py fetch --bbox lon0,lat0,lon1,lat1 --out <file.img.png> [--size 512]",
                          "next_action": "lune run kit world imagery <Name> --bbox lon0,lat0,lon1,lat1"}))
        return 2
    try:
        bbox = [float(v) for v in argv[argv.index("--bbox") + 1].split(",")]
        size = int(argv[argv.index("--size") + 1]) if "--size" in argv else 512
        if len(bbox) != 4:
            raise ValueError("bbox needs 4 numbers")
    except (ValueError, IndexError) as e:
        print(json.dumps({"status": "fail", "summary": f"imagery: {e}", "next_action": "fix the arguments"}))
        return 2
    out = argv[argv.index("--out") + 1]
    try:
        meta = fetch(bbox, out, size)
    except Exception as e:  # noqa: BLE001 - one verdict line whatever went wrong
        print(json.dumps({"status": "fail", "summary": f"imagery: {e}", "next_action": "check the box (US land only: NAIP) and the network"}))
        return 1
    most = sorted(meta["cover"].items(), key=lambda kv: -kv[1])[:4]
    print(json.dumps({"status": "pass",
                      "summary": f"imagery: {meta['width_m'] / 1000:.2f} km square (the ground the box's heights cover: latitude "
                                 f"{meta['covers']['lat'][0]:.4f} to {meta['covers']['lat'][1]:.4f}, longitude "
                                 f"{meta['covers']['lon'][0]:.4f} to {meta['covers']['lon'][1]:.4f}) at {meta['m_per_px'][0]:.1f} m a "
                                 f"pixel, read as {', '.join(f'{k} {v:.0%}' for k, v in most)} -> {out}",
                      "next_action": "LOOK at the picture; then lune run kit world terrain <Name> ... --imagery " + out.replace(os.sep, "/"),
                      "meta": meta}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
