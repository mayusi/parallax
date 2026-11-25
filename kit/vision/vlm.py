"""vlm.py — the kit's local vision-language model (Qwen3-VL-4B-Instruct, vetted + pinned: kit/vision/models.json
"qwen3-vl-4b"), offline like every kit vision model. It READS a picture the way an artist reads a reference: which
small details are there and where (kit refs inventory), what an engraving says (kit refs read).

    ask(image, "question")                    -> the model's answer (text)
    details(image, what="the object", n=40)   -> [{"label", "kind", "box": [x0, y0, x1, y1] picture px, "note"}]
    read_text(image)                          -> the text written / engraved in the picture ("" if none)

Qwen3-VL gives boxes on a 0-1000 scale of the picture it was shown; parse_details() maps them to the picture's own
pixels (pure: test_inventory.py). Never a judge of quality: it finds and names, a person looks.
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

NAME = "qwen3-vl-4b"
# the files installed() asks for only when models.json has no entry for the model (it normally checks every file the
# manifest lists, shards included, at its recorded size)
_REQUIRED_FILES = ("config.json", "tokenizer.json", "tokenizer_config.json")
KINDS = ("fastener", "gem", "trim", "engraving", "text", "logo", "control", "sight", "chain", "panel", "texture",
         "opening", "edge", "part", "other")
_M = {}

DETAIL_PROMPT = (
    "You are a 3D artist listing EVERY small visible detail of {what} in this picture, so each can be modelled: "
    "screws, pins, rivets, gems and their settings, raised trim and borders, engraving, text, logos, buttons, levers, "
    "the hammer, the trigger, sights, chains and rings, panels and their seams, grip texture, holes, vents, any "
    "decoration. Give up to {n} items, small ones included, each a separate thing (not the whole object). Answer ONLY "
    "a JSON list, one object per detail: "
    '{{"label": "short name", "kind": one of {kinds}, "bbox_2d": [x0, y0, x1, y1], "note": "at most 4 words"}}. No other '
    'text.')


PARTS_PROMPT = (
    "You are a 3D artist listing the separate PARTS of {what} in this picture, each one that would be modelled as its "
    "own piece: for a weapon the barrel, muzzle / crown, front sight, rear sight, slide / frame, hammer, trigger, "
    "trigger guard, grip and grip panels, buttons, levers, pins, chains, charms, rings, the gem and its setting; for "
    "anything else its equivalent pieces. Give up to {n} items, each a separate part (not the whole object). Answer "
    "ONLY a JSON list, one object per part: "
    '{{"label": "short name", "kind": one of {kinds}, "bbox_2d": [x0, y0, x1, y1], "note": "at most 4 words"}}. No other '
    'text.')
PROMPTS = {"details": DETAIL_PROMPT, "parts": PARTS_PROMPT}


def installed():
    """True when EVERY file the manifest (models.json) lists for the model is in the cache at its recorded size - a
    download cut short is not installed, so the caller hands the AI client a packet instead of crashing on half a model.
    Does NOT import torch, load weights or hash anything. Uses KIT_MODELS when set, else
    ~/.cache/roblox-kit/models/qwen3-vl-4b. (No manifest entry: its minimum files.)"""
    folder = os.path.join(
        os.environ.get("KIT_MODELS") or os.path.join(os.path.expanduser("~"), ".cache", "roblox-kit", "models"),
        NAME,
    )
    if not os.path.isdir(folder):
        return False
    try:
        with open(os.path.join(HERE, "models.json"), encoding="utf-8") as fh:
            files = json.load(fh)["models"][NAME]["files"]
    except (OSError, ValueError, KeyError, TypeError):
        files = None
    if not files:
        return all(os.path.isfile(os.path.join(folder, f)) for f in _REQUIRED_FILES)
    for f in files:
        if not isinstance(f, dict) or not isinstance(f.get("path"), str):
            return False  # (a manifest entry the kit cannot read: not installed, the packet route instead)
        p = os.path.join(folder, f["path"])
        if not os.path.isfile(p) or (f.get("size") and os.path.getsize(p) != f["size"]):
            return False
    return True


def _load():
    if "m" not in _M:
        import run  # noqa: PLC0415  (offline guard, pin check)

        torch, dev = run._torch()
        from transformers import AutoModelForImageTextToText, AutoProcessor  # noqa: PLC0415

        folder = run.ensure(NAME)
        proc = AutoProcessor.from_pretrained(folder, local_files_only=True)
        kw = {"local_files_only": True, "use_safetensors": True}
        quant = os.environ.get("KIT_VLM_QUANT", "auto")
        if dev == "cuda" and quant == "auto":  # (bf16 needs ~10 GB; a shared card short of it: 4-bit, ~3.5 GB)
            free_b, _total = torch.cuda.mem_get_info()
            quant = "bf16" if free_b > 10.5e9 else "4bit"
        if dev == "cuda" and quant == "4bit":
            from transformers import BitsAndBytesConfig  # noqa: PLC0415

            kw.update(quantization_config=BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                                             bnb_4bit_compute_dtype=torch.bfloat16), device_map="cuda")
            model = AutoModelForImageTextToText.from_pretrained(folder, **kw)
        else:
            model = AutoModelForImageTextToText.from_pretrained(
                folder, dtype=torch.bfloat16 if dev == "cuda" else torch.float32, **kw).to(dev)
        _M["m"], _M["p"], _M["dev"], _M["quant"] = model.eval(), proc, dev, quant
    return _M["m"], _M["p"], _M["dev"]


def free():
    """let the GPU go (a generator or another model runs next)"""
    if _M:
        import torch  # noqa: PLC0415

        _M.clear()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


def yes_scores(prompts, batch=1):
    """text-only yes/no questions: each prompt's yes-minus-no logit for its first answer token (higher = more of a
    yes). The parts libraries' re-ranker (kit/tools/parts_rerank.py) asks "does this card help build that?" here, so a
    warm vision worker answers a whole sheet with the model loaded once. One prompt per pass by default: the batch's
    shape moves the scores (bf16 / 4-bit kernels: the same prompt -2.75 alone, -3.24 beside its own copy - fresh
    review, P1), so a card's score never depends on what else is on the sheet"""
    import torch  # noqa: PLC0415

    model, proc, dev = _load()
    tok = proc.tokenizer
    first = {w: tok.encode(w, add_special_tokens=False)[0] for w in ("yes", "Yes", "no", "No")}
    yes, no = [first["yes"], first["Yes"]], [first["no"], first["No"]]
    out = []
    side = tok.padding_side
    tok.padding_side = "left"  # (every row's last position is its own last token)
    try:
        for i in range(0, len(prompts), batch):
            chunk = prompts[i:i + batch]
            texts = [proc.apply_chat_template([{"role": "user", "content": [{"type": "text", "text": p}]}],
                                              tokenize=False, add_generation_prompt=True) for p in chunk]
            enc = tok(texts, return_tensors="pt", padding=True).to(dev)
            with torch.inference_mode():
                logits = model(**enc).logits[:, -1].float()
            out += (torch.logsumexp(logits[:, yes], 1) - torch.logsumexp(logits[:, no], 1)).tolist()
    finally:
        tok.padding_side = side
    return out


def _fit(image, max_side):
    from PIL import Image  # noqa: PLC0415

    im = image if isinstance(image, Image.Image) else Image.open(image)
    im = im.convert("RGB")
    k = max_side / max(im.size)
    if k < 1:
        im = im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)
    return im


def ask(image, prompt, max_side=896, max_new_tokens=1400):
    import torch  # noqa: PLC0415

    model, proc, dev = _load()
    im = _fit(image, max_side)
    msgs = [{"role": "user", "content": [{"type": "image", "image": im}, {"type": "text", "text": prompt}]}]
    inputs = proc.apply_chat_template(msgs, tokenize=True, add_generation_prompt=True, return_dict=True,
                                      return_tensors="pt").to(dev)
    with torch.inference_mode():
        out = model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
    return proc.batch_decode(out[:, inputs["input_ids"].shape[1]:], skip_special_tokens=True)[0].strip()


def _json_list(text):
    """the first JSON list in the model's answer (it may wrap it in ```json fences or stop mid-list)"""
    t = re.sub(r"```(?:json)?", "", text)
    starts = [m.start() for m in re.finditer(r"\[", t)]
    for i in starts:  # (a "[" in the model's preamble — "[up to 30] items:" — is not the list: try each)
        body = t[i:]
        if not body[1:].lstrip().startswith(("{", "]")):
            continue
        for end in range(len(body), 0, -1):  # a cut-off answer: drop the broken tail object
            chunk = body[:end].rstrip().rstrip(",")
            if not chunk.endswith("]"):
                j = chunk.rfind("}")
                if j < 0:
                    break
                chunk = chunk[:j + 1] + "]"
            try:
                v = json.loads(chunk)
                if isinstance(v, list):
                    return v
                break
            except ValueError:
                continue
    return []


def parse_details(text, width, height):
    """the model's JSON -> details with boxes in the picture's pixels (0-1000 scale -> px), clipped, de-duplicated
    (same label + boxes overlapping > 0.8), the whole-object box dropped (> 85% of the picture)"""
    out = []
    for d in _json_list(text):
        if not isinstance(d, dict):
            continue
        b = d.get("bbox_2d") or d.get("box") or d.get("bbox")
        if not (isinstance(b, (list, tuple)) and len(b) == 4):
            continue
        try:
            x0, y0, x1, y1 = (float(v) for v in b)
        except (TypeError, ValueError):
            continue
        x0, x1 = sorted((x0, x1))
        y0, y1 = sorted((y0, y1))
        box = [max(0.0, x0 / 1000 * width), max(0.0, y0 / 1000 * height), min(width, x1 / 1000 * width),
               min(height, y1 / 1000 * height)]
        if box[2] - box[0] < 2 or box[3] - box[1] < 2:
            continue
        if (box[2] - box[0]) * (box[3] - box[1]) > 0.85 * width * height:
            continue
        label = str(d.get("label") or "detail").strip()[:60]
        kind = str(d.get("kind") or "other").strip().lower()
        kind = kind if kind in KINDS else "other"
        if any(o["label"].lower() == label.lower() and iou(o["box"], box) > 0.8 for o in out):
            continue
        out.append({"label": label, "kind": kind, "box": [round(v, 1) for v in box],
                    "note": str(d.get("note") or "")[:120]})
    return out


def iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / u if u > 0 else 0.0


def details(image, what="the object", n=30, max_side=896, passes=("details",)):
    """every pass's list (small DETAILS: decoration, fasteners, text; PARTS: the pieces a modeller builds), merged:
    the same label over the same place (IoU > 0.6) kept once"""
    im = _fit(image, 10 ** 6)
    found, raws = [], []
    for p in passes:
        text = ask(im, PROMPTS[p].format(what=what, n=n, kinds=list(KINDS)), max_side=max_side)
        raws.append(f"## {p}\n{text}")
        for d in parse_details(text, im.width, im.height):
            if not any(o["label"].lower() == d["label"].lower() and iou(o["box"], d["box"]) > 0.6 for o in found):
                d["pass"] = p
                found.append(d)
    return found, "\n\n".join(raws)


def read_text(image, max_side=896):
    t = ask(image, "Read every letter and number written, engraved or stamped in this picture, exactly as written, "
                   "line by line. Answer only the text; answer NONE if there is no text.", max_side=max_side,
            max_new_tokens=256)
    return "" if t.strip().upper().startswith("NONE") else t.strip()
