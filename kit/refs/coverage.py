"""coverage.py — can the pictures show the hero features? `lune run kit refs coverage <asset>`.

Each hero feature of the brief (assets/models/<asset>.brief.md: `<feature> | <route> | <what> | <picture> x0,y0,x1,y1
| <size> mm`) and each part traced in a view (assets/models/<asset>_<view>.trace.json, sized by
refs/<asset>.views.json) gets its pixels per mm in every picture that shows it: a traced picture by its own scale
(the object's length in pixels over its length in mm), a close-up by the feature's box over its size. Under 2 px/mm
at best nobody can model a hero feature from the pictures — ask the owner for a close-up (the build says the same:
`coverage`, a warning on a prop, an error on hero / aaa).

    python kit/refs/coverage.py <asset> [--root <project>]  -> the table, then one JSON result line
    python kit/refs/coverage.py <asset> --parts [--fetch N]  EVERY part of the part review: the best px/mm among the
        pictures its answer cites (traced views, library tiles / close-ups at a known scale), or a dims row; the parts
        under 2 px/mm or with no scale are named (--fetch N runs kit refs find for N of them)
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_plan as P  # noqa: E402


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def _read(path):
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def measure(asset, root=ROOT):
    """-> (the parsed brief or None, the coverage, the traces found)"""
    brief = P.load_brief(P.brief_path(asset, root=root), root)
    spec = _read(os.path.join(root, "refs", f"{asset}.spec.json"))
    views = _read(os.path.join(root, (spec or {}).get("views") or f"refs/{asset}.views.json"))
    traces = P.load_traces(asset, root)
    cov = P.coverage((brief or {}).get("hero_features") or [], traces, views, (spec or {}).get("length_mm"))
    return brief, cov, traces


def library_scales(root=ROOT):
    """{picture: px_per_mm} of every dissected reference model's pictures (kit library inspect): each part's tile and
    each --part close-up was rendered orthographically at a known mm per pixel"""
    out = {}
    folder = os.path.join(root, "refs")
    for f in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        if not f.endswith(".inspect.json"):
            continue
        d = _read(os.path.join(folder, f)) or {}
        for p in d.get("parts", []):
            if p.get("tile") and p.get("tile_mm_per_px"):
                out[P._norm_path(p["tile"])] = 1.0 / p["tile_mm_per_px"]
        for c in d.get("closeups") or []:
            if c.get("image") and c.get("mm_per_px"):
                out[P._norm_path(c["image"])] = 1.0 / c["mm_per_px"]
    return out


def parts_coverage(asset, root=ROOT):
    """EVERY part family of the part review (assets/models/<asset>.parts.md): the best px/mm among the pictures its
    answer cites (a traced view's scale, a library tile / close-up's), "measured" when it cites a dimension row, or
    unknown (no picture with a known scale) -> [{family, best_px_per_mm, picture, measured, cited}]"""
    sys.path.insert(0, HERE)
    import parts as refparts  # noqa: PLC0415  (the part review's line format)

    review = os.path.join(root, "assets", "models", f"{asset}.parts.md")
    if not os.path.isfile(review):
        return None
    _brief, _cov, traces = measure(asset, root)
    spec = _read(os.path.join(root, "refs", f"{asset}.spec.json"))
    views = _read(os.path.join(root, (spec or {}).get("views") or f"refs/{asset}.views.json"))
    scales = {k: v["px_per_mm"] for k, v in P.picture_scales(traces, views, (spec or {}).get("length_mm")).items()}
    scales.update(library_scales(root))
    out = []
    with open(review, encoding="utf-8") as fh:
        for line in fh:
            m = refparts.ENTRY.match(line.rstrip("\n"))
            if not m:
                continue
            field = refparts.review_refs.ref_field(m["body"]) or ""
            pics = refparts.review_refs._PATH.findall(field)
            known = [(scales[P._norm_path(p)], p) for p in pics if P._norm_path(p) in scales]
            best = max(known) if known else (None, None)
            out.append({"family": m["fam"], "best_px_per_mm": round(best[0], 2) if best[0] else None,
                        "picture": best[1], "measured": bool(refparts.review_refs._DIMS.search(field)), "cited": pics})
    return out


def parts_main(asset, root, fetch=0):
    rows = parts_coverage(asset, root)
    if rows is None:
        return emit("fail", f"refs coverage --parts: no assets/models/{asset}.parts.md", f"lune run kit asset {asset} --geo")
    low = [r for r in rows if r["best_px_per_mm"] is not None and r["best_px_per_mm"] < P.MIN_PX_PER_MM]
    unknown = [r for r in rows if r["best_px_per_mm"] is None and not r["measured"]]
    table = []
    for r in rows:
        state = ("measured (dims row)" if r["measured"] and r["best_px_per_mm"] is None else
                 f"{r['best_px_per_mm']:.1f} px/mm" if r["best_px_per_mm"] is not None else "scale unknown")
        flag = "  << LOW" if r in low else ("  << ?" if r in unknown else "")
        table.append(f"  {r['family'][:28]:<28} {state:<22} {(r['picture'] or (r['cited'][:1] or ['no picture'])[0])[:70]}{flag}")
    for row in table:
        print(row)
    fetched = []
    if fetch:
        import subprocess  # noqa: PLC0415

        sys.path.insert(0, HERE)
        import parts as refparts  # noqa: PLC0415  (the brief's object name, as kit refs parts searches it)

        obj = re.sub(r"^(the|a|an) ", "", refparts.short_name(refparts.brief_line(asset, "what")) or asset, flags=re.I)
        for r in (low + unknown)[:fetch]:
            q = f"{obj} {refparts_words(r['family'])} close up"
            subprocess.run([sys.executable, os.path.join(HERE, "find.py"), q, "--n", "8"], capture_output=True, timeout=600)
            fetched.append(q)
    n_bad = len(low) + len(unknown)
    return emit("pass", f"refs coverage {asset} --parts: {len(rows)} part famil(ies), {len(low)} under "
                f"{P.MIN_PX_PER_MM:g} px/mm, {len(unknown)} with no picture at a known scale"
                + (f"; searched: {'; '.join(fetched)}" if fetched else ""),
                ("a close-up at a KNOWN scale for each flagged part: kit library inspect <uid> --part <words> (a "
                 "reference model's part, mm-exact), or kit refs find \"<object> <part> close up\" -> kit refs crop -> "
                 "kit vision upscale, then cite it in the part's ref:" if n_bad else
                 "every part has a picture sharp enough (or a measurement): model each from its best picture"),
                table=table, low=[r["family"] for r in low], unknown=[r["family"] for r in unknown])


def refparts_words(family):
    sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
    import review_refs  # noqa: PLC0415

    return review_refs.part_words(family)


def main(argv):
    if argv and not argv[0].startswith("-") and "--parts" in argv:
        root = argv[argv.index("--root") + 1] if "--root" in argv else ROOT
        fetch = int(argv[argv.index("--fetch") + 1]) if "--fetch" in argv else 0
        return parts_main(argv[0], root, fetch)
    if not argv or argv[0].startswith("-"):
        return emit("fail", "refs coverage: usage: coverage.py <asset> [--root <project>]",
                    "lune run kit refs coverage <asset>")
    asset = argv[0]
    root = argv[argv.index("--root") + 1] if "--root" in argv else ROOT
    brief, cov, traces = measure(asset, root)
    feats = (brief or {}).get("hero_features") or []
    if not feats and not cov["rows"]:
        why = ("no brief" if brief is None else "the brief names no hero features") + \
              f" and no traced parts ({len(traces)} traced view(s))"
        return emit("pass", f"refs coverage {asset}: nothing to measure — {why}",
                    f"ask the owner what players notice first and write it in assets/models/{asset}.brief.md "
                    "(`hero features`: one numbered line each, with the picture and box that show it and its size "
                    "in mm), then run this again", coverage=cov)
    table = P.coverage_table(cov)
    for row in table:
        print(row)
    hero = [f for f in cov["features"] if f["hero"]]
    measured = [f for f in hero if f["best_px_per_mm"] is not None]
    pictures = {r["picture"] for r in cov["rows"] if r.get("picture")}
    low = cov["low"]
    summary = (f"refs coverage {asset}: {len(hero)} hero feature(s) ({len(measured)} measured), {len(pictures)} "
               f"picture(s), {len(cov['rows'])} row(s)"
               + (f"; LOW: {'; '.join(P.low_text(f) for f in low)}" if low else
                  f"; every measured hero feature >= {cov['min_px_per_mm']:g} px/mm" if measured else ""))
    unmeasured = [f["name"] for f in hero if f["best_px_per_mm"] is None]
    if low:
        nxt = (f"{P.low_text(low[0])} — ask the owner for a close-up picture only of what they alone have (a game's "
               "design); first find sharper ones yourself: lune run kit refs find \"<the real object> <the part>\" "
               "(and refs patent, cross-sections, field strips; per part, per side); else make a clean view (low trust); "
               "add it to the feature's line in the brief (`<picture> x0,y0,x1,y1`, its size in mm) and run this again")
    elif unmeasured:
        nxt = (f"not measured: {', '.join(unmeasured[:6])} — give each a picture with its box and its size in mm in "
               f"assets/models/{asset}.brief.md (or trace the picture: kit trace ... --part <name>=x0,y0,x1,y1)")
    else:
        nxt = "the pictures can show every hero feature: model them from the best picture each row names"
    return emit("pass", summary, nxt, table=table, coverage=cov)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
