"""proc_picks.py — the PICK SHEET for one action's candidate round (mission 04-anim 5.6). Every candidate is rendered on
the OWNER'S rig (look_r6: its controllers keyed, the three-quarter + the GAME camera) and shown only with its fidelity
line ("rig = clip within ..."); a candidate whose render is not faithful is left off the page. Each card is a REAL-TIME
gif (every 4th 60 fps frame at 67 ms - the look gifs' 17 -> 20 ms frames played ~20 % slow - or every 2nd at 30/40 ms
for a FAST spin or cut, with the Hit held ~0.2 s), labelled by its effort sliders; the dossier's reading cues sit beside them; hotkeys 1-9 pick 1-2, a words box
turns the picks into the line to send back + the `kit verdict anim ... --vs ... --tag pick` commands.
    python kit/anim/proc_picks.py <Name> [--round K] [--jobs 3]
      -> build/candidates/<Name>/round_K/picks.html (+ <id>.gif) and an entry in board/plans/missions/pending/anim.md"""
import html
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
_KIT = os.path.abspath(os.path.join(HERE, ".."))
if _KIT not in sys.path:
    sys.path.insert(0, _KIT)
import proc_dossier as DS  # noqa: E402
from blender_path import find_blender  # noqa: E402

BLENDER = find_blender() or "blender"
MANIFESTS = os.path.join("assets", "animations", "candidates")
PENDING = os.path.join("board", "plans", "missions", "pending", "anim.md")
EVERY, FRAME_MS, HIT_HOLD = 4, 67, 3
# a FAST move (the governor 2026-11-05: the drill's 15 fps gif strobed at 3.6 turns a second; a 0.16 s cut is under
# three 15 fps frames): every 2nd 60 fps frame (30 fps) when the body spins >= FAST_TURNS turns/s or the blade tip passes
# FAST_TIP studs/s
FAST_TURNS, FAST_TIP = 2.0, 90.0


def frame_step(clip):
    """-> how many 60 fps frames one gif frame advances: 2 (30 fps) for a fast spin or cut, else EVERY (15 fps)"""
    import numpy as np
    import shape_ref as SR
    tip = (clip.get("sword") or {}).get("tip")
    if tip and len(tip) > 1:
        t = np.asarray(tip, float)
        if float((np.linalg.norm(np.diff(t, axis=0), axis=1) * float(clip.get("fps", 60))).max()) >= FAST_TIP:
            return 2
    try:
        return 2 if SR.measure(clip)["spin_turns_per_s"] >= FAST_TURNS else EVERY
    except Exception:                                         # an arms-only / odd clip: the default rate
        return EVERY


def real_time_ms(n, step):
    """per-frame gif delays (ms, whole centiseconds - what the gif format stores) whose running sum tracks real time
    for frames `step` 60 fps frames apart: 2 -> 30, 40, 30, 30, 40 ... (a flat 33 ms is stored as 30: 10 % fast)"""
    out, acc = [], 0
    for k in range(n):
        end = int(round((k + 1) * step * 1000 / 60 / 10)) * 10
        out.append(end - acc)
        acc = end
    return out


def views_for(d):
    """the look_r6 camera flags + the views drawn: a game with its own THIRD-PERSON camera (the dossier's
    build.tp_camera - Sample Game over the right shoulder) is judged from THAT camera + a three-quarter (2026-11-05: the
    generic 'game' view, Roblox's high default chase camera, showed the Hit end-on where the player's camera sees the
    blade across); else the three-quarter / game / side views. build.look_reach: the still cameras on the root and wide
    enough for the weapon's whole sweep (a drill's blade disc)"""
    b = d.get("build") or {}
    reach = ["--frame-reach"] if b.get("look_reach") else []
    if b.get("tp_camera"):
        return ["--tp", "--also", "three-quarter", *reach], ("three-quarter", "tp")
    return ["--views", "3", *reach], ("three-quarter", "game")


def render(c, out_dir, cam=("--views", "3")):
    """look_r6 on the owner's rig -> (frames dir, fidelity) or (None, why)"""
    tag = c["id"].split("/")[-1]
    p = subprocess.run([BLENDER, "-b", os.environ.get("PARALLAX_R6_RIG") or "assets/rigs/R6_IK.blend", "--disable-autoexec", "--python-exit-code", "2", "-P",
                        "kit/anim/look_r6.py", "--", tag, "--clip", c["clip"], "--out", out_dir, *cam, "--size", "280"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    verdict = None
    for line in reversed((p.stdout or "").splitlines()):
        if line.startswith("{") and '"status"' in line:
            verdict = json.loads(line)
            break
    if not verdict or verdict.get("status") != "pass" or not verdict.get("fidelity"):
        return None, (verdict or {}).get("summary") or (p.stderr or p.stdout)[-300:]
    return verdict["dir"], verdict["fidelity"]


def gif(frames_dir, clip, label, path):
    from PIL import Image, ImageDraw
    info = json.load(open(os.path.join(frames_dir, "look.json"), encoding="utf-8"))
    frames, views = info["frames"], info["views"]
    hit = next((e["t"] for e in clip.get("events", []) if e.get("name") == "Hit"), None)
    hit_f = int(round(hit * 60)) if hit is not None else None
    tiles, durs = [], []
    step = frame_step(clip)
    base = real_time_ms(len(range(0, len(frames), step)), step)
    for n_, k in enumerate(range(0, len(frames), step)):
        f = frames[k]
        ims = [Image.open(os.path.join(frames_dir, f"{v}_{f:04d}.png")).convert("RGB") for v in views]
        w, h = ims[0].size
        tile = Image.new("RGB", (w * len(ims), h + 22), (235, 236, 240))
        for i, im in enumerate(ims):
            tile.paste(im, (i * w, 22))
        d = ImageDraw.Draw(tile)
        d.text((6, 4), f"{label}   t={(f - frames[0]) / 60:.2f}s   ({' | '.join(views)})", fill=(30, 30, 34))
        tiles.append(tile.convert("P", palette=Image.ADAPTIVE, colors=128))
        durs.append(base[n_] + (FRAME_MS * HIT_HOLD if hit_f is not None and f <= hit_f < f + step else 0))
    tiles[0].save(path, save_all=True, append_images=tiles[1:], duration=durs, loop=0)


BEATS = (-0.15, 0.0, 0.2, 0.45)          # seconds from the Hit: the wind-in, the Hit, the hold, late


def _beat_frames(frames_dir, beats=BEATS):
    info = json.load(open(os.path.join(frames_dir, "look.json"), encoding="utf-8"))
    fr = info["frames"]
    hit = (info.get("hits") or [fr[len(fr) // 2]])[0]
    fps = float(info.get("fps", 60))
    return [min(fr, key=lambda f: abs(f - (hit + b * fps))) for b in beats]


def beat_sheet(cards, path, views=("three-quarter", "game"), size=150, beats=BEATS):
    """THE SIDE-BY-SIDE SHEET (the governor 2026-11-04): for every candidate, its loved reference (by kind) above it at
    matching beats - BEATS from each one's own Hit - from the three-quarter and the game camera"""
    from PIL import Image, ImageDraw
    rows = []
    for c in cards:
        pair = [(f"loved {c['loved']['id']}", c["loved"].get("frames"))] if (c.get("loved") or {}).get("frames") else []
        pair.append((c["id"], c.get("frames")))
        for label, fd in pair:
            if not fd or not os.path.isfile(os.path.join(fd, "look.json")):
                continue
            tiles = []
            for f in _beat_frames(fd, beats):
                for v in views:
                    pth = os.path.join(fd, f"{v}_{f:04d}.png")
                    im = Image.open(pth).convert("RGB") if os.path.isfile(pth) else Image.new("RGB", (size, size), (200, 200, 200))
                    tiles.append(im.resize((size, int(size * im.size[1] / im.size[0]))))
            h = max(t.size[1] for t in tiles)
            row = Image.new("RGB", (size * len(tiles), h + 18), (235, 236, 240))
            for i, t in enumerate(tiles):
                row.paste(t, (i * size, 18))
            ImageDraw.Draw(row).text((4, 3), f"{label}   beats {tuple(beats)} s from the Hit, each beat: {' | '.join(views)}", fill=(30, 30, 34))
            rows.append(row)
    if not rows:
        return None
    W, H = max(r.size[0] for r in rows), sum(r.size[1] + 4 for r in rows)
    sheet = Image.new("RGB", (W, H), (255, 255, 255))
    y = 0
    for r in rows:
        sheet.paste(r, (0, y))
        y += r.size[1] + 4
    sheet.save(path, quality=85)
    return path


def refs_by_kind(d, name):
    """the loved clips a dossier names BY KIND for a clip (build.loved_refs: {glob: [library id, ...]}; the governor
    2026-11-04: the drill's 'nearest loved' was HeartRipOut, picked by pose distance, while the library has loved spins)
    -> the ids, or None (then the whole loved bank, by pose distance)"""
    import fnmatch
    for pat, ids in ((d.get("build") or {}).get("loved_refs") or {}).items():
        if fnmatch.fnmatchcase(str(name), pat):
            return list(ids)
    return None


def nearest_loved(clip, group="combat", only=None):
    """the candidate's NEAREST LOVED clip (the governor 2026-11-04: each candidate beside its nearest loved one, so the
    owner compares it with what he already loves): by the R6 vocabulary profile (r6_vocab.measures: each limb's slide and
    turn range, its motion share and peak speed), each measure scaled by its spread over the loved set - the owner's
    'love' clips of the dossier's category (game licence), the same set the vocabulary is calibrated on
    -> (id, its words, its clip) or None"""
    import numpy as np
    import r6_vocab as RV
    sys.path.insert(0, os.path.join(HERE, "..", "..", "diagnostics"))
    import translate_test as TT
    LIMB = (("Right Arm", "Right Arm"), ("Left Arm", "Left Arm"), ("kick_leg", "Right Leg"), ("support_leg", "Left Leg"))
    MS = ("slide_p95", "rot_range", "moving", "peak_speed")

    def feat(c):
        m = RV.measures(c, kick_leg="Right Leg")
        return np.array([float(m[r].get(k, 0.0)) for r, _ in LIMB for k in MS])
    key = tuple(only) if only else None
    if getattr(nearest_loved, "_key", "none") != key:
        bank = []
        for lb in TT.labels():
            if only is not None:
                if lb["id"] not in only:
                    continue
            elif lb["owner_verdict"] != "love" or lb["licence"] != "game" or lb["group"] != group:
                continue
            c = TT.loved_clip(lb["id"])[0]
            if len(c["times"]) < (15 if only else 30) or "Right Leg" not in c["joints"]:
                continue
            bank.append((lb["id"], lb.get("text") or lb["id"], c, feat(c)))
        nearest_loved._bank, nearest_loved._key = bank, key
    bank = nearest_loved._bank
    if not bank:
        return None
    F = np.array([b[3] for b in bank])
    sd = F.std(axis=0) + 1e-6
    i = int(np.argmin(np.linalg.norm((F - feat(clip)) / sd, axis=1)))
    return bank[i][0], bank[i][1], bank[i][2]


def trim_window(c, seconds=2.0):
    """a loved clip cut to `seconds` around its fastest moment (a 5 s ultimate made a 15 MB gif, embedded once per card)"""
    import numpy as np
    n = len(c["times"])
    fps = float(c.get("fps", 60))
    w = int(seconds * fps)
    if n <= w:
        return c
    sp = np.zeros(n)
    for j in c["joints"].values():
        q = np.asarray([f[:4] for f in j["frames"]], float)
        sp[1:] = np.maximum(sp[1:], 1 - np.abs(np.sum(q[1:] * q[:-1], axis=1)))
    i0 = int(min(max(0, int(np.argmax(sp)) - w // 2), n - w))
    out = dict(c, times=[t - c["times"][i0] for t in c["times"][i0:i0 + w]],
               joints={k: dict(v, frames=v["frames"][i0:i0 + w]) for k, v in c["joints"].items()})
    t0, t1 = c["times"][i0], c["times"][i0 + w - 1]
    out["events"] = [dict(e, t=e["t"] - t0) for e in c.get("events", []) if t0 <= e.get("t", -1) <= t1]
    for key in ("root",):
        if isinstance(c.get(key), list) and len(c[key]) == n:
            out[key] = c[key][i0:i0 + w]
    return out


def direction_pick(name):
    """the move's DIRECTION (assets/animations/direction/<Name>.md, its '## Pick' section's first line): which of the
    A/B/C readings the round was built from and whose call it was - shown on the sheet (2026-11-05: a governor's
    default stays open to the owner, and the page says so)"""
    p = os.path.join("assets", "animations", "direction", f"{name}.md")
    if not os.path.isfile(p):
        return None
    lines = open(p, encoding="utf-8").read().splitlines()
    for i, ln in enumerate(lines):
        if ln.strip().lower() == "## pick":
            body = [x.strip() for x in lines[i + 1:] if x.strip() and not x.startswith("#")]
            return body[0] if body else None
    return None


def page(name, rnd, d, cards, out):
    cues = "".join(f"<li>{html.escape(x)}</li>" for x in d.get("reading_cues", []))
    pick = direction_pick(name)
    direction = f'<p><b>Direction:</b> {html.escape(pick)}</p>' if pick else ""
    mistakes = "".join(f"<li>{html.escape(x)}</li>" for x in d.get("mistakes", [])[:6])
    items = []
    for i, c in enumerate(cards, 1):
        bars = "".join(f'<div class="s"><span>{k}</span><i style="--v:{(v + 1) / 2:.3f}"></i><b>{v:+.2f}</b></div>' if isinstance(v, (int, float))
                       else f'<div class="s"><span>{k}</span><em>{html.escape(str(v))}</em><b></b></div>' for k, v in c["sliders"].items())
        items.append(f'''<figure class="card" data-id="{html.escape(c['id'])}" data-n="{i}">
  <div class="num">{i}</div><img src="{html.escape(os.path.basename(c['gif']))}" alt="{html.escape(c['id'])}">
  <figcaption><b>{html.escape(c['id'])}</b><div class="fid">rig = clip within {c['fidelity']['studs']} studs / {c['fidelity']['deg']} deg</div>{bars}
  {(f'<div class="loved"><span>nearest loved: {html.escape(c["loved"]["text"][:80])}</span><img src="{html.escape(os.path.basename(c["loved"]["gif"]))}" alt="loved"></div>') if c.get("loved") else ""}</figcaption></figure>''')
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(name)} picks</title><style>
:root{{--bg:#f4f4f6;--fg:#1c1c20;--card:#fff;--muted:#6a6a74;--acc:#2f6fd6;--pick:#e8a317}}
@media (prefers-color-scheme:dark){{:root{{--bg:#16161a;--fg:#ececf1;--card:#212127;--muted:#9a9aa6;--acc:#6aa0ff}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,sans-serif}}
main{{max-width:1500px;margin:0 auto;padding:16px}} h1{{margin:.2em 0}} .muted{{color:var(--muted)}}
.top{{display:grid;grid-template-columns:2fr 1fr;gap:16px}} @media (max-width:800px){{.top{{grid-template-columns:1fr}}}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(420px,1fr));gap:14px;margin-top:14px}}
.card{{margin:0;background:var(--card);border-radius:10px;padding:8px;position:relative;cursor:pointer;border:3px solid transparent}}
.card.picked{{border-color:var(--pick)}} .card img{{width:100%;border-radius:6px;display:block}}
.num{{position:absolute;top:12px;left:12px;background:var(--acc);color:#fff;border-radius:6px;padding:0 8px;font-weight:700}}
.fid{{font-size:12px;color:var(--muted)}} .loved{{margin-top:6px;font-size:12px;color:var(--muted)}} .loved img{{width:60%;border-radius:6px;opacity:.95}} .s{{display:grid;grid-template-columns:52px 1fr 44px;gap:6px;align-items:center;font-size:12px}}
.s i{{height:6px;border-radius:3px;background:linear-gradient(90deg,var(--acc) calc(var(--v)*100%),#8884 0)}}
textarea{{width:100%;min-height:70px;font:inherit;border-radius:8px;padding:8px;box-sizing:border-box;background:var(--card);color:var(--fg)}}
pre{{white-space:pre-wrap;background:var(--card);padding:10px;border-radius:8px;font-size:13px}}
</style></head><body><main>
<h1>{html.escape(name)} — round {rnd}: pick 1–2</h1>{direction}
<p class="muted">Our own from-scratch candidates (dossier <b>{html.escape(d['name'])}</b>), every one through all the gates, rendered on your R6 rig — three-quarter | game camera | side — in real time with the Hit held. Press <b>1–9</b> (or click) to pick up to two, write what you see, send the line below.</p>
<div class="top"><section><div class="grid" id="grid">{''.join(items)}</div></section>
<aside><h3>What makes it read (the dossier)</h3><ul>{cues}</ul><h3>Classic mistakes</h3><ul>{mistakes}</ul>
<h3>Your words</h3><textarea id="words" placeholder="what works, what doesn't"></textarea>
<h3>Send this</h3><pre id="out">pick up to two</pre></aside></div>
</main><script>
const picked=[];const cards=[...document.querySelectorAll('.card')];
function draw(){{cards.forEach(c=>c.classList.toggle('picked',picked.includes(c.dataset.id)));
const w=document.getElementById('words').value.trim().replace(/"/g,"'");
const out=picked.length?`PICKS {name} round {rnd}: ${{picked.join(', ')}} — ${{w||'(words)'}}\\n\\n`+picked.map((p,i)=>`lune run kit verdict anim ${{p}} <0-10> "${{w||'...'}}"`+(picked.length>1?` --vs ${{picked[1-i]}}`:'')+' --tag pick').join('\\n'):'pick up to two';
document.getElementById('out').textContent=out;}}
function toggle(id){{const i=picked.indexOf(id);if(i>=0)picked.splice(i,1);else{{picked.push(id);if(picked.length>2)picked.shift();}}draw();}}
cards.forEach(c=>c.addEventListener('click',()=>toggle(c.dataset.id)));
document.addEventListener('keydown',e=>{{if(e.target.tagName==='TEXTAREA')return;const n=+e.key;if(n>=1&&n<=cards.length)toggle(cards[n-1].dataset.id);}});
document.getElementById('words').addEventListener('input',draw);
</script></body></html>"""
    open(out, "w", encoding="utf-8", newline="").write(doc)


def standalone(page_path):
    """the same page with every gif embedded (one file to open anywhere / send to a phone): <page>.standalone.html"""
    import base64
    import re
    doc = open(page_path, encoding="utf-8").read()
    base = os.path.dirname(page_path)

    # each DISTINCT gif embedded ONCE (the same nearest-loved gif sat under several cards: 147 MB for 8 candidates),
    # the img tags filled from it on load
    names = sorted(set(re.findall(r'src="([^"]+\.gif)"', doc)))
    data = {n: base64.b64encode(open(os.path.join(base, n), "rb").read()).decode("ascii") for n in names}
    doc = re.sub(r'src="([^"]+\.gif)"', lambda m: f'data-gif="{m.group(1)}"', doc)
    js = ("<script>const G={" + ",".join(f'"{n}":"data:image/gif;base64,{v}"' for n, v in data.items()) +
          "};document.querySelectorAll('img[data-gif]').forEach(i=>i.src=G[i.dataset.gif]);</script>")
    out = page_path.replace(".html", ".standalone.html")
    open(out, "w", encoding="utf-8", newline="").write(doc.replace("</body>", js + "</body>"))
    return out


def pending(name, rnd, page_path, n, dossier=""):
    os.makedirs(os.path.dirname(PENDING), exist_ok=True)
    head = "# pending — anim (see ../AUTONOMY.md §2; cap: TWO pick sheets)\n"
    text = open(PENDING, encoding="utf-8").read() if os.path.exists(PENDING) else head
    key = f"## anim picks {name} — round {rnd}"
    if key in text:
        return
    import datetime
    text += (f"\n{key} — {datetime.date.today().isoformat()}\n- look at: {page_path} ({n} candidates, real-time gifs on the owner's rig)\n"
             f"- reference: assets/animations/dossiers/{dossier + '.json' if dossier else ''} (the dossier's reading cues are on the page)\n"
             f"- question: pick 1-2 and words?\n")
    open(PENDING, "w", encoding="utf-8", newline="").write(text)


def main(a):
    name = a[0]
    rnd = int(a[a.index("--round") + 1]) if "--round" in a else 0
    jobs = int(a[a.index("--jobs") + 1]) if "--jobs" in a else 3
    man = json.load(open(os.path.join(MANIFESTS, name, f"round_{rnd}.json"), encoding="utf-8"))
    d = DS.require(man["dossier"])
    out_dir = os.path.join("build", "candidates", name, f"round_{rnd}")
    look_dir = os.path.join(out_dir, "look")
    os.makedirs(look_dir, exist_ok=True)
    cam, sheet_views = views_for(d)
    with ThreadPoolExecutor(jobs) as ex:
        res = list(ex.map(lambda c: render(c, look_dir, cam), man["candidates"]))
    cards, dropped = [], []
    for c, (frames_dir, fid) in zip(man["candidates"], res):
        if frames_dir is None:
            dropped.append({"id": c["id"], "why": str(fid)[:200]})
            continue
        clip = json.load(open(c["clip"], encoding="utf-8"))
        g = os.path.join(out_dir, c["id"].split("/")[-1] + ".gif")
        label = c["id"] + "  " + " ".join(f"{k[0]}{v:+.1f}" if isinstance(v, (int, float)) else str(v) for k, v in c["sliders"].items())
        gif(frames_dir, clip, label, g)
        card = {**c, "gif": g, "fidelity": fid, "frames": frames_dir}
        if "--no-loved" not in a:
            near = nearest_loved(clip, d.get("category", "combat"), refs_by_kind(d, name))
            if near:
                lid, ltext, lclip = near
                safe = "loved_" + "".join(ch if ch.isalnum() else "_" for ch in str(lid))[-60:]
                lpath = os.path.join(out_dir, f"{safe}.clip.json")
                lgif = os.path.join(out_dir, f"{safe}.gif")
                if not os.path.isfile(lgif):
                    lclip = trim_window(lclip)
                    json.dump(lclip, open(lpath, "w", encoding="utf-8"))
                    lf, lfid = render({"id": safe, "clip": lpath}, look_dir, cam)
                    if lf:
                        gif(lf, lclip, f"loved: {ltext[:50]}", lgif)
                if os.path.isfile(lgif):
                    card["loved"] = {"id": lid, "text": ltext, "gif": lgif, "frames": os.path.join(look_dir, f"{safe}.look")}
        cards.append(card)
    if len(cards) < 4:
        print(json.dumps({"schema": 1, "status": "fail", "summary": f"{name} round {rnd}: only {len(cards)} faithful render(s)",
                          "next_action": f"read the dropped renders: {dropped[:2]}", "dropped": dropped}))
        return 1
    out = os.path.join(out_dir, "picks.html")
    # a dossier may set its own beats (a drill's Hit is its dead stop: the spin is a second before it)
    sheet = beat_sheet(cards, os.path.join(out_dir, "beats_vs_loved.jpg"), views=sheet_views,
                       beats=tuple((d.get("build") or {}).get("sheet_beats") or BEATS))
    page(name, rnd, d, cards, out)
    standalone(out)
    pending(name, rnd, out.replace(os.sep, "/"), len(cards), man["dossier"])   # (it named no dossier until 2026-11-11)
    print(json.dumps({"schema": 1, "status": "pass",
                      "summary": f"{name} round {rnd}: {len(cards)} candidates on the pick sheet {out} ({len(dropped)} dropped: unfaithful render)",
                      "next_action": f"look at {out} - the owner picks 1-2 (queued in {PENDING})", "page": out, "beat_sheet": sheet, "dropped": dropped,
                      # the line this command ends with (kit/cmd/anim.luau prints it last - the studio route's A0)
                      "look": (f"LOOK: {out_dir}/ - picks.html ({len(cards)} candidates as real-time gifs on the owner's rig, "
                               f"its own page) + {os.path.basename(str(sheet))} (their beats on one sheet); one candidate's "
                               f"key poses large, beside the dossier's reference frames: lune run kit anim sheet {name} "
                               f"--clip {out_dir}/<id>.clip.json --dossier {man['dossier']}").replace(os.sep, "/")}))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
