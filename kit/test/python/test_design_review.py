"""kit design review (kit/tools/design.py) - the pure parts of the director's review: bans become yes/no questions
(yes = broken), the fix list puts broken bans first, then a stray silhouette, missed pillars, unreadable outlines,
a copy of a past piece and a detail share far from the maker's; a clean build has no fixes."""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
import design  # noqa: E402


def test_ban_and_pillar_questions():
    assert design.ban_question("no gold (gold belongs to the Erdtree and Stormhold)") == \
        "Look at this object. Does it have gold? Answer only yes or no."
    assert design.ban_question("no glow of any kind") == "Look at this object. Does it have glow? Answer only yes or no."
    assert "the lantern chamber is the heart" in design.pillar_question("the lantern chamber is the heart.")
    assert design.pillar_question("x", views=3).startswith("These are views of one single object")
    assert design.yes("Yes.") and design.yes("**Yes**") and not design.yes("No") and not design.yes("")


def test_fix_list_order_and_a_clean_build():
    bad = {"bans_broken": ["no gold"], "silhouette_iou": 0.6, "pillars_missed": ["tide rings everywhere"],
           "read": 0.7, "novelty": 0.05, "nearest": "scarborough_fair.png", "detail_target": 30, "detail_share": 55}
    fixes = design.judge(bad)
    assert fixes[0].startswith("BAN broken: no gold")
    assert "silhouette" in fixes[1] and fixes[2].startswith("PILLAR missed (advisory")
    assert any("reads like a past piece (scarborough_fair.png" in x for x in fixes)
    assert any("too busy" in x for x in fixes)
    clean = {"bans_broken": [], "silhouette_iou": 0.9, "pillars_missed": [], "read": 0.92, "novelty": 0.3,
             "detail_target": 30, "detail_share": 34}
    assert design.judge(clean) == []


def test_a_makers_materials_against_the_docs_bans():
    gold_leaf = {"materials": ["pale ash wood — carved", "gold leaf — worn"], "motif": ["a leaf-blade line"]}
    bronze = {"materials": ["verdigris bronze — weathered", "frosted glass — panes"], "motif": ["stacked tide rings"]}
    bans = ["no gold (gold belongs to the Erdtree)", "no skulls or bones", "no tactical rails or modern parts"]
    assert design.ban_conflicts(bans, gold_leaf) == ["no gold (gold belongs to the Erdtree)"]
    assert design.ban_conflicts(bans, bronze) == []
    assert design.ban_conflicts(bans, None) == []


def test_the_build_answers_to_the_pick_not_the_directions_best():
    # the Sheet is the direction's BEST-scored plate; the pick may be another (the Lantern Hook: B's second) — the
    # pick's concept view wins when it exists, the doc's View naming which
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        folder = os.path.join(tmp, "direction")
        os.makedirs(folder)
        doc = os.path.join(folder, "Hook.md")
        with open(doc, "w", encoding="utf-8") as fh:
            fh.write("# Hook - direction\n\nView: side.\n")
        chosen = {"sheet": "direction/Hook_B.png"}
        assert design.review_target(folder, "Hook", doc, chosen) == os.path.join(tmp, "direction/Hook_B.png")
        open(os.path.join(folder, "Hook.side.png"), "wb").close()
        assert design.review_target(folder, "Hook", doc, chosen) == os.path.join(folder, "Hook.side.png")
        assert design.review_target(folder, "Other", doc, None) is None
