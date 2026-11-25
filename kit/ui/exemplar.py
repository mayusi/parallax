"""exemplar.py — a screen's PROCESS page, written from its data (mission 03, 5.10): what a rated screen was made FROM
and HOW, so `kit new screen <New> --from <Example>` copies the process and not only the spec (Voyager's lesson: a
skill enters the library with the steps that proved it). Nothing in it is typed by hand — every line is read from
the files the route left behind:

  1 the stills       the identity's stills by screen type and resolution (refs.json), REFS.md's measured table
  2 the identity     tokens, fonts, lettering defaults and where their evidence came from
  3 the pieces       every picture by ROUTE (kit/ui/routes.py) with the recipe that remakes it (its sidecar's flags)
  4 the rounds       every commit that changed the spec (git log), the looks, the verifier's differences
  5 the verdicts     the owner's words first, then the judges (bugs only)
  6 redo it          the commands, stage by stage, for a NEW screen of a NEW game (never re-skin this one)

    python kit/ui/exemplar.py <Screen> [--specs assets/ui] [--refs assets/ui/refs] [--out <file.md>]
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import refsdb  # noqa: E402
import routes as R  # noqa: E402

RECIPE_KEYS = {
    "letter": ("text", "style", "font", "weight", "size", "fill", "ink", "outline", "shadow", "lean", "shear", "track", "inline", "arc", "glow"),
    "render": ("items", "material", "size", "camera"),
    "ink": ("from", "mode", "palette"),
    "trace": ("from", "box", "still"),
    "smear": ("from", "angle", "length", "echoes"),
    "spin": ("material", "motion", "depth", "bevel", "frames"),
}


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def load(path):
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001
        return None


def recipe(art_root, piece, route):
    """the flags that remake a piece, from its sidecar"""
    if not piece or route not in RECIPE_KEYS:
        return ""
    ident, name = piece.split("/", 1)
    side = None
    for ext in (f"{route}.json", "render.json", "anchors.json"):
        side = load(os.path.join(art_root, ident, f"{name}.{ext}"))
        if isinstance(side, dict):
            break
    if not isinstance(side, dict):
        return ""
    bits = []
    for k in RECIPE_KEYS[route]:
        v = side.get(k)
        if v in (None, "", [], {}):
            continue
        if isinstance(v, (list, dict)):
            v = json.dumps(v)[:60]
        bits.append(f"{k} {v}")
    return "; ".join(bits)[:220]


def rounds(spec_path):
    """every commit that changed the spec: the screen's rounds, newest first"""
    try:
        out = subprocess.run(["git", "log", "--format=%ad %s", "--date=short", "--", spec_path],
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30).stdout
    except Exception:  # noqa: BLE001
        return []
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def page(name, specs, refs_root, with_rounds=True):
    """the page; with_rounds=False leaves out the git history (the vault's copy: a commit would make it stale)"""
    spec = load(os.path.join(specs, f"{name}.json"))
    if not spec:
        return None
    ident_name = spec.get("identity")
    ident = load(os.path.join(specs, "identities", f"{ident_name}.json")) or {}
    judge = load(os.path.join(specs, f"{name}.judge.json")) or {}
    look = load(os.path.join(specs, f"{name}.look.json")) or {}
    ver = load(os.path.join(specs, f"{name}.verify.json")) or {}
    owner = judge.get("owner") or {}
    L = [f"# {name} — the process (an exemplar: copy HOW it was made, never the look)", "",
         f"Identity `{ident_name}`, kind `{spec.get('kind', 'menu')}`, quality `{spec.get('quality', 'prop')}`, focus `{spec.get('focus')}`"
         + (f", hero `{spec.get('hero')}`" if spec.get("hero") else "") + ". Written by `kit/ui/exemplar.py` from the screen's files.", ""]
    L += ["## 5 The verdicts (first: the owner's eye is the bar)", ""]
    if owner.get("score") is not None:
        L.append(f"- **The owner: {owner['score']}/100 — \"{owner.get('words', '')}\"**")
    else:
        L.append("- the owner has not rated this screen")
    if judge.get("score") is not None:
        L.append(f"- fresh judges: {judge.get('judges')} — median {judge.get('score')} (judges underrate the owner by 30-45 points: read them for BUGS)")
    if ver:
        L.append(f"- the verifier ({ver.get('by')}): {len(ver.get('pairs') or [])} difference(s), {len(ver.get('bugs') or [])} bug(s)")
    L += ["", "## 1 The stills (the source is the ceiling)", ""]
    st = refsdb.stills(ident_name or "", refs_root, ident)
    for s in st:
        size = s.get("size")
        if not size:  # (not indexed yet: measure the file, never call it small for want of a number)
            try:
                from PIL import Image
                with Image.open(s["path"]) as im:
                    size = list(im.size)
                s["size"] = size
            except Exception:  # noqa: BLE001
                size = ["?", "?"]
        L.append(f"- `{s['path']}` — {size[0]}x{size[1]}, {s.get('kind') or 'untyped'}" + (f":{s['screen']}" if s.get("screen") else "")
                 + (" (>= 1080p)" if refsdb.is_1080(s.get("size")) else " (UNDER 1080p: measure-only, never trace from it)"))
    if not st:
        L.append("- none recorded: `kit ui refs <id> \"<game>\" \"<screen words>\" --rank ...` then `--index` / `--tag`")
    for d in refsdb.folders(ident_name or "", refs_root, ident):
        md = os.path.join(d, "REFS.md")
        if os.path.isfile(md):
            with open(md, encoding="utf-8", errors="replace") as fh:
                rows = [ln.rstrip() for ln in fh if ln.startswith("|")]
            if rows:
                L += ["", f"Measured in `{md}`:", ""] + rows[:14]
    L += ["", "## 2 The identity", ""]
    toks = ident.get("tokens") or {}
    L.append("- tokens: " + ", ".join(f"{k} {v}" for k, v in list(toks.items())[:10]))
    L.append(f"- fonts: {json.dumps(ident.get('fonts') or {})}")
    if ident.get("lettering"):
        lt = {k: v for k, v in ident["lettering"].items() if k != "evidence"}
        L.append(f"- lettering defaults: {json.dumps(lt)[:200]}")
        if ident["lettering"].get("evidence"):
            L.append(f"  - evidence: {ident['lettering']['evidence'][:200]}")
    for k in ("accent_evidence", "typed_hero_evidence"):
        if ident.get(k):
            L.append(f"- {k}: {ident[k][:200]}")
    L += ["", "## 3 The pieces, by route (the medium is the lever)", "", "| node | piece | route | standing | remake it with |", "| --- | --- | --- | --- | --- |"]
    tab = R.table()
    seen = set()
    for path, piece, route, why in R.screen_routes(spec, os.path.join(specs, "art")):
        if route == "typed" or (piece and piece in seen):
            continue
        seen.add(piece)
        L.append(f"| `{path}` | `{piece}` | {route} | {tab.get(route, {}).get('status', '?')} | {recipe(os.path.join(specs, 'art'), piece, route) or why[:90]} |")
    typed = sum(1 for _, p, r, _ in R.screen_routes(spec, os.path.join(specs, "art")) if r == "typed")
    L.append(f"\n({typed} small typed text(s) — the numbers that change, hints; never the hero)")
    L += ["", "## 4 The rounds", ""]
    if with_rounds:
        hist = rounds(os.path.join(specs, f"{name}.json"))
        L += [f"- {h[:200]}" for h in hist[:20]] or ["- (no commits yet)"]
    else:
        L.append("- the commit history: `git log -- " + os.path.join(specs, f"{name}.json").replace(os.sep, "/") + "` (the starter's copy carries it, frozen at promote)")
    if look.get("note"):
        L += ["", f"Last look ({look.get('by')}): {look['note'][:300]}"]
    for p in (ver.get("pairs") or [])[:6]:
        L.append(f"- verifier, {p.get('piece')}: {p.get('difference', '')[:140]} → {p.get('edit', '')[:140]}")
    L += ["", "## 6 Redo it for a NEW game (the route, never this look)", "",
          "1. refs: `lune run kit ui refs <id> \"<game>\" \"<this screen type>\" --rank \"<what it shows>\"` → `--keep` → `--index` / `--tag <file>=" + str(spec.get("kind", "menu")) + "`; `kit ui read <still>` + `kit ui measure <still>` → REFS.md",
          "2. identity: `lune run kit ui identity_from <id>` → merge into `assets/ui/identities/<id>.json` (tokens sampled, minimums, lettering defaults from `kit ui read type`)",
          "3. pieces: the routes above, in the NEW game's own language — " + ", ".join(sorted({r for _, _, r, _ in R.screen_routes(spec, os.path.join(specs, 'art')) if tab.get(r, {}).get('status') in ('golden', 'ok')})) + " first",
          "4. assemble: `lune run kit ui <New> --motion`; scale from the measured boxes (never a judge's word)",
          "5. look: `lune run kit ui look <New> \"<what you saw>\"`",
          "6. judge: `lune run kit ui verify <New> --pairs` → `kit ui verify <New>` → a FRESH model → `--record`; show the owner every round",
          "7. promote: only on the owner's verdict (`kit verdict screen <New> <0-10> \"<words>\"`)"]
    return "\n".join(L) + "\n"


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("screen")
    ap.add_argument("--specs", default="assets/ui")
    ap.add_argument("--refs", default="assets/ui/refs")
    ap.add_argument("--out", default=None)
    ap.add_argument("--no-rounds", action="store_true", help="leave out the git history (the vault's copy)")
    a = ap.parse_args()
    text = page(a.screen, a.specs, a.refs, with_rounds=not a.no_rounds)
    if text is None:
        return emit("fail", f"exemplar: no {a.specs}/{a.screen}.json", "name a screen in assets/ui")
    out = a.out or os.path.join("build", "ui", "process", f"{a.screen}.process.md")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return emit("pass", f"exemplar {a.screen}: the process page ({text.count(chr(10))} lines) -> {out}",
                f"read it before copying: lune run kit new screen <New> --from {a.screen} brings it along as <New>.process.md")


if __name__ == "__main__":
    raise SystemExit(main())
