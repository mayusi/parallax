"""fit.py — FIT an asset's a.param() numbers to its REFERENCES, never to the quality score: CMA-ES
(kit/blender/cmaes.py) over --geo builds through the persistent Blender worker (kit/blender/worker.py).

    python kit/blender/fit.py <asset> [--evals 120] [--only a,b] [--write] [--sigma 0.3]
                              [--weights side=1,front=0.4] [--hold <view>]
    (lune run kit fit <asset> starts the worker and runs this)

Every a.param(name, default, lo, hi) of the build script is a dimension (or --only those). One evaluation = one --geo
build with the trial values (env KIT_PARAMS), and its LOSS is how far the build is from its references:
    1 - silhouette IoU, averaged over the reference views (facts.references: what Asset(reference=...) and
    a.trace_match measure), + the proportion error |1 - aspect(model) / aspect(reference)|.
The quality score never enters: a fit that chased it would buy detail, not resemblance (the 2026-10-05 lesson).
THE PARTS too, where the build links them (a.trace_match(..., parts={traced part: [model parts]})): each traced part's
own IoU against its model part in that view - where the guard, the grip, the pommel sit, not only the whole
outline - is in the loss (PART_WEIGHT of 1 - their mean IoU); a linked part the view cannot find counts as missed.
The OPENINGS too (facts.references[i]["openings"], where a trace names its see-through holes: a trigger guard's
window, the gap between a guard and the grip): OPENING_WEIGHT of 1 - their IoU - one outline IoU barely moves when
an opening is closed, so without it a fit trades a window away for a hair of outline.
THE CROSS-SECTIONS (a.section_match: facts.deep.section_match): each slice's width, depth and roundness against the
measured reference's at that height (SECTION_WEIGHT of their mean relative error, each capped at 1; a slice missing on one side is a full miss,
one the reference has in pieces - its row marked "skipped" - is left out). THE 3D FORM (a.form_match against a real model: facts.deep.form_match):
the build's surface against the model's in both directions - the depth and the cavities no picture shows
(FORM_WEIGHT of the mean gap over twice the bar, 3 mm unless the build names one). The terms are reported apart
(terms_before / terms_after): what the fit gained, and where. THE RELIEF (a.trace_match(..., depth=True):
facts.references[i]["depth"]): DEPTH_WEIGHT of (1 - its correlation with the photo's relief) / 2.
--weights: how far each view's picture is to be trusted (his V3 list, 3D stage A.3: an orthographic drawing 1.0, a
photo about 0.7, a concept 0.4; a view not named weighs 1) - the loss is their weighted mean.
--hold <view>: that view is NOT fitted to: the fit sees the others, and the held-out view's IoU before and after says
whether it learned the object or only those pictures. A fit that leaves the held-out view WORSE (by HOLD_SLACK) is
an overfit: said, and --write writes nothing.
-> the best values (assets/models/<asset>.params.json with --write: every later build uses them) and the
   before / after match per view.
"""

import json
import os
import sys
import time
import urllib.request

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from cmaes import CMAES  # noqa: E402


def _emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


class Worker:
    """the persistent Blender (worker.py) this project runs: <build>/worker.json says where"""

    def __init__(self, build_dir):
        with open(os.path.join(build_dir, "worker.json"), encoding="utf-8") as fh:
            st = json.load(fh)
        self.base = f"http://127.0.0.1:{st['port']}"
        self.headers = {"X-Kit-Token": st["token"], "Content-Type": "application/json"}
        self.build_dir = build_dir

    def _call(self, method, path, body=None):
        req = urllib.request.Request(self.base + path, method=method, headers=self.headers,
                                     data=json.dumps(body).encode() if body is not None else None)
        return json.loads(urllib.request.urlopen(req, timeout=60).read())

    def build(self, script, params):
        """one --geo build with these a.param values (merged over the kept ones by rbx; for THIS script only) -> its
        JSON verdict (or None when it crashed)"""
        env = {"KIT_BUILD": self.build_dir, "KIT_PARAMS": json.dumps(params),
               "KIT_PARAMS_SCRIPT": os.path.abspath(script)}
        job = self._call("POST", "/build", {"script": script, "args": ["--geo"], "env": env})
        if job.get("restart"):
            raise RuntimeError("the kit changed during the fit: restart it")
        while True:
            r = self._call("GET", f"/result/{job['job']}")
            if r.get("done"):
                for line in reversed(r.get("output", "").splitlines()):
                    if line.startswith("{") and '"schema"' in line:
                        try:
                            return json.loads(line)
                        except ValueError:
                            break
                return None
            time.sleep(0.05)


HOLD_SLACK = 0.01   # the held-out view's IoU may fall this much (noise) before the fit is called an overfit
PART_WEIGHT = 1.0   # the linked parts' miss (1 - their mean IoU) beside the whole outline's: where each part sits


def part_miss(ref):
    """a reference view's linked parts (facts.references[i]["parts"]) -> 1 - their mean IoU, or None when it links
    none; a part the view could not find (an "error" row) is a full miss"""
    parts = ref.get("parts") or {}
    rows = [0.0 if "error" in (r or {}) else float((r or {}).get("iou", 0.0)) for r in parts.values()]
    return (1.0 - float(np.mean(rows))) if rows else None


OPENING_WEIGHT = 1.0   # the openings' miss (1 - their IoU) beside the outline's: what the outline cannot see
SECTION_WEIGHT = 1.0   # the cross-sections' mean relative error (width and depth) at the measured heights
FORM_WEIGHT = 1.0      # the 3D form's mean gap (both ways) over twice its bar, at most 1: depth and cavities
FORM_BAR_MM = 3.0      # (a.form_match without bar_mm=)
DEPTH_WEIGHT = 1.0     # the relief's miss ((1 - its corr with the photo's) / 2): a.trace_match(..., depth=True)
CRASH_LOSS = 10.0      # a trial whose build crashed or measured nothing: worse than any loss the terms can make
#                        (outline about 1.5 at most + four terms of at most 1)


def section_miss(deep):
    """facts.deep -> the cross-sections' mean relative error (width, depth, squareness), or None when the build holds
    none (a.section_match)"""
    rows = (deep or {}).get("section_match") or []
    errs = []
    for row in rows:
        if row.get("skipped"):
            continue            # (that reference's slice is in pieces there: not a section)
        b, r = row.get("build"), row.get("reference")
        if not b or not r:
            errs.append(1.0)
            continue
        # width, depth and ROUNDNESS (squareness: 2 an ellipse, 17 a box - a boxy grip as wide and deep as the
        # wrapped one is still wrong: the fixture pair section_boxy / section_wrapped measured it), each capped at 1
        e = [min(1.0, abs(float(b[k]) / float(r[k]) - 1.0))
             for k in ("width_mm", "depth_mm", "squareness") if float(r.get(k) or 0) > 0 and b.get(k) is not None]
        errs.append(float(np.mean(e)) if e else 1.0)
    return float(np.mean(errs)) if errs else None


def form_miss(deep):
    """facts.deep -> the 3D form's miss (mean gap both ways over twice the bar, at most 1), or None (a.form_match)"""
    reps = [r for r in (deep or {}).get("form_match") or [] if isinstance(r, dict)]
    out = []
    for r in reps:
        if r.get("extra_mean_mm") is None or r.get("missing_mean_mm") is None:
            out.append(1.0)     # (a side measured nothing - an empty surface: a full miss, never a perfect 0)
            continue
        gap = float(r["extra_mean_mm"]) + float(r["missing_mean_mm"])
        out.append(min(1.0, gap / (2.0 * float(r.get("bar_mm") or FORM_BAR_MM))))
    return float(np.mean(out)) if out else None


def terms_of(verdict, weights=None, hold=None):
    """the loss's terms -> ({term: value}, every view's IoU): "outline" (1 - the weighted mean silhouette IoU + the
    weighted proportion error), "parts", "openings" (the views'), "sections", "form" (the whole build's) - each
    present only when the build has it; the held-out view (hold) is in the IoUs but in no term"""
    facts = (verdict or {}).get("facts") or {}
    refs = facts.get("references") or []
    per_view = {r.get("view"): round(float(r.get("iou", 0.0)), 4) for r in refs}
    terms = {}
    fit = [r for r in refs if r.get("view") != hold]
    w = np.array([float((weights or {}).get(r.get("view"), 1.0)) for r in fit])
    if fit and w.sum() > 0:
        ious = np.array([float(r.get("iou", 0.0)) for r in fit])
        aspect = np.array([abs(1.0 - float(r.get("aspect_model_vs_ref", 1.0))) for r in fit])
        terms["outline"] = (1.0 - float(np.average(ious, weights=w))) + 0.5 * float(np.average(aspect, weights=w))
        miss = [(m, wi) for m, wi in ((part_miss(r), wi) for r, wi in zip(fit, w)) if m is not None]
        if miss and sum(wi for _m, wi in miss) > 0:
            terms["parts"] = PART_WEIGHT * float(np.average([m for m, _w in miss], weights=[wi for _m, wi in miss]))
        holes = [(1.0 - float(r["openings"].get("iou", 0.0)), wi) for r, wi in zip(fit, w) if r.get("openings")]
        if holes and sum(wi for _h, wi in holes) > 0:
            terms["openings"] = OPENING_WEIGHT * float(np.average([h for h, _w in holes],
                                                                  weights=[wi for _h, wi in holes]))
        reliefs = [((1.0 - float(r["depth"]["corr"])) / 2.0, wi) for r, wi in zip(fit, w)
                   if isinstance(r.get("depth"), dict) and "corr" in r["depth"]]
        if reliefs and sum(wi for _d, wi in reliefs) > 0:
            terms["depth"] = DEPTH_WEIGHT * float(np.average([d for d, _w in reliefs],
                                                             weights=[wi for _d, wi in reliefs]))
    deep = facts.get("deep") or {}
    for key, fn, weight in (("sections", section_miss, SECTION_WEIGHT), ("form", form_miss, FORM_WEIGHT)):
        v = fn(deep)
        if v is not None:
            terms[key] = weight * v
    return terms, per_view


def loss_of(verdict, weights=None, hold=None):
    """the sum of the loss's terms (terms_of) -> (loss, every view's IoU); None when there is nothing to fit to"""
    terms, per_view = terms_of(verdict, weights, hold)
    return (float(sum(terms.values())) if terms else None), per_view


def parse_weights(text):
    """"side=1,front=0.4" -> {"side": 1.0, "front": 0.4}; a weight outside 0..1, or a part without "=", is refused"""
    out = {}
    for part in [x.strip() for x in str(text or "").split(",") if x.strip()]:
        if "=" not in part:
            raise ValueError(f"fit: --weights {part!r} - view=weight, e.g. side=1,front=0.4")
        view, v = (x.strip() for x in part.split("=", 1))
        if not 0.0 <= float(v) <= 1.0:
            raise ValueError(f"fit: --weights {view}={v} - a weight from 0 to 1")
        out[view] = float(v)
    return out


def main(argv):
    if not argv or argv[0].startswith("--"):
        return _emit("fail", "fit: needs an asset", "lune run kit fit <asset>")
    asset = argv[0]
    opt = {"evals": "120", "only": "", "sigma": "0.3", "models": "assets/models", "build": "build", "weights": "",
           "hold": ""}
    for i, a in enumerate(argv):
        if a.startswith("--") and a[2:] in opt and i + 1 < len(argv):
            opt[a[2:]] = argv[i + 1]
    script = os.path.join(opt["models"], f"build_{asset}.py")
    if not os.path.isfile(script):
        return _emit("fail", f"fit: no build script {script}", "lune run kit new asset <name>")
    try:
        weights = parse_weights(opt["weights"])
    except ValueError as e:
        return _emit("fail", str(e), "lune run kit fit <asset> --weights side=1,front=0.4")
    hold = opt["hold"] or None
    worker = Worker(opt["build"])
    first = worker.build(script, {})  # (the build as it is: defaults with the KEPT values over them)
    params = ((first or {}).get("facts") or {}).get("params") or {}
    if hold and hold not in {r.get("view") for r in ((first or {}).get("facts") or {}).get("references") or []}:
        return _emit("fail", f"fit: --hold {hold} - {asset} has no reference view of that name",
                     "hold out one of its reference views (facts.references)")
    base_loss, base_views = loss_of(first, weights, hold)
    base_terms = terms_of(first, weights, hold)[0]
    if base_loss is None:
        return _emit("fail", f"fit: {asset} has nothing to fit to (no reference view, no section_match, no form_match)",
                     "give the asset a reference: Asset(reference={'side': 'assets/models/<trace>.trace.json'}), "
                     "a.trace_match(...), a.section_match(...) or a.form_match(...) — a fit only ever chases "
                     "resemblance")
    only = [p for p in opt["only"].split(",") if p]
    names = [n for n in params if not only or n in only]
    if not names:
        return _emit("fail", f"fit: {asset} declares no a.param() to fit" + (f" among {only}" if only else ""),
                     'declare the numbers that shape it: L = a.param("barrel_length", 2.4, lo=1.8, hi=3.0)')
    lo = np.array([float(params[n]["lo"]) for n in names])
    hi = np.array([float(params[n]["hi"]) for n in names])
    x0 = np.array([float(params[n]["value"]) for n in names])
    span = np.maximum(hi - lo, 1e-9)
    current = {n: float(params[n]["value"]) for n in params}  # every param as the build uses it now
    best = {"loss": base_loss, "values": dict(zip(names, x0.tolist())), "views": base_views, "terms": base_terms}
    evals = [0]

    def f(z):
        values = lo + np.clip(z, 0.0, 1.0) * span
        trial = dict(zip(names, (float(v) for v in values)))
        v = worker.build(script, trial)
        evals[0] += 1
        terms, views = terms_of(v, weights, hold)
        if not terms:
            return CRASH_LOSS
        loss = float(sum(terms.values()))
        if loss < best["loss"]:
            best.update(loss=loss, values=trial, views=views, terms=terms)
        return loss

    es = CMAES((x0 - lo) / span, float(opt["sigma"]), lo=np.zeros(len(names)), hi=np.ones(len(names)), seed=0,
               max_evals=int(opt["evals"]), popsize=max(6, 4 + int(3 * np.log(len(names)))))
    while not es.done():
        zs = es.ask()
        es.tell(zs, [f(np.asarray(z)) for z in zs])
    improved = best["loss"] < base_loss - 1e-6
    held = None
    if hold:   # (the view the fit never saw: did it learn the object, or only the other pictures?)
        held = {"view": hold, "before": base_views.get(hold), "after": best["views"].get(hold)}
        held["overfit"] = bool(improved and held["after"] is not None and held["before"] is not None
                               and held["after"] < held["before"] - HOLD_SLACK)
    merged = {**current, **best["values"]}  # (--only fits some; the rest keep the values they had)
    out = {"asset": asset, "params": {k: round(v, 5) for k, v in merged.items()}, "fitted": names,
           "loss_before": round(base_loss, 4), "loss_after": round(best["loss"], 4),
           "views_before": base_views, "views_after": best["views"], "evaluations": evals[0], "improved": improved,
           "weights": weights, "held_out": held,
           "terms_before": {k: round(v, 4) for k, v in base_terms.items()},
           "terms_after": {k: round(v, 4) for k, v in best["terms"].items()}}
    path = os.path.join(opt["models"], f"{asset}.params.json")
    write = "--write" in argv and improved and not (held or {}).get("overfit")   # (never over the kept values with
    #                                                          something no better, nor with an overfit)
    if write:
        with open(path, "w", encoding="utf-8", newline=chr(10)) as fh:
            json.dump({"params": out["params"], "fitted": time.strftime("%Y-%m-%d %H:%M"),
                       "loss": out["loss_after"], "views": out["views_after"]}, fh, indent=1)
            fh.write(chr(10))
    vs = ", ".join(f"{k} {base_views.get(k, 0):.3f} -> {best['views'].get(k, 0):.3f}" for k in best["views"])
    keys = list(out["terms_before"]) + [k for k in out["terms_after"] if k not in out["terms_before"]]
    ts = ", ".join(f"{k} {out['terms_before'].get(k, 0):.3f} -> {out['terms_after'].get(k, 0):.3f}" for k in keys)
    vs = (f"silhouette IoU {vs}; " if vs else "") + f"loss terms {ts}"   # (each constraint before -> after)
    if held and held["overfit"]:
        return _emit("fail", f"fit {asset}: OVERFIT - the views it saw improved but the held-out {hold} view fell "
                     f"{held['before']:.3f} -> {held['after']:.3f} ({vs})"
                     + (" — nothing written" if "--write" in argv else ""),
                     "the params chase those pictures, not the object: fewer params (--only), tighter bounds, or "
                     "another reference view", fit=out)
    if not improved:
        return _emit("pass", f"fit {asset}: {evals[0]} builds found nothing better than the values it has "
                     f"({vs})" + (" — nothing written" if "--write" in argv else ""),
                     "the build already matches its references as well as these params can: change the shape (or "
                     "the params' bounds), not the numbers", fit=out)
    return _emit("pass", f"fit {asset}: {evals[0]} builds, {vs}; "
                 + ", ".join(f"{k} = {v:.4g}" for k, v in out["params"].items() if k in names)
                 + (f" -> {path}" if write else ""),
                 "look at the build; keep the values with --write (every later build uses them)" if not write
                 else f"lune run kit asset {asset} (the full build now uses the fitted values)", fit=out)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
