# The kit's calibration builds

`scripts/g_*.py` are the builds the owner graded blind on 2026-10-05 (21 grades in `kit/grades.json`; the other five
graded models live in the owner's test game). They are kept with the kit so their measurements can be re-taken
whenever the measuring code changes (`rbx_score.MEASURE_VERSION`): `lune run kit grades --remeasure` rebuilds every
graded build it can find — these, and any project model graded with `kit grade` — and refreshes the stored
components, matched on asset, project and script (sha). A rebuild that no longer makes the model the owner saw (its
fingerprint: triangle count, size) keeps its old measurements and is named — ask the owner to grade it again. The
owner's numbers and notes never change. Then `lune run kit grades` shows the fit, and `--write` keeps a refit only
when no metric's own test says it is worse than the hand weights (p < .05) and one says it is better (p < .0914 each:
three looks that together keep a no-better refit at most one time in four) — written beside the grades, with the
grades it saw (`fitted_on`): grades given later are the FRESH, prospective test.

The variants: `_mine` = the hand-built starters, `_agent` = the score-chased versions, `_flat` = the same model with
flat paint (no grain, no wear), `_greebled` = extra surface detail, `_old` / `_now` = earlier and later versions.

## Who grades

Only the owner. `lune run kit grade <asset> <0-100> "why"` asks them to type the score again at their own terminal,
and `lune run kit grades --import <round.json>` asks them to type the number of grades; an agent's shell has no
terminal, so a model can prepare a round and start the command in the owner's terminal but never finish it.

## A blind round

1. Build what is to be graded (fresh scripts in `scripts/`, or a project's own models) with the current kit, and
   change nothing afterwards — the round must grade the builds that are measured.
2. Make the page: every build's hero render, shuffled, authorship hidden, a 0-100 score and a note per build.
3. The owner grades on the page. Save their answers as a round file, with the page as its source and, per build,
   the script sha and triangle count it was shown with — both REQUIRED, from the build's own history entry
   (`build/.../models/<asset>.quality.json`: `script_sha`, `tris`, written when it was built):

   ```json
   {"source": "https://... (the round's page)",
    "grades": [{"asset": "g_crate_mine", "project": "Parallax/grading", "object": "Wooden crate",
                "owner": 71, "note": "...", "script_sha": "96eed9afb8f1b29f", "tris": 2210}]}
   ```

4. The OWNER runs `lune run kit grades --import <round.json>` (it asks them to confirm) — it refuses the whole round
   when any build is not the one shown (another script, triangles moved, measured by older code), an asset is in it
   twice, or its source was imported before; every imported grade carries the source page.
5. `lune run kit grades` — the "fresh" line now tests the current weights on grades they never saw.

## An "A or B?" round

People judge a PAIR far more reliably than a number (the owner's own re-grades moved 5 points on average; GPTEval3D
ranks 3D generators by pairwise votes). An A-or-B round asks only "which of these two builds of the same object looks
better?" — and tells where the kit's score agrees with the owner's eye.

1. Build both sides of each pair with the current kit (as for a blind round) and list them:
   `{"title": "...", "pairs": [{"a": {"asset", "project", "render", "script_sha", "tris"}, "b": {...}}]}` — script_sha
   and tris from each build's own history entry (`build/.../models/<asset>.quality.json`), render = its sheet.
2. `lune run kit grades --pairs-page <list.json>` writes a self-contained page (build/grading/pairs_<date>.html: the
   renders embedded, the sides shuffled, authorship hidden). The owner opens it in a browser, picks A / B / same
   ("clearly" for a big gap), adds a word why, and downloads `pairs_round.json` (it names its page as the source).
3. The OWNER runs `lune run kit grades --import-pairs <pairs_round.json>`: every side must be the build the page showed
   (the same checks as a blind round), a source comes in once, and it asks them to confirm — into `kit/pairs.json`.
4. `lune run kit grades` then adds "A-or-B: the score agrees with the owner on N/M pairs" and names the pairs it gets
   wrong; `python kit/grading/pairs.py strengths kit/pairs.json` gives the owner's own ranking (Bradley-Terry).
