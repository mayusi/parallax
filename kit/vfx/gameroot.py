"""Where kit/vfx's Python tools read and write: the ACTIVE GAME's folder, as kit/lib/config.luau sees it.

kit/lib/config.luau puts every path of a game inside games/<Name>/ (Config.build("vfx") = games/<Name>/build/vfx), so
`kit vfx play` records a game's effect into games/<Name>/build/vfx/booth. The V0 to V2 tools (denseclip, dailies,
stylesheet, animatic) and the beat chart wrote the project's own build/vfx whatever game was active: a game's recording
got no dailies (or the dailies of a project recording of the same name) and `kit vfx animatic` wrote its preset where
the game's play command does not look (card t6rx, found 2026-11-12). One rule here, used by all of them.

Pure: no Windows calls (capture.py imports ctypes window APIs; this module is imported by tools that must run anywhere).
"""
import os


def active_game():
    """the game kit works in, as Config.game() reads it: KIT_GAME, else games/.active; None = the project root.
    A name with no folder (or "none") is the project root, like the Luau side."""
    g = os.environ.get("KIT_GAME")
    if not g:
        try:
            g = open(os.path.join("games", ".active"), encoding="utf-8").read().strip()
        except OSError:
            g = ""
    return g if g and g != "none" and os.path.isdir(os.path.join("games", g)) else None


def game_root():
    """'' for the project, games/<Name> for a game (no trailing separator)"""
    g = active_game()
    return os.path.join("games", g) if g else ""


def build(*parts):
    """Config.build(...) in Python: <game root>/build/<parts...>, forward slashes like the Luau side writes them"""
    return "/".join(p for p in (game_root().replace("\\", "/"), "build", *parts) if p)
