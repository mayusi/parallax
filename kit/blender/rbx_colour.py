"""rbx_colour.py — colour arithmetic for the kit's colour checks (plain numpy: no Blender, unit-tested).

    lab = srgb_to_lab((0.8, 0.6, 0.4))          # sRGB 0..1 -> CIELAB (D65): L* lightness, a* green-red, b* blue-yellow
    colour_words(lab_model, lab_reference)      # "darker by 16 L*, greyer" / "green where the reference is blue"
    colour_off(lab_model, lab_reference)        # another HUE, or half / twice the saturation (lightness is light's)
"""

import math

import numpy as np


def srgb_to_lab(rgb):
    """sRGB colours (0..1, ... x 3) -> CIELAB (D65): L* 0..100 lightness, a* green(-)..red(+), b* blue(-)..yellow(+)"""
    c = np.clip(np.asarray(rgb, dtype=np.float64), 0.0, 1.0)
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    xyz = lin @ np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]]).T
    xyz = xyz / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > (6 / 29) ** 3, np.cbrt(xyz), xyz / (3 * (6 / 29) ** 2) + 4 / 29)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def colour_words(model_lab, ref_lab):
    """how a model colour differs from the reference's, in words ("darker by 14 L*, greyer, more yellow")"""
    dl = model_lab[0] - ref_lab[0]
    cm, cr = float(np.hypot(*model_lab[1:])), float(np.hypot(*ref_lab[1:]))
    out = []
    if abs(dl) >= 5:
        out.append(f"{'lighter' if dl > 0 else 'darker'} by {abs(dl):.0f} L*")
    if abs(cm - cr) >= 6:
        out.append("more saturated" if cm > cr else "greyer")
    hm = math.degrees(math.atan2(model_lab[2], model_lab[1])) % 360
    hr_ = math.degrees(math.atan2(ref_lab[2], ref_lab[1])) % 360
    turn = hue_turn(model_lab, ref_lab)
    if min(cm, cr) >= 8 and turn >= 35:  # another colour altogether: name both
        out.append(f"{hue_name(hm)} where the reference is {hue_name(hr_)}")
    elif min(cm, cr) >= 5 and turn >= 8:  # (a hue shift means little on a near-grey)
        da, db = model_lab[1] - ref_lab[1], model_lab[2] - ref_lab[2]
        out.append(("redder" if da > 0 else "greener") if abs(da) >= abs(db) else ("yellower" if db > 0 else "bluer"))
    return ", ".join(out) or "close"


def hue_name(deg):
    """a CIELAB hue angle as a colour word (red ~30, orange ~60, yellow ~95, green ~140, cyan ~200, blue ~280)"""
    for top, word in ((15, "magenta-red"), (45, "red"), (75, "orange"), (110, "yellow"), (170, "green"), (230, "cyan"),
                      (300, "blue"), (340, "purple"), (360, "magenta-red")):
        if deg < top:
            return word
    return "red"


def hue_turn(model_lab, ref_lab):
    """the angle (degrees) between two colours' hues"""
    hm = math.degrees(math.atan2(model_lab[2], model_lab[1])) % 360
    hr_ = math.degrees(math.atan2(ref_lab[2], ref_lab[1])) % 360
    return min(abs(hm - hr_), 360 - abs(hm - hr_))


def colour_off(model_lab, ref_lab, turn=30.0, ratio=2.0, grey=10.0):
    """is the model's colour another colour than the reference's? Judged on what LIGHT leaves alone: the hue (more
    than `turn` degrees apart, both colours saturated past `grey`) and the saturation (one more than `ratio` times the
    other's, the stronger past 1.5 x `grey`). Lightness is not judged here: a lit picture's lightness is its light's,
    and a material's is checked against the PBR ranges"""
    cm, cr = float(np.hypot(*model_lab[1:])), float(np.hypot(*ref_lab[1:]))
    if min(cm, cr) >= grey and hue_turn(model_lab, ref_lab) > turn:
        return True
    return max(cm, cr) >= 1.5 * grey and max(cm, cr) > ratio * max(min(cm, cr), 1e-6)
