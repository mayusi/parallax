"""perceive.py — how alike the model LOOKS to its reference, through the vetted vision models:

    python kit/vision/perceive.py build/renders/<asset>_ref_<view>_lines.json

The reference photo and the shaded model are put in ONE frame exactly as the internal-lines check puts them (the
trace's own cut of the photo: box, rotation, exclusions, front; both fitted to their outline), then:
  - SigLIP 2: the cosine of the whole look (content, finish, style) — and the same for the model's bare silhouette in
    flat grey, so the report says how much the model's SURFACE (its detail, materials, texture) adds beyond its outline;
  - DINOv2: the difference per 14 px patch (1 - cosine) on the shared frame — WHERE the model departs from the picture.
-> build/renders/<asset>_perceptual_<view>.png (reference | model | where they differ: bright = differs) + one JSON line.
A REPORT, never a gate: looking alike is not quality (measured on the owner's grades: SigLIP alone does not track
them). Its use: point at the regions that differ most, and show whether an iteration moved the look toward the picture.
"""

import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import lines as L  # noqa: E402  (the same frame as the internal-lines check)
import run as V  # noqa: E402  (the vetted models, offline)

REPO = L.REPO
AREA = 448 * 448  # DINOv2 input area (14 px patches: ~1024 patches on any aspect)
SCALE = 0.6  # 1 - cosine at which the map is fully bright (completely different content)


def frames(info):
    """-> (reference RGB, model RGB, reference mask, model mask) at one size, both fitted to their outline"""
    p_rgb, p_mask = L.photo_frame(info)
    m_rgb, m_mask = L.model_frame(os.path.join(REPO, info["model"]))
    aspect = p_rgb.shape[1] / p_rgb.shape[0]
    w = max(28, int(round((AREA * aspect) ** 0.5 / 14)) * 14)
    h = max(28, int(round(AREA / w / 14)) * 14)
    return (L._resize(p_rgb, w, h), L._resize(m_rgb, w, h), L._resize(p_mask, w, h, True),
            L._resize(m_mask, w, h, True))


def patch_grid(rgb):
    """DINOv2 per-patch features of an RGB array whose sides are multiples of 14 -> (rows, cols, d), L2-normalised"""
    torch, dev = V._torch()
    model, proc = V._dino()
    inp = proc(images=Image.fromarray(rgb), return_tensors="pt", do_resize=False, do_center_crop=False).to(dev)
    with torch.no_grad():
        hid = model(**inp).last_hidden_state[0]
    rows, cols = rgb.shape[0] // 14, rgb.shape[1] // 14
    grid = hid[1 + model.config.num_register_tokens:][: rows * cols].float()
    return torch.nn.functional.normalize(grid, dim=-1).reshape(rows, cols, -1).cpu().numpy()


def _where(r, c, rows, cols, front):
    """a patch -> words along the model ("front third, top")"""
    u = (c + 0.5) / cols
    u = u if front == "right" else 1 - u
    third = "back" if u < 1 / 3 else "middle" if u < 2 / 3 else "front"
    vert = "top" if r < rows / 3 else "middle" if r < 2 * rows / 3 else "bottom"
    return f"{third} third, {vert} ({u:.0%} along the length)"


def perceive(info):
    ref, mod, p_mask, m_mask = frames(info)
    sil = np.full_like(mod, 255)
    sil[m_mask] = 128  # the model's bare outline in flat grey: what the look would be with no surface at all
    e = V.embed([Image.fromarray(ref), Image.fromarray(mod), Image.fromarray(sil)])
    sim, sim_sil = float(e[0] @ e[1]), float(e[0] @ e[2])
    d = np.clip(1.0 - (patch_grid(ref) * patch_grid(mod)).sum(-1), 0, 2)
    rows, cols = d.shape
    either = np.asarray(Image.fromarray(((p_mask | m_mask) * 255).astype(np.uint8)).resize((cols, rows), Image.BOX)) > 32
    inside = d[either] if either.any() else d.ravel()
    order = np.argsort(np.where(either, d, -1).ravel())[::-1]
    worst, seen = [], set()
    for k in order[:40]:
        r, c = divmod(int(k), cols)
        where = _where(r, c, rows, cols, "right")
        if where.split(" (")[0] in seen or not either[r, c]:
            continue
        seen.add(where.split(" (")[0])
        worst.append({"where": where, "differs": round(float(d[r, c]), 3)})
        if len(worst) == 3:
            break
    # the picture: reference | model | where they differ (the map over the model, bright = differs)
    h, w = ref.shape[:2]
    heat = np.asarray(Image.fromarray((np.clip(d / SCALE, 0, 1) * 255).astype(np.uint8)).resize((w, h), Image.BILINEAR))
    over = (mod.astype(np.float32) * 0.35 + np.stack([heat, heat * 0.35, heat * 0.1], -1) * 0.65).astype(np.uint8)
    sheet = Image.new("RGB", (w * 3 + 16, h + 22), "white")
    for i, (im, label) in enumerate(((ref, "reference"), (mod, "model"), (over, "where they differ"))):
        sheet.paste(Image.fromarray(im), (i * (w + 8), 22))
        ImageDraw.Draw(sheet).text((i * (w + 8) + 4, 4), label, fill=(0, 0, 0))
    out = os.path.join(REPO, "build", "renders", f"{info['asset']}_perceptual_{info['view']}.png")
    sheet.save(out)
    return {"view": info["view"], "similarity": round(sim, 4), "silhouette_similarity": round(sim_sil, 4),
            "surface_gain": round(sim - sim_sil, 4), "differ_mean": round(float(inside.mean()), 4), "worst": worst,
            "image": os.path.relpath(out, REPO).replace("\\", "/")}


def main(argv):
    with open(argv[0], encoding="utf-8") as fh:
        info = json.load(fh)
    view = info["view"]
    stale = os.path.join(REPO, "build", "renders", f"{info['asset']}_perceptual_{view}.png")
    if os.path.isfile(stale):
        os.remove(stale)  # a picture from an older build must never pass for this one's

    def emit(status, summary, next_action, **extra):
        print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
        return 0

    photo = info.get("photo")
    if not photo or not os.path.isfile(os.path.join(REPO, photo)):
        return emit("pass", f"perceptual_{view}: skipped — the reference photo {photo} is missing",
                    "restore it (refs/ are often untracked) to see the perceptual map")
    try:
        import torch  # noqa: F401, PLC0415 — the vision stack needs it in system python

        V.ensure("siglip2-base")
        V.ensure("dinov2-reg-small")
        if str(info.get("mask") or "").startswith("BiRefNet"):
            V.ensure("birefnet")
    except V.PinMismatch as e:
        return emit("pass", f"perceptual_{view}: skipped — {e}", "lune run kit vision setup   (re-fetches the pinned file)")
    except (V.ModelMissing, ImportError) as e:
        return emit("pass", f"perceptual_{view}: skipped — the vision models are not set up ({e})",
                    "lune run kit vision setup   (vetted, pinned downloads)")
    r = perceive(info)
    worst = "; ".join(f"{w['where']} ({w['differs']:.2f})" for w in r["worst"]) or "nowhere in particular"
    return emit("pass",
                f"perceptual_{view}: looks {r['similarity']:.2f} like the reference (SigLIP 2; the bare outline alone "
                f"{r['silhouette_similarity']:.2f}, so the surface adds {r['surface_gain']:+.2f}); DINOv2 differs most "
                f"at {worst}",
                f"look at {r['image']} (bright = the model departs from the picture there) — a report, not a gate",
                perceptual=r)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
