"""kit design explore (kit/tools/design.py) - the pure parts of the silhouette exploration: a long rod reads as long,
a disc as solid and readable, a thin comb as open and harder to read at 32 px; a silhouette cut by the frame is never
shown; one that reads like a past piece scores down hard; MAP-Elites keeps the best candidate of each kind; the
direction doc's directions and the prompt carry the axes and the maker's language."""

import os
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
import design  # noqa: E402


def canvas():
    return np.zeros((400, 600), bool)


def test_traits_of_a_rod_a_disc_and_a_comb():
    rod = canvas()
    rod[190:210, 50:550] = True
    disc = canvas()
    yy, xx = np.mgrid[:400, :600]
    disc[(yy - 200) ** 2 + (xx - 300) ** 2 < 120 ** 2] = True
    comb = canvas()
    comb[150:170, 100:500] = True
    for x in range(100, 500, 24):
        comb[170:300, x:x + 4] = True
    r, d, c = design.describe(rod), design.describe(disc), design.describe(comb)
    assert r["aspect"] > 20 and d["aspect"] < 1.05
    assert d["solidity"] > 0.97 and c["solidity"] < 0.5
    assert d["read"] > 0.95 and c["read"] < d["read"]
    assert not d["touches_frame"]
    assert design.cell_of(r)[0] == "2" and design.cell_of(d) == "02"


def test_quality_refuses_cut_off_and_copies():
    base = {"read": 0.9, "touches_frame": False, "fill": 0.1}
    assert design.quality({**base, "touches_frame": True}) == 0.0
    assert design.quality({**base, "novelty": 0.30}) > design.quality({**base, "novelty": None})
    assert design.quality({**base, "novelty": 0.03}) < 0.1 * design.quality({**base, "novelty": 0.30})


def test_grid_bins_spread_a_family_over_the_grid():
    cands = [{"aspect": 1.4 + 0.05 * i, "solidity": 0.70 + 0.01 * (i % 7)} for i in range(12)]
    bins = design.grid_bins(cands)
    cells = {design.cell_of(c, bins) for c in cands}
    assert len(cells) >= 5      # (fixed bins would put all twelve in one cell)
    assert len({design.cell_of(c) for c in cands}) <= 2


def test_elites_keep_the_best_of_each_kind():
    cands = [{"cell": "00", "quality": 0.5, "id": 1}, {"cell": "00", "quality": 0.8, "id": 2},
             {"cell": "12", "quality": 0.6, "id": 3}, {"cell": "21", "quality": 0.0, "id": 4}]
    got = design.elites(cands)
    assert [c["id"] for c in got] == [2, 3]


DOC = """# Clockbow - direction

## The one idea
A crossbow that winds like a music box.

## Directions
### A - Courtly
Axes: maker=brightwind; era=1890s; shape=round; material=brass; mood=elegant
Draw: a small brass crossbow with a music-box drum under its stock
Sheet: direction/Clockbow_A.png

### B - Workshop
Axes: maker=ironhall; era=1850s; shape=square; material=iron; mood=sturdy
Sheet: direction/Clockbow_B.png
"""


def test_directions_and_prompt():
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "Clockbow.md")
        open(p, "w", encoding="utf-8").write(DOC)
        idea, dirs = design.direction_blocks(p)
        assert idea.startswith("A crossbow")
        assert [d["letter"] for d in dirs] == ["A", "B"] and dirs[0]["axes"]["shape"] == "round"
        mk = {"primary": "round", "secondary": "blade", "motif": ["a whiplash curve"], "edge_rule": "round",
              "materials": ["brass — polished", "lacquer — green"]}
        pr = design.explore_prompt(idea, dirs[0], mk)
        for word in ("brass round-formed", "brightwind", "1890s", "whiplash curve", "side view",
                     "a small brass crossbow with a music-box drum"):
            assert word in pr, (word, pr)
        assert "muzzle" not in pr and "fire" not in pr and "no " not in pr   # (named, even after "no", it is drawn)
        assert dirs[1]["draw"] is None and "A crossbow that winds" in design.explore_prompt(idea, dirs[1])
        assert design.doc_view(p) == "side"
        assert "a clean front view" in design.explore_prompt(idea, dirs[0], mk, "front")
        open(p, "w", encoding="utf-8").write(DOC.replace("# Clockbow - direction", "# Clockbow - direction\n\nView: front."))
        assert design.doc_view(p) == "front"
