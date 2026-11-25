"""kimodo_r6_text.py — Kimodo-style text for every game-safe R6 clip (owner brief 2026-10-13: Kimodo-R6 fine-tune, step 3).
Kimodo was trained on sentences like "a person throws a jab and a cross punch"; our labels were pack strings. Each clip
gets 2 descriptions (action, limb, direction, speed, modifiers, duration) from its name / kind / group / tags + the
limb MEASURED from the motion (the fastest hand / foot relative to the torso). A mirrored augmentation swaps left and
right in its text. Then every unique text is embedded ONCE with Kimodo's own encoder (LLM2Vec on Llama-3-8B, on the
CPU) and cached.
    python kit/anim/kimodo_r6_text.py texts            -> _artifacts/kimodo_r6/texts.json  (any python with numpy)
    <kimodo venv> python kit/anim/kimodo_r6_text.py embed   -> _artifacts/kimodo_r6/text_emb.npz  (CPU, bf16: ~13 s a text)
    <kimodo venv> python kit/anim/kimodo_r6_text.py embed_gpu --quant int8|nf4 [--validate]   (bitsandbytes on the GPU)"""
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(ROOT, "_artifacts", "kimodo_r6")
DATA = os.path.join(ROOT, "_artifacts", "r6data")
WEAPON = r"slash|sword|swing|katana|blade|cleave|chop|stab|greatsword|claymore|axe|scythe|spear|weapon"
EXCLUDE_VERDICTS = {"bad", "laggy"}         # the owner's own verdict: not motion to learn from


def measured_limb(rot, pos):
    """the limb that moves fastest relative to the torso: 'right hand' / 'left hand' / 'right foot' / 'left foot'"""
    sys.path.insert(0, HERE)
    import motion_model as MM
    pts = MM.fk_points(MM.quat_to_mat(rot), pos, xp=np)
    torso = pts["Torso"]
    best, name = -1.0, "right hand"
    for part, lab in (("Right Arm", "right hand"), ("Left Arm", "left hand"), ("Right Leg", "right foot"), ("Left Leg", "left foot")):
        rel = pts[part] - torso
        sp = np.percentile(np.linalg.norm(np.diff(rel, axis=0), axis=1), 98) if len(rel) > 2 else 0.0
        if sp > best:
            best, name = sp, lab
    return name


def seconds_words(s):
    if s < 0.4:
        return "in a split second"
    if s < 0.8:
        return "in about half a second"
    if s < 1.4:
        return "in about one second"
    if s < 2.5:
        return "over about two seconds"
    return f"over about {int(round(s))} seconds"


def describe(lb, limb, secs):
    """-> two Kimodo-style sentences"""
    name = (lb["text"] or "").split(" | ")[0]
    pack = ((lb["text"] or "").split(" | ") + ["", ""])[1]
    kind, group, tags = lb.get("kind") or "other", lb.get("group") or "other", set(lb.get("tags") or [])
    low = (name + " " + pack).lower()
    weapon = bool(re.search(WEAPON, low))
    mods = []
    if "fast" in tags:
        mods.append("quickly")
    if "slow" in tags:
        mods.append("slowly")
    extras = []
    for t, w in (("windup", "winding up first"), ("lunge", "lunging forward"), ("spin", "spinning around"),
                 ("twist", "twisting the torso"), ("crouch", "crouching low"), ("airborne", "leaping into the air"),
                 ("lean", "leaning into it"), ("backstep", "stepping back"), ("sidestep", "stepping to the side"),
                 ("holds", "holding the final pose")):
        if t in tags:
            extras.append(w)
    direction = next((d for d in ("downward", "upward", "horizontal", "diagonal", "thrust") if d in tags), None)
    dir_words = {"downward": "downward", "upward": "upward", "horizontal": "sideways", "diagonal": "diagonally", "thrust": "straight forward"}
    hands = "both hands" if ("twohanded" in tags or ("botharms" in tags and weapon)) else f"the {limb}" if "hand" in limb else None
    if kind in ("attack", "m1/combo") or (group == "combat" and "strike" in tags and kind not in ("idle", "dash", "reaction", "defence")):
        if "foot" in limb:
            act = f"kicks {dir_words.get(direction, '')} with the {limb.split()[0]} leg".replace("  ", " ")
        elif weapon:
            act = f"swings a sword {dir_words.get(direction, '')} with {hands or 'the ' + limb}".replace("  ", " ")
        else:
            act = f"punches {dir_words.get(direction, '')} with {hands or 'the ' + limb}".replace("  ", " ")
        if kind == "m1/combo" or "combo" in low:
            act = act.replace("punches", "throws a combo of punches").replace("swings a sword", "chains sword slashes")
    elif kind == "run":
        act = "runs forward in place" if "fast" not in tags else "sprints forward in place"
    elif kind == "walk":
        act = "walks forward in place"
    elif kind == "idle":
        act = "stands idle in a fighting stance" if group == "combat" else "stands idle, breathing and shifting weight"
    elif kind == "jump":
        act = "jumps up and lands"
    elif kind == "dash":
        d = "to the left" if re.search(r"left|\ba\b", name, re.I) else "to the right" if re.search(r"right|\bd\b", name, re.I) \
            else "backward" if re.search(r"back|\bs\b", name, re.I) else "forward"
        act = f"dashes {d}"
    elif kind == "reaction":
        act = "reacts to being hit, recoiling"
    elif kind == "defence":
        act = "raises a guard to block"
    elif kind == "ability":
        act = "charges up and unleashes a powerful move"
    elif kind in ("dance", "emote") or group == "dance_emote":
        act = "dances energetically" if kind == "dance" else "performs an expressive gesture"
    else:
        words = re.sub(r"[^a-z ]", " ", name.lower()).strip()
        act = f"performs a {words} move" if words else "performs a move"
    m = (" " + mods[0]) if mods else ""
    power = " with great force" if "heavy" in tags else ""
    t1 = f"A person{m} {act}{power}" + (", " + ", ".join(extras[:3]) if extras else "") + f", {seconds_words(secs)}."
    lead = "A fighter" if group == "combat" else "A character"
    t2 = f"{lead} {act}{m}" + (" while " + extras[0] if extras else "") + ("" if "loop" not in tags else ", repeating in a loop") + "."
    return [re.sub(r"\s+", " ", t1).strip(), re.sub(r"\s+", " ", t2).strip()]


def swap_lr(s):
    return re.sub(r"\b(left|right)\b", lambda m: "right" if m.group(1) == "left" else "left", s)


def texts():
    labels = [json.loads(s) for s in open(os.path.join(DATA, "labels.jsonl"), encoding="utf-8")]
    labels = [lb for lb in labels if lb["licence"] == "game" and lb["owner_verdict"] not in EXCLUDE_VERDICTS]
    base = {lb["id"]: lb for lb in labels if lb["augmentation"] is None}
    z = np.load(os.path.join(DATA, "clips.npz"))
    zs = {}
    out = {}
    for lb in labels:
        src = lb.get("source_id") or lb["id"]
        if src not in base:
            continue
        if src not in zs:
            rot, pos = z[f"{src}/rot"], z[f"{src}/pos"]
            zs[src] = (measured_limb(rot, pos), len(rot) / 60.0)
        limb, secs = zs[src]
        aug = lb["augmentation"] or {}
        secs_a = secs * float(aug.get("retime", 1.0))
        t = describe(base[src], limb, secs_a)
        if aug.get("mirror"):
            t = [swap_lr(x) for x in t]
        out[lb["id"]] = {"source": src, "texts": t, "group": base[src]["group"], "verdict": base[src]["owner_verdict"]}
    os.makedirs(OUT, exist_ok=True)
    json.dump(out, open(os.path.join(OUT, "texts.json"), "w", encoding="utf-8"), indent=0)
    uniq = sorted({t for v in out.values() for t in v["texts"]})
    print(json.dumps({"schema": 1, "status": "pass", "summary": f"{len(out)} clips ({len(base)} base, bad/laggy left out), {len(uniq)} unique texts",
                      "next_action": "embed them: <kimodo venv> python kit/anim/kimodo_r6_text.py embed"}))
    return out


def embed():
    """every unique text -> Kimodo's LLM2Vec embedding [4096] (CPU), cached; resumable"""
    import time
    import torch
    from kimodo.model.llm2vec.llm2vec_wrapper import LLM2VecEncoder
    out = json.load(open(os.path.join(OUT, "texts.json"), encoding="utf-8"))
    extra = json.load(open(os.path.join(OUT, "prompts.json"), encoding="utf-8")) if os.path.exists(os.path.join(OUT, "prompts.json")) else []
    uniq = sorted({t for v in out.values() for t in v["texts"]} | set(extra))
    path = os.path.join(OUT, "text_emb.npz")
    have = dict(np.load(path, allow_pickle=False)) if os.path.exists(path) else {}
    keys = json.load(open(path + ".keys.json", encoding="utf-8")) if os.path.exists(path + ".keys.json") else []
    done = {k: have[str(i)] for i, k in enumerate(keys)}
    # priority: the test prompts and every clip's FIRST description, then the second ones (training can start early)
    first = list(extra) + sorted({v["texts"][0] for v in out.values()})
    todo = [t for t in dict.fromkeys(first + uniq) if t not in done]
    print(f"{len(uniq)} texts, {len(todo)} to embed", flush=True)
    enc = LLM2VecEncoder("McGill-NLP/LLM2Vec-Meta-Llama-3-8B-Instruct-mntp", "McGill-NLP/LLM2Vec-Meta-Llama-3-8B-Instruct-mntp-supervised",
                         "bfloat16", 4096, device="cpu")
    t0 = time.time()
    for i in range(0, len(todo), 16):
        chunk = todo[i: i + 16]
        e, _ = enc(chunk)
        for t, v in zip(chunk, e[:, 0].float().cpu().numpy()):
            done[t] = v.astype(np.float16)
        if (i // 16) % 10 == 0 or i + 16 >= len(todo):
            keys = list(done)
            np.savez(path, **{str(j): done[k] for j, k in enumerate(keys)})
            json.dump(keys, open(path + ".keys.json", "w", encoding="utf-8"))
            print(f"  {len(done)}/{len(uniq)}  {time.time() - t0:.0f} s", flush=True)


def gpu_encoder(quant):
    """LLM2Vec (Llama-3-8B) on the 12 GB GPU, quantised by bitsandbytes: 'int8' or 'nf4' (bf16 compute).
    transformers 5.1's on-load quantiser cannot walk this repo's adapter-wrapped layers (int8: '...base_layer.SCB is
    neither a parameter...'; nf4: 'weight is not an nn.Module'), so: load bf16 on the CPU, MERGE both LoRA adapters
    into the weights, then swap every nn.Linear for bitsandbytes' own Linear8bitLt / Linear4bit and move to the GPU
    (bitsandbytes quantises on that move)"""
    import torch
    import bitsandbytes as bnb
    from kimodo.model.llm2vec.llm2vec import LLM2Vec
    enc = LLM2Vec.from_pretrained(base_model_name_or_path="McGill-NLP/LLM2Vec-Meta-Llama-3-8B-Instruct-mntp",
                                  peft_model_name_or_path="McGill-NLP/LLM2Vec-Meta-Llama-3-8B-Instruct-mntp-supervised",
                                  torch_dtype=torch.bfloat16, merge_peft=True)
    model = enc.model

    def swap(parent):
        for name, child in list(parent.named_children()):
            if isinstance(child, torch.nn.Linear):
                W = child.weight.data
                if quant == "int8":
                    new = bnb.nn.Linear8bitLt(child.in_features, child.out_features, bias=child.bias is not None,
                                              has_fp16_weights=False, threshold=6.0)
                    new.weight = bnb.nn.Int8Params(W.to(torch.float16), requires_grad=False, has_fp16_weights=False)
                else:
                    new = bnb.nn.Linear4bit(child.in_features, child.out_features, bias=child.bias is not None,
                                            compute_dtype=torch.bfloat16, quant_type="nf4")
                    new.weight = bnb.nn.Params4bit(W, requires_grad=False, quant_type="nf4")
                if child.bias is not None:
                    new.bias = torch.nn.Parameter(child.bias.data, requires_grad=False)
                setattr(parent, name, new.to("cuda"))       # quantised here
                del child
            else:
                swap(child)
    swap(model)
    model.to("cuda")                                       # embeddings / norms stay bf16
    enc.to = lambda *a, **k: enc                          # encode() calls self.to(device): already placed
    enc.eval()
    return enc


def gpu_embed(texts_list, enc, bs=16):
    import torch
    out = []
    with torch.inference_mode():
        for i in range(0, len(texts_list), bs):
            e = enc.encode(texts_list[i: i + bs], batch_size=bs, show_progress_bar=False, device="cuda")
            out.append(np.asarray(e, np.float32))
    return np.concatenate(out)


def embed_gpu(quant="int8", validate=False, bs=1):
    # bs MUST stay 1: LLM2Vec's padding changes the embedding (measured 2026-10-13, NF4: batch 1 vs the CPU reference cos
    # min 0.984, batch 16 only 0.825; batch 1 vs batch 16 0.834) - Kimodo's own wrapper forces 1 for the same reason
    """validate: re-embed the texts already embedded on the CPU and compare (cosine); else embed every text not done"""
    import time
    import torch
    path = os.path.join(OUT, "text_emb.npz")
    keys = json.load(open(path + ".keys.json", encoding="utf-8"))
    z = np.load(path)
    done = {k: z[str(i)].astype(np.float32) for i, k in enumerate(keys)}
    t0 = time.time()
    enc = gpu_encoder(quant)
    load_s = time.time() - t0
    vram = torch.cuda.max_memory_allocated() / 1e9
    if validate:
        ref_keys = keys[:32]
        t1 = time.time()
        g = gpu_embed(ref_keys, enc, bs)
        r = np.stack([done[k] for k in ref_keys])
        cos = (g * r).sum(1) / (np.linalg.norm(g, axis=1) * np.linalg.norm(r, axis=1))
        rep = {"quant": quant, "texts": len(ref_keys), "cos_min": round(float(cos.min()), 5), "cos_mean": round(float(cos.mean()), 5),
               "load_s": round(load_s, 1), "embed_s": round(time.time() - t1, 1), "vram_gb_after_load": round(vram, 2),
               "vram_gb_peak": round(torch.cuda.max_memory_allocated() / 1e9, 2)}
        print(json.dumps(rep), flush=True)
        json.dump(rep, open(os.path.join(OUT, f"validate_{quant}.json"), "w"), indent=1)
        return rep
    out = json.load(open(os.path.join(OUT, "texts.json"), encoding="utf-8"))
    extra = json.load(open(os.path.join(OUT, "prompts.json"), encoding="utf-8"))
    uniq = list(dict.fromkeys(list(extra) + sorted({t for v in out.values() for t in v["texts"]})))
    todo = [t for t in uniq if t not in done]
    print(f"{len(uniq)} texts, {len(done)} done on the CPU, {len(todo)} to embed on the GPU ({quant})", flush=True)
    t1 = time.time()
    for i in range(0, len(todo), 256):
        chunk = todo[i: i + 256]
        for t, v in zip(chunk, gpu_embed(chunk, enc, bs)):
            done[t] = v
        ks = list(done)
        np.savez(path, **{str(j): done[k].astype(np.float16) for j, k in enumerate(ks)})
        json.dump(ks, open(path + ".keys.json", "w", encoding="utf-8"))
        print(f"  {len(done)}/{len(uniq)}  {time.time() - t1:.0f} s", flush=True)
    rep = {"quant": quant, "embedded": len(todo), "total": len(done), "seconds": round(time.time() - t1, 1), "load_s": round(load_s, 1),
           "vram_gb_peak": round(torch.cuda.max_memory_allocated() / 1e9, 2)}
    json.dump(rep, open(os.path.join(OUT, f"embed_gpu_{quant}.json"), "w"), indent=1)
    print(json.dumps(rep), flush=True)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "embed_gpu":
        sys.stdout.reconfigure(encoding="utf-8")
        q = sys.argv[sys.argv.index("--quant") + 1] if "--quant" in sys.argv else "int8"
        embed_gpu(q, "--validate" in sys.argv, int(sys.argv[sys.argv.index("--bs") + 1]) if "--bs" in sys.argv else 1)
        sys.exit(0)
    sys.stdout.reconfigure(encoding="utf-8")
    {"texts": texts, "embed": embed}[sys.argv[1]]()
