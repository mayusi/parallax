"""build_game_settings_nogroup.py — twin of build_game_settings.py with the word `nogroup` (see its docstring for
what the build must say). Used by `lune run kit selftest`. Never "fix" this file."""

import os
import runpy
import sys

sys.argv.append("nogroup")
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_game_settings.py"),
               run_name="__main__")
