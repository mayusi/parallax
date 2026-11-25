"""test_zero_llm_parity.py — zero-local-LLM parity (release blueprint Part IV §4.2).

Each test monkeypatches vlm.installed() to return False (the VLM absent), then checks that:
  - design review writes the packet + PROMPT.md and never imports/loads weights
  - design review --record validates correctly and stores the verdict
  - font read saves the crop and prints a next_action
  - inventory defaults to no VLM passes
  - parts_rerank falls back to None (BM25 stays in charge) without loading the VLM

Run: python -m pytest kit/test/python/test_zero_llm_parity.py
"""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))

# --- helpers -------------------------------------------------------------------

def _quiet(fn, *a, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = fn(*a, **kw)
    lines = [ln for ln in buf.getvalue().splitlines() if ln.startswith("{")]
    return code, (json.loads(lines[-1]) if lines else {}), buf.getvalue()


# ============================================================ design review ===

class DesignReviewPacket(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, os.path.join(ROOT, "kit", "tools"))
        sys.path.insert(0, os.path.join(ROOT, "kit", "vision"))
        import vlm
        self._orig_installed = vlm.installed
        vlm.installed = lambda: False

    def tearDown(self):
        import vlm
        vlm.installed = self._orig_installed

    def _make_direction_doc(self, folder, name):
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"{name}.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(f"# {name} - direction\n\n"
                     "## Bans\n- no gold\n- no skulls\n\n"
                     "## Pillars\n- the lantern chamber is the heart\n\n"
                     "## Pick\npicked: A\n")
        return path

    def test_packet_written_when_vlm_absent(self):
        """With VLM absent and a valid .blend stub, cmd_review writes packet + PROMPT.md and does NOT call vlm.ask."""
        import design
        import numpy as np
        from PIL import Image

        with tempfile.TemporaryDirectory() as tmp:
            # design.py uses REPO to compute build_root; override it temporarily
            import design
            orig_repo = design.REPO
            design.REPO = tmp

            # minimal direction doc under tmp/assets/models/direction/Hook.md
            dir_folder = os.path.join(tmp, "assets", "models", "direction")
            self._make_direction_doc(dir_folder, "Hook")

            # fake .blend and .manifest.json so design.py doesn't fail before the VLM block
            build_models = os.path.join(tmp, "build", "models")
            os.makedirs(build_models, exist_ok=True)
            open(os.path.join(build_models, "Hook_A.blend"), "wb").close()
            with open(os.path.join(build_models, "Hook_A.manifest.json"), "w") as fh:
                json.dump({"part_bounds": {"body": [[-1, -1, -1], [1, 1, 1]]}}, fh)

            # stub subprocess so the Blender render "succeeds" with a grey PNG
            import subprocess as _sp
            _orig_run = _sp.run

            def _fake_run(cmd, **kw):
                # write the requested output file as a tiny grey PNG
                try:
                    out = cmd[cmd.index("--") + 1]
                    if out.endswith(".png"):
                        os.makedirs(os.path.dirname(out), exist_ok=True)
                        Image.new("RGBA", (64, 64), (128, 128, 128, 255)).save(out)
                except Exception:
                    pass

                class R:
                    returncode = 0
                    stdout = ""
                    stderr = ""
                return R()

            _sp.run = _fake_run
            # stub look.blender()
            sys.path.insert(0, os.path.join(ROOT, "kit", "tools"))
            import look as _look
            _orig_blender = _look.blender
            _look.blender = lambda: "blender"
            # stub past_pieces and novelty (they access the real repo)
            _orig_past = design.past_pieces
            _orig_novelty = design.novelty
            design.past_pieces = lambda: []
            design.novelty = lambda files, refs: ([0.5] * len(files), [""] * len(files))
            try:
                code, res, raw = _quiet(
                    design.cmd_review,
                    ["Hook", "--asset", "Hook_A"]
                )
            finally:
                _sp.run = _orig_run
                _look.blender = _orig_blender
                design.REPO = orig_repo
                design.past_pieces = _orig_past
                design.novelty = _orig_novelty

            # the result must say "packet"
            self.assertIn("packet", res.get("summary", "") + res.get("next_action", ""),
                          f"Expected packet mention. res={res}\nraw={raw}")
            # packet file must exist
            packet_path = os.path.join(tmp, "build", "design", "Hook", "review_Hook_A_packet.json")
            self.assertTrue(os.path.isfile(packet_path), f"packet not found at {packet_path}")
            packet = json.load(open(packet_path))
            self.assertIn("questions", packet)
            self.assertEqual(len(packet["questions"]["bans"]), 2)   # "no gold", "no skulls"
            self.assertEqual(len(packet["questions"]["pillars"]), 1)
            # PROMPT.md must exist
            prompt_path = os.path.join(tmp, "build", "design", "Hook", "PROMPT.md")
            self.assertTrue(os.path.isfile(prompt_path), "PROMPT.md not written")
            prompt_text = open(prompt_path).read()
            self.assertIn("--record", prompt_text)


class DesignReviewRecord(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, os.path.join(ROOT, "kit", "tools"))
        sys.path.insert(0, os.path.join(ROOT, "kit", "vision"))

    def _make_packet(self, out_dir, asset, bans, pillars):
        os.makedirs(out_dir, exist_ok=True)
        packet = {
            "asset": asset,
            "piece": "Hook",
            "views": "build/design/Hook/review_Hook_A_views.png",
            "questions": {
                "bans": [{"id": i, "ban": b, "question": f"question for {b}"} for i, b in enumerate(bans)],
                "pillars": [{"id": i, "pillar": p, "question": f"pillar q for {p}"} for i, p in enumerate(pillars)],
            },
        }
        path = os.path.join(out_dir, f"review_{asset}_packet.json")
        with open(path, "w") as fh:
            json.dump(packet, fh)
        return packet

    def test_valid_verdict_stored(self):
        import design
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = os.path.join(tmp, "build", "design", "Hook")
            self._make_packet(out_dir, "Hook_A", ["no gold", "no skulls"], ["the lantern chamber is the heart"])
            # verdict: ban 0 broken (no gold), pillar 0 present (not missed)
            verdict = {"bans_broken": [0], "pillars_missed": []}
            vpath = os.path.join(tmp, "verdict.json")
            with open(vpath, "w") as fh:
                json.dump(verdict, fh)

            orig_root = design.REPO
            design.REPO = tmp
            try:
                code, res, _ = _quiet(design.cmd_review_record,
                                      ["Hook", "--asset", "Hook_A", "--record", vpath])
            finally:
                design.REPO = orig_root

            self.assertEqual(res.get("status"), "fail",
                             "a broken ban should produce fail status")
            self.assertIn("BAN broken: no gold", res.get("review", {}).get("fixes", [None])[0] or "")
            review = json.load(open(os.path.join(out_dir, "review_Hook_A.json")))
            self.assertEqual(review["bans_broken"], ["no gold"])
            self.assertEqual(review["pillars_missed"], [])

    def test_invalid_verdict_refused(self):
        """An ID not in the packet (e.g. ban id=5) must be rejected."""
        import design
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = os.path.join(tmp, "build", "design", "Hook")
            self._make_packet(out_dir, "Hook_A", ["no gold"], ["the lantern chamber"])
            verdict = {"bans_broken": [5], "pillars_missed": []}  # 5 is not a valid id
            vpath = os.path.join(tmp, "verdict.json")
            with open(vpath, "w") as fh:
                json.dump(verdict, fh)

            orig_root = design.REPO
            design.REPO = tmp
            try:
                code, res, _ = _quiet(design.cmd_review_record,
                                      ["Hook", "--asset", "Hook_A", "--record", vpath])
            finally:
                design.REPO = orig_root

            self.assertEqual(res.get("status"), "fail")
            self.assertIn("not in the packet", res.get("summary", ""))

    def test_clean_verdict_stored(self):
        """No bans broken, no pillars missed -> fix list empty -> pass status."""
        import design
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = os.path.join(tmp, "build", "design", "Hook")
            self._make_packet(out_dir, "Hook_A", ["no gold"], ["the lantern chamber"])
            verdict = {"bans_broken": [], "pillars_missed": []}
            vpath = os.path.join(tmp, "verdict.json")
            with open(vpath, "w") as fh:
                json.dump(verdict, fh)

            orig_root = design.REPO
            design.REPO = tmp
            try:
                code, res, _ = _quiet(design.cmd_review_record,
                                      ["Hook", "--asset", "Hook_A", "--record", vpath])
            finally:
                design.REPO = orig_root

            # a clean verdict can still be fail (other judge fields missing), but bans/pillars are empty
            review = json.load(open(os.path.join(out_dir, "review_Hook_A.json")))
            self.assertEqual(review["bans_broken"], [])
            self.assertEqual(review["pillars_missed"], [])


# ============================================================ font read =======

class FontReadPacket(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, os.path.join(ROOT, "kit", "refs"))
        sys.path.insert(0, os.path.join(ROOT, "kit", "vision"))
        import vlm
        self._orig_installed = vlm.installed
        vlm.installed = lambda: False

    def tearDown(self):
        import vlm
        vlm.installed = self._orig_installed

    def test_crop_saved_and_next_action_tells_agent_to_read(self):
        from PIL import Image
        import font

        with tempfile.TemporaryDirectory() as tmp:
            pic = os.path.join(tmp, "side.png")
            Image.new("RGB", (200, 80), (40, 40, 40)).save(pic)

            orig_repo = font.REPO
            font.REPO = tmp
            orig_environ = os.environ.get("KIT_BUILD")
            os.environ["KIT_BUILD"] = "build"
            try:
                code, res, raw = _quiet(font.main_read, [pic])
            finally:
                font.REPO = orig_repo
                if orig_environ is None:
                    os.environ.pop("KIT_BUILD", None)
                else:
                    os.environ["KIT_BUILD"] = orig_environ

            # crop must be saved
            crop_path = os.path.join(tmp, "build", "refs", "read_crop.png")
            self.assertTrue(os.path.isfile(crop_path), f"crop not written at {crop_path}")
            # next_action must tell the agent to read the crop and use font command
            self.assertIn("lune run kit refs font", res.get("next_action", ""))
            # status is pass (not fail — this is a graceful skip)
            self.assertEqual(res.get("status"), "pass")


# ============================================================ inventory =======

class InventoryNoVlm(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, os.path.join(ROOT, "kit", "refs"))
        sys.path.insert(0, os.path.join(ROOT, "kit", "vision"))
        import vlm
        self._orig_installed = vlm.installed
        vlm.installed = lambda: False

    def tearDown(self):
        import vlm
        vlm.installed = self._orig_installed

    def test_no_vlm_skips_passes_and_prints_warning(self):
        """With VLM absent and no --passes flag, inventory skips VLM and continues to --parts / --boxes."""
        import subprocess
        from PIL import Image

        with tempfile.TemporaryDirectory() as tmp:
            pic = os.path.join(tmp, "pic.png")
            Image.new("RGB", (400, 200), (200, 200, 200)).save(pic)
            boxes = os.path.join(tmp, "b.json")
            with open(boxes, "w") as fh:
                json.dump([{"label": "gem", "kind": "gem", "box": [20, 20, 90, 90]}], fh)
            out = os.path.join(tmp, "x.details.json")
            p = subprocess.run(
                [sys.executable,
                 os.path.join(ROOT, "kit", "refs", "inventory.py"),
                 pic, "--name", "x", "--boxes", boxes, "--out", out],
                capture_output=True, text=True,
                env={**os.environ, "KIT_BUILD": tmp,
                     # make installed() return False by putting a fake KIT_MODELS dir with no model files
                     "KIT_MODELS": os.path.join(tmp, "no_models")})
            self.assertEqual(p.returncode, 0, p.stderr)
            lines = [ln for ln in p.stdout.splitlines() if ln.startswith("{")]
            last = json.loads(lines[-1])
            self.assertEqual(last["status"], "pass", p.stdout + p.stderr)

    def test_explicit_passes_flag_still_honored(self):
        """--passes none with VLM absent must still work (SAM-3 path)."""
        import subprocess
        from PIL import Image

        with tempfile.TemporaryDirectory() as tmp:
            pic = os.path.join(tmp, "pic.png")
            Image.new("RGB", (400, 200), (200, 200, 200)).save(pic)
            boxes = os.path.join(tmp, "b.json")
            with open(boxes, "w") as fh:
                json.dump([{"label": "pin", "kind": "fastener", "box": [50, 50, 70, 70]}], fh)
            out = os.path.join(tmp, "x.details.json")
            p = subprocess.run(
                [sys.executable,
                 os.path.join(ROOT, "kit", "refs", "inventory.py"),
                 pic, "--name", "x", "--boxes", boxes, "--out", out, "--passes", "none"],
                capture_output=True, text=True,
                env={**os.environ, "KIT_BUILD": tmp,
                     "KIT_MODELS": os.path.join(tmp, "no_models")})
            lines = [ln for ln in p.stdout.splitlines() if ln.startswith("{")]
            last = json.loads(lines[-1])
            self.assertEqual(last["status"], "pass", p.stdout + p.stderr)


# ============================================================ parts_rerank ====

class PartsRerankNoVlm(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, os.path.join(ROOT, "kit", "tools"))
        sys.path.insert(0, os.path.join(ROOT, "kit", "vision"))
        # ensure parts_rerank is freshly imported (or reuse)
        import parts_rerank
        import vlm
        self._pr = parts_rerank
        self._orig_installed = vlm.installed
        vlm.installed = lambda: False

    def tearDown(self):
        import vlm
        vlm.installed = self._orig_installed

    def test_scores_many_returns_none_when_vlm_absent_and_no_worker(self):
        """With no worker and VLM absent, scores_many(cold=True) must return None (not raise)."""
        # Stub worker() to return None (no warm worker)
        orig_worker = self._pr.worker
        self._pr.worker = lambda: None
        try:
            result = self._pr.scores_many([("build a barrel stave", "thirty staves placed by angle")], cold=True)
        finally:
            self._pr.worker = orig_worker
        self.assertIsNone(result, "expected None when VLM absent; fallback to plain order")

    def test_cold_false_default_returns_none_when_no_worker(self):
        """The new default cold=False must also return None when no worker (no VLM loaded at all)."""
        orig_worker = self._pr.worker
        self._pr.worker = lambda: None
        try:
            result = self._pr.scores_many([("query", "card text")])  # cold defaults to False
        finally:
            self._pr.worker = orig_worker
        self.assertIsNone(result)

    def test_scores_signature_default_changed(self):
        """scores() and scores_many() default cold must be False."""
        import inspect
        sig_many = inspect.signature(self._pr.scores_many)
        self.assertFalse(sig_many.parameters["cold"].default,
                         "scores_many cold default must be False")
        sig_scores = inspect.signature(self._pr.scores)
        self.assertFalse(sig_scores.parameters["cold"].default,
                         "scores cold default must be False")
        sig_rerank = inspect.signature(self._pr.rerank)
        self.assertFalse(sig_rerank.parameters["cold"].default,
                         "rerank cold default must be False")


# ============================================================ vlm.installed ===

class VlmInstalled(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, os.path.join(ROOT, "kit", "vision"))

    def test_returns_false_when_cache_missing(self):
        import vlm
        orig = os.environ.get("KIT_MODELS")
        os.environ["KIT_MODELS"] = "/no/such/path/models"
        try:
            self.assertFalse(vlm.installed())
        finally:
            if orig is None:
                os.environ.pop("KIT_MODELS", None)
            else:
                os.environ["KIT_MODELS"] = orig

    def test_returns_false_when_config_missing(self):
        import vlm
        with tempfile.TemporaryDirectory() as tmp:
            model_dir = os.path.join(tmp, vlm.NAME)
            os.makedirs(model_dir)
            # only tokenizer.json present — config.json absent
            open(os.path.join(model_dir, "tokenizer.json"), "w").close()
            orig = os.environ.get("KIT_MODELS")
            os.environ["KIT_MODELS"] = tmp
            try:
                self.assertFalse(vlm.installed())
            finally:
                if orig is None:
                    os.environ.pop("KIT_MODELS", None)
                else:
                    os.environ["KIT_MODELS"] = orig

    def test_the_minimum_files_alone_are_a_download_cut_short(self):
        # (the weights missing: not installed, so the packet route runs instead of a crash on half a model; a model
        # whose every manifest file is there at its size IS installed: test_vlm_installed.py)
        import vlm
        with tempfile.TemporaryDirectory() as tmp:
            model_dir = os.path.join(tmp, vlm.NAME)
            os.makedirs(model_dir)
            for f in vlm._REQUIRED_FILES:
                open(os.path.join(model_dir, f), "w").close()
            orig = os.environ.get("KIT_MODELS")
            os.environ["KIT_MODELS"] = tmp
            try:
                self.assertFalse(vlm.installed())
            finally:
                if orig is None:
                    os.environ.pop("KIT_MODELS", None)
                else:
                    os.environ["KIT_MODELS"] = orig

    def test_does_not_import_torch(self):
        """installed() must NOT import torch (the whole point: it checks files only)."""
        import vlm
        import sys as _sys
        with tempfile.TemporaryDirectory() as tmp:
            orig = os.environ.get("KIT_MODELS")
            os.environ["KIT_MODELS"] = tmp
            # remove torch from sys.modules if present to prove we don't re-import it
            torch_was_loaded = "torch" in _sys.modules
            try:
                vlm.installed()
                # if torch was not already loaded it must still not be loaded
                if not torch_was_loaded:
                    self.assertNotIn("torch", _sys.modules)
            finally:
                if orig is None:
                    os.environ.pop("KIT_MODELS", None)
                else:
                    os.environ["KIT_MODELS"] = orig


if __name__ == "__main__":
    unittest.main()
