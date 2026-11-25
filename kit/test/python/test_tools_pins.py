"""kit/tools/pins: exactly the owner-approved wheels (2026-10-06, VETLOG.md), each with a sha256 — and the reader
refuses a line without one (pip's --require-hashes would too, but later and less plainly)."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tools"))

import tools  # noqa: E402

APPROVED = {
    "kit-python": {"vtracer": "0.6.15", "spandrel": "0.4.2"},
    "mitsuba": {"mitsuba": "3.9.1", "drjit": "1.5.0"},
    "cad": {"build123d": "0.13.0", "cadquery-ocp-novtk": "8.0.1.0.0",
            # build123d's own dependencies, approved by the owner 2026-10-07 (VETLOG.md)
            "svgpathtools": "1.8.0", "anytree": "2.13.0", "ezdxf": "1.4.4", "ocpsvg": "0.7.0", "ocp-gordon": "0.3.1",
            "trianglesolver": "1.2", "webcolors": "24.8.0", "lib3mf": "2.5.0", "bd-materials": "0.2.4",
            "threejs-materials": "1.2.4", "cadquery-ocp-proxy": "8.0.1.0.0", "svgwrite": "1.4.3", "svgelements": "1.9.6",
            "pygltflib": "1.16.5", "platformdirs": "4.12.3", "dataclasses-json": "0.6.7", "deprecated": "1.3.1",
            "marshmallow": "3.26.2", "typing-inspect": "0.9.0", "wrapt": "2.5.0", "mypy-extensions": "1.1.0",
            # the build123d parts library (screws, nuts, threads): the owner approved the plan naming it, 2026-10-07
            # ("we'll do it all — let's set up what we need first"); vetted in VETLOG.md
            "bd-warehouse": "0.3.0"},
}


class TestPins(unittest.TestCase):
    def test_every_environment_pins_exactly_the_approved_versions(self):
        self.assertEqual(set(tools.ENVS), set(APPROVED))
        for env, want in APPROVED.items():
            self.assertEqual(tools.pins(env), want, env)

    def test_every_tool_names_a_pinned_package_of_its_environment(self):
        for t in tools.TOOLS:
            pinned = tools.pins(t["env"])
            for p in t["packages"]:
                self.assertIn(tools.canon(p), pinned, t["name"])

    def test_a_line_without_a_hash_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "pins"))
            with open(os.path.join(tmp, "pins", "x.txt"), "w", encoding="utf-8") as fh:
                fh.write("# a comment\n\nvtracer==0.6.15\n")
            here, tools.HERE = tools.HERE, tmp
            try:
                with self.assertRaises(ValueError):
                    tools.pins("x")
            finally:
                tools.HERE = here

    def test_names_compare_as_pip_does(self):
        self.assertEqual(tools.canon("cadquery_ocp_novtk"), "cadquery-ocp-novtk")
        self.assertEqual(tools.canon("Typing.Extensions"), "typing-extensions")


if __name__ == "__main__":
    unittest.main()
