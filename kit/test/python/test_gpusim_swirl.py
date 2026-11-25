"""kit/vfx/gpusim.py `swirl` (2026-10-25, firewhirl's simulated core): a Rankine vortex round the vertical axis. Measured,
the two terms pull against each other - the SPIN flings the column outward, the INFLOW (air drawn in below `height`)
pulls it back; their balance sets a whirl's width. The test pins both directions on a tiny grid (seconds; CUDA when
present - exact repeats - else the CPU, whose runs vary a little: ratios 2.4 / 0.15-0.33 against margins 1.5 / 0.7)."""
import importlib.util
import os
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")
try:
    import torch  # noqa: F401
    HAVE_TORCH = True
except ImportError:
    HAVE_TORCH = False


def load():
    spec = importlib.util.spec_from_file_location("vfx_gpusim", os.path.join(ROOT, "kit", "vfx", "gpusim.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@unittest.skipUnless(HAVE_TORCH, "torch is not installed")
class Swirl(unittest.TestCase):
    def spread(self, sw):
        g = load()
        p = {"res": [32, 32, 48], "steps": 60, "emitter": 0.12, "inflow_until": 0.9, "heat": 2.0, "velocity": 1.5,
             "turbulence": 0.0, "vorticity": 0.0, "pressure_iters": 20, "sheet_start": 0.0, "sheet_end": 1.0}
        if sw:
            p["swirl"] = sw
        frames = g.simulate({"recipe": "gpu_smoke", "frames": 4, "seed": 3, "params": p}, None)
        dens = frames[-1][0].float()
        Z, Y, X = dens.shape
        yy, xx = torch.meshgrid(torch.arange(Y, dtype=torch.float32), torch.arange(X, dtype=torch.float32), indexing="ij")
        r = torch.sqrt((xx - (X - 1) / 2) ** 2 + (yy - (Y - 1) / 2) ** 2)
        upper = dens[Z // 3:]  # the column above the source
        return float((upper * r).sum() / upper.sum().clamp(min=1e-6))

    def test_spin_flings_out_and_inflow_pulls_back(self):
        plain = self.spread(None)
        spin = self.spread({"strength": 2.0, "core": 0.08, "rise": 0.2, "inflow": 0.0, "height": 0.6})
        fed = self.spread({"strength": 2.0, "core": 0.08, "rise": 0.2, "inflow": 1.2, "height": 0.75})  # the same spin, fed
        self.assertGreater(spin, plain * 1.5, f"the spin alone widens the column: {spin:.2f} vs plain {plain:.2f}")
        self.assertLess(fed, spin * 0.7, f"the inflow pulls it back in: {fed:.2f} vs spin only {spin:.2f}")


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(HAVE_TORCH, "torch is not installed")
class Pacing(unittest.TestCase):
    def test_steps_per_frame_flags_a_fractional_stride(self):
        g = load()
        # skyfall's surge as first written: 200 steps over 0.04..0.62 for 64 frames = 1.8 a frame (alternating strides)
        self.assertLess(g.steps_per_frame({"steps": 200, "sheet_start": 0.04, "sheet_end": 0.62}, 64), 2)
        self.assertGreaterEqual(g.steps_per_frame({"steps": 270, "sheet_start": 0.09, "sheet_end": 0.62}, 64), 2)
        # the nuke's surge (fx finish green): 200 over 0.05..0.72
        self.assertGreaterEqual(g.steps_per_frame({"steps": 200, "sheet_start": 0.05, "sheet_end": 0.72}, 64), 2)
