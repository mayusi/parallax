"""subprompts.py - PROMPT-X stage 5 (LIMITATIONS_FIXES_V4 9.2 row 5 / 9.3; Promptist arXiv:2212.09611, TIPO
arXiv:2411.08127): the prompts the kit's TOOLS get, each in the only form that tool reads well.

  flux2      positive words only: an image model draws what a prompt names, even after "no" ("naming fire, even after
             'no', draws it": a living flame drew muzzle flashes on 30 of 36 candidates, kit/tools/design.py). Every
             negated span is cut out whole and its positive opposite put in (positive_substitute).
  qwen_edit  one change per call, the camera as "<sks> azimuth elevation distance", everything else kept.
  trellis2   one isolated hero object, a wide 15% margin, neutral light; no scene words reach it.
  dsl        the lane DSLs' numbers (swing bounds, VFX holds, A/V tolerance ...) from the template, moved by the prompt's
             own words and the owner's answers."""

import copy
import re

try:
    from . import models, route
except ImportError:
    import models
    import route

VISUAL = ("3d", "vfx", "ui", "world", "anim")
DESCRIPTORS = set(
    "crimson red scarlet orange amber gold golden yellow green emerald teal cyan blue indigo navy purple violet magenta "
    "pink white black grey gray silver bronze copper brass steel iron wood wooden stone marble leather cloth glass "
    "fire flame flames water ice frost lightning thunder wind smoke ink shadow light dark bright glowing molten "
    "katana sword greatsword claymore dagger spear axe scythe hammer shield bow gun pistol rifle revolver blade hilt "
    "scabbard armour armor helmet slash arc ring wave spiral burst beam orb ribbon ribbons tidal sun moon star "
    "ornate engraved worn aged polished rusty sleek heavy massive slim curved straight jagged gothic medieval "
    "glow spark sparks ember embers rune runes flare halo petals crystal shard shards dust debris mist".split()
)


def _flux_profile():
    return models.profile("flux2")


def positive_substitute(text, bans=None, prof=None):
    """cut every negated span ('no fire', 'never, ever glowing', 'shouldn't have any smoke', 'fire-free', 'w/o blur')
    and every banned word out of the text, and put the positive opposite in; what is left names only what should be
    drawn (the one negation reader: route.NEG_SPAN / NEG_AFFIX)"""
    prof = prof or _flux_profile()
    subs = prof["substitutions"]
    keys = sorted(subs, key=len, reverse=True)
    added = []

    def replacements_for(span):
        found = []
        s = span.lower()
        for k in keys:
            # (a key's own word forms: glow -> glowing, flame -> flames)
            if re.search(rf"\b{re.escape(k)}(?:s|es|ing|ed|y)?\b", s):
                if subs[k] not in found:
                    found.append(subs[k])
                s = re.sub(rf"\b{re.escape(k)}(?:s|es|ing|ed|y)?\b", " ", s)
        return found

    out = route.normalize(text)
    for a, b, negated in sorted(route.negation_ranges(text), reverse=True):
        rep = replacements_for(" ".join(negated))
        added[:0] = rep or [prof["fallback"]]
        out = out[:a] + " " + out[b:]
    for b in bans or []:
        if re.search(rf"\b{re.escape(b)}\b", out, flags=re.I):
            out = re.sub(rf"\b{re.escape(b)}\b", " ", out, flags=re.I)
            added.append(subs.get(b.lower(), prof["fallback"]))
    trig = "|".join(re.escape(t) for t in sorted(route.NEG_TRIGGERS, key=len, reverse=True))
    out = re.sub(rf"(?<![\w'])(?:{trig})(?![\w'])", " ", out, flags=re.I)  # a stray trigger word on its own
    out = re.sub(r"\(\s*\)", " ", out)
    pieces = [p.strip(" ,;:()") for p in re.split(r"[,;]", out)]
    pieces = [re.sub(r"\s+", " ", p) for p in pieces if p.strip(" ,;:()")]
    pieces = [re.sub(r"^(?:and|or|but|with)\s+", "", p, flags=re.I) for p in pieces]
    # (a stub the cut left behind: "katana that is", "katana with", "it", "I")
    for _ in range(3):
        pieces = [re.sub(r"\s+(?:that is|that|which|with|and|or|of|it|is|has|have)$", "", p, flags=re.I) for p in pieces]
    pieces = [re.sub(r"^[\-\s]+", "", p) for p in pieces]
    pieces = [p for p in pieces if p.lower() not in ("i", "it", "we", "you", "they", "that", "this", "is")]
    for a in added:
        if a not in pieces:
            pieces.append(a)
    return ", ".join(p for p in pieces if p)


def negated_spans(text, prof=None):
    return route.negated_spans(text)


def _descriptors(raw):
    """the colours, materials, elements and objects the prompt asks FOR (a negated span names what it does not want)"""
    seen, out = set(), []
    for w in route.words(route.strip_negated(raw)):
        if w in DESCRIPTORS and w not in seen:
            seen.add(w)
            out.append(w)
    return out


def _subject(lane, raw):
    t = models.template(lane)
    base = t.get("tool_subject") or "an object"
    d = _descriptors(raw)
    return f"{base} with {' '.join(d)}" if d else base


def flux2(lane, raw, angle="side"):
    prof = _flux_profile()
    owner_negations = "; ".join(negated_spans(raw, prof))
    body = f"{prof['style']}: {_subject(lane, raw)}, {angle} view, {prof['backdrop']}, {prof['lighting']}, crisp clean edges, wide frame margin"
    if owner_negations:
        body += "; " + owner_negations
    return positive_substitute(body, prof=prof)


def qwen_edit(lane, raw, azimuth=90, elevation=0, distance=1.0, change=None):
    prof = models.profile("qwen_edit")
    pose = prof["pose"].format(azimuth=azimuth, elevation=elevation, distance=distance)
    subject = re.sub(r"^(?:a|an|the)\s+", "", _subject(lane, raw), flags=re.I)
    what = change or f"the same {subject} turned to this camera"
    return f"{pose}, {what}; {prof['preserve']}"


def trellis2(lane, raw):
    prof = models.profile("trellis2")
    subject = _subject(lane, raw)
    for w in prof["strip_words"]:
        subject = re.sub(rf"\b{re.escape(w)}\b", " ", subject, flags=re.I)
    subject = re.sub(r"\s+", " ", subject).strip()
    subject = re.sub(r"^(?:a|an|the)\s+", "", subject, flags=re.I)  # (the framing says "a single isolated ...")
    return f"{prof['framing'].format(subject=subject)}, {prof['lighting']}, {prof['backdrop']}"


def dsl_overrides(lanes, raw, decisions=None):
    raw_lower = route.strip_negated(raw).lower()  # "not calm" sets no calm intent
    out = {}
    # the IR's decisions read "<lane>.<slot>: <chosen option> (<how>)"
    chosen = {d["text"].split(":", 1)[0]: d["text"] for d in decisions or []}
    for lane in lanes:
        dsl = copy.deepcopy(models.template(lane).get("dsl") or {})
        if not dsl:
            continue
        if lane == "anim":
            for intent in ("calm", "aggressive", "proper"):
                if route._has(raw_lower, intent) or any(intent in v.lower() for k, v in chosen.items() if k.endswith("anim.intent")):
                    dsl["intent"] = intent
            # the weight band's deep end: asked heavy, or "floaty" refused (a floaty moon jump stays light)
            refused = route.negated_words(raw)
            if any(route._has(raw_lower, w) for w in ("heavy", "weighty", "brutal")) or "floaty" in refused:
                dsl["pelvis_drop_st"] = [-0.45, -0.35]  # the deep end of the weight band
                dsl["snap_hold_f"] = max(3, dsl.get("snap_hold_f", 3))
            if route._has(raw_lower, "fast") or route._has(raw_lower, "snappy"):
                dsl["whip_lag_f"] = 4
        if lane == "vfx" and any(route._has(raw_lower, w) for w in ("heavy", "floaty", "impact")):
            dsl["hold_s"] = max(0.75, dsl.get("hold_s", 0.75))
        out[lane] = dsl
    return out


def build(routed, ir):
    lanes = routed["lanes"]
    raw = routed["raw_prompt"]
    visual = [lane for lane in lanes if lane in VISUAL and models.template(lane).get("tool_subject")]
    lead_visual = visual[0] if visual else None
    return {
        "flux2": flux2(lead_visual, raw) if lead_visual else None,
        "qwen_edit": qwen_edit(lead_visual, raw) if lead_visual in ("3d", "vfx", "ui", "anim") else None,
        "trellis2": trellis2("3d", raw) if "3d" in lanes else None,
        "dsl_overrides": dsl_overrides(lanes, raw, ir.get("decisions")),
    }
