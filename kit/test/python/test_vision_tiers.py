"""kit/vision/setup.py's HARDWARE TIERS (the release blueprint's Part III): every models.json entry names its tier; a bare
`kit vision setup` fetches only the lightweight core (~2.4 GB, not every model); each tier includes the ones below it;
the on_demand extras come only with --tier all or by name; a gated model a TIER would fetch is skipped with a note (only
a model named outright fails without its token); a build for another OS is skipped there; an unknown tier is refused."""
import importlib.util
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
# (loaded under its own name: another "setup" module in the same test run must never be the one imported)
_spec = importlib.util.spec_from_file_location("kit_vision_setup", os.path.join(ROOT, "kit", "vision", "setup.py"))
vsetup = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vsetup)

with open(os.path.join(ROOT, "kit", "vision", "models.json"), encoding="utf-8") as fh:
    MAN = json.load(fh)
CORE6 = {"sam2.1-hiera-small", "depth-anything-v2-small", "birefnet", "teed", "siglip2-base", "dinov2-reg-small"}


def size(names):
    return sum(f["size"] for n in names for f in MAN["models"][n]["files"])


def run(argv, env):
    out = io.StringIO()
    with mock.patch.dict(os.environ, env), redirect_stdout(out):
        code = vsetup.main(argv)
    lines = out.getvalue().strip().splitlines()
    return code, json.loads(lines[-1]), lines


class Tiers(unittest.TestCase):
    def test_every_entry_has_a_tier_and_the_dead_entry_is_gone(self):
        for name, m in MAN["models"].items():
            self.assertIn(m.get("tier"), vsetup.TIERS, name)
        self.assertNotIn("geocalib-pinhole", MAN["models"])
        self.assertEqual(MAN["models"]["qwen3-vl-4b"]["tier"], "vision")  # (the local VLM is no longer a default)

    def test_the_default_is_the_light_core_and_each_tier_includes_the_ones_below(self):
        core, _ = vsetup.selected(MAN, "core", [])
        vision, _ = vsetup.selected(MAN, "vision", [])
        gen, _ = vsetup.selected(MAN, "gen", [])
        self.assertTrue(CORE6 <= set(core))
        self.assertLess(size(core), 3.0e9)  # (~2.4 GB, never the old 47 GB default)
        self.assertTrue(set(core) < set(vision) and set(vision) <= set(gen))
        self.assertNotIn("qwen3-vl-4b", core)
        self.assertIn("qwen3-vl-4b", vision)
        self.assertNotIn("clap-general", gen)  # (an on_demand extra: only --tier all or by name)
        everything, _ = vsetup.selected(MAN, "all", [])
        self.assertIn("clap-general", everything)
        self.assertEqual(vsetup.selected(MAN, "core", ["clap-general"])[0], ["clap-general"])

    def test_a_build_for_another_os_is_skipped_with_a_note(self):
        with mock.patch.object(vsetup, "OS_NAME", "linux"):
            names, notes = vsetup.selected(MAN, "gen", [])
        self.assertNotIn("sd-cpp", names)
        self.assertTrue(any(n.startswith("sd-cpp:") for n in notes))
        with mock.patch.object(vsetup, "OS_NAME", "windows"):
            self.assertIn("sd-cpp", vsetup.selected(MAN, "gen", [])[0])

    def test_a_gated_model_is_skipped_by_a_tier_but_fails_when_named(self):
        with tempfile.TemporaryDirectory() as empty:
            env = {"KIT_MODELS": empty, "KIT_TOOLS": empty, "HF_TOKEN": ""}
            _code, res, _lines = run(["--check", "--quick", "--tier", "vision"], env)
            self.assertTrue(any(s.startswith("sam3:") for s in res["skipped"]))
            self.assertFalse(any(m.startswith("sam3/") for m in res["missing"] + res["bad"]))
            _code, named, _lines = run(["--check", "--quick", "sam3"], env)
            self.assertTrue(any(m.startswith("sam3/") for m in named["missing"]))

    def test_an_empty_cache_fails_the_check_and_an_unknown_tier_is_refused(self):
        with tempfile.TemporaryDirectory() as empty:
            env = {"KIT_MODELS": empty, "KIT_TOOLS": empty}
            code, res, _lines = run(["--check", "--quick"], env)
            self.assertEqual(code, 1)
            self.assertEqual(res["tier"], "core")
            self.assertTrue(res["missing"])
            code, res, _lines = run(["--tier", "huge"], env)
            self.assertEqual(code, 1)
            self.assertIn("unknown tier", res["summary"])


if __name__ == "__main__":
    unittest.main()
