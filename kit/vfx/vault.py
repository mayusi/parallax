"""vault.py — the VFX library: EVERYTHING the VFX pipeline makes is saved, packaged by part, named properly, for reuse
and reference (the owner's rule, 2026-10-12: "anything ever made is to be saved ... packaged by parts, name properly").
Enforced: `kit vfx` and `kit vfx play --record` run `save`; `kit verify` runs `check` — an effect, part, texture, mesh
or preview that is not in the vault (or is stale) FAILS the gate. The vault never deletes: every version of every
source is kept, and the owner's verdicts stay with the version they were given to. A kit starter that `kit init`
seeded and nobody touched is the kit's work, not the project's (its text is one the kit's record holds:
kit/vfx/starters.json, kit/vfx/starters.py); `check` asks for it from its first edit, or once it is saved here.

    python kit/vfx/vault.py save    [--effects assets/effects] [--textures assets/textures] [--build build] [--out library/vfx]
    python kit/vfx/vault.py check   [same]                 -> fail when anything made is missing or stale
    python kit/vfx/vault.py list    [--out library/vfx]
    python kit/vfx/vault.py find    "<words>"
    python kit/vfx/vault.py get     <effect> --as <new>    (the effect + its parts + its textures into this project)
    python kit/vfx/vault.py verdict <effect> "<the owner's words>" [--score N]

library/vfx/
  INDEX.md, index.json             every effect / part / texture / mesh, what it is, where it is used, owner verdicts
  verdicts.json                    the owner's verdicts, each tied to the effect version it judged (never removed)
  effects/<name>/
      README.md                    what it is, the owner's verdict, beats, the parts it uses, every layer (name, kind,
                                   time, texture), the textures it needs, how to reuse it
      effect.json                  the source preset          expanded.json   as it plays (parts composed in)
      manifest.json                hashes of everything below + what each preview was made from
      previews/sheet.png           the frame strip            previews/<view>.png / <view>.mp4   recorded views
      previews/all.png, metrics.json, judge.png
      versions/<stamp>-<hash>.json every earlier version of effect.json
  parts/<name>/       part.json, README.md (points, layers, used by), versions/
  textures/<name>/    spec.json, texture.png (the finished sheet), README.md (recipe, grid, uploaded id, used by), versions/
  meshes/<name>/      spec.json, mesh.obj, README.md, versions/
Files are rewritten only when their bytes change (a rebuild with nothing new changes nothing in git).
"""
import argparse
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

VIEW_RE = re.compile(r"^(?P<name>.+)_play_(?P<view>[a-z0-9]+)\.(?P<ext>png|mp4)$")


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


TEXT_EXT = (".json", ".md", ".luau", ".lua", ".txt", ".py", ".toml", ".yaml", ".yml", ".csv", ".obj", ".mtl")
# (.obj / .mtl: a mesh is text - git writes the library's copy with CRLF, the mesh tool its build copy with LF or the
# reverse, and kit prove's LF sandbox found all 7 VFX meshes "stale" for their line endings alone)


def sha(path):
    """sha256 of a file; text files are hashed with CRLF read as LF, so the same content hashes the same in a
    checkout git wrote with Windows line endings (core.autocrlf: a fresh worktree) and one tools wrote with LF"""
    with open(path, "rb") as fh:
        data = fh.read()
    if path.lower().endswith(TEXT_EXT):
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001
        return default


def write_bytes(dst, data, written):
    """write only when the bytes differ (keeps git quiet on rebuilds)"""
    if os.path.isfile(dst):
        with open(dst, "rb") as fh:
            if fh.read() == data:
                return False
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "wb") as fh:
        fh.write(data)
    written.append(dst)
    return True


def write_text(dst, text, written):
    return write_bytes(dst, text.replace("\r\n", "\n").encode("utf-8"), written)


def write_json(dst, data, written):
    return write_text(dst, json.dumps(data, ensure_ascii=False, indent=1) + "\n", written)


def put(src, dst, written):
    if not os.path.isfile(src):
        return False
    with open(src, "rb") as fh:
        return write_bytes(dst, fh.read(), written)


def save_source(src, dst, versions_dir, written):
    """copy a source file into the package; the copy it replaces is kept in versions/<stamp>-<hash>.<ext>"""
    if not os.path.isfile(src):
        return False
    with open(src, "rb") as fh:
        new = fh.read()
    if os.path.isfile(dst):
        with open(dst, "rb") as fh:
            old = fh.read()
        if old == new:
            return False
        ext = os.path.splitext(dst)[1]
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(os.path.getmtime(dst)))
        write_bytes(os.path.join(versions_dir, f"{stamp}-{sha_bytes(old)[:8]}{ext}"), old, written)
    return write_bytes(dst, new, written)


def compress_video(src, dst, written):
    """a recorded view at 640 px (the full recordings are 10-16 MB): only when the source changed"""
    tmp = dst + ".tmp.mp4"
    try:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-vf", "scale=640:-2", "-c:v", "libx264",
                        "-crf", "30", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-an", tmp], check=True, timeout=600)
    except Exception:  # noqa: BLE001 — no ffmpeg: keep the original rather than nothing
        if os.path.isfile(tmp):
            os.remove(tmp)
        return put(src, dst, written)
    with open(tmp, "rb") as fh:
        data = fh.read()
    os.remove(tmp)
    return write_bytes(dst, data, written)


# ---------------------------------------------------------------- what exists in the project


def scan(a):
    eff_dir, tex_dir, build = a.effects, a.textures, a.build
    effects = {}
    for p in sorted(glob.glob(os.path.join(eff_dir, "*.json"))):
        n = os.path.basename(p)[:-5]
        if n.startswith("_"):
            continue
        d = read_json(p)
        if isinstance(d, dict):
            effects[n] = {"path": p, "data": d}
    parts = {}
    for p in sorted(glob.glob(os.path.join(eff_dir, "parts", "*.json"))):
        d = read_json(p)
        if isinstance(d, dict):
            parts[os.path.basename(p)[:-5]] = {"path": p, "data": d}
    textures = {}
    for p in sorted(glob.glob(os.path.join(tex_dir, "*.json"))):
        n = os.path.basename(p)[:-5]
        if n.startswith("_"):
            continue
        d = read_json(p)
        if isinstance(d, dict):
            png = os.path.join(build, "textures", f"{n}.png")
            if not os.path.isfile(png):  # a game's kit texture is built in the PROJECT's build/textures (fxfinish), where
                png = os.path.join("build", "textures", f"{n}.png")  # the player serves it from (2026-11-10)
            textures[n] = {"path": p, "data": d, "png": png if os.path.isfile(png) else None}
    meshes = {}
    for p in sorted(glob.glob(os.path.join(eff_dir, "meshes", "*.json"))):
        n = os.path.basename(p)[:-5]
        obj = os.path.join(build, "vfxmeshes", f"{n}.obj")
        meshes[n] = {"path": p, "data": read_json(p, {}), "obj": obj if os.path.isfile(obj) else None}
    registry = read_json(os.path.join(eff_dir, "_textures.json"), {}) or {}
    mesh_reg = read_json(os.path.join(eff_dir, "_meshes.json"), {}) or {}
    return effects, parts, textures, meshes, registry, mesh_reg


def layer_textures(layers):
    out = []
    for el in layers or []:
        if isinstance(el, dict) and isinstance(el.get("texture"), str) and el["texture"] not in out:
            out.append(el["texture"])
    return out


def layer_meshes(layers):
    out = []
    for el in layers or []:
        if isinstance(el, dict) and isinstance(el.get("mesh"), str) and el["mesh"] not in out:
            out.append(el["mesh"])
    return out


def effect_deps(d, parts):
    used_parts = []
    for u in d.get("use") or []:
        if isinstance(u, dict) and isinstance(u.get("part"), str) and u["part"] not in used_parts:
            used_parts.append(u["part"])
    tex = layer_textures(d.get("layers"))
    mesh = layer_meshes(d.get("layers"))
    for p in used_parts:
        pd = (parts.get(p) or {}).get("data") or {}
        for t in layer_textures(pd.get("layers")):
            if t not in tex:
                tex.append(t)
        for m in layer_meshes(pd.get("layers")):
            if m not in mesh:
                mesh.append(m)
    return used_parts, sorted(tex), sorted(mesh)


def previews(name, build):
    """every picture / recording the pipeline made of this effect: (vault file, source file, compress?)"""
    out = []
    vfx = os.path.join(build, "vfx")
    booth = os.path.join(vfx, "booth")
    for src, dst in ((os.path.join(vfx, f"{name}.png"), "sheet.png"), (os.path.join(vfx, f"{name}.judge.png"), "judge.png"),
                     (os.path.join(booth, f"{name}_play_all.png"), "all.png"), (os.path.join(booth, f"{name}_all.png"), "booth_all.png"),
                     (os.path.join(booth, f"{name}_play.metrics.json"), "metrics.json")):
        if os.path.isfile(src):
            out.append((dst, src, False))
    for src in sorted(glob.glob(os.path.join(booth, f"{name}_play_*.*"))):
        m = VIEW_RE.match(os.path.basename(src))
        if m and m.group("name") == name and m.group("view") != "all":
            out.append((f"{m.group('view')}.{m.group('ext')}", src, m.group("ext") == "mp4"))
    return out


def route_files(name, d, effects, build):
    """the route an effect was built on (mission 02-vfx 5.11): its scene's beat sheet + chart (data and picture), the
    fresh verifier's record, the evolve rounds (state + every round's sheet), the verifier's detail crop per beat
    (v2: no booth sheet is required; the player's recordings are previews)"""
    out = []
    scene = d.get("scene") if isinstance(d.get("scene"), dict) else None
    if scene and isinstance(scene.get("set"), str):
        st = scene["set"]
        measured = os.path.join(effects, "refs_measured")
        for src, dst in ((os.path.join(measured, f"{st}.beats.md"), "beats.md"), (os.path.join(measured, f"{st}.chart.json"), "chart.json"),
                         (os.path.join(build, "vfx", "charts", f"{st}.png"), "chart.png")):
            if os.path.isfile(src):
                out.append((dst, src))
    for src, dst in ((os.path.join(effects, "judge", f"{name}.json"), "verifier.json"), (os.path.join(effects, "evolve", f"{name}.json"), "evolve.json")):
        if os.path.isfile(src):
            out.append((dst, src))
    for src in sorted(glob.glob(os.path.join(build, "vfx", "evolve", name, "round_*.png"))):
        out.append((f"evolve_{os.path.basename(src)}", src))
    # mission 02-vfx v2: the player is the studio - its recordings are kept by previews(); the route keeps the
    # verifier's DETAIL CROPS (the render zoomed per beat). Never the scene's own crops: reference frames stay private.
    for src in sorted(glob.glob(os.path.join(build, "judge", "vfx", name, "detail_beat*.png"))):
        out.append((os.path.basename(src), src))
    return out


# ---------------------------------------------------------------- READMEs


def fmt_time(v):
    return v if isinstance(v, str) else (f"{v:g}" if isinstance(v, (int, float)) else "")


def verdict_lines(verdicts):
    if not verdicts:
        return ["(no owner verdict yet — `lune run kit vfx vault verdict <name> \"<words>\" [--score N]`)"]
    return [f"- {v.get('date', '?')}: {('**' + str(v['score']) + '/100** ') if v.get('score') is not None else ''}\"{v.get('words', '')}\""
            f" (version {v.get('effect_sha', '')[:8]})" for v in verdicts]


def effect_readme(name, d, used_parts, tex, mesh, verdicts, prevs):
    L = [f"# {name}", "", d.get("about") or "(no about)", "", "## Owner verdict", *verdict_lines(verdicts), ""]
    if d.get("beats"):
        L += ["## Beats", "", " · ".join(f"{k} {fmt_time(v)}" for k, v in d["beats"].items()), ""]
    if used_parts:
        L += ["## Parts it uses (library/vfx/parts/)", ""]
        for u in d.get("use") or []:
            if isinstance(u, dict):
                L.append(f"- `{u.get('part')}` as `{u.get('as', '')}` at {fmt_time(u.get('at', 0))}, point {json.dumps(u.get('point'))}")
        L.append("")
    L += ["## Layers", "", "| name | kind | at | life | texture |", "|---|---|---|---|---|"]
    for el in d.get("layers") or []:
        if isinstance(el, dict):
            life = el.get("life", el.get("lifetime", el.get("for", "")))
            L.append(f"| {el.get('name', '')} | {el.get('kind', '')} | {fmt_time(el.get('at', 0))} | {json.dumps(life) if life != '' else ''} | {el.get('texture', '')} |")
    L += ["", "## Textures it needs (library/vfx/textures/)", "", ", ".join(f"`{t}`" for t in tex) or "(none)", ""]
    if mesh:
        L += ["## Meshes it needs (library/vfx/meshes/)", "", ", ".join(f"`{m}`" for m in mesh), ""]
    if prevs:
        L += ["## Previews", "", *[f"- previews/{p}" for p in prevs], ""]
    L += ["## Reuse", "", f"- the whole effect into a project: `lune run kit vfx vault get {name} --as <new_name>`",
          f"- start from it: `lune run kit new vfx <new_name> --from {name}` (when promoted as an example)",
          "- a part of it: `\"use\": [{\"part\": \"<part>\", \"as\": \"<as>\", \"at\": <t>, \"point\": <where>}]`", ""]
    return "\n".join(L)


def part_readme(name, d, used_by):
    L = [f"# part: {name}", "", d.get("about") or "(no about)", "", "## Points", ""]
    for k, v in (d.get("points") or {}).items():
        L.append(f"- `{k}` {json.dumps(v)}")
    L += ["", "## Layers", "", "| name | kind | at | texture |", "|---|---|---|---|"]
    for el in d.get("layers") or []:
        if isinstance(el, dict):
            L.append(f"| {el.get('name', '')} | {el.get('kind', '')} | {fmt_time(el.get('at', 0))} | {el.get('texture', '')} |")
    L += ["", "## Used by", "", ", ".join(f"`{e}`" for e in used_by) or "(nothing yet)", "",
          "## Reuse", "", f"`\"use\": [{{\"part\": \"{name}\", \"as\": \"{name}\", \"at\": <t>, \"point\": <where>, \"scale\": 1}}]`"
          " (copy library/vfx/parts/" + name + "/part.json to assets/effects/parts/ if the project lacks it)", ""]
    return "\n".join(L)


def texture_readme(name, d, reg, used_by):
    L = [f"# texture: {name}", "", d.get("about") or "", "",
         f"- recipe: `{d.get('recipe', d.get('kind', d.get('engine', '?')))}`, engine `{d.get('engine', 'kit')}`, "
         f"frames {d.get('frames', 1)}, grid {d.get('grid', 1)}, cell {d.get('cell', '')}"]
    if d.get("source"):
        L.append(f"- imported from `{d['source']}` (texture.png here is the finished sheet; the download folder is not kept)")
    if isinstance(reg, dict) and reg.get("id"):
        L.append(f"- uploaded: `{reg['id']}`")
    L += ["- used by: " + (", ".join(f"`{e}`" for e in used_by) or "(nothing yet)"), "",
          "Reuse: copy spec.json to assets/textures/<name>.json (an imported one: point its `source` at this texture.png).", ""]
    return "\n".join(L)


# ---------------------------------------------------------------- save / check


def plan(a):
    """everything that must be in the vault: (kind, name, vault file, source, compress) + the package metadata"""
    effects, parts, textures, meshes, registry, mesh_reg = scan(a)
    out = a.out
    items = []
    used_by_part, used_by_tex, used_by_mesh = {}, {}, {}
    deps = {}
    for n, e in effects.items():
        up, tx, ms = effect_deps(e["data"], parts)
        deps[n] = (up, tx, ms)
        for p in up:
            used_by_part.setdefault(p, []).append(n)
        for t in tx:
            used_by_tex.setdefault(t, []).append(n)
        for m in ms:
            used_by_mesh.setdefault(m, []).append(n)
        base = os.path.join(out, "effects", n)
        items.append(("effect", n, os.path.join(base, "effect.json"), e["path"], "source"))
        expanded = os.path.join(a.build, "vfx", "play", f"{n}.json")
        if os.path.isfile(expanded):
            items.append(("effect", n, os.path.join(base, "expanded.json"), expanded, "expanded"))
        for dst, src, comp in previews(n, a.build):
            items.append(("preview", n, os.path.join(base, "previews", dst), src, "video" if comp else "copy"))
        for dst, src in route_files(n, e["data"], a.effects, a.build):
            items.append(("preview", n, os.path.join(base, "route", dst), src, "copy"))
    for n, p in parts.items():
        items.append(("part", n, os.path.join(out, "parts", n, "part.json"), p["path"], "source"))
    for n, t in textures.items():
        items.append(("texture", n, os.path.join(out, "textures", n, "spec.json"), t["path"], "source"))
        if t["png"]:
            items.append(("texture", n, os.path.join(out, "textures", n, "texture.png"), t["png"], "copy"))
    for n, m in meshes.items():
        items.append(("mesh", n, os.path.join(out, "meshes", n, "spec.json"), m["path"], "source"))
        if m["obj"]:
            items.append(("mesh", n, os.path.join(out, "meshes", n, "mesh.obj"), m["obj"], "copy"))
    meta = dict(effects=effects, parts=parts, textures=textures, meshes=meshes, registry=registry, mesh_reg=mesh_reg,
                deps=deps, used_by_part=used_by_part, used_by_tex=used_by_tex, used_by_mesh=used_by_mesh)
    return items, meta


def manifest_path(out, kind, name):
    folder = {"effect": "effects", "preview": "effects", "part": "parts", "texture": "textures", "mesh": "meshes"}[kind]
    return os.path.join(out, folder, name, "manifest.json")


def cmd_save(a):
    items, meta = plan(a)
    written = []
    manifests = {}
    for kind, name, dst, src, how in items:
        mpath = manifest_path(a.out, kind, name)
        man = manifests.setdefault(mpath, read_json(mpath, {}) or {})
        files = man.setdefault("files", {})
        rel = os.path.relpath(dst, os.path.dirname(mpath)).replace("\\", "/")
        src_hash = sha(src)
        if how == "source":
            save_source(src, dst, os.path.join(os.path.dirname(mpath), "versions"), written)
        elif how == "video":
            if files.get(rel, {}).get("from_sha") != src_hash or not os.path.isfile(dst):
                compress_video(src, dst, written)
        else:
            put(src, dst, written)
        files[rel] = {"from": src.replace("\\", "/"), "from_sha": src_hash}
    verdicts = read_json(os.path.join(a.out, "verdicts.json"), {}) or {}
    for n, e in meta["effects"].items():
        up, tx, ms = meta["deps"][n]
        base = os.path.join(a.out, "effects", n)
        prevs = sorted(os.path.basename(p) for p in glob.glob(os.path.join(base, "previews", "*")))
        route = sorted(os.path.basename(p) for p in glob.glob(os.path.join(base, "route", "*")))
        text = effect_readme(n, e["data"], up, tx, ms, verdicts.get(n, []), prevs)
        if route:  # the route it was built on (mission 02-vfx 5.11)
            sc = e["data"].get("scene") or {}
            text += "\n".join(["", "## The route it was built on", "",
                                f"scene set `{sc.get('set', '-')}` (colours `{sc.get('colours', sc.get('set', '-'))}`): the beat sheet, the approved chart, "
                                "the fresh verifier's per-beat differences + edits, the evolve rounds, the booth's sheets", "",
                                *[f"- route/{r}" for r in route], ""])
        write_text(os.path.join(base, "README.md"), text, written)
        mp = manifest_path(a.out, "effect", n)
        manifests.setdefault(mp, read_json(mp, {}) or {}).update(
            name=n, kind="effect", about=e["data"].get("about", ""), parts=up, textures=tx, meshes=ms)
    for n, p in meta["parts"].items():
        write_text(os.path.join(a.out, "parts", n, "README.md"), part_readme(n, p["data"], sorted(meta["used_by_part"].get(n, []))), written)
        mp = manifest_path(a.out, "part", n)
        manifests.setdefault(mp, read_json(mp, {}) or {}).update(name=n, kind="part", about=p["data"].get("about", ""),
                                                                   used_by=sorted(meta["used_by_part"].get(n, [])))
    for n, t in meta["textures"].items():
        reg = meta["registry"].get(n)
        write_text(os.path.join(a.out, "textures", n, "README.md"), texture_readme(n, t["data"], reg, sorted(meta["used_by_tex"].get(n, []))), written)
        mp = manifest_path(a.out, "texture", n)
        manifests.setdefault(mp, read_json(mp, {}) or {}).update(name=n, kind="texture", about=t["data"].get("about", ""),
                                                                   recipe=t["data"].get("recipe", t["data"].get("kind")),
                                                                   registry=reg, used_by=sorted(meta["used_by_tex"].get(n, [])))
    for n, m in meta["meshes"].items():
        mp = manifest_path(a.out, "mesh", n)
        reg = meta["mesh_reg"].get(n)
        write_text(os.path.join(a.out, "meshes", n, "README.md"),
                   f"# mesh: {n}\n\n- spec: {json.dumps(m['data'])}\n- uploaded: `{(reg or {}).get('id', '-')}`\n- used by: "
                   + (", ".join(f"`{e}`" for e in sorted(meta["used_by_mesh"].get(n, []))) or "(nothing yet)") + "\n", written)
        manifests.setdefault(mp, read_json(mp, {}) or {}).update(name=n, kind="mesh", registry=reg,
                                                                   used_by=sorted(meta["used_by_mesh"].get(n, [])))
    for mp, man in manifests.items():
        write_json(mp, man, written)
    write_index(a, meta, verdicts, written)
    n_eff, n_part, n_tex, n_mesh = len(meta["effects"]), len(meta["parts"]), len(meta["textures"]), len(meta["meshes"])
    return emit("pass", f"vfx vault: {n_eff} effects, {n_part} parts, {n_tex} textures, {n_mesh} meshes saved in {a.out}"
                f" ({len(written)} file(s) written)", f"commit {a.out} with the work; reuse: lune run kit vfx vault find \"<words>\"",
                written=len(written))


def write_index(a, meta, verdicts, written):
    idx = {"schema": 1, "rule": "everything the VFX pipeline makes is saved here, packaged by part (kit/vfx/vault.py); the vault never deletes",
           "effects": {}, "parts": {}, "textures": {}, "meshes": {}}
    # one library, many sources (the project root + each games/<Name>): keep the entries this scan did not see, so a
    # game's save never drops the project's effects from the index (and the reverse)
    old = read_json(os.path.join(a.out, "index.json"), {}) or {}
    for kind in ("effects", "parts", "textures", "meshes"):
        if isinstance(old.get(kind), dict):
            idx[kind].update(old[kind])
    for n, e in meta["effects"].items():
        up, tx, ms = meta["deps"][n]
        v = verdicts.get(n) or []
        idx["effects"][n] = {"about": e["data"].get("about", ""), "version": e["data"].get("version", 1), "parts": up,
                             "textures": len(tx), "layers": len(e["data"].get("layers") or []),
                             "owner": v[-1] if v else None, "path": f"effects/{n}"}
    for n, p in meta["parts"].items():
        idx["parts"][n] = {"about": p["data"].get("about", ""), "layers": len(p["data"].get("layers") or []),
                           "used_by": sorted(meta["used_by_part"].get(n, [])), "path": f"parts/{n}"}
    for n, t in meta["textures"].items():
        idx["textures"][n] = {"about": t["data"].get("about", ""), "recipe": t["data"].get("recipe", t["data"].get("kind")),
                              "used_by": sorted(meta["used_by_tex"].get(n, [])), "uploaded": bool((meta["registry"].get(n) or {}).get("id")),
                              "path": f"textures/{n}"}
    for n in meta["meshes"]:
        idx["meshes"][n] = {"used_by": sorted(meta["used_by_mesh"].get(n, [])), "path": f"meshes/{n}"}
    write_json(os.path.join(a.out, "index.json"), idx, written)
    L = ["# VFX library", "", "Everything the VFX pipeline ever made, packaged by part (kit/vfx/vault.py; `kit verify` fails",
         "when something made is missing here). Find: `lune run kit vfx vault find \"<words>\"`; take: `kit vfx vault get <effect> --as <new>`.",
         "", f"## Effects ({len(idx['effects'])})", "", "| effect | owner | parts | about |", "|---|---|---|---|"]
    for n, e in sorted(idx["effects"].items(), key=lambda kv: (kv[1]["owner"] is None, kv[0])):
        own = e["owner"]
        own_s = (f"{own.get('score')}/100 " if own and own.get("score") is not None else "") + (f"\"{own['words'][:60]}\"" if own else "")
        L.append(f"| [{n}](effects/{n}/README.md) | {own_s} | {', '.join(e['parts'])} | {e['about'][:110].replace('|', '/')} |")
    L += ["", f"## Parts ({len(idx['parts'])})", "", "| part | used by | about |", "|---|---|---|"]
    for n, p in sorted(idx["parts"].items()):
        L.append(f"| [{n}](parts/{n}/README.md) | {', '.join(p['used_by'])} | {p['about'][:110].replace('|', '/')} |")
    L += ["", f"## Textures ({len(idx['textures'])})", "", "| texture | recipe | used by |", "|---|---|---|"]
    for n, t in sorted(idx["textures"].items()):
        L.append(f"| [{n}](textures/{n}/README.md) | {t['recipe']} | {', '.join(t['used_by'][:6])}{' ...' if len(t['used_by']) > 6 else ''} |")
    L += ["", f"## Meshes ({len(idx['meshes'])})", "", ", ".join(f"[{n}](meshes/{n}/README.md)" for n in sorted(idx["meshes"])), ""]
    write_text(os.path.join(a.out, "INDEX.md"), "\n".join(L), written)


# the record of the kit's starter pieces (kit/vfx/starters.py): kit-owned and written only in the kit's home, so a
# project cannot make its own piece look like a starter by editing kit/starter/ (which is not fingerprinted)
RECORD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "starters.json")


def text_sha(data):
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def kit_starters(a, record=None):
    """the kit's starter pieces -> {(kind, name): {sha256, ...}} (kit/vfx/starters.json; a missing or broken record
    recognises nothing)"""
    try:
        with open(record or RECORD, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    out = {}
    for key, shas in (data.get("pieces") or {}).items() if isinstance(data, dict) else []:
        kind, _, name = key.split("#")[0].partition("/")
        if name and isinstance(shas, list):
            out.setdefault((kind, name), set()).update(s for s in shas if isinstance(s, str))
    return out


def as_packed(a, data):
    """a project's copy of a packed starter part or texture, its pictures' folder put back to the packed placeholder
    (kit/lib/library.luau installVfx points `__DEPS__/textures/` into <textures>/_library/)"""
    libs = {a.textures}
    try:
        libs.add(os.path.relpath(a.textures))  # (the folder as init wrote it: relative to the project)
    except ValueError:  # (another drive)
        pass
    out = []
    for lib in libs:
        prefix = (lib.replace("\\", "/").rstrip("/") + "/_library/").encode("utf-8")
        if prefix in data:
            out.append(data.replace(prefix, b"__DEPS__/textures/"))
    return out


def untouched_starters(a, items, record=None):
    """the pieces that are still the kit's starters as `kit init` seeded them and were never saved here: the KIT's
    work (made, judged and versioned where the kit is made), not this project's. The rule asks for one from its first
    edit on (its text is then no starter's), and a piece saved here is checked like any other -> {(kind, name)}.
    (The whole package is left to the kit: what the kit's builders make from an untouched starter - its texture
    picture, its mesh, its expanded preset, a recording of it - is the kit's starter played, not the project's work;
    a run that records one saves the package, and from then on every file of it is checked.)"""
    kit = kit_starters(a, record)
    if not kit:
        return set()
    out = set()
    for kind, name, dst, src, how in items:
        if how != "source" or kind not in ("effect", "part", "texture", "mesh") or (kind, name) not in kit:
            continue
        if os.path.isfile(manifest_path(a.out, kind, name)):
            continue
        try:
            with open(src, "rb") as fh:
                data = fh.read()
        except OSError:
            continue
        forms = [data] + (as_packed(a, data) if kind in ("part", "texture") else [])
        if any(text_sha(f) in kit[(kind, name)] for f in forms):
            out.add((kind, name))
    return out


def piece(kind, name):
    """the package an item belongs to (an effect's previews are in the effect's)"""
    return ("effect" if kind == "preview" else kind, name)


def cmd_check(a):
    items, meta = plan(a)
    kits = untouched_starters(a, items)
    missing, stale = [], []
    mans = {}
    for kind, name, dst, src, how in items:
        if piece(kind, name) in kits:
            continue
        mpath = manifest_path(a.out, kind, name)
        man = mans.setdefault(mpath, read_json(mpath, {}) or {})
        rel = os.path.relpath(dst, os.path.dirname(mpath)).replace("\\", "/")
        label = f"{kind} {name}: {os.path.basename(dst)}"
        if not os.path.isfile(dst):
            missing.append(label)
            continue
        src_hash = sha(src)
        if how == "video":
            if (man.get("files", {}).get(rel) or {}).get("from_sha") != src_hash:
                stale.append(label)
        elif sha(dst) != src_hash:
            stale.append(label)
    for n in meta["effects"]:
        if ("effect", n) not in kits and not os.path.isfile(os.path.join(a.out, "effects", n, "README.md")):
            missing.append(f"effect {n}: README.md")
    kit_note = (f" ({len(kits)} untouched kit starter(s) left to the kit: each is saved here from its first edit)"
                if kits else "")
    if missing or stale:
        bad = missing + stale
        return emit("fail", f"vfx vault: {len(missing)} missing, {len(stale)} stale — the owner's rule: everything the VFX "
                    f"pipeline makes is saved (e.g. {', '.join(bad[:4])}){kit_note}",
                    "lune run kit vfx vault  (saves it all), then commit library/vfx",
                    missing=missing[:60], stale=stale[:60], kit_starters=len(kits))
    count = {k: len(meta[group]) - sum(1 for kind, _ in kits if kind == k)
             for k, group in (("effect", "effects"), ("part", "parts"), ("texture", "textures"), ("mesh", "meshes"))}
    return emit("pass", f"vfx vault: all {count['effect']} effects, {count['part']} parts, {count['texture']} "
                f"textures, {count['mesh']} meshes saved and current{kit_note}", "none", kit_starters=len(kits))


def cmd_list(a):
    idx = read_json(os.path.join(a.out, "index.json"), None)
    if not idx:
        return emit("fail", "vfx vault: empty", "lune run kit vfx vault")
    for kind in ("effects", "parts"):
        print(f"-- {kind}")
        for n, e in sorted(idx[kind].items()):
            own = e.get("owner")
            print(f"  {n:24s} {('[owner: ' + own['words'][:40] + '] ') if own else ''}{(e.get('about') or '')[:90]}")
    print(f"-- textures: {len(idx['textures'])}, meshes: {len(idx['meshes'])}")
    return emit("pass", f"vfx vault: {len(idx['effects'])} effects, {len(idx['parts'])} parts, {len(idx['textures'])} textures",
                "kit vfx vault find \"<words>\" | kit vfx vault get <effect> --as <new>")


def cmd_find(a):
    idx = read_json(os.path.join(a.out, "index.json"), None) or {}
    words = [w.lower() for w in re.findall(r"\w+", a.words or "")]
    hits = []
    for kind in ("effects", "parts", "textures", "meshes"):
        for n, e in (idx.get(kind) or {}).items():
            hay = (n + " " + json.dumps(e)).lower()
            score = sum(hay.count(w) for w in words)
            if score:
                hits.append((score, kind, n, (e.get("about") or "")[:100]))
    hits.sort(reverse=True)
    for s, kind, n, about in hits[:25]:
        print(f"  {kind[:-1]:8s} {n:26s} {about}")
    top = ", ".join(f"{kind[:-1]} {n}" for _, kind, n, _ in hits[:8])
    return emit("pass" if hits else "fail", f"vfx vault find: {len(hits)} match(es) for \"{a.words}\" — best: {top}",
                f"read library/vfx/<kind>/<name>/README.md; take an effect: kit vfx vault get <effect> --as <new>"
                if hits else "nothing saved matches — make it, and the vault keeps it")


def cmd_get(a):
    base = os.path.join(a.out, "effects", a.name)
    src = os.path.join(base, "effect.json")
    if not os.path.isfile(src):
        return emit("fail", f"vfx vault get: no effect {a.name} in {a.out}", "kit vfx vault list")
    new = a.as_ or a.name
    root = a.into or "."
    written, skipped = [], []
    dst = os.path.join(root, a.effects, f"{new}.json")
    if os.path.isfile(dst):
        return emit("fail", f"vfx vault get: {dst} already exists", "pick another --as name")
    man = read_json(os.path.join(base, "manifest.json"), {}) or {}
    put(src, dst, written)
    for p in man.get("parts", []):
        pd = os.path.join(root, a.effects, "parts", f"{p}.json")
        if os.path.isfile(pd):
            skipped.append(pd)
        else:
            put(os.path.join(a.out, "parts", p, "part.json"), pd, written)
    for t in man.get("textures", []):
        td = os.path.join(root, a.textures, f"{t}.json")
        if os.path.isfile(td):
            skipped.append(td)
            continue
        spec = read_json(os.path.join(a.out, "textures", t, "spec.json"))
        if spec is None:
            continue
        if spec.get("recipe") == "import" and os.path.isfile(os.path.join(a.out, "textures", t, "texture.png")):
            spec["source"] = os.path.join(a.out, "textures", t, "texture.png").replace("\\", "/")
        write_json(td, spec, written)
    reg_path = os.path.join(root, a.effects, "_textures.json")
    reg = read_json(reg_path, {}) or {}
    added = 0
    for t in man.get("textures", []):
        tm = read_json(os.path.join(a.out, "textures", t, "manifest.json"), {}) or {}
        if t not in reg and tm.get("registry"):
            reg[t] = tm["registry"]
            added += 1
    if added:
        write_json(reg_path, reg, written)
    return emit("pass", f"vfx vault get: {a.name} -> {dst} with {len(written) - 1} dependency file(s) ({len(skipped)} already here)",
                f"lune run kit vfx {new}", written=written)


def cmd_verdict(a):
    src = os.path.join(a.effects, f"{a.name}.json")
    if not os.path.isfile(src):
        return emit("fail", f"vfx vault verdict: no effect {src}", "name an effect in assets/effects")
    path = os.path.join(a.out, "verdicts.json")
    v = read_json(path, {}) or {}
    v.setdefault(a.name, []).append({"date": time.strftime("%Y-%m-%d"), "words": a.words, "score": a.score,
                                     "effect_sha": sha(src)})
    written = []
    write_json(path, v, written)
    cmd_save(a)
    # the ONE verdict record: the knowledge vault files this verdict now (kit/scripts/vault_migrate.py, store "vfx")
    filed = _vault_sync("vfx")
    return emit("pass", f"vfx vault verdict: {a.name} — \"{a.words[:60]}\" kept with version {sha(src)[:8]}"
                + ("; filed in the knowledge vault" if filed else "; vault not updated (run: lune run kit vault sync)"),
                "commit library/vfx and kit/knowledge/vault")


def _vault_sync(store):
    """sync one store of the knowledge vault; never raises (the verdict is already safe in library/vfx)"""
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
        import vault_migrate  # noqa: E402

        return vault_migrate.sync_store(store)
    except Exception:  # noqa: BLE001
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["save", "check", "list", "find", "get", "verdict"])
    ap.add_argument("name", nargs="?")
    ap.add_argument("words", nargs="?")
    ap.add_argument("--effects", default="assets/effects")
    ap.add_argument("--textures", default="assets/textures")
    ap.add_argument("--build", default="build")
    ap.add_argument("--out", default="library/vfx")
    ap.add_argument("--as", dest="as_")
    ap.add_argument("--into")
    ap.add_argument("--score", type=float)
    a = ap.parse_intermixed_args()
    if a.cmd == "find":
        a.words = a.name if a.words is None else f"{a.name} {a.words}"
    if a.cmd in ("get", "verdict") and not a.name:
        return emit("fail", f"vfx vault {a.cmd}: name the effect", f"kit vfx vault {a.cmd} <effect> ...")
    if a.cmd == "verdict" and not a.words:
        return emit("fail", "vfx vault verdict: say the owner's words", "kit vfx vault verdict <effect> \"<words>\" [--score N]")
    return {"save": cmd_save, "check": cmd_check, "list": cmd_list, "find": cmd_find, "get": cmd_get, "verdict": cmd_verdict}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
