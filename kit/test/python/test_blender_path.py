"""test_blender_path.py — unit tests for kit/blender_path.py.

Tests the resolution order (KIT_BLENDER → BLENDER → the OS's install folders → PATH, as kit/lib/run.luau) and
each OS branch by monkeypatching env, shutil.which, sys.platform, and os.path.isfile.
No real Blender installation is required."""

import importlib
import os
import sys
import unittest
from unittest import mock

# Ensure kit/ is on the path so blender_path can be imported directly.
HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.abspath(os.path.join(HERE, "..", ".."))
if KIT not in sys.path:
    sys.path.insert(0, KIT)

import blender_path as BP  # noqa: E402

FAKE_HOME = "/home/testuser"


def _reload():
    importlib.reload(BP)
    return BP


def _base_patches(env=None, which_ret=None, isfile_side=None, glob_side=None, platform="win32"):
    """Return a list of context managers that fully isolate blender_path discovery."""
    def fake_isfile(p):
        return isfile_side(p) if isfile_side else False

    def fake_glob(pattern):
        return glob_side(pattern) if glob_side else []

    return [
        mock.patch.dict(os.environ, env or {}, clear=True),
        mock.patch("shutil.which", return_value=which_ret),
        mock.patch("os.path.isfile", side_effect=fake_isfile),
        mock.patch("blender_path.glob.glob", side_effect=fake_glob),
        mock.patch("blender_path.os.path.expanduser", side_effect=lambda p: p.replace("~", FAKE_HOME)),
        mock.patch.object(sys, "platform", platform),
    ]


class _Ctx:
    """Enter/exit a list of context managers."""
    def __init__(self, patches):
        self._patches = patches
        self._cms = []

    def __enter__(self):
        for p in self._patches:
            self._cms.append(p.__enter__())
        return self

    def __exit__(self, *args):
        for p, cm in zip(self._patches, self._cms):
            p.__exit__(*args)


class TestResolutionOrder(unittest.TestCase):
    """KIT_BLENDER → BLENDER → the OS's install folders → PATH → None."""

    def _run(self, env, which_ret=None, isfile_side=None, platform="win32"):
        with _Ctx(_base_patches(env, which_ret, isfile_side, platform=platform)):
            _reload()
            return BP.find_blender()

    def test_kit_blender_wins(self):
        result = self._run(
            {"KIT_BLENDER": "/fake/blender", "BLENDER": "/other/blender"},
            isfile_side=lambda p: p == "/fake/blender",
        )
        self.assertEqual(result, "/fake/blender")

    def test_blender_env_wins_over_path(self):
        result = self._run(
            {"BLENDER": "/env/blender"},
            which_ret="/path/blender",
            isfile_side=lambda p: p == "/env/blender",
        )
        self.assertEqual(result, "/env/blender")

    def test_an_installed_blender_wins_over_the_path(self):
        # (an old Blender on the PATH must not win over the installed one the Luau commands use)
        result = self._run(
            {},
            which_ret="/old/blender",
            isfile_side=lambda p: p == "/usr/bin/blender",
            platform="linux",
        )
        self.assertEqual(result, "/usr/bin/blender")

    def test_the_path_is_the_fallback(self):
        result = self._run(
            {},
            which_ret="/path/blender",
            isfile_side=lambda p: False,
        )
        self.assertEqual(result, "/path/blender")

    def test_returns_none_when_nothing_found(self):
        result = self._run(
            {},
            which_ret=None,
            isfile_side=lambda p: False,
        )
        self.assertIsNone(result)

    def test_kit_blender_missing_file_skipped(self):
        # KIT_BLENDER set but file absent → falls through to BLENDER
        result = self._run(
            {"KIT_BLENDER": "/missing/blender", "BLENDER": "/env/blender"},
            isfile_side=lambda p: p == "/env/blender",
        )
        self.assertEqual(result, "/env/blender")


class TestWindowsScan(unittest.TestCase):
    """Windows Program Files glob, newest version first."""

    def test_picks_newest_version(self):
        candidates = [
            "C:/Program Files/Blender Foundation/Blender 4.2/blender.exe",
            "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe",
            "C:/Program Files/Blender Foundation/Blender 3.6/blender.exe",
        ]

        def fake_glob(pattern):
            if "Program Files" in pattern:
                return candidates
            return []

        with _Ctx(_base_patches(glob_side=fake_glob, platform="win32")):
            _reload()
            result = BP.find_blender()
        # 5.2 > 4.2 > 3.6
        self.assertEqual(result, "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe")

    def test_a_version_tie_goes_to_the_plainer_name_and_numbers_compare_as_numbers(self):
        # (the same rule as kit/lib/run.luau: 5.10 after 5.2; "Blender 5.10" before "Blender 5.10 Alpha")
        candidates = [
            "C:/Program Files/Blender Foundation/Blender 5.10 Alpha/blender.exe",
            "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe",
            "C:/Program Files/Blender Foundation/Blender 5.10/blender.exe",
        ]

        def fake_glob(pattern):
            return candidates if "Program Files" in pattern else []

        with _Ctx(_base_patches(glob_side=fake_glob, platform="win32")):
            _reload()
            result = BP.find_blender()
        self.assertEqual(result, "C:/Program Files/Blender Foundation/Blender 5.10/blender.exe")

    def test_localappdata_fallback(self):
        local = f"{FAKE_HOME}/AppData/Local/Programs/Blender Foundation/Blender 5.1/blender.exe"

        def fake_glob(pattern):
            if "Local" in pattern or "AppData" in pattern:
                return [local]
            return []

        with _Ctx(_base_patches(glob_side=fake_glob, platform="win32")):
            _reload()
            result = BP.find_blender()
        self.assertEqual(result, local)


class TestMacOSScan(unittest.TestCase):
    def test_applications_first(self):
        SYS_PATH = "/Applications/Blender.app/Contents/MacOS/Blender"
        USER_PATH = f"{FAKE_HOME}/Applications/Blender.app/Contents/MacOS/Blender"

        with _Ctx(_base_patches(isfile_side=lambda p: p == SYS_PATH, platform="darwin")):
            _reload()
            result = BP.find_blender()
        self.assertEqual(result, SYS_PATH)

    def test_user_applications_fallback(self):
        USER_PATH = f"{FAKE_HOME}/Applications/Blender.app/Contents/MacOS/Blender"

        with _Ctx(_base_patches(isfile_side=lambda p: p == USER_PATH, platform="darwin")):
            _reload()
            result = BP.find_blender()
        self.assertEqual(result, USER_PATH)


class TestLinuxScan(unittest.TestCase):
    def test_usr_bin_first(self):
        with _Ctx(_base_patches(
            isfile_side=lambda p: p in ("/usr/bin/blender", "/opt/blender5/blender"),
            platform="linux",
        )):
            _reload()
            result = BP.find_blender()
        self.assertEqual(result, "/usr/bin/blender")

    def test_opt_blender_glob(self):
        def fake_glob(pattern):
            if "opt" in pattern:
                return ["/opt/blender4/blender", "/opt/blender5/blender"]
            return []

        with _Ctx(_base_patches(glob_side=fake_glob, platform="linux")):
            _reload()
            result = BP.find_blender()
        # /opt/blender5 > /opt/blender4 (by directory name, lexically)
        self.assertEqual(result, "/opt/blender5/blender")


if __name__ == "__main__":
    unittest.main()
