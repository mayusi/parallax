"""kit gen --res 1024 (kit/gen/trellis2_run.py; the owner: "Yes, download it", 2026-11-19 - TRELLIS.2's 1024 networks):
1024 is the CASCADE (the 512 flow lays the shape, the 1024 flow refines it); without the 1024 networks on the PC a
--res 1024 run is refused with the fetch command; the pipeline config carries the 1024 networks only when they are
there; the fetcher's file list and the runner's are the same networks."""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "gen"))
import fetch as F  # noqa: E402
import trellis2_run as R  # noqa: E402

BASE = ["ss_flow_img_dit_1_3B_64_bf16", "slat_flow_img2shape_dit_1_3B_512_bf16",
        "slat_flow_imgshape2tex_dit_1_3B_512_bf16", "shape_dec_next_dc_f16c32_fp16", "tex_dec_next_dc_f16c32_fp16"]
MODELS = {"sparse_structure_decoder": "microsoft/TRELLIS-image-large/ckpts/ss_dec_conv3d_16l8_fp16",
          "sparse_structure_flow_model": "ckpts/ss_flow_img_dit_1_3B_64_bf16",
          "shape_slat_decoder": "ckpts/shape_dec_next_dc_f16c32_fp16",
          "shape_slat_flow_model_512": "ckpts/slat_flow_img2shape_dit_1_3B_512_bf16",
          "shape_slat_flow_model_1024": "ckpts/slat_flow_img2shape_dit_1_3B_1024_bf16",
          "tex_slat_decoder": "ckpts/tex_dec_next_dc_f16c32_fp16",
          "tex_slat_flow_model_512": "ckpts/slat_flow_imgshape2tex_dit_1_3B_512_bf16",
          "tex_slat_flow_model_1024": "ckpts/slat_flow_imgshape2tex_dit_1_3B_1024_bf16"}


def touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("{}")


class Res(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="kit_trellis_res_")
        self.was = R.WEIGHTS
        R.WEIGHTS = self.dir
        ck = os.path.join(self.dir, "TRELLIS.2-4B", "ckpts")
        for n in BASE:
            for e in ("json", "safetensors"):
                touch(os.path.join(ck, f"{n}.{e}"))
        for e in ("json", "safetensors"):
            touch(os.path.join(self.dir, "TRELLIS-image-large", "ckpts", f"ss_dec_conv3d_16l8_fp16.{e}"))
        with open(os.path.join(self.dir, "TRELLIS.2-4B", "pipeline.json"), "w", encoding="utf-8") as fh:
            json.dump({"args": {"models": MODELS, "image_cond_model": {"args": {}}}}, fh)

    def tearDown(self):
        R.WEIGHTS = self.was
        shutil.rmtree(self.dir, ignore_errors=True)

    def add_hi_res(self):
        for n in R.HI_RES:
            for e in ("json", "safetensors"):
                touch(os.path.join(self.dir, "TRELLIS.2-4B", "ckpts", f"{n}.{e}"))

    def models(self):
        base, name = R.pipeline_config()
        with open(os.path.join(base, name), encoding="utf-8") as fh:
            return json.load(fh)["args"]["models"]

    def test_1024_is_the_cascade(self):
        self.assertEqual(R.PIPELINES, {"512": "512", "1024": "1024_cascade"})

    def test_the_1024_networks_join_the_config_only_when_they_are_on_the_pc(self):
        self.assertFalse(R.hi_res_ready())
        self.assertNotIn("shape_slat_flow_model_1024", self.models())     # (left out, no error: a 512 run works)
        self.assertIn("shape_slat_flow_model_512", self.models())
        self.add_hi_res()
        self.assertTrue(R.hi_res_ready())
        m = self.models()
        self.assertTrue(m["shape_slat_flow_model_1024"].endswith("slat_flow_img2shape_dit_1_3B_1024_bf16"))
        self.assertTrue(m["tex_slat_flow_model_1024"].endswith("slat_flow_imgshape2tex_dit_1_3B_1024_bf16"))

    def test_half_a_set_is_not_ready(self):
        touch(os.path.join(self.dir, "TRELLIS.2-4B", "ckpts", f"{R.HI_RES[0]}.safetensors"))
        self.assertFalse(R.hi_res_ready())

    def run_main(self, *argv):
        pic = os.path.join(self.dir, "pic.png")
        touch(pic)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = R.main([pic, os.path.join(self.dir, "out.glb"), *argv])
        return code, json.loads(out.getvalue().strip().splitlines()[-1])

    def test_1024_without_its_networks_is_refused_with_the_fetch_command(self):
        code, said = self.run_main("--res", "1024")
        self.assertEqual((code, said["status"]), (1, "fail"))
        self.assertIn("1024 networks", said["summary"])
        self.assertIn("fetch.py --1024", said["next_action"])

    def test_an_unknown_resolution_is_refused(self):
        code, said = self.run_main("--res", "2048")
        self.assertEqual((code, said["status"]), (1, "fail"))
        self.assertIn("one of 512, 1024", said["summary"])

    def test_the_fetcher_fetches_what_the_runner_looks_for_at_the_512_sets_commit(self):
        names = F.HI_RES["microsoft/TRELLIS.2-4B"]
        self.assertEqual(sorted(names), sorted(f"ckpts/{n}.{e}" for n in R.HI_RES for e in ("json", "safetensors")))
        self.assertEqual(len(F.TRELLIS2_COMMIT), 40)
        self.assertNotIn("microsoft/TRELLIS.2-4B", {k for k in F.FILES if any("1024" in n for n in F.FILES[k])})


if __name__ == "__main__":
    unittest.main()
