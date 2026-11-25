"""rbx_pack.py — a build script READS its asset's pack (assets/models/<asset>.pack.json, written by `kit pack` and
scanned from the kit's own files): `pk = a.pack()` in a build, then

    pk.length_mm                        the real object's length (`kit pack <asset> object "<name>" --length dims:<id>`)
    pk.size("slide.length")             a size in mm with its source (`kit pack <asset> size slide.length dims:<id>`)
    pk.profile("slide")                 a traced part's outline in mm (kit refs profiles: f forward, h up)
    pk.extents("slide")                 its [f0, f1, h0, h1] in mm
    pk.outline() / pk.holes()           the whole traced outline / its openings in mm
    pk.colour("slide")                  the part's MEASURED colour, LINEAR (what a.material(color=) takes; the
                                        lighting taken out); pk.colour_srgb() as measured; pk.rough / pk.metal
    pk.levels("<reference model>")      a reference model's horizontal slices (kit refs measure: a grip that wraps)
    pk.draft()                          the generated draft's GLB (kit gen views / kit gen), to import or compare

Why: numbers typed into a script from memory (or copied by hand from one tool to another) were how the Glock 17 got
a 7%-short grip and no measured colour; a pack value carries its source, and a missing one says exactly which
command fills it. Pure python (no bpy): unit-tested; every value read is listed in the verdict (facts.pack).
"""

import json
import os


def _linear(s):
    """sRGB 0..1 -> linear (IEC 61966-2-1; rbx_pbr.to_linear)"""
    s = min(1.0, max(0.0, float(s)))
    return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4


class PackMissing(KeyError):
    """a value the build asked for is not in the pack: the message is the command that puts it there"""

    def __str__(self):
        return str(self.args[0]) if self.args else "pack: missing"


class Pack:
    def __init__(self, asset, root, folder=None):
        """folder: where <asset>.pack.json lies — beside the build script (assets/models/ for every asset; a selftest
        fixture keeps its own beside it). Paths inside the pack are the repository's (root)."""
        self.asset, self.root, self._mod = asset, root, None
        self.path = os.path.join(folder or os.path.join(root, "assets", "models"), f"{asset}.pack.json")
        try:
            with open(self.path, encoding="utf-8") as fh:
                self.data = json.load(fh)
        except (OSError, ValueError):
            self.data = {}
        if not isinstance(self.data, dict):
            self.data = {}  # (a pack file that is not a pack is no pack)
        if not isinstance(self.data.get("found"), dict):
            self.data.pop("found", None)
        self._rescan()
        self.used = []  # (kind, key, value, source): what the build read, for the verdict
        self._profiles = {}

    def _rescan(self):
        """what the asset HAS, found again now (kit/tools/pack.py scan): a profile, trace, model or draft made after
        the last `kit pack` is read too — the file's own `found` (a fixture's) is kept where the scan finds nothing"""
        tools = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools")
        if not os.path.isfile(os.path.join(tools, "pack.py")):
            return
        import importlib.util  # noqa: PLC0415

        try:
            spec = importlib.util.spec_from_file_location("kit_tools_pack", os.path.join(tools, "pack.py"))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            fresh = mod.scan(self.asset, self.root)
        except Exception:  # noqa: BLE001  (the scan is a convenience: the pack file still stands)
            return
        self._mod = mod
        found = dict(self.data.get("found") or {})

        def as_dict(v):
            return v if isinstance(v, dict) else {}

        for key in ("traces", "models", "drafts"):
            # the scan is the truth where it finds anything (a trace deleted or renamed since is gone); the file's
            # own entries stand only where the scan finds none of that kind (a fixture's pack beside its script)
            found[key] = as_dict(fresh.get(key)) or as_dict(found.get(key))
        albedo = found.get("albedo") if isinstance(found.get("albedo"), list) else []
        found["albedo"] = sorted(set(map(str, albedo)) | set(fresh.get("albedo") or []))
        found["params"] = fresh.get("params") or found.get("params")
        if self.data or any(found.get(k) for k in ("traces", "models", "drafts")):
            self.data = {**self.data, "found": found}

    # ---------------------------------------------------------------- helpers
    def _missing(self, what, fix):
        raise PackMissing(f"pack {self.asset}: {what} — {fix}")

    def _note(self, kind, key, value, source):
        self.used.append({"kind": kind, "key": key, "value": value, "source": source})
        return value

    def _found(self):
        return self.data.get("found") or {}

    @property
    def exists(self):
        return bool(self.data)

    @property
    def length_mm(self):
        obj = self.data.get("object") or {}
        if not obj.get("length_mm"):
            self._missing("no real length", f'lune run kit pack {self.asset} object "<name>" --length dims:<id>')
        return self._note("object", "length_mm", float(obj["length_mm"]),
                          "unsourced (given)" if obj.get("trust") == "unsourced" or obj.get("source") in (None, "given")
                          else obj.get("source"))

    def size(self, key, default=None):
        """a size in mm by its key ('slide.length'); default= a fallback said in the verdict as UNSOURCED"""
        row = (self.data.get("sizes") or {}).get(key)
        if row is None:
            if default is not None:
                return self._note("size", key, float(default), "default (not in the pack)")
            self._missing(f"no size '{key}'", f"lune run kit pack {self.asset} size {key} dims:<id>  "
                          f'(lune run kit refs dims find "<object> <part>")')
        return self._note("size", key, float(row["mm"]),
                          "unsourced (given)" if row.get("trust") == "unsourced" else row.get("source"))

    def sizes(self):
        return {k: float(v["mm"]) for k, v in (self.data.get("sizes") or {}).items()}

    # ---------------------------------------------------------------- traced profiles (kit refs profiles, in mm)
    def _profiles_for(self, part=None, trace=None, view="side"):
        """the mm profiles holding `part` — of the named trace, else of a trace of `view` (side by default: a front
        view's slide is its WIDTH, never its length; view=None: any), a photo's before a reference model's"""
        traces = self._found().get("traces") or {}
        names = [trace] if trace else sorted(
            (n for n in traces if view is None or traces[n].get("view") == view),
            key=lambda n: (traces[n].get("source") != "photo", n))
        broken = []
        for name in names:
            t = traces.get(name) or {}
            rel = t.get("profiles")
            if not rel:
                continue
            if rel not in self._profiles:
                try:
                    with open(os.path.join(self.root, rel), encoding="utf-8") as fh:
                        self._profiles[rel] = json.load(fh)
                except (OSError, ValueError):
                    broken.append(rel)  # (a stale entry: the next trace may hold the part)
                    continue
            prof = self._profiles[rel]
            if not isinstance(prof, dict) or not isinstance(prof.get("parts", {}), dict):
                broken.append(rel)  # (not a profiles file kit refs profiles wrote)
                continue
            if part is None or part in (prof.get("parts") or {}):
                return name, rel, prof
        where = f"trace '{trace}'" if trace else (f"a {view} trace" if view else "any trace")
        if broken:
            where += (f" (gone or broken: {', '.join(broken)} — make it again: lune run kit refs profiles "
                      f"<its trace>.trace.json --anchor <part> --length-mm <mm>; a trace deleted since: lune run kit "
                      f"pack {self.asset})")
        self._missing(f"no mm profile of '{part}' in {where}" if part else f"no mm outline in {where}",
                      f"lune run kit refs profiles assets/models/<trace>.trace.json --anchor <part> --length-mm <real "
                      f"length>" + (f"   (the part traced: kit trace ... --part-box / --part-text {part}=...)"
                                    if part else ""))

    def profile(self, part, trace=None, view="side"):
        """the part's traced outline in mm [(f, h), ...] (f forward of the anchor's rear end, h up) — of the side view
        unless view= / trace= say another"""
        name, rel, prof = self._profiles_for(part, trace, view)
        pts = self._points(prof["parts"][part], rel, f"part '{part}'")
        self._note("profile", f"{part}@{name}", len(pts), rel)
        return pts

    def _points(self, ring, rel, what):
        """[(f, h), ...] from a profiles file's ring — a malformed one is said, never a raw exception"""
        try:
            pts = [(float(p[0]), float(p[1])) for p in ring]
        except (TypeError, ValueError, IndexError, KeyError):
            pts = []
        if len(pts) < 3 and what != "holes":
            self._missing(f"the profiles file {rel} holds no usable {what}",
                          f"make it again: lune run kit refs profiles <its trace>.trace.json --anchor <part> --length-mm "
                          f"<mm>")
        return pts

    def extents(self, part, trace=None, view="side"):
        name, rel, prof = self._profiles_for(part, trace, view)
        e = (prof.get("extents") if isinstance(prof.get("extents"), dict) else {}).get(part)
        try:
            e = [float(x) for x in e]
            assert len(e) == 4
        except (TypeError, ValueError, AssertionError):
            ring = self._points(prof["parts"][part], rel, f"part '{part}'")
            e = [min(p[0] for p in ring), max(p[0] for p in ring), min(p[1] for p in ring), max(p[1] for p in ring)]
        return self._note("extents", f"{part}@{name}", e, rel)

    def outline(self, trace=None, view="side"):
        name, rel, prof = self._profiles_for(None, trace, view)
        return self._note("outline", name, self._points(prof.get("outline") or [], rel, "outline"), rel)

    def holes(self, trace=None, view="side"):
        name, rel, prof = self._profiles_for(None, trace, view)
        holes = prof.get("holes") if isinstance(prof.get("holes"), list) else []
        return self._note("holes", name, [self._points(h, rel, "holes") for h in holes], rel)

    # ---------------------------------------------------------------- measured colour
    def _colour_row(self, part):
        row = (self.data.get("colours") or {}).get(part)
        if row is None:
            self._missing(f"no measured colour of '{part}'",
                          f"lune run kit vision albedo <the traced picture> -o assets/models/{self.asset}.albedo.npz  "
                          f"then  lune run kit pack {self.asset} colours --trace <the trace>")
        return row

    def colour_srgb(self, part):
        """the part's measured colour as the picture holds it (sRGB 0..1)"""
        row = self._colour_row(part)
        return tuple(self._note("colour", part, [float(x) for x in row["srgb"]], row.get("albedo")))

    def colour(self, part):
        """the part's measured colour, LINEAR — straight into a.material(name, color=pk.colour(part), ...)"""
        return tuple(round(_linear(c), 4) for c in self.colour_srgb(part))

    def rough(self, part, default=None):
        row = (self.data.get("colours") or {}).get(part) or {}
        if "rough" not in row:
            if default is not None:
                return self._note("rough", part, float(default), "default (not measured)")
            self._colour_row(part)
            self._missing(f"no measured roughness of '{part}'", "take the albedo again (Marigold-IID gives it)")
        return self._note("rough", part, float(row["rough"]), row.get("albedo"))

    def metal(self, part, default=None):
        row = (self.data.get("colours") or {}).get(part) or {}
        if "metal" not in row:
            if default is not None:
                return self._note("metal", part, float(default), "default (not measured)")
            self._colour_row(part)
            self._missing(f"no measured metalness of '{part}'", "take the albedo again (Marigold-IID gives it)")
        return self._note("metal", part, float(row["metal"]), row.get("albedo"))

    # ---------------------------------------------------------------- reference models + drafts
    def levels(self, model):
        entry = (self._found().get("models") or {}).get(model) or {}
        rel = entry.get("measure")
        if not rel:
            self._missing(f"no measured reference model '{model}'",
                          f"lune run kit refs measure <model.glb> --name {model} --length-mm <real length>")
        try:
            with open(os.path.join(self.root, rel), encoding="utf-8") as fh:
                lv = json.load(fh).get("levels") or []
        except (OSError, ValueError, AttributeError):
            self._missing(f"the measure file {rel} of '{model}' is gone or broken",
                          f"lune run kit refs measure <model.glb> --name {model} --length-mm <real length>  (then: "
                          f"lune run kit pack {self.asset})")
        return self._note("levels", model, lv, rel)

    def draft(self, name=None):
        drafts = self._found().get("drafts") or {}
        hits = [n for n in sorted(drafts) if drafts[n].get("glb") and (name is None or n == name)]
        if not hits:
            self._missing(f"no generated draft{' ' + name if name else ''}",
                          f"lune run kit gen views {self.asset}_draft --view side=<cut-out> --view front=<cut-out> "
                          f"(or lune run kit gen {self.asset}_draft --image <picture>)")
        return self._note("draft", hits[0], drafts[hits[0]]["glb"], drafts[hits[0]].get("record"))

    def facts(self):
        """for the verdict: how many values the build read from the pack, and the unsourced ones"""
        return {"pack": os.path.relpath(self.path, self.root).replace("\\", "/") if self.exists else None,
                "read": len(self.used), "kinds": sorted({u["kind"] for u in self.used}),
                "unsourced": [u["key"] for u in self.used
                              if str(u.get("source", "")).startswith(("default", "unsourced"))],
                "inputs_stale": self.inputs_stale()}

    def inputs_stale(self):
        """True when the pack's chosen values no longer match the checksum `kit pack` saved with them (edited by hand):
        the build's identity (rbx_score.build_identity) folds the SAVED checksum in — `kit pack <asset>` refreshes it"""
        if self._mod is None or not self.data:
            return False
        try:
            return self._mod.inputs_sha(self.data) != self.data.get("inputs_sha")
        except Exception:  # noqa: BLE001
            return False
