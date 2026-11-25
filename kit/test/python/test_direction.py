"""kit/direction.py: the direction step - a doc is draft until complete, ready to show, picked only by the owner."""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import direction  # noqa: E402

GOOD = """# Keep — direction

## Intent
The player should feel small and watched as they climb toward the keep, then curious about what broke it open; the
place is old, sacred and dangerous at once, and every surface carries the history of the people who held it and the
thing that is now taking it back from them.

## The one idea
The keep was built around a living root that is breaking it open from within.

## References
- Photo of Ta Prohm (photography) — take: roots lifting blocks — leave: jungle green
- Mont-Saint-Michel (photography) — take: stacked climb — leave: the sea
- Carcassonne (architecture) — take: crenel rhythm — leave: restored look
- Friedrich, Abbey in the Oakwood (painting) — take: ruin against light — leave: winter
- Anor Londo (game) — take: gold side light — leave: spires
- Tournus abbey (architecture) — take: round arches — leave: interior scale

## Pillars
- The tree is in the stone
- Layers of history
- Read far, reward near

## Bans
- No clean theme-park castle
- No gothic spires
- No green jungle

## Directions
### A — Golden age
Feeling: awe. Risk: clean.
Axes: state=intact; light=low sun; palette=warm; mood=awe
Frame: direction/Keep_A.png

### B — Siege
Feeling: dread. Risk: generic.
Axes: state=breached; light=overcast; palette=soot; mood=dread
Frame: direction/Keep_B.png

### C — The root
Feeling: sacred. Risk: none yet.
Axes: state=broken by a root; light=backlit; palette=gold; mood=uncanny
Frame: direction/Keep_C.png

## Pick
pending
"""


class Direction(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.dir, "direction"))
        for k in "ABC":
            open(os.path.join(self.dir, "direction", f"Keep_{k}.png"), "wb").close()
        self.doc = os.path.join(self.dir, "direction", "Keep.md")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def write(self, text):
        open(self.doc, "w", encoding="utf-8").write(text)

    def test_a_complete_doc_is_ready_to_show_not_picked(self):
        self.write(GOOD)
        status, probs, info = direction.check(self.doc, "world")
        self.assertEqual((status, probs), ("ready", []))
        self.assertEqual(info["directions"], ["A", "B", "C"])

    def test_only_the_owners_words_make_it_picked(self):
        self.write(GOOD.replace("pending", 'picked: C by owner — "the root one, go"'))
        self.assertEqual(direction.check(self.doc, "world")[0], "picked")

    def test_the_template_is_a_draft(self):
        os.remove(self.doc) if os.path.isfile(self.doc) else None
        self.assertEqual(direction.main(["new", self.doc, "--lane", "world", "--name", "Keep"]), 0)
        status, probs, _ = direction.check(self.doc, "world")
        self.assertEqual(status, "draft")
        self.assertIn("TODO left in the doc", probs)

    def test_thin_direction_is_caught(self):
        thin = GOOD.replace("- Tournus abbey (architecture) — take: round arches — leave: interior scale\n", "")
        thin = thin.replace("- Read far, reward near\n", "")
        thin = thin.replace("Frame: direction/Keep_C.png", "Frame: direction/Keep_Z.png")
        self.write(thin)
        status, probs, _ = direction.check(self.doc, "world")
        self.assertEqual(status, "draft")
        joined = " | ".join(probs)
        self.assertIn("5 reference(s)", joined)
        self.assertIn("2 pillars", joined)
        self.assertIn("frame not found: direction/Keep_Z.png", joined)

    def test_a_sound_direction_needs_sketches_not_frames(self):
        self.write(GOOD)
        status, probs, _ = direction.check(self.doc, "sfx")
        self.assertEqual(status, "draft")
        self.assertTrue(any("Sketch:" in p for p in probs))

    def test_one_idea_in_three_grades_is_not_three_directions(self):
        graded = GOOD.replace("Axes: state=breached; light=overcast; palette=soot; mood=dread",
                              "Axes: state=intact; light=low sun; palette=soot; mood=awe")
        self.write(graded)
        status, probs, _ = direction.check(self.doc, "world")
        self.assertEqual(status, "draft")
        self.assertTrue(any("directions A and B differ on 1 axis" in p for p in probs), probs)

    def test_references_from_one_medium_are_too_narrow(self):
        narrow = GOOD
        for med in ("(photography)", "(architecture)", "(painting)"):
            narrow = narrow.replace(med, "(game)")
        self.write(narrow)
        status, probs, _ = direction.check(self.doc, "world")
        self.assertEqual(status, "draft")
        self.assertTrue(any("medium/media" in p for p in probs), probs)


    def test_years_in_brackets_are_not_media(self):
        years = GOOD
        for med in ("(photography)", "(architecture)", "(painting)", "(game)"):
            years = years.replace(med, "(1980..1985)")
        self.write(years)
        status, probs, _ = direction.check(self.doc, "world")
        self.assertEqual(status, "draft")
        self.assertTrue(any("medium/media" in p for p in probs), probs)

    def test_axes_must_name_the_lanes_core_axes(self):
        self.write(GOOD.replace("Axes: state=intact; light=low sun; palette=warm; mood=awe", "Axes: foo=1; bar=2"))
        status, probs, _ = direction.check(self.doc, "world")
        self.assertEqual(status, "draft")
        self.assertTrue(any("must name light, palette, mood" in p for p in probs), probs)

if __name__ == "__main__":
    unittest.main()
