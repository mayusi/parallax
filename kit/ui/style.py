"""style.py — an identity exported as a Roblox STYLESHEET (UI Styling, full release 2026; transitions in the sheet):
a game's OWN hand-made screens wear the identity — its colours, its fonts, its corner radius, its hover timing —
without the kit compiling them.

    python kit/ui/style.py <identity> [--ui assets/ui] [--out src/ui/styles]

-> src/ui/styles/<identity>.model.json: a StyleSheet whose ATTRIBUTES are the identity's tokens (Color3 / string /
number: a rule refers to one as "$accent", so changing a token restyles everything) and whose StyleRules carry their
selector + priority. A rule's properties and its transition are set by METHOD (StyleRule:SetProperties /
SetDefaultPropertyTransition), which a model file cannot hold: they ride in the attributes Kit_Props (JSON) and
Kit_Transition ("seconds,Style,Direction"), and Ui.styles() applies them in game (Ui.link(gui, identity) links a
hand-made ScreenGui to the sheet). Tags the rules select: KitTitle, KitPanel, KitPrimary, KitMuted.
BREAKPOINTS (v7, LIMITATIONS_FIXES_V4 UI-X): the identity's "queries": {"Phone": {"when": {"MaxSize": [900, 500]},
"rules": {".KitTitle": {"TextSize": 28}}}} -> a StyleQuery "Phone" (conditions in Kit_Conditions: MinSize / MaxSize
[w, h], AspectRatioRange [lo, hi], PreferredInput) + a "@Phone" StyleRule holding those rules; a condition the engine
does not take, a malformed size or a query with no rules FAILS the export (query_problems).
"""
import argparse
import json
import os
import sys


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def hex3(h):
    return [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]


def rules_for(identity):
    """the identity's grammar as StyleRules: (name, selector, priority, props, transition or None)"""
    fonts = identity.get("fonts") or {}
    shape = identity.get("shape") or {}
    motion = identity.get("motion") or {}
    radius = shape.get("radius")
    r_px = int(radius) if isinstance(radius, (int, float)) else (8 if radius is None else 0)
    hover = motion.get("hover") if isinstance(motion.get("hover"), dict) else {}
    hover_s = float(hover.get("duration", 0.12)) if hover else 0.12
    trans = f"{hover_s},Quad,Out"
    font = fonts.get("font") or "GothamMedium"
    title = fonts.get("titleFont") or font
    return [
        ("Text", "TextLabel", 0, {"TextColor3": "$text", "Font": {"Enum": "Font", "Name": font}}, None),
        ("Buttons", "TextButton", 0, {"TextColor3": "$text", "BackgroundColor3": "$panel2", "AutoButtonColor": False,
                                      "Font": {"Enum": "Font", "Name": font}}, trans),
        ("Primary", ".KitPrimary", 10, {"BackgroundColor3": "$accent", "TextColor3": "$bg"}, trans),
        ("Title", ".KitTitle", 10, {"Font": {"Enum": "Font", "Name": title}, "TextColor3": "$text"}, None),
        ("Muted", ".KitMuted", 10, {"TextColor3": "$muted"}, None),
        ("Panel", ".KitPanel", 5, {"BackgroundColor3": "$panel", "BackgroundTransparency": 0}, None),
        ("Corners", "UICorner", 0, {"CornerRadius": {"UDim": [0, r_px]}}, None),
        ("Strokes", "UIStroke", 0, {"Color": "$line"}, None),
    ]


def build(identity, name):
    tokens = identity.get("tokens") or {}
    attrs = {"Kit_Style": {"String": name}}
    for k, v in tokens.items():
        if isinstance(v, str) and v.startswith("#") and len(v) == 7:
            attrs[k] = {"Color3": hex3(v)}
    fonts = identity.get("fonts") or {}
    for k in ("font", "titleFont", "monoFont"):
        if fonts.get(k):
            attrs[k] = {"String": fonts[k]}
    children = []
    for rname, selector, prio, props, trans in rules_for(identity):
        ra = {"Kit_Props": {"String": json.dumps(props, separators=(",", ":"))}}
        if trans:
            ra["Kit_Transition"] = {"String": trans}
        children.append({"Name": rname, "ClassName": "StyleRule",
                         "Properties": {"Selector": selector, "Priority": prio, "Attributes": {"Attributes": ra}}})
    # STYLE QUERIES (v7 breakpoints): each query is a StyleQuery (its conditions set by method, so they ride in
    # Kit_Conditions) and a "@<Name>" StyleRule holding the rules that apply only while the query is active. The engine
    # evaluates a query only UNDER the styled root and "@<Name>" selects that root (Studio, 2026-11-20): the runtime
    # (Ui.link / Ui.styles, src/kit/UiStyleRules.luau) copies each query there and scopes the inner rules to ">> sel"
    for qname, q in sorted((identity.get("queries") or {}).items()):
        children.append({"Name": qname, "ClassName": "StyleQuery", "Properties": {
            "Attributes": {"Attributes": {"Kit_Conditions": {"String": json.dumps(q["when"], separators=(",", ":"))}}}}})
        inner = []
        for i, (selector, props) in enumerate(sorted(q["rules"].items())):
            inner.append({"Name": f"{qname}{i + 1}", "ClassName": "StyleRule", "Properties": {
                "Selector": selector, "Priority": 20,
                "Attributes": {"Attributes": {"Kit_Props": {"String": json.dumps(props, separators=(",", ":"))}}}}})
        children.append({"Name": f"At{qname}", "ClassName": "StyleRule",
                         "Properties": {"Selector": f"@{qname}", "Priority": 20}, "Children": inner})
    return {"Name": f"{name}Style", "ClassName": "StyleSheet", "Properties": {"Attributes": {"Attributes": attrs}},
            "Children": children}


# the conditions a StyleQuery takes (Roblox's StyleQuery: MinSize / MaxSize are Vector2 px of the styled root,
# AspectRatioRange a NumberRange of width / height, PreferredInput an Enum.PreferredInput)
QUERY_CONDITIONS = {"MinSize", "MaxSize", "AspectRatioRange", "PreferredInput"}
PREFERRED_INPUTS = {"KeyboardAndMouse", "Gamepad", "Touch", "MicroGamepad"}


def query_problems(identity):
    """the identity's "queries" checked before export: a condition the engine does not take, a size that is not two
    positive numbers, a range that is not [lo, hi], an input that is not an Enum.PreferredInput, a query with no rules -
    each would leave a breakpoint that never fires (the engine ignores what it does not know, silently)"""
    out = []
    queries = identity.get("queries")
    if queries is None:
        return out
    if not isinstance(queries, dict):
        return ['"queries" is {"<Name>": {"when": {...}, "rules": {"<selector>": {...}}}}']
    for qname, q in queries.items():
        if not (isinstance(qname, str) and qname.isidentifier()):
            out.append(f"query {qname!r}: a name is letters / digits / _ (the selector is @{qname})")
            continue
        if not isinstance(q, dict) or not isinstance(q.get("when"), dict) or not q["when"]:
            out.append(f"query {qname}: needs \"when\": {{conditions}} (MinSize, MaxSize, AspectRatioRange, PreferredInput)")
            continue
        for k, v in q["when"].items():
            if k not in QUERY_CONDITIONS:
                out.append(f"query {qname}: \"{k}\" is not a StyleQuery condition (one of {', '.join(sorted(QUERY_CONDITIONS))})")
            elif k in ("MinSize", "MaxSize"):
                if not (isinstance(v, list) and len(v) == 2 and all(isinstance(x, (int, float)) and x > 0 for x in v)):
                    out.append(f"query {qname}: {k} is [width, height] in pixels, both > 0 (got {v!r})")
            elif k == "AspectRatioRange":
                if not (isinstance(v, list) and len(v) == 2 and all(isinstance(x, (int, float)) and x >= 0 for x in v) and v[0] <= v[1]):
                    out.append(f"query {qname}: AspectRatioRange is [low, high] (width / height), low <= high (got {v!r})")
            elif k == "PreferredInput" and v not in PREFERRED_INPUTS:
                out.append(f"query {qname}: PreferredInput is one of {', '.join(sorted(PREFERRED_INPUTS))} (got {v!r})")
        lo, hi = q["when"].get("MinSize"), q["when"].get("MaxSize")
        pair = lambda v: isinstance(v, list) and len(v) == 2 and all(isinstance(x, (int, float)) for x in v)  # noqa: E731
        if pair(lo) and pair(hi):
            if lo[0] > hi[0] or lo[1] > hi[1]:
                out.append(f"query {qname}: MinSize {lo} is larger than MaxSize {hi} - it can never be active")
        rules = q.get("rules")
        if not isinstance(rules, dict) or not rules or not all(isinstance(p, dict) and p for p in rules.values()):
            out.append(f"query {qname}: needs \"rules\": {{\"<selector>\": {{properties}}}} (a query with no rules styles nothing)")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("identity")
    ap.add_argument("--ui", default="assets/ui")
    ap.add_argument("--out", default="src/ui/styles")
    a = ap.parse_args(argv)
    path = os.path.join(a.ui, "identities", f"{a.identity}.json")
    if not os.path.isfile(path):
        return emit("fail", f"style: no identity '{a.identity}'", "lune run kit ui identities")
    with open(path, encoding="utf-8") as fh:
        identity = json.load(fh)
    bad = query_problems(identity)
    if bad:
        return emit("fail", f"style: {a.identity}: {len(bad)} style query problem(s): " + " | ".join(bad[:4]),
                    f"fix \"queries\" in {path.replace(os.sep, '/')}", problems=bad)
    model = build(identity, a.identity)
    os.makedirs(a.out, exist_ok=True)
    out = os.path.join(a.out, f"{a.identity}.model.json")
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(model, fh, indent=1)
    n_tok = len(model["Properties"]["Attributes"]["Attributes"]) - 1
    return emit("pass", f"style: {a.identity} -> {out} (a StyleSheet: {n_tok} token(s), {len(model['Children'])} rule(s))",
                f"in game: Ui.styles() applies it, Ui.link(myScreenGui, \"{a.identity}\") makes a hand-made screen wear it "
                "(tag pieces KitTitle / KitPanel / KitPrimary / KitMuted)", file=out.replace("\\", "/"))


if __name__ == "__main__":
    sys.exit(main())
