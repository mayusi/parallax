"""kit design concept (kit/tools/design.py) - the redraw that keeps the design wins: best_match picks the candidate
whose silhouette lies on the pick's (at any scale, mirrored too), and a different shape scores low."""

import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
import design  # noqa: E402


def gun(H=400, W=600, s=1.0, flip=False):
    m = np.zeros((H, W), bool)
    m[int(150 * s):int(200 * s), int(100 * s):int(450 * s)] = True       # the barrel
    m[int(200 * s):int(330 * s), int(360 * s):int(430 * s)] = True       # the grip
    return m[:, ::-1] if flip else m


def test_the_redraw_that_kept_the_design_wins():
    pick = gun()
    other = np.zeros((400, 600), bool)
    yy, xx = np.mgrid[:400, :600]
    other[(yy - 200) ** 2 + (xx - 300) ** 2 < 100 ** 2] = True
    f, iou = design.best_match([("blob", other), ("same_smaller_mirrored", gun(400, 600, 0.8, True))], pick)
    assert f == "same_smaller_mirrored" and iou > 0.85, (f, iou)


def test_concept_prompt_keeps_the_object_and_turns_the_view():
    p = design.concept_prompt("front", "a lantern pistol")
    assert "The same weapon exactly as in the reference image" in p and "directly in front" in p
    assert "no " not in p


def staff(H=600, W=400):
    m = np.zeros((H, W), bool)
    m[120:560, 220:250] = True        # the pole
    m[80:120, 120:250] = True         # the crook's top
    m[80:260, 110:150] = True         # its arm down to a lantern
    m[260:360, 95:170] = True         # the lantern
    return m


def test_a_turned_view_that_is_the_base_plus_a_disc_is_a_copy():
    base = staff()
    plus = base.copy()
    yy, xx = np.mgrid[:600, :400]
    plus[(yy - 300) ** 2 + (xx - 235) ** 2 < 70 ** 2] = True     # (the Lantern Hook's "front": its side + a disc)
    assert design.best_match([("plus", plus)], base)[1] <= 0.75    # (the old rule kept it)
    assert design.copies_base(plus, base)
    front = np.zeros((600, 400), bool)
    front[80:560, 185:215] = True                                    # a real front: one thin upright bar
    front[260:360, 165:235] = True
    assert not design.copies_base(front, base)
