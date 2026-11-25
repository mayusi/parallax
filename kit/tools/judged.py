"""Keep a small copy of what the owner judged, beside the verdict (`kit verdict ... --shown <file>`).

The vault learns the owner's eye only if it keeps WHAT was judged: on 2026-11-08 none of the 351 verdict notes did.
One copy per source file: the copy is named by the sha256 of the source bytes, so a strip judged for three pieces is
stored once. A picture or GIF becomes a small JPEG (longest side <= 640 px, about 150 KB at most; a GIF gives its
middle frame, the action rather than the wind-up). A sound is kept as it is up to 512 KB; a longer PCM wav is cut to
its first 4 seconds; any other long sound is refused. Anything that is neither is refused with the reason, and a file
that does not decode is never stored.

usage: python kit/tools/judged.py <source> <vault-dept-dir>
prints one JSON line: {"rel": "<dept>/judged/<sha16>.<ext>", "reused": bool, "bytes": n, "kind": "image"|"sound"}
or {"error": "..."} with exit 1 (2 for a usage error).
"""

import hashlib
import io
import json
import os
import sys
import wave

IMAGE = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
SOUND = {".wav", ".ogg", ".mp3", ".flac"}
MAX_SIDE = 640
MAX_IMAGE = 150_000
MAX_SOUND = 512_000
CUT_SECONDS = 4.0


def emit(obj, code=0):
    print(json.dumps(obj))
    sys.exit(code)


def sha16(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def image_bytes(src):
    from PIL import Image  # noqa: PLC0415  (the kit's renders already need Pillow)

    with Image.open(src) as im:
        if getattr(im, "is_animated", False):
            im.seek(im.n_frames // 2)
        frame = im.convert("RGB")
    frame.thumbnail((MAX_SIDE, MAX_SIDE))
    data = b""
    for quality in (85, 75, 65, 55, 45):
        buf = io.BytesIO()
        frame.save(buf, "JPEG", quality=quality, optimize=True)
        data = buf.getvalue()
        if len(data) <= MAX_IMAGE:
            break
    return data


MAGIC = {".ogg": (b"OggS",), ".flac": (b"fLaC",), ".mp3": (b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2", b"\xff\xfa")}


def check_sound(src, ext):
    """A sound that does not decode is refused (the 11-05 restore left files of the right size full of zeros)."""
    with open(src, "rb") as f:
        head = f.read(4096)
    if not head.strip(b"\x00"):
        raise ValueError("its first 4 KB are all zeros")
    if ext == ".wav":
        with wave.open(src, "rb") as w:
            frames = w.readframes(min(w.getnframes(), w.getframerate()))
        if not frames or not frames.strip(b"\x00"):
            raise ValueError("a wav with no samples, or only silence")
    elif not head.startswith(MAGIC[ext]):
        raise ValueError(f"it does not start like a {ext} file")


def sound_bytes(src, ext):
    check_sound(src, ext)
    size = os.path.getsize(src)
    if size <= MAX_SOUND:
        with open(src, "rb") as f:
            return f.read(), ext
    if ext != ".wav":
        raise ValueError(f"{size} bytes is over {MAX_SOUND} and only a wav can be cut: keep a shorter take")
    with wave.open(src, "rb") as w:
        params = w.getparams()
        frames = w.readframes(int(params.framerate * CUT_SECONDS))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as out:
        out.setnchannels(params.nchannels)
        out.setsampwidth(params.sampwidth)
        out.setframerate(params.framerate)
        out.writeframes(frames)
    return buf.getvalue(), ".wav"


def vault_rel(dept_dir, path):
    # "<dept>/judged/<file>": relative to the vault root, the department folder's parent
    root = os.path.dirname(os.path.abspath(dept_dir))
    return os.path.relpath(os.path.abspath(path), root).replace(os.sep, "/")


def main(argv):
    if len(argv) != 3:
        emit({"error": "usage: judged.py <source> <vault-dept-dir>"}, 2)
    src, dept_dir = argv[1], argv[2]
    if not os.path.isfile(src):
        emit({"error": f"no such file: {src}"}, 1)
    ext = os.path.splitext(src)[1].lower()
    if ext in IMAGE:
        kind, final_ext = "image", ".jpg"
    elif ext in SOUND:
        kind, final_ext = "sound", ext
    else:
        emit(
            {
                "error": f"{ext or 'no extension'} is not kept: pass the picture (png/jpg/webp/gif) or the sound "
                "(wav/ogg/mp3/flac) the owner was shown"
            },
            1,
        )
    digest = sha16(src)
    judged_dir = os.path.join(dept_dir, "judged")
    # the same source bytes kept before AS THIS KIND (a picture's copy is a .jpg, a sound keeps its own extension;
    # a cut wav stays .wav): bytes kept as a sound are never handed back for a picture
    kept = os.path.join(judged_dir, digest + final_ext)
    if os.path.isfile(kept):
        emit({"rel": vault_rel(dept_dir, kept), "reused": True, "bytes": os.path.getsize(kept), "kind": kind})
    try:
        if kind == "image":
            data = image_bytes(src)
        else:
            data, final_ext = sound_bytes(src, ext)
    except Exception as e:  # noqa: BLE001  (a file that does not decode is refused, never stored)
        emit({"error": f"could not keep {src}: {e}"}, 1)
    os.makedirs(judged_dir, exist_ok=True)
    dest = os.path.join(judged_dir, digest + final_ext)
    with open(dest, "wb") as f:
        f.write(data)
    emit({"rel": vault_rel(dept_dir, dest), "reused": False, "bytes": len(data), "kind": kind})


if __name__ == "__main__":
    main(sys.argv)
