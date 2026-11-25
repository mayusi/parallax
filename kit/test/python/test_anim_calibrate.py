"""kit/anim/calibrate.py: only the owner's OWN loved score teaches a range; a range widens just enough (+10 %, one frame
for a time) to hold a loved value and never narrows"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "anim"))
import calibrate as CAL  # noqa: E402


def note(folder, fname, **front):
    body = "---\n" + "\n".join(f"{k}: {v}" for k, v in front.items()) + "\n---\n"
    (folder / fname).write_text(body, encoding="utf-8")


def test_only_the_owners_own_score_counts(tmp_path):
    note(tmp_path, "a--2026-10-24.md", name="ClipA", score="8.0", date="2026-10-24", by="owner", source="owner")
    note(tmp_path, "b--2026-10-24.md", name="ClipB", score="9.0", date="2026-10-24", by="owner", source="inferred")
    note(tmp_path, "c--2026-10-24.md", name="ClipC", score="9.0", date="2026-10-24", by="claude", source="owner")
    note(tmp_path, "a--2026-10-25.md", name="ClipA", score="6.0", date="2026-10-25", by="owner", source="owner")
    assert CAL.owner_score("ClipA", str(tmp_path))[0] == 6.0          # the LATEST of his own
    assert CAL.owner_score("ClipB", str(tmp_path)) is None            # inferred, no word of his
    assert CAL.owner_score("ClipC", str(tmp_path)) is None            # not by the owner
    note(tmp_path, "b--2026-10-26.md", name="ClipB", score="7.5", date="2026-10-26", by="owner", source="inferred", word="love")
    assert CAL.owner_score("ClipB", str(tmp_path))[0] == 7.5          # inferred number but his own word


def test_widen_holds_the_value_with_a_margin_and_never_narrows():
    assert CAL.widen([30, 57], 40, "torso_peak_deg") == [30.0, 57.0]
    lo, hi = CAL.widen([30, 57], 27.5, "torso_peak_deg")
    assert hi == 57 and abs(lo - 24.75) < 1e-6
    lo, hi = CAL.widen([-0.067, 0.15], 0.167, "torso_lag_s")
    assert lo == -0.067 and abs(hi - (0.167 + 1 / 60)) < 1e-3          # a time gets at least one frame of margin
