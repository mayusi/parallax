"""find.py — search FREE, licensed reference pictures for an object and download them with their licence attached.

    python kit/refs/find.py "treasure chest" [--n 16] [--licenses cc0,pdm,by,by-sa] [--out build/refs/<slug>]

Sources (anonymous HTTPS, no login, no key): Openverse (api.openverse.org — Creative Commons images from Flickr,
Wikimedia, museums...; anonymous limit 20 requests a minute / 200 a day), Wikimedia Commons (its own API: licence and
author per file), The Met (collectionapi.metmuseum.org: Open Access objects are CC0 — its Arms & Armor and decorative
arts are real weapons, chests and tools — v1.1 search, v1 objects) and the Cleveland Museum of Art
(openaccess-api.clevelandart.org: CC0 works only). The museums' records carry the object's REAL DIMENSIONS, kept with
each picture (dimensions / dimensions_parsed): a spec's length_mm from the object itself. `--dry` lists what would be
fetched (titles, licences, dimensions) without downloading a picture. Only licences that allow commercial use AND changes are kept by default: CC0, public domain (pdm),
CC BY, CC BY-SA — never NC (non-commercial) or ND (no derivatives). Every picture is saved beside a .json with its
title, author, licence, licence URL, source page and retrieval date; `kit refs pick` turns a chosen one into
refs/<name>_<view>.<ext> + a SOURCES.md row. This is the ONLY kit tool that reaches the network for references: the
ranking that follows (kit/vision/run.py rank) runs offline.
"""

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

UA = os.environ.get("KIT_REFS_UA") or "roblox-kit-refs/1.0 (local reference search for a Roblox content kit)"
OK_LICENSES = {"cc0", "pdm", "by", "by-sa"}
MAX_BYTES = 15 * 1024 * 1024
# a reference to TRACE wants every pixel the photographer took: the ORIGINAL file up to this size (a thumbnail only
# beyond it). The 1600-px thumbnails this used to save cut a Colt 1911 shot at 8688 px to a fifth of its detail
# (the Silverballer test, 2026-10-07: part outlines traced from them came out jagged)
MAX_ORIGINAL = 40 * 1024 * 1024
TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


def _get(url, timeout=30, limit=MAX_BYTES):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        data = r.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"over {limit // (1024 * 1024)} MB")
    return data, ctype


def slug(text):
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:48] or "refs"


def _licence(short):
    """a Commons licence name -> openverse-style code (cc0 / pdm / by / by-sa / nc...), None when unknown"""
    s = (short or "").lower().replace("_", " ")
    if "cc0" in s or "cc-zero" in s:
        return "cc0"
    if "public domain" in s or s.startswith("pd"):
        return "pdm"
    if s.startswith("cc by") or s.startswith("cc-by"):
        if "nc" in s.split("-") or " nc" in s or "-nc" in s:
            return "by-nc"
        if "nd" in s.split("-") or " nd" in s or "-nd" in s:
            return "by-nd"
        return "by-sa" if "sa" in s else "by"
    return None


def _strip(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html or "")).strip()


def openverse(query, n, licenses):
    q = urllib.parse.urlencode({"q": query, "license": ",".join(sorted(licenses)), "page_size": min(n, 50),
                                "mature": "false"})
    data, _ = _get(f"https://api.openverse.org/v1/images/?{q}")
    out = []
    for r in json.loads(data).get("results", []):
        lic = (r.get("license") or "").lower()
        if lic not in licenses:
            continue
        out.append({"source": "openverse/" + (r.get("provider") or "?"), "id": r.get("id"), "title": r.get("title") or "",
                    "creator": r.get("creator") or "", "license": lic, "license_version": r.get("license_version") or "",
                    "license_url": r.get("license_url") or "", "page": r.get("foreign_landing_url") or "",
                    "url": r.get("url"), "width": r.get("width"), "height": r.get("height")})
    return out


def wikimedia(query, n, licenses):
    q = urllib.parse.urlencode({"action": "query", "generator": "search", "gsrsearch": query, "gsrnamespace": 6,
                                "gsrlimit": min(n, 50), "prop": "imageinfo", "iiprop": "url|extmetadata|size|mime",
                                "iiurlwidth": 1600, "format": "json"})
    data, _ = _get(f"https://commons.wikimedia.org/w/api.php?{q}")
    out = []
    for p in (json.loads(data).get("query") or {}).get("pages", {}).values():
        ii = (p.get("imageinfo") or [{}])[0]
        em = ii.get("extmetadata") or {}
        lic = _licence((em.get("LicenseShortName") or {}).get("value"))
        if lic not in licenses or ii.get("mime") not in TYPES:
            continue
        out.append({"source": "wikimedia", "id": str(p.get("pageid")), "title": p.get("title", "").replace("File:", ""),
                    "creator": _strip((em.get("Artist") or {}).get("value")), "license": lic,
                    "license_version": (em.get("LicenseShortName") or {}).get("value", ""),
                    "license_url": (em.get("LicenseUrl") or {}).get("value", ""), "page": ii.get("descriptionurl", ""),
                    "url": (ii.get("url") if ii.get("url") and (ii.get("size") or 0) <= MAX_ORIGINAL
                            else ii.get("thumburl") or ii.get("url")),
                    "original": bool(ii.get("url") and (ii.get("size") or 0) <= MAX_ORIGINAL),
                    "width": ii.get("width"), "height": ii.get("height")})
    return out


# words that say WHERE or HOW a picture looks, not WHAT is in it: a museum's full-text search matches them anywhere in a
# record (a cabinet came back for "glock 17 gen 5 left side slide markings")
_VIEW_WORDS = {"left", "right", "side", "sides", "front", "back", "rear", "top", "bottom", "view", "views", "close",
               "closeup", "detail", "details", "markings", "marking", "the", "and", "with", "for", "from", "gen", "new",
               "old", "photo", "picture", "image", "real", "full", "part", "parts", "angle", "profile"}


def _relevant(query, *texts):
    """a museum record is about the query when one of the query's own words (not a view word) is in the object's
    own name — its title, object name, classification or tags; not just somewhere in its catalogue text"""
    words = {w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) >= 3 and w not in _VIEW_WORDS
             and not w.isdigit()}
    if not words:
        return True
    own = set(re.findall(r"[a-z0-9]+", " ".join(t for t in texts if t).lower()))
    return bool(words & own) or any(w + "s" in own or w.rstrip("s") in own for w in words)


def met(query, n, licenses):
    """The Met: only Open Access objects (isPublicDomain: CC0), with their measured dimensions (cm) — and only those
    whose own name shares a word with the query (its search matches anywhere in a record)"""
    if "cc0" not in licenses:
        return []
    q = urllib.parse.urlencode({"q": query, "hasImages": "true", "limit": max(3 * n, 24)})
    data, _ = _get(f"https://collectionapi.metmuseum.org/public/collection/v1.1/search?{q}")
    out = []
    for oid in (json.loads(data).get("objectIDs") or [])[:3 * n]:
        if len(out) >= n:
            break
        try:
            rec = json.loads(_get(f"https://collectionapi.metmuseum.org/public/collection/v1/objects/{oid}")[0])
        except Exception:  # noqa: BLE001 — one record down is skipped
            continue
        if not rec.get("isPublicDomain") or not rec.get("primaryImage"):
            continue
        if not _relevant(query, rec.get("title"), rec.get("objectName"), rec.get("classification"),
                         " ".join(t.get("term", "") for t in (rec.get("tags") or []) if isinstance(t, dict))):
            continue
        out.append({"source": "met", "id": str(oid), "title": rec.get("title") or rec.get("objectName") or "",
                    "creator": rec.get("artistDisplayName") or rec.get("culture") or "", "license": "cc0",
                    "license_version": "CC0 1.0 (The Met Open Access)",
                    "license_url": "https://creativecommons.org/publicdomain/zero/1.0/", "page": rec.get("objectURL") or "",
                    "url": rec["primaryImage"], "width": None, "height": None,
                    "dimensions": rec.get("dimensions") or "", "dimensions_parsed": rec.get("dimensionsParsed")})
    return out


def cleveland(query, n, licenses):
    """The Cleveland Museum of Art: only CC0 works (share_license_status), with their dimensions (metres)"""
    if "cc0" not in licenses:
        return []
    q = urllib.parse.urlencode({"q": query, "cc0": "", "has_image": 1, "limit": n})
    data, _ = _get(f"https://openaccess-api.clevelandart.org/api/artworks/?{q}")
    out = []
    for r in json.loads(data).get("data") or []:
        web = (r.get("images") or {}).get("web") or {}
        if (r.get("share_license_status") or "").upper() != "CC0" or not web.get("url"):
            continue
        if not _relevant(query, r.get("title"), r.get("type")):
            continue
        out.append({"source": "cleveland", "id": str(r.get("id")), "title": r.get("title") or "",
                    "creator": "; ".join(c.get("description") or "" for c in r.get("creators") or []), "license": "cc0",
                    "license_version": "CC0 1.0 (Cleveland Museum of Art Open Access)",
                    "license_url": "https://creativecommons.org/publicdomain/zero/1.0/", "page": r.get("url") or "",
                    "url": web["url"], "width": int(web.get("width") or 0) or None,
                    "height": int(web.get("height") or 0) or None, "dimensions": r.get("measurements") or "",
                    "dimensions_parsed": r.get("dimensions")})
    return out


def main(argv):
    if not argv or argv[0].startswith("--"):
        print(json.dumps({"schema": 1, "status": "fail", "summary": "refs find: needs what to search for",
                          "next_action": 'lune run kit refs find "treasure chest"'}))
        return 1
    query = argv[0]

    def opt(name, default):
        return argv[argv.index(name) + 1] if name in argv else default
    n = int(opt("--n", 16))
    licenses = {x.strip().lower() for x in opt("--licenses", ",".join(sorted(OK_LICENSES))).split(",")}
    bad = licenses - OK_LICENSES
    if bad:
        print(json.dumps({"schema": 1, "status": "fail", "summary": f"refs find: {', '.join(sorted(bad))} not allowed "
                          "(non-commercial or no-derivatives licences cannot be used in a game)",
                          "next_action": "use cc0, pdm, by, by-sa"}))
        return 1
    out_dir = opt("--out", os.path.join("build", "refs", slug(query)))
    os.makedirs(out_dir, exist_ok=True)
    found, errors = [], []
    for name, fn in (("openverse", openverse), ("wikimedia", wikimedia), ("met", met), ("cleveland", cleveland)):
        try:
            found += fn(query, n, licenses)
        except Exception as e:  # noqa: BLE001 — one source down is reported, never fatal
            errors.append(f"{name}: {e}")
    # biggest first (detail to trace), then interleave sources so one provider cannot fill the set
    found.sort(key=lambda r: -((r.get("width") or 0) * (r.get("height") or 0)))
    picked, seen = [], set()
    while found and len(picked) < n:
        for src in sorted({r["source"].split("/")[0] for r in found}):
            for r in list(found):
                if r["source"].split("/")[0] == src:
                    found.remove(r)
                    if r["url"] and r["url"] not in seen:
                        seen.add(r["url"])
                        picked.append(r)
                    break
            if len(picked) >= n:
                break
    if "--dry" in argv:  # what WOULD be fetched: nothing is downloaded
        print(json.dumps({"schema": 1, "status": "pass" if picked else "fail",
                          "summary": f"refs find (dry): {len(picked)} licensed result(s) for '{query}' from "
                                     f"{', '.join(sorted({r['source'].split('/')[0] for r in picked})) or 'no source'}",
                          "next_action": "run again without --dry to download them (each with its licence record)",
                          "results": [{k: r.get(k) for k in ("source", "title", "license", "page", "dimensions")}
                                      for r in picked], "errors": errors[:5]}))  # (ASCII: a cp1252 console mangles UTF-8)
        return 0 if picked else 1
    saved = []
    for i, r in enumerate(picked):
        base = f"{i + 1:02d}_{r['source'].split('/')[0]}_{slug(str(r['id']))[:24]}"
        try:
            data, ctype = _get(r["url"], timeout=120, limit=MAX_ORIGINAL if r.get("original") else MAX_BYTES)
            ext = TYPES.get(ctype)
            if not ext:
                errors.append(f"{base}: not an image ({ctype})")
                continue
            path = os.path.join(out_dir, base + ext)
            with open(path, "wb") as fh:
                fh.write(data)
            meta = dict(r, file=os.path.basename(path), bytes=len(data), query=query,
                        retrieved=time.strftime("%Y-%m-%d"))
            with open(path + ".json", "w", encoding="utf-8") as fh:
                json.dump(meta, fh, indent=1, ensure_ascii=False)
            saved.append(meta)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{base}: {e}")
    with open(os.path.join(out_dir, "found.json"), "w", encoding="utf-8") as fh:
        json.dump({"query": query, "licenses": sorted(licenses), "saved": saved, "errors": errors}, fh, indent=1,
                  ensure_ascii=False)
    ok = bool(saved)
    print(json.dumps({
        "schema": 1, "status": "pass" if ok else "fail",
        "summary": f"refs find: {len(saved)} licensed picture(s) of '{query}' in {out_dir}"
                   + (f" ({len(errors)} skipped)" if errors else ""),
        "next_action": (f"rank them: lune run kit refs rank {out_dir} --what \"{query}\"" if ok
                        else "no licensed results — try other words (the object's common name, 'side view', a model name)"),
        "out": out_dir.replace("\\", "/"), "saved": len(saved), "errors": errors[:5]}))  # (ASCII, as above)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
