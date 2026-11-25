"""flash.py — the PHOTOSENSITIVITY check (WCAG 2.3.1 / the Harding research): no more than THREE flashes in any one
second, red flashes stricter. A screen's own fx (flicker, split, ping, bursts, flashes) can break it; this counts what
a reel actually shows.

    flash_report(frames, fps) -> {"max_hz", "red_max_hz", "area_share", "fail", "where"}

The WCAG definitions, measured per pixel on the reel's frames:
- a general flash is a PAIR of opposing changes in relative luminance of >= 10% of the maximum, where the darker state
  is below 0.80;
- a red flash is a pair of opposing transitions to or from a saturated red (R / (R+G+B) >= 0.8) whose red change
  (R - G - B) * 320 is > 20;
- it is a FAILURE when, in some one-second window, the pixels flashing more than 3 times cover more than 25% of a 10
  degree field of view: 341 x 256 px at 1024 x 768, scaled to the frame's size.
The reel (kit/ui/reel.py) runs this on every film and FAILS the reel above the line; Ui.setReduceFlashing(true)
stills the fx that flash (split, flicker, ping) for players who ask.
"""
import numpy as np

FIELD_SHARE = 0.25 * (341 * 256) / (1024 * 768)   # the WCAG area: a quarter of a 10-degree field, as a share of the screen


def luminance(rgb):
    c = np.asarray(rgb, dtype=np.float64) / 255.0
    c = np.where(c <= 0.03928, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * c[..., 0] + 0.7152 * c[..., 1] + 0.0722 * c[..., 2]


def _transitions(series, thr, dark_cap):
    """per pixel, the frames where a qualifying luminance change happens, signed (+1 brighter, -1 darker, 0 none)"""
    d = np.diff(series, axis=0)
    lo = np.minimum(series[:-1], series[1:])
    big = (np.abs(d) >= thr) & (lo < dark_cap)
    return np.where(big, np.sign(d), 0).astype(np.int8)


def _flash_counts(trans, fps):
    """per pixel, the most flashes (pairs of opposing transitions) inside any one-second window"""
    n = trans.shape[0]
    win = max(1, int(round(fps)))
    best = np.zeros(trans.shape[1:], dtype=np.int32)
    for s in range(0, max(1, n - win + 1)):
        w = trans[s:s + win]
        # opposing pairs: count sign alternations among the nonzero transitions
        last = np.zeros(trans.shape[1:], dtype=np.int8)
        alts = np.zeros(trans.shape[1:], dtype=np.int32)
        for k in range(w.shape[0]):
            t = w[k]
            flip = (t != 0) & (last != 0) & (t != last)
            alts += flip
            last = np.where(t != 0, t, last)
        best = np.maximum(best, (alts + 1) // 2)
    return best


def flash_report(frames, fps, small=160):
    """frames: a list of PIL images (one film); fps: its frame rate"""
    if len(frames) < 3:
        return {"max_hz": 0, "red_max_hz": 0, "area_share": 0.0, "red_area_share": 0.0, "fail": False, "where": None}
    w0, h0 = frames[0].size
    k = small / max(w0, h0)
    size = (max(8, int(w0 * k)), max(8, int(h0 * k)))
    arr = np.stack([np.asarray(f.convert("RGB").resize(size)) for f in frames]).astype(np.float64)
    lum = luminance(arr)
    gen = _flash_counts(_transitions(lum, 0.10, 0.80), fps)
    rgb_sum = arr.sum(-1) + 1e-6
    red_sat = (arr[..., 0] / rgb_sum) >= 0.8
    red_val = np.where(red_sat, (arr[..., 0] - arr[..., 1] - arr[..., 2]) / 255.0 * 320.0, 0.0)
    red = _flash_counts(_transitions(red_val, 20.0, 1e9), fps)
    over = gen > 3
    red_over = red > 3
    share = float(over.mean())
    red_share = float(red_over.mean())
    where = None
    if over.any() or red_over.any():
        ys, xs = np.nonzero(over | red_over)
        where = [int(xs.min() / size[0] * w0), int(ys.min() / size[1] * h0), int((xs.max() + 1) / size[0] * w0), int((ys.max() + 1) / size[1] * h0)]
    return {
        "max_hz": int(gen.max()),
        "red_max_hz": int(red.max()),
        "area_share": round(share, 4),
        "red_area_share": round(red_share, 4),
        "fail": share > FIELD_SHARE or red_share > FIELD_SHARE,
        "where": where,
    }
