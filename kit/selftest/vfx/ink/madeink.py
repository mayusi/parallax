"""madeink.py — what the ink's proof needs beside the trace's made flame (kit/selftest/vfx/trace/made.py):

    truth_cell(k, scale, offset, cell)   drawing k's TRUE flame (body with its cut-out) drawn straight into a cell
                                         through the same window the ink used - what the cell must show
    truth_core_cell(...)                 the same for its core: where the cell must be the core's colour
    split()                              a made scene of two drawings that are NOT the same pieces and barely
                                         overlap: one flame on the left, then two small flames on the right. An
                                         in-between of them is a blend, not a drawing - the ink must refuse it
"""

import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "trace"))
import made  # noqa: E402


def truth_cell(k, scale, offset, cell, ss=4):
    body, hole, _, _ = made.outline(k)

    def put(poly):
        return [((x + offset[0]) * scale * ss, (y + offset[1]) * scale * ss) for x, y in poly]

    im = Image.new("L", (cell * ss, cell * ss), 0)
    pen = ImageDraw.Draw(im)
    pen.polygon(put(body), fill=255)
    pen.polygon(put(hole), fill=0)
    return np.asarray(im.resize((cell, cell), Image.BOX)) >= 128


def truth_core_cell(k, scale, offset, cell, ss=4):
    """drawing k's TRUE core drawn straight into a cell through the ink's window"""
    core = made.outline(k)[2]
    im = Image.new("L", (cell * ss, cell * ss), 0)
    ImageDraw.Draw(im).polygon([((x + offset[0]) * scale * ss, (y + offset[1]) * scale * ss) for x, y in core], fill=255)
    return np.asarray(im.resize((cell, cell), Image.BOX)) >= 128


def _frame(polys, seed):
    back = made.night()
    cov = Image.new("L", (made.W * made.SS, made.H * made.SS), 0)
    pen = ImageDraw.Draw(cov)
    for p in polys:
        pen.polygon([(x * made.SS, y * made.SS) for x, y in p], fill=255)
    a = np.asarray(cov.resize((made.W, made.H), Image.BOX), dtype=np.float32)[..., None] / 255.0
    back = back * (1 - a) + np.array(made.BODY, dtype=np.float32) * a
    grain = np.random.default_rng(2000 + seed).integers(-3, 4, size=back.shape)
    return np.clip(back + grain, 0, 255).astype(np.uint8)


def split():
    """-> (N, H, W, 3): one flame on the left held two frames, then two small flames on the right held two frames"""
    body = made.outline(0)[0]
    left = [(x - 60.0, y) for x, y in body]

    def small(dx, dy):
        return [(330.0 + (x - 330.0) * 0.45 + dx, 310.0 + (y - 310.0) * 0.45 + dy) for x, y in body]

    right = [small(190.0, -10.0), small(255.0, -60.0)]
    return np.stack([_frame([left], 0), _frame([left], 1), _frame(right, 2), _frame(right, 3)])
