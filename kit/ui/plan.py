"""plan.py — the HERO ROUTE for one screen as SEVEN LOCKED STAGES, and the next command, for any model (the hand-holder).

    python kit/ui/plan.py <Screen> [--specs assets/ui] [--models src/ui] [--ui build/ui] [--starter kit/starter/ui]
                                   [--verify .verify/ui.json] [--refs assets/ui/refs]

    1 refs      >= 2 real stills of THIS screen type (the spec's "kind", + "screen_type") at >= 1080p, typed in
                refs.json (kit ui refs --index / --tag), a REFS.md — or the owner's quoted waiver
    2 identity  the identity names fonts, shape, bans, minimums and references with pictures
    3 pieces    every piece names its ROUTE (kit/ui/routes.py): none unknown, none prompt-made for a known character,
                the hero piece not typed, at least one piece on a golden route (trace / letter / ink / render / smear),
                renders current
    4 assemble  focus named, built from the current spec, the preview's notes cleared
    5 look      a model looked at THIS build's sheet and said what it saw
    6 judge     the owner's rating of this build at the bar (or two fresh judges' median, for BUGS)
    7 promote   in the example library

A stage is LOCKED until every stage before it is done: a locked stage shows what it found but offers no command
(every round that skipped a step was called AI slop; the source is the ceiling). Each stage offers <= 5 commands.
Prop screens (quality "prop") skip the refs lock. Ends with summary / next_action like every kit command.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import refsdb  # noqa: E402
import routes as R  # noqa: E402

BARS = {"prop": 55, "hero": 75, "aaa": 88}
MAX_CMDS = 5
STAGES = ("refs", "identity", "pieces", "assemble", "look", "judge", "promote")
GOLDEN = {k for k, v in R.table().items() if v.get("status") == "golden"}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        h.update(fh.read())
    return h.hexdigest()


def load(path):
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def node_named(spec, dotted):
    """the spec node a "focus" / "hero" path names (Root.Child.Leaf, or a suffix of one)"""
    found = []

    def walk(n, path):
        if not isinstance(n, dict):
            return
        p = f"{path}.{n.get('name')}" if path else str(n.get("name"))
        if p == dotted or p.endswith("." + dotted):
            found.append(n)
        for c in n.get("children") or []:
            walk(c, p)
    walk(spec.get("root"), "")
    return found[0] if found else None


HUD_COMPONENTS = {"crosshair", "hitmarker", "ammo", "feed", "ring"}


def infer_kind(spec):
    """the compiler's rule: a screen with HUD components is a HUD, else a menu"""
    def has(n):
        return isinstance(n, dict) and (n.get("type") in HUD_COMPONENTS or any(has(c) for c in n.get("children") or []))
    return "hud" if has(spec.get("root")) else "menu"


def typed_evidence_ok(ident):
    """the compiler's exception, the same test: typed_hero_evidence = "<one of its references' image>: <words>" and
    that picture exists"""
    ev = (ident or {}).get("typed_hero_evidence")
    if not isinstance(ev, str):
        return False
    for r in (ident or {}).get("references") or []:
        img = r.get("image") if isinstance(r, dict) else None
        if isinstance(img, str) and img and ev.startswith(img + ":") and os.path.isfile(img):
            return True
    return False


def node_paths(spec):
    """every named node's path under the root (Root.Child.Leaf)"""
    out = set()

    def walk(n, path):
        if not isinstance(n, dict):
            return
        p = f"{path}.{n.get('name')}" if path else str(n.get("name"))
        out.add(p)
        for c in n.get("children") or []:
            walk(c, p)
    walk((spec or {}).get("root"), "")
    return out


def derived_drops(spec, source):
    """a derived screen ("derived_from": "<Screen>") against its source: the source's nodes it neither has nor names
    in "drops" (a path or a node name) — (missing paths, the source spec or None)"""
    if not isinstance(source, dict):
        return [], None
    have = node_paths(spec)
    drops = set(spec.get("drops") or [])
    # the roots may be named differently (Hud vs Combo): compare below the root
    def rel(p):
        return p.split(".", 1)[1] if "." in p else ""
    mine = {rel(p) for p in have}
    missing = []
    for p in sorted(node_paths(source), key=lambda q: (q.count("."), q)):
        r = rel(p)
        parts = r.split(".")
        # (a node named in "drops", by path or by name, takes its children with it)
        if not r or r in mine or any(".".join(parts[: k + 1]) in drops or parts[k] in drops for k in range(len(parts))):
            continue
        if any(r.startswith(m + ".") for m in missing):
            continue  # (a dropped parent names its children)
        missing.append(r)
    return missing, source


def plan(name, specs, models, ui, starter, verify, refs_root="assets/ui/refs"):
    """[{stage, done, locked, checks: [{check, done, detail}], cmds: [...]}], next command"""
    specs, models, ui, starter = (x.replace("\\", "/") for x in (specs, models, ui, starter))
    out = []

    def stage(label, checks):
        """checks: [(check, done, detail, cmd)] -> one stage, done when every check is"""
        cmds = []
        for _, done, _, cmd in checks:
            if not done and cmd and cmd not in cmds:
                cmds.append(cmd)
        out.append({"stage": label, "done": all(c[1] for c in checks), "locked": False,
                    "checks": [{"check": c[0], "done": c[1], "detail": c[2]} for c in checks], "cmds": cmds[:MAX_CMDS]})

    spec_path = os.path.join(specs, f"{name}.json")
    spec = load(spec_path)
    if not spec:
        stage("refs", [("spec", False, f"no {spec_path}", f"lune run kit new screen {name} --from Arcade5Title   (copies the PROCESS: refs, identity, pieces)")])
        return finish(out)
    quality = spec.get("quality", "prop")
    hero = quality in ("hero", "aaa")
    bar = BARS.get(quality, 55)
    ident_name = spec.get("identity")
    ident = load(os.path.join(specs, "identities", f"{ident_name}.json")) if ident_name else None
    kind = spec.get("kind") or infer_kind(spec)
    screen_type = spec.get("screen_type")

    # 1 refs — the source is the ceiling
    checks = []
    if hero:
        ok, detail, todo = refsdb.gate(ident_name, refs_root, ident, kind, screen_type)
        checks.append(("stills", ok, detail, todo))
        md = any(os.path.isfile(os.path.join(d, "REFS.md")) for d in refsdb.folders(ident_name or "", refs_root, ident)) if ident_name else False
        checks.append(("REFS.md", md, "REFS.md with sources + 1:1 measurements" if md else "no REFS.md",
                       f"write {refs_root}/{ident_name or '<identity>'}/REFS.md: each still's source URL, frame size, every piece's px box and sampled colour (kit ui measure <still>)"))
    else:
        checks.append(("stills", True, f"quality {quality}: the refs lock is for hero screens", ""))
    stage("refs", checks)

    # 2 identity — numbers from the stills, not habit
    checks = []
    if ident:
        missing = [k for k in ("references", "bans", "minimums", "shape", "fonts") if not ident.get(k)]
        refs = ident.get("references") or []
        pics = sum(1 for r in refs if isinstance(r, dict) and r.get("image") and os.path.isfile(r["image"]))
        checks.append(("fields", not missing, f"{ident_name}: fonts, shape, bans, minimums, references" + (f" — missing {missing}" if missing else ""),
                       f"edit {specs}/identities/{ident_name}.json: add {', '.join(missing)} (minimums = the scale floors measured from the stills)"))
        checks.append(("pictures", pics >= 1 or not hero, f"{len(refs)} reference(s), {pics} with a real picture",
                       f"list the stills in {specs}/identities/{ident_name}.json \"references\" with \"image\": \"{refs_root}/{ident_name}/<still>\" and what was measured"))
    else:
        checks.append(("identity", False, "no identity (a hero screen without one is an error)",
                       f"lune run kit ui identity_from {ident_name or '<identity>'}   (a DRAFT from the measured stills), then set \"identity\" in {name}.json"))
    stage("identity", checks)

    # 3 pieces — every piece by its route; the hero piece on a golden route, never typed
    checks = []
    art_root = os.path.join(specs, "art")
    rows = R.screen_routes(spec, art_root) if ident_name else []
    counts = {}
    for _, _, r, _ in rows:
        counts[r] = counts.get(r, 0) + 1
    pictures = [r for r in rows if r[1]]
    unknown = [r for r in pictures if r[2] == "unknown"]
    golden = [r for r in pictures if r[2] in GOLDEN]
    by = ", ".join(f"{k} {v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1])) or "no pieces"
    checks.append(("routes", not unknown, f"{len(pictures)} picture(s) by route: {by}" + (f"; {len(unknown)} with NO source ({', '.join(r[1] for r in unknown[:3])})" if unknown else ""),
                   f"name where {unknown[0][1] if unknown else '<piece>'} came from: a sidecar (kit ui render / trace / ink / letter) or a PROVENANCE.md row"))
    if hero:
        heropath = spec.get("hero") if isinstance(spec.get("hero"), str) else spec.get("focus")
        # (the exact node; a label on a plate is its TEXT: the typed row wins over the plate's)
        hrows = [r for r in rows if heropath and r[0] == heropath]
        hrow = next((r for r in hrows if r[2] == "typed"), hrows[0] if hrows else None)
        typed_ok = typed_evidence_ok(ident)
        hroute = hrow[2] if hrow else None
        standing = R.table().get(hroute, {}).get("status")
        # the hero piece is made on a golden / ok route — drawn, concept and plate pieces are "never the hero"
        hero_ok = bool(hrow) and (standing in ("golden", "ok") or (hroute == "typed" and typed_ok))
        checks.append(("hero piece", hero_ok, f"the hero piece {heropath or '(none named)'} is on route {hroute or '?'}" + (" (the identity's typed_hero_evidence)" if hroute == "typed" and typed_ok else ""),
                       f"make {heropath or 'the hero piece'} on a golden route: \"lettering\" / kit ui render {ident_name}/<piece> / kit ui trace / kit ui ink — or a \"number\" node; never a typed glyph, a script drawing or a plate"))
        checks.append(("medium", bool(golden), f"{len(golden)} piece(s) on a golden route (trace / letter / ink / render / smear)" + ("" if golden else " — every piece is typed, drawn or plates: the AI-slop medium"),
                       f"change the MEDIUM before any polish: letter the display words (\"lettering\"), render the hero plate (kit ui render {ident_name}/<piece>), or trace it from a still (kit ui trace)"))
        prompted = [r[1] for r in pictures if r[2] == "concept" and re.search(r"(crest|silhouette|logo|character|witch|portrait|hero)", r[1], re.I)]
        checks.append(("no stand-ins", not prompted, f"{len(prompted)} prompt-made character / logo piece(s)" + (f": {', '.join(prompted[:3])}" if prompted else ""),
                       f"replace {prompted[0] if prompted else '<piece>'} with the REAL picture: lune run kit ui ink {ident_name}/<piece> --from <picture> --mode cel"))
        d = os.path.join(art_root, ident_name or "")
        stale = []
        if os.path.isdir(d):
            for f in os.listdir(d):
                if f.endswith(".render.json"):
                    p = os.path.join(d, f[:-12] + ".png")
                    if not os.path.isfile(p) or os.path.getmtime(p) < os.path.getmtime(os.path.join(d, f)) - 1:
                        stale.append(f[:-12])
        checks.append(("current", not stale, "every render current" if not stale else f"{len(stale)} render(s) older than their recipe: {', '.join(stale[:3])}",
                       f"lune run kit ui render {ident_name}/{stale[0] if stale else '<piece>'}"))
    stage("pieces", checks)

    # 4 assemble — focus, build, preview notes
    checks = []
    focus = spec.get("focus")
    checks.append(("focus", bool(focus) or not hero, f"focus {focus or 'NONE'} (what the eye lands on), kind {kind}, quality {quality} (bar {bar})",
                   f'edit {specs}/{name}.json: "focus": "<Root>.<Node>" (what the eye lands on first)'))
    src_name = spec.get("derived_from")
    if isinstance(src_name, str) and src_name:
        missing, src = derived_drops(spec, load(os.path.join(specs, f"{src_name}.json")))
        checks.append(("derived", src is not None and not missing,
                       (f"derived from {src_name}: " + (f"{len(missing)} of its node(s) DROPPED: {', '.join(missing[:4])}" if missing else "every node kept or named in \"drops\""))
                       if src is not None else f"derived from {src_name}, which has no spec",
                       f"copy {missing[0] if missing else '<node>'} from {src_name} into {name}, or list it in \"drops\" (a derived screen that copies a node list loses every NEW piece — StriveCombo, 2026-10-15)"))
    model_path = os.path.join(models, f"{name}.model.json")
    built =os.path.isfile(model_path) and os.path.getmtime(model_path) >= os.path.getmtime(spec_path) - 1
    checks.append(("build", built, "built and current" if built else ("built before the spec changed" if os.path.isfile(model_path) else "not built"),
                   f"lune run kit ui {name} --motion"))
    notes = []
    for step in (load(verify) or {}).get("steps") or []:
        for r in (step.get("result") or {}).get("screens") or []:
            if r.get("name") == name:
                notes = [c.get("fix") or c.get("message") or "" for c in r.get("checks") or []]
    sheet = f"{ui}/{name}.png"
    checks.append(("preview", os.path.isfile(sheet) and built and not notes,
                   (f"{len(notes)} note(s): " + "; ".join(n[:80] for n in notes[:3])) if notes else ("sheet at " + sheet if os.path.isfile(sheet) else "no sheet"),
                   f"fix the preview notes, then lune run kit ui {name} --motion"))
    stage("assemble", checks)

    # 5 look
    model_sha = sha256_file(model_path) if os.path.isfile(model_path) else None
    look = load(os.path.join(specs, f"{name}.look.json"))
    looked = bool(look) and look.get("model_sha256") == model_sha
    stage("look", [("look", looked, (f"{look.get('by')} saw: {look.get('note', '')[:90]}" if looked else ("a look at an OLDER build" if look else "nobody looked")),
                    f'look at {sheet} (desktop, phone, tablet) and {name}.motion.png, then: lune run kit ui look {name} "<what you saw, what you will change>"')])

    # 6 judge — the owner's eye; fresh judges find bugs
    judge = load(os.path.join(specs, f"{name}.judge.json")) or {}
    owner = judge.get("owner") or {}
    if owner.get("model_sha256") == model_sha and (owner.get("score") or 0) >= bar:
        jc = ("owner", True, f"the OWNER rated this build {owner['score']}/100: \"{str(owner.get('words', ''))[:70]}\"", "")
    elif owner.get("score") is not None:
        jc = ("owner", False, f"the owner rated an EARLIER build {owner['score']}/100; this build changed since",
              f"show the owner build/ui/{name}.png, then: lune run kit ui judge {name} --owner <score> \"<their words>\"")
    else:
        judged = judge.get("model_sha256") == model_sha and (judge.get("judges") or 0) >= 2
        score = judge.get("score")
        gaps = [f"{g.get('where')}: {g.get('what')}" for vd in judge.get("verdicts") or [] for g in vd.get("gaps") or []]
        ok = judged and score is not None and score >= bar
        jc = ("judges", ok, (f"{judge.get('judges')} judge(s), median {score} vs bar {bar}" + ("" if judge.get("model_sha256") == model_sha else " (an OLDER build)")) if judge else "not judged — the owner's eye decides; two fresh judges find BUGS",
              (f"fix the located gaps first: {'; '.join(g[:90] for g in gaps[:2])}" if gaps and not ok
               else f"show the owner build/ui/{name}.png → lune run kit ui judge {name} --owner <score> \"<words>\"; or lune run kit ui judge {name} → a FRESH judge → --record"))
    # the VERIFIER (kit ui verify): a fresh model's one difference + one edit per piece against the real still, and
    # the bugs it saw — for THIS build, with no bug left open (the owner's eye stays the bar)
    vr = load(os.path.join(specs, f"{name}.verify.json")) or {}
    v_now = vr.get("model_sha256") == model_sha
    v_bugs = len(vr.get("bugs") or []) if v_now else 0
    vc = ("verifier", v_now and v_bugs == 0,
          (f"{vr.get('by')}: {len(vr.get('pairs') or [])} difference(s), {v_bugs} bug(s) open" if v_now
           else ("a verify record of an OLDER build" if vr else "no verifier pass (one difference + one edit per piece, no score)")),
          (f"fix the verifier's bugs: {'; '.join(str(b.get('where')) + ': ' + str(b.get('what'))[:80] for b in (vr.get('bugs') or [])[:2])}" if v_now and v_bugs
           else f"lune run kit ui verify {name} --pairs (once), then lune run kit ui verify {name} → a FRESH model → --record <verdict.json>"))
    stage("judge", [vc, jc] if hero else [jc])

    # 7 promote
    promoted = os.path.isfile(os.path.join(starter, f"{name}.json"))
    stage("promote", [("example", promoted, "in the example library" if promoted else "not an example yet",
                       f'lune run kit promote screen {name} --about "<one line>"   (only once the owner rated it)')])
    return finish(out)


def finish(out):
    nxt = None
    blocked = False
    for st in out:
        if blocked:
            st["locked"] = True
            continue
        if not st["done"]:
            nxt = st["cmds"][0] if st["cmds"] else None
            blocked = True
    return out, nxt


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # (Windows consoles default to cp1252; the kit reads utf-8)
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--specs", default="assets/ui")
    ap.add_argument("--models", default="src/ui")
    ap.add_argument("--ui", default="build/ui")
    ap.add_argument("--starter", default="kit/starter/ui")
    ap.add_argument("--verify", default=".verify/ui.json")
    ap.add_argument("--refs", default=None, help="default: <specs>/refs")
    a = ap.parse_args()
    stages, nxt = plan(a.name, a.specs, a.models, a.ui, a.starter, a.verify, a.refs or os.path.join(a.specs, "refs").replace("\\", "/"))
    for i, st in enumerate(stages, 1):
        tag = "LOCKED" if st["locked"] else ("done" if st["done"] else "todo")  # (a locked stage's own checks are shown, never counted)
        print(f"  {i} [{tag:6s}] {st['stage']}")
        for c in st["checks"]:
            print(f"      {'+' if c['done'] else '-'} {c['check']}: {c['detail']}")
        if not st["done"] and not st["locked"]:
            for cmd in st["cmds"]:
                print(f"      -> {cmd}")
    done = sum(1 for st in stages if st["done"] and not st["locked"])
    first = next((st for st in stages if not st["done"]), None)
    status = "pass" if first is None else "fail"
    why = next((c["detail"] for c in first["checks"] if not c["done"]), "") if first else ""
    summary = f"ui plan {a.name}: {done}/{len(stages)} stages done" + (f"; at {first['stage']} (later stages locked): {why[:140]}" if first else "")
    print(json.dumps({"schema": 1, "status": status, "summary": summary,
                      "next_action": nxt or (f"{a.name} is proven and promoted — nothing left in the pass" if first is None else f"finish the {first['stage']} stage"),
                      "stages": stages, "made": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
