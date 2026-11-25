"""kit/anim/ab_picks.py - blind A/B (AAA gaps v2 F3): the page and the gifs never name the versions before the pick"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import ab_picks as AB  # noqa: E402


def test_the_order_is_seeded_and_both_ways_happen():
    assert AB.order("A", "B", 7) == AB.order("A", "B", 7)
    seen = {AB.order("A", "B", s) for s in range(40)}
    assert seen == {("A", "B"), ("B", "A")}


def test_the_page_hides_the_names_outside_the_reveal_script(tmp_path):
    out = tmp_path / "ab.html"
    AB.page("KatanaOld", "KatanaNew", str(out))
    doc = out.read_text(encoding="utf-8")
    shown = re.sub(r"<script>.*?</script>", "", doc, flags=re.S)
    assert "KatanaOld" not in shown and "KatanaNew" not in shown          # nothing visible names them
    assert 'src="x.gif"' in shown and 'src="y.gif"' in shown
    assert '"X": "KatanaOld"' in doc and "--tag ab" in doc                 # revealed by the script after a pick
