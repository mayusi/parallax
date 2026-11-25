"""kit/vfx/gpusim.py budget() - gpusim at 256^3 and up (LIMITATIONS_FIXES_V4 3.4 step 4). What is proven: the memory
model is the measured one (a small grid's REAL peak on this GPU stays under what budget() asks for), a grid that does
not fit the free GPU or host memory is refused before it runs and the largest cube that fits is named, and 256^3 is
within a 12 GB GPU.
Run: python -m pytest kit/test/python/test_gpusim_budget.py -q"""

import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "vfx"))
import gpusim as G  # noqa: E402

GiB = 2 ** 30


def spec(r, frames=64):
    return {"frames": frames, "params": {"res": [r, r, r]}}


class Budget(unittest.TestCase):
    def test_refuses_what_does_not_fit_and_names_the_cube(self):
        ok, why, cube = G.budget(spec(512), free_gpu=10 * GiB, free_host=64 * GiB)
        self.assertFalse(ok)
        self.assertIn("GPU memory", why)
        self.assertTrue(250 < cube < 512)
        ok, why, _ = G.budget(spec(384), free_gpu=11 * GiB, free_host=12 * GiB)
        self.assertFalse(ok)
        self.assertIn("host memory", why)
        ok, _, _ = G.budget(spec(384, frames=16), free_gpu=11 * GiB, free_host=12 * GiB)
        self.assertTrue(ok)                                      # fewer kept frames: it fits

    def test_256_cubed_fits_a_12gb_gpu(self):
        ok, why, _ = G.budget(spec(256), free_gpu=10 * GiB, free_host=12 * GiB)
        self.assertTrue(ok, why)

    @unittest.skipUnless(G.DEV == "cuda", "needs the CUDA GPU")
    def test_model_covers_the_real_peak(self):
        _tex = os.path.join(HERE, "..", "..", "..", "assets", "textures", "gpu_dust_puff.json")
        if not os.path.isfile(_tex):
            self.skipTest("the author's assets/textures/gpu_dust_puff.json is not shipped with the kit")
        import torch
        s = json.load(open(_tex, encoding="utf-8"))
        s["frames"] = 4
        s["params"]["res"] = [96, 96, 96]
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()
        base = torch.cuda.memory_allocated()
        G.simulate(s, None)
        peak = torch.cuda.max_memory_allocated() - base
        self.assertLess(peak, 96 ** 3 * G.GPU_BYTES_PER_CELL)
        self.assertGreater(peak, 0.5 * 96 ** 3 * G.GPU_BYTES_PER_CELL)   # and the model is not wildly loose


if __name__ == "__main__":
    unittest.main()
