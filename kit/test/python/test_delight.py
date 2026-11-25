"""Taking the light out of a scan's colour, against an exact answer (kit/tools/delight.py's split; his D-R03).

A known colour (a speckle) times a known shading (a lamp from one side and a sky, a function of the way each texel
faces) is the "photographed" texture; the split must find that shading and give back the speckle, its tie to the
shading gone. (A colour that truly changes with the facing is NOT tested here: the assumption takes part of it for
shading - said on the page.)"""

import os
import sys
import tempfile
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "tools"))
import delight as D  # noqa: E402


def sphere_facing(size):
    """a texture whose texels face every way (a lat-long map of a sphere's normals), RGB = (n + 1) / 2"""
    v, u = np.meshgrid(np.linspace(0.02, 0.98, size), np.linspace(0, 1, size), indexing="ij")
    th, ph = v * np.pi, u * 2 * np.pi
    n = np.stack([np.sin(th) * np.cos(ph), np.sin(th) * np.sin(ph), np.cos(th)], -1)
    return n


def save(path, rgb01):
    from PIL import Image  # noqa: PLC0415

    Image.fromarray((np.clip(rgb01, 0, 1) * 255 + 0.5).astype(np.uint8)).save(path)


def to_srgb(lin):
    return np.where(lin <= 0.0031308, lin * 12.92, 1.055 * np.power(np.clip(lin, 0, 1), 1 / 2.4) - 0.055)


class Split(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        rng = np.random.default_rng(3)
        size = 256
        self.n = sphere_facing(size)
        light = np.array([0.6, -0.3, 0.74])
        light /= np.linalg.norm(light)
        self.shade = 0.25 + 0.75 * np.clip(self.n @ light, 0, None)          # a lamp from one side and a sky
        blocks = rng.uniform(0.2, 0.9, (16, 16, 3))
        self.albedo = np.kron(blocks, np.ones((16, 16, 1)))                  # a speckle of flat patches
        self.photo = self.albedo * self.shade[..., None]
        d = self.tmp.name
        self.tex, self.fac = os.path.join(d, "photo.png"), os.path.join(d, "facing.png")
        save(self.tex, to_srgb(self.photo))
        save(self.fac, (self.n + 1) / 2)

    def tearDown(self):
        self.tmp.cleanup()

    def test_the_shading_is_found_and_the_colour_given_back(self):
        sh, _ = D.shading_split(self.tex, self.fac)
        fac = (self.n + 1) / 2
        b = D.basis(fac * 2 - 1)
        e = np.stack([b @ np.array(sh[c * 9:(c + 1) * 9]) for c in range(3)], -1)
        found = (self.photo / np.maximum(e, 0.05))
        found *= self.albedo.mean() / found.mean()
        # the colour given back is the speckle (a lamp of 0.25 .. 1.0 taken out of it, to a few percent)
        err = np.abs(found - self.albedo).mean() / self.albedo.mean()
        before = np.abs(self.photo * (self.albedo.mean() / self.photo.mean()) - self.albedo).mean() / self.albedo.mean()
        self.assertLess(err, 0.4 * before, (err, before))
        # and its tie to the shading is gone
        lum = np.array([0.2126, 0.7152, 0.0722])
        s = e @ lum
        self.assertGreater(np.corrcoef((self.photo @ lum).ravel(), s.ravel())[0, 1], 0.5)
        self.assertLess(abs(np.corrcoef((found @ lum).ravel(), s.ravel())[0, 1]), 0.1)

    def test_the_tie_measure_reads_the_same_way(self):
        sh, _ = D.shading_split(self.tex, self.fac)
        found = os.path.join(self.tmp.name, "found.png")
        b = D.basis(self.n)
        e = np.stack([b @ np.array(sh[c * 9:(c + 1) * 9]) for c in range(3)], -1)
        save(found, to_srgb(np.clip(self.photo / np.maximum(e, 0.05) * 0.5, 0, 1)))
        tie = D.shading_left(self.tex, found, self.fac, sh)
        self.assertGreater(tie["photographed"], 0.5)
        self.assertLess(abs(tie["delit"]), 0.1)


if __name__ == "__main__":
    unittest.main()
