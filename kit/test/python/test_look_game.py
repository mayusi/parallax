"""kit look follows the active game (kit/tools/look.py game_build): --game <Name> > KIT_GAME > games/.active ->
games/<Name>/build; a KIT_BUILD the caller set wins; an unknown game falls back to the root's build"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
import look  # noqa: E402


def test_game_build(monkeypatch):
    monkeypatch.delenv("KIT_BUILD", raising=False)
    monkeypatch.delenv("KIT_GAME", raising=False)
    games = [g for g in os.listdir(os.path.join(look.REPO, "games")) if os.path.isdir(os.path.join(look.REPO, "games", g))]         if os.path.isdir(os.path.join(look.REPO, "games")) else []
    if not games:
        import pytest
        pytest.skip("no games/ in this project")
    g = games[0]
    assert look.game_build(["closeup", "x", "--game", g]) == os.path.join("games", g, "build")
    monkeypatch.setenv("KIT_GAME", g)
    assert look.game_build(["closeup", "x"]) == os.path.join("games", g, "build")
    assert look.game_build(["closeup", "x", "--game", "NoSuchGame"]) is None   # (a game named that does not exist: the root)
    monkeypatch.setenv("KIT_BUILD", "build")
    assert look.game_build(["closeup", "x", "--game", g]) is None
