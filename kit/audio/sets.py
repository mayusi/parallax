"""sets.py — a SOUND SET: sounds that share DNA (one sword's ring, one world's room) rendered and gated as a family.

Usage: python kit/audio/sets.py <set|all> [--sets DIR] [--out DIR]   (normally: lune run kit sfx set <set|all>)
assets/sounds/sets/<set>.json:
{
  "about": "R6 sword combat",
  "identity": "anime_battlegrounds",        optional: also gated by kit/audio/identity.py
  "variations": 3, "loudness": -16,          defaults for every member (LUFS target; members may override)
  "dna": {                                   shared layers, each with an "id" — the family resemblance
    "ring":  { "role": "tail", "source": "modal", "modes": [[1240, 0.9, 1.0], ...], "gain": 0.4 },
    "crack": { "role": "transient", "source": "click", "env": {"attack": 0.0003, "decay": 0.006} }
  },
  "fx": { "reverb": 0.15 },                  shared fx (members may override keys)
  "members": {
    "sword_hit_metal": {
      "class": "hit",                        loudness is compared inside a class (footsteps are not hits)
      "duration": 1.2,
      "use": ["crack", "ring"] | {"ring": {"gain": 0.8}},   dna layers this member takes (with overrides)
      "layers": [ ...its own layers... ],
      "weights": [0.15, 0.5, 0.9]             -> sword_hit_metal_light / _medium / _heavy  (one weight -> plain name)
    }
  },
  "gates": { "loudness_spread": 2.0, "take_min": 0.35, "take_max": 6.0, "surface_min": 1.0 },
  "matrix": {                                THE MATERIAL MATRIX: a member <weapon>_<verb>_<surface> per cell
    "verb": "hit", "base": { "class": "hit", "weights": [0.15, 0.5, 0.9] },
    "weapons":  { "sword": { "use": ["crack"] }, "fist": { "layers": [...] } },
    "surfaces": { "metal": { "use": {"ring": {}} }, "wood": { "layers": [ a modal body ] } }
  }                                          (base + weapon + surface merged: layers add up, use merges; a member
}                                             the set already names keeps its own recipe for that cell)
Renders resolved recipes into build/sounds/sets/<set>/ and the sounds into build/sounds/. Gates (errors):
  every file passes the Roblox audio gate · per class the medium takes sit within loudness_spread LU ·
  a LOOP joins unheard (no click, level within seam_level_db, brightness within seam_bright, >= bed_min_s long) ·
  heavier is never quieter or brighter than lighter, and a hit's heaviest take drops at least its medium's sub on the impact · takes of one sound differ (distance >= take_min: no
  machine-gun repetition) but stay in the family (<= take_max) · one weapon on two surfaces differs (>= surface_min) ·
  every layer does its ROLE when heard alone · no two layers mask each other: same moment, same loudest bands (an ERROR
  for a set made since the gate - first committed on/after MASKING_ENFORCED_FROM, or not committed yet - or one that
  declares "masking": "enforce"; a warning for the sets already in the repo before it: masking_mode)
  (transient = a hit under 60 ms, sub = most energy under 120 Hz, air = most energy over 3 kHz, tail >= 150 ms).
Draws build/sounds/sheets/set_<set>.png: one spectrogram per member x weight. Prints one JSON verdict line.
"""

import json
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib.util  # noqa: E402

import ears as E  # noqa: E402
import synth  # noqa: E402
import synth_only  # noqa: E402

# the AUDIO gate by path: kit/world/check.py is also a "check" module (the combined test run imports both)
_spec = importlib.util.spec_from_file_location("kit_audio_check", os.path.join(os.path.dirname(os.path.abspath(__file__)), "check.py"))
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)

WEIGHT_NAMES = {3: ["light", "medium", "heavy"], 2: ["light", "heavy"]}
ROLE_RULES = {
    "transient": ("a hit under 60 ms", lambda e: e["transient_ms"] <= 15 and e["tail_ms"] <= 120),
    "sub": ("most energy under 120 Hz", lambda e: e["sub_share"] >= 0.5),
    "air": ("most energy over 3 kHz", lambda e: e["high_share"] >= 0.4),
    "tail": ("a tail of 150 ms or more", lambda e: e["tail_ms"] >= 150),
}


def _use_dict(use):
    return dict(use) if isinstance(use, dict) else {u: {} for u in (use or [])}


def merge_member(a, b):
    """b over a: dicts merge deep, "layers" add up, "use" (list or dict) merges by layer id, anything else replaces"""
    out = dict(a)
    for k, v in b.items():
        if k == "layers":
            out[k] = list(out.get(k, [])) + list(v)
        elif k == "use":
            u = _use_dict(out.get(k))
            for lid, ov in _use_dict(v).items():
                u[lid] = merge_member(u.get(lid, {}), ov)
            out[k] = u
        elif isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge_member(out[k], v)
        else:
            out[k] = v
    return out


def expand_matrix(spec):
    """the MATERIAL MATRIX: "matrix": {"verb", "base", "weapons": {w: part}, "surfaces": {s: part}} -> a member
    <w>_<verb>_<s> per cell = base + weapon + surface (merge_member). A member the set already names keeps its
    hand-made recipe and still stands for its cell. -> (members, {member: (weapon, surface)})"""
    members = dict(spec.get("members", {}))
    mx = spec.get("matrix")
    cells = {}
    if not mx:
        return members, cells
    verb = mx.get("verb", "hit")
    for w, wpart in (mx.get("weapons") or {}).items():
        for s, spart in (mx.get("surfaces") or {}).items():
            name = f"{w}_{verb}_{s}"
            cells[name] = (w, s)
            if name not in members:
                members[name] = merge_member(merge_member(dict(mx.get("base") or {}), wpart), spart)
    return members, cells


def resolve(spec):
    """{sound name: recipe} for every member x weight."""
    dna = spec.get("dna", {})
    out = {}
    members, cells = expand_matrix(spec)
    for mname, m in members.items():
        use = m.get("use", [])
        overrides = use if isinstance(use, dict) else {u: {} for u in use}
        layers = []
        for lid, ov in overrides.items():
            if lid not in dna:
                raise ValueError(f'{mname}: uses dna layer "{lid}" which the set does not define (has: {", ".join(dna) or "none"})')
            layer = {k: v for k, v in dna[lid].items() if k != "id"}
            layer.update(ov)
            layers.append(layer)
        layers += m.get("layers", [])
        if not layers:
            raise ValueError(f"{mname}: no layers (give it 'use' and/or 'layers')")
        fx = dict(spec.get("fx", {}))
        fx.update(m.get("fx", {}))
        loud = m.get("loudness", spec.get("loudness"))
        if loud is not None:
            fx["loudness"] = loud
        base = {
            "duration": m.get("duration", spec.get("duration", 1.0)),
            "variations": m.get("variations", spec.get("variations", 3)),
            "loop": m.get("loop", False),
            "pitch_spread": m.get("pitch_spread", spec.get("pitch_spread", 0.06)),
            "fx": fx,
            "layers": layers,
            "_class": m.get("class", "default"),
            "_member": mname,
            "_cell": cells.get(mname),
        }
        weights = m.get("weights", [0.5])
        weights = sorted(float(w) for w in weights)
        names = WEIGHT_NAMES.get(len(weights))
        for i, w in enumerate(weights):
            r = dict(base)
            r["weight"] = w
            r["_weight_rank"] = i
            if len(weights) == 1:
                sname = mname
            elif names:
                sname = f"{mname}_{names[i]}"
            else:
                sname = f"{mname}_w{i + 1}"
            out[sname] = r
    return out


def early_sub(x, sr):
    """the share of energy under 120 Hz in the first 150 ms after the onset (the SUB DROP on the impact)"""
    x = np.asarray(x, dtype=float)
    a = np.abs(x)
    if a.max() <= 0:
        return 0.0
    on = int(np.argmax(a > 0.1 * a.max()))
    seg = x[on : on + int(0.15 * sr)]
    if len(seg) < 64:
        return 0.0
    mag = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))) ** 2
    f = np.fft.rfftfreq(len(seg), 1 / sr)
    return float(mag[f < 120].sum() / max(mag.sum(), 1e-12))


def seam_errors(name, x, sr, gates):
    """a LOOP must join without anyone hearing where: the last sample steps to the first like any sample does (no
    click), the last quarter second matches the first in level (3 dB) and brightness (25 %), and a bed is long enough
    that its repeat is not a rhythm (bed_min_s)"""
    errs = []
    x = np.asarray(x, dtype=float)
    if len(x) < sr // 2:
        return [f"{name}: a loop of {len(x) / sr:.2f} s is too short to join"]
    steps = np.abs(np.diff(x))
    jump = abs(x[0] - x[-1])
    usual = float(np.percentile(steps, 99)) + 1e-9
    if jump > 2 * usual:
        errs.append(f"{name}: the loop clicks at its seam (a {jump:.4f} step vs {usual:.4f} inside) — check the crossfade and the filters")
    q = sr // 4
    a, b = x[:q], x[-q:]

    def rms_db(v):
        return 20 * np.log10(np.sqrt(np.mean(v * v)) + 1e-9)

    def centroid(v):
        mag = np.abs(np.fft.rfft(v * np.hanning(len(v))))
        f = np.fft.rfftfreq(len(v), 1 / sr)
        return float(np.sum(f * mag) / (np.sum(mag) + 1e-9))

    # the seam may move as much as the sound moves anywhere else (lapping water swells by more than 3 dB in a quarter
    # second, everywhere): the limit is the larger of the gate and the loop's own 95th-percentile neighbour change
    wins = [x[i : i + q] for i in range(0, len(x) - q + 1, q)]
    lv = [rms_db(w) for w in wins]
    cs = [centroid(w) for w in wins]
    own_lv = float(np.percentile(np.abs(np.diff(lv)), 95)) if len(lv) > 2 else 0.0
    own_c = float(np.percentile([abs(u - v) / max(u, v, 1e-9) for u, v in zip(cs, cs[1:])], 95)) if len(cs) > 2 else 0.0
    lim_lv, lim_c = max(gates["seam_level_db"], own_lv), max(gates["seam_bright"], own_c)
    if abs(rms_db(a) - rms_db(b)) > lim_lv:
        errs.append(f"{name}: the loop's end is {rms_db(b) - rms_db(a):+.1f} dB from its start (max {lim_lv:.1f}: the gate or the loop's own movement) — a level jump at every repeat")
    ca, cb = centroid(a), centroid(b)
    # the colour of near-silence is its noise floor, not the sound: a loop that ends quiet before a downbeat stab
    # joins fine, so the colour is compared only when both sides sound (the level check above still holds)
    peak_db = 20 * np.log10(np.max(np.abs(x)) + 1e-9)
    both_sound = min(rms_db(a), rms_db(b)) > peak_db - 45
    if both_sound and abs(ca - cb) / max(ca, cb, 1e-9) > lim_c:
        errs.append(f"{name}: the loop's end is {cb:.0f} Hz bright vs its start {ca:.0f} Hz — a colour jump at every repeat")
    if len(x) / sr < gates["bed_min_s"]:
        errs.append(f"{name}: a {len(x) / sr:.1f} s bed repeats like a rhythm (min {gates['bed_min_s']} s)")
    return errs


def role_errors(name, recipe):
    errs = []
    total = int(float(recipe["duration"]) * synth.SR)
    layers, wpitch = synth.apply_weight(recipe)
    for i, layer in enumerate(layers):
        role = layer.get("role")
        if role not in ROLE_RULES:
            continue
        x = synth.render_layer(layer, total, np.random.default_rng(7), wpitch, 0)
        if np.max(np.abs(x)) <= 0:
            continue
        e = E.measure(x, synth.SR)
        want, ok = ROLE_RULES[role]
        if not ok(e):
            errs.append(f'{name} layer {i + 1} is a "{role}" but is not {want} (alone: transient {e["transient_ms"]} ms, tail {e["tail_ms"]} ms, sub {e["sub_share"]}, air {e["high_share"]})')
    return errs


def _bands(x, sr):
    """energy per third-octave band (63 Hz .. 12.5 kHz), in dB, over the layer's loudest 150 ms"""
    n = int(0.15 * sr)
    if len(x) > n:
        env = np.convolve(x * x, np.ones(n), "valid")
        i = int(np.argmax(env))
        x = x[i:i + n]
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    f = np.fft.rfftfreq(len(x), 1 / sr)
    centres = 63 * 2 ** (np.arange(24) / 3)
    out = []
    for c in centres:
        m = (f >= c / 2 ** (1 / 6)) & (f < c * 2 ** (1 / 6))
        out.append(10 * np.log10(spec[m].sum() + 1e-20) if m.any() else -200.0)
    return centres, np.array(out)


def masking_warnings(name, recipe):
    """two layers that hit together with their loudest bands on top of each other at similar levels mask each other:
    the ear hears one smeared layer, not two (pro practice: carve each layer its own band, or offset it in time)"""
    total = int(float(recipe["duration"]) * synth.SR)
    layers, wpitch = synth.apply_weight(recipe)
    rendered = []
    for i, layer in enumerate(layers):
        x = synth.render_layer(layer, total, np.random.default_rng(7), wpitch, 0)
        if np.max(np.abs(x)) <= 0:
            continue
        onset = int(np.argmax(np.abs(x) > np.max(np.abs(x)) * 0.3))
        c, b = _bands(x, synth.SR)
        rendered.append((i, layer.get("role", "?"), onset, float(np.sum(x * x)), c, b))
    if len(rendered) < 2:
        return []
    mix_e = sum(r[3] for r in rendered)
    warns = []
    for a in range(len(rendered)):
        for b_ in range(a + 1, len(rendered)):
            i, ri, oi, ei, c, bi = rendered[a]
            j, rj, oj, ej, _, bj = rendered[b_]
            if abs(oi - oj) > 0.03 * synth.SR or min(ei, ej) < 0.15 * mix_e:
                continue  # (offset in time, or one is a quiet sweetener: no fight)
            loud_i, loud_j = bi > bi.max() - 6, bj > bj.max() - 6
            both = loud_i & loud_j & (np.abs((bi - bi.max()) - (bj - bj.max())) < 6)
            share = both.sum() / max(1, min(loud_i.sum(), loud_j.sum()))
            if share >= 0.6 and both.sum() >= 2:
                lo, hi = c[both].min(), c[both].max()
                warns.append(f"{name}: layers {i + 1} ({ri}) and {j + 1} ({rj}) mask each other in {lo:.0f}-{hi:.0f} Hz "
                             f"({share * 100:.0f} % of their loudest bands, same moment) - carve one (a filter) or offset it in time")
    return warns


# THE MASKING GATE (LIMITATIONS_FIXES_V4 SFX-X B: "spectral masking gate not enforced in sets.py"): an ERROR for a set
# that declares "masking": "enforce" and for every set first committed on or after this date (or not committed yet);
# a WARNING for the sets that were already in the repo before the gate existed. No set is named: a rule by birth date
# (the set file's first commit), never a list - an old set that wants the error declares "enforce".
MASKING_ENFORCED_FROM = "2026-11-20"


def set_born(path):
    """the date (YYYY-MM-DD) the set file was first committed; "" when it is not committed yet (a new set); None when
    git cannot say (no git, a file outside any repository)"""
    import subprocess

    folder, base = os.path.split(os.path.abspath(path))
    try:
        out = subprocess.run(["git", "-C", folder, "log", "--diff-filter=A", "--follow", "--format=%cs", "--", base],
                             capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    dates = [d.strip() for d in out.stdout.splitlines() if d.strip()]
    return dates[-1] if dates else ""


def masking_mode(spec, path):
    """-> ("error" | "warn", why): how the masking check counts for this set"""
    declared = spec.get("masking") if isinstance(spec, dict) else None
    if declared == "enforce":
        return "error", 'the set declares "masking": "enforce"'
    born = set_born(path)
    if born == "":
        return "error", "a new set (not committed yet): masking is an error for sets made since " + MASKING_ENFORCED_FROM
    if born is None:
        return "warn", "the set's age is unknown (no git history): a warning; declare \"masking\": \"enforce\" for the error"
    if born >= MASKING_ENFORCED_FROM:
        return "error", f"a new set (first committed {born}): masking is an error for sets made since {MASKING_ENFORCED_FROM}"
    return "warn", (f"an older set (first committed {born}, before the gate on {MASKING_ENFORCED_FROM}): a warning; "
                    "carve the layers, then declare \"masking\": \"enforce\"")


def takes_of(name, out_dir):
    takes = [os.path.join(out_dir, f"{name}.ogg")]
    i = 2
    while os.path.isfile(os.path.join(out_dir, f"{name}_{i}.ogg")):
        takes.append(os.path.join(out_dir, f"{name}_{i}.ogg"))
        i += 1
    return takes


def draw(set_name, recipes, measured, out_png):
    members = sorted({r["_member"] for r in recipes.values()})
    cols = max(len([n for n in recipes if recipes[n]["_member"] == m]) for m in members)
    span = max(len(measured[n]["x"]) for n in recipes) / synth.SR  # one time scale: lengths compare at a glance
    fig, axes = plt.subplots(len(members), cols, figsize=(3.6 * cols, 2.0 * len(members)), facecolor="#14161b", squeeze=False)
    for r, m in enumerate(members):
        names = sorted([n for n in recipes if recipes[n]["_member"] == m], key=lambda n: recipes[n]["_weight_rank"])
        for c in range(cols):
            ax = axes[r][c]
            ax.set_facecolor("#14161b")
            ax.set_xticks([])
            ax.set_yticks([])
            if c >= len(names):
                ax.axis("off")
                continue
            n = names[c]
            x = measured[n]["x"]
            mm, fs, _ = E.mel(x, synth.SR, bands=64)
            ax.imshow(np.clip(mm, mm.max() - 80, mm.max()), aspect="auto", origin="lower", cmap="magma", extent=[0, mm.shape[1] * fs, 0, 64])
            e = measured[n]["ears"]
            ax.set_title(f"{n}\n{e['lufs']} LUFS · {e['brightness_hz']} Hz · tail {e['tail_ms']} ms", color="#e8e6e1", fontsize=7, loc="left")
    fig.suptitle(f"set {set_name} — rows = members, columns = light .. heavy", color="#e8e6e1", fontsize=10, x=0.01, ha="left")
    fig.tight_layout()
    os.makedirs(os.path.dirname(out_png), exist_ok=True)
    fig.savefig(out_png, dpi=80, facecolor="#14161b")
    plt.close(fig)


def run_set(path, out_dir):
    with open(path, encoding="utf-8") as fh:
        spec = json.load(fh)
    set_name = os.path.splitext(os.path.basename(path))[0]
    gates = {"loudness_spread": 2.0, "take_min": 0.35, "take_max": 6.0, "surface_min": 1.0, "seam_level_db": 3.0,
             "seam_bright": 0.25, "bed_min_s": 12.0, "heavy_sub_min": 0.1}
    gates.update(spec.get("gates", {}))
    recipes = resolve(spec)
    # --- synth-only gate (owner verdict 2026-10-13: "pure synth is audio slop"): an error beside the set's other
    # gates, never instead of them (a synth-only set still hears every other fault it has) ---
    _so = synth_only.check_synth_only(set_name, spec, path.replace(os.sep, "/"))
    rdir = os.path.join(out_dir, "sets", set_name)
    os.makedirs(rdir, exist_ok=True)
    for n, r in recipes.items():
        with open(os.path.join(rdir, f"{n}.json"), "w", encoding="utf-8", newline="\n") as fh:
            json.dump({k: v for k, v in r.items() if not k.startswith("_")}, fh, indent=1)
    errors, warns = [], []
    if _so["level"] == "error":
        errors.append(_so["msg"])
    elif _so["level"] == "warn":
        warns.append(_so["msg"])
    mask_level, mask_why = masking_mode(spec, path)
    for n, r in recipes.items():
        errors += role_errors(n, r)
        found = masking_warnings(n, r)
        if mask_level == "error":
            errors += [f"{w} [masking is an error here: {mask_why}]" for w in found]
        else:
            warns += found
    # render through the one synth (stdout of synth.main is its own verdict: swallow it, keep ours last)
    import contextlib
    import io

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = synth.main(sorted(recipes), rdir, out_dir)
    if code != 0:
        v = json.loads(buf.getvalue().strip().splitlines()[-1])
        return {"set": set_name, "ok": False, "errors": [v["summary"]], "warnings": [], "sounds": []}
    measured = {}
    for n, r in recipes.items():
        takes = takes_of(n, out_dir)
        for t in takes:
            res = check.check_file(t)
            if not res["ok"]:
                bad = [c for c in res["checks"] if not c["ok"] and c["severity"] == "error"]
                errors.append(f"{os.path.basename(t)}: " + ", ".join(f"{c['name']}={c['value']} ({c['fix']})" for c in bad))
        xs = [E.decode(t)[0] for t in takes]
        if r.get("loop"):
            for t, xt in zip(takes, xs):
                errors += seam_errors(os.path.basename(t), xt, E.SR, gates)
        es = [E.measure(x, synth.SR, loop=r.get("loop", False)) for x in xs]
        measured[n] = {"x": xs[0], "xs": xs, "ears": es[0], "takes": es}
        if len(es) > 1:
            dists = [E.distance(es[i], es[j]) for i in range(len(es)) for j in range(i + 1, len(es))]
            if min(dists) < gates["take_min"]:
                errors.append(f"{n}: takes sound alike (distance {min(dists):.2f} < {gates['take_min']}) — machine-gun repetition: vary a sample (round-robin list), the modal strike, pitch or a noise layer")
            if max(dists) > gates["take_max"]:
                errors.append(f"{n}: a take left the family (distance {max(dists):.2f} > {gates['take_max']}) — narrow the variation")
    # loudness per class (the medium / single take of each member)
    by_class = {}
    for n, r in recipes.items():
        ranks = sorted(rr["_weight_rank"] for rr in recipes.values() if rr["_member"] == r["_member"])
        mid = ranks[len(ranks) // 2]
        if r["_weight_rank"] == mid:
            by_class.setdefault(r["_class"], []).append((n, measured[n]["ears"]["lufs"]))
    for cls, vals in by_class.items():
        if len(vals) > 1:
            lo, hi = min(vals, key=lambda v: v[1]), max(vals, key=lambda v: v[1])
            if hi[1] - lo[1] > gates["loudness_spread"]:
                errors.append(f'class "{cls}": {hi[0]} {hi[1]} LUFS vs {lo[0]} {lo[1]} LUFS — {hi[1] - lo[1]:.1f} LU apart (max {gates["loudness_spread"]}): one family, one loudness (set "loudness" in the set)')
    # weights: heavier never quieter / brighter
    for m in {r["_member"] for r in recipes.values()}:
        names = sorted([n for n in recipes if recipes[n]["_member"] == m], key=lambda n: recipes[n]["_weight_rank"])
        for a, b in zip(names, names[1:]):
            ea, eb = measured[a]["ears"], measured[b]["ears"]
            if eb["lufs"] < ea["lufs"] - 0.5:
                errors.append(f"{b} is quieter than {a} ({eb['lufs']} vs {ea['lufs']} LUFS): heavier must not be quieter (weight_gain on the body/sub layers)")
            if eb["brightness_hz"] > ea["brightness_hz"] * 1.1:
                errors.append(f"{b} is brighter than {a} ({eb['brightness_hz']} vs {ea['brightness_hz']} Hz): heavier must not be brighter")
        # the SUB DROP on the impact (the anime / fighting-game vocabulary): a hit's heaviest take carries at least the
        # sub its middle take does in its first 150 ms, and some (heavy_sub_min) - a heavy hit that thins out reads weak
        if len(names) >= 2 and recipes[names[-1]]["_class"] == "hit":
            heavy, mid = names[-1], names[len(names) // 2 - (1 if len(names) % 2 == 0 else 0)]
            # the median over the takes (one take is noise: a modal strike moves 0.2 -> 0.7 between takes); a hit
            # already mostly sub (>= 0.75) has its drop even when a bigger transient thins the share a little
            sh = float(np.median([early_sub(x, E.SR) for x in measured[heavy]["xs"]]))
            sm = float(np.median([early_sub(x, E.SR) for x in measured[mid]["xs"]]))
            if heavy != mid and sh < sm - 0.05 and sh < 0.75:
                errors.append(f"{heavy} drops less sub on the impact than {mid} ({sh:.2f} vs {sm:.2f} of the first 150 ms under 120 Hz): heavier hits drop MORE sub (weight_gain on the sub layer)")
            if sh < gates["heavy_sub_min"]:
                errors.append(f"{heavy} has almost no sub on the impact ({sh:.2f} < {gates['heavy_sub_min']}): a heavy hit needs its drop (a sub layer, weight_gain)")
    # the matrix: one weapon on two surfaces must not sound alike (the medium takes; surface_min apart by the ears)
    matrix = []
    mids = {}
    for n, r in recipes.items():
        if r.get("_cell"):
            ranks = sorted(rr["_weight_rank"] for rr in recipes.values() if rr["_member"] == r["_member"])
            if r["_weight_rank"] == ranks[len(ranks) // 2]:
                mids[r["_cell"]] = n
    for w in sorted({c[0] for c in mids}):
        row = sorted((c[1], n) for c, n in mids.items() if c[0] == w)
        for i in range(len(row)):
            for j in range(i + 1, len(row)):
                d = E.distance(measured[row[i][1]]["ears"], measured[row[j][1]]["ears"])
                matrix.append({"weapon": w, "a": row[i][0], "b": row[j][0], "distance": round(float(d), 2)})
                if d < gates["surface_min"]:
                    errors.append(f"{w} on {row[i][0]} and on {row[j][0]} sound alike (distance {d:.2f} < {gates['surface_min']}) — give the surfaces their own body: a modal resonance, a grit / wet layer, a different thud filter")
    png = os.path.join(out_dir, "sheets", f"set_{set_name}.png")
    draw(set_name, recipes, measured, png)
    sounds = [{"name": n, "member": recipes[n]["_member"], "weight": recipes[n]["weight"], "ears": measured[n]["ears"]} for n in sorted(recipes)]
    return {"set": set_name, "ok": not errors, "errors": errors, "warnings": warns, "sheet": png.replace("\\", "/"), "sounds": sounds, "matrix": matrix,
            "masking": {"level": mask_level, "why": mask_why}}


def main(argv):
    sets_dir, out_dir, names = os.path.join("assets", "sounds", "sets"), os.path.join("build", "sounds"), []
    i = 0
    while i < len(argv):
        if argv[i] in ("--sets", "--out"):
            if argv[i] == "--sets":
                sets_dir = argv[i + 1]
            else:
                out_dir = argv[i + 1]
            i += 2
            continue
        names.append(argv[i])
        i += 1
    if not names or names == ["all"]:
        names = sorted(f[:-5] for f in os.listdir(sets_dir) if f.endswith(".json")) if os.path.isdir(sets_dir) else []
    if not names:
        print(json.dumps({"status": "fail", "summary": f"no sets in {sets_dir}", "next_action": f"write one: {sets_dir}/<set>.json (shape: top of kit/audio/sets.py)"}))
        return 1
    results = []
    for n in names:
        # a set name, or a path to a set file
        p = n if (n.endswith(".json") and os.path.isfile(n)) else os.path.join(sets_dir, f"{n}.json")
        if not os.path.isfile(p):
            results.append({"set": n, "ok": False, "errors": [f"no set file {p}"], "warnings": [], "sounds": []})
            continue
        try:
            results.append(run_set(p, out_dir))
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            results.append({"set": n, "ok": False, "errors": [f"{type(exc).__name__}: {exc}"], "warnings": [], "sounds": []})
    bad = [r for r in results if not r["ok"]]
    count = sum(len(r["sounds"]) for r in results)
    if bad:
        summary = f"{len(bad)} set(s) fail: " + " | ".join(f"{r['set']}: " + " / ".join(r["errors"]) for r in bad)
        nxt = f"fix {bad[0]['set']}: {bad[0]['errors'][0]}"
    else:
        summary = f"{len(results)} set(s), {count} sound(s) rendered and gated as families"
        nxt = f"look at {results[0]['sheet']} — then listen: lune run kit sfx listen " + " ".join(s["name"] for s in results[0]["sounds"][:6])
    print(json.dumps({"status": "fail" if bad else "pass", "summary": summary, "next_action": nxt, "sets": results}))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
