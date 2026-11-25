"""kit/tools/parts.py - the parts libraries' engine (board/plans/archive/2026-11-09-parts-libraries-plan.md, P0). Pure parts:
words, BM25, kinds (exact / sibling / axes), the top-three cap, interleaving, the brief's split, the answer sheet and
its check, Cohen's kappa. A fixture vault: the owner-only evidence rules (a guessed number never counts; the owner's
words naming a part weigh in full; the newest rejection marks "avoid"), the look hidden unless the OWNER allowed it,
a sheet's credit from the owner's later verdict, and a part of another object found by its kind.
Run: python kit/test/python/run.py -k test_parts"""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "tools"))
import parts as P  # noqa: E402

KINDS = {
    "lane": "3d",
    "axes": {"form": "how it is made", "role": "what it does"},
    "kinds": [
        {"id": "radial_array", "axis": "form", "label": "copies round a circle",
         "words": ["spoke", "radial array", "stave", "evenly round"], "code": [r"for \w+ in range\(\w+\):\s*\n\s*ang"],
         "siblings": ["linear_array"]},
        {"id": "linear_array", "axis": "form", "label": "copies along a line", "words": ["row of", "rungs"]},
        {"id": "turned", "axis": "form", "label": "turned profile", "words": ["lathe", "revolve", "turned", "rim"]},
        {"id": "rim", "axis": "role", "label": "rim or lip", "words": ["rim", "lip", "raised edge"]},
    ],
    "look_fields": ["texture", "palette"],
}

ADAPTER = '''
LANE = "3d"
def sources(root):
    return []
def collect(root):
    return {"pieces": [{"name": "barrel"}, {"name": "ladder"}, {"name": "cup"}],
            "docs": [
        {"id": "3d/recipe/barrel/staves", "type": "recipe", "piece": "barrel", "title": "staves",
         "text": "thirty staves placed by angle", "code": "for i in range(N):\\n    ang = i * 12",
         "src": "build_barrel.py:3", "mech": {"count": 30}, "look": {"texture": "oak_scan"}},
        {"id": "3d/part/barrel/hoops", "type": "part", "piece": "barrel", "title": "iron hoops",
         "text": "two iron hoops", "src": "barrel.parts.md"},
        {"id": "3d/part/ladder/rungs", "type": "part", "piece": "ladder", "title": "rungs", "text": "a row of rungs"},
        {"id": "3d/part/cup/body", "type": "part", "piece": "cup", "title": "body", "text": "a turned cup on a lathe"},
    ]}
def home(root, piece):
    return None
'''


def verdict(name, score, words, date, source="owner", by="owner"):
    return (f"---\nkind: verdict\narea: 3d\nname: {name}\nscore: {score}\ndate: {date}\nby: {by}\nsource: {source}\n"
            f"---\n\n{words}\n")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def quiet(fn, *a, **k):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = fn(*a, **k)
    lines = [ln for ln in buf.getvalue().splitlines() if ln.startswith("{")]
    return code, (json.loads(lines[-1]) if lines else {})


class PureTest(unittest.TestCase):
    def test_words_fold_short_plurals(self):
        self.assertEqual(P.toks("Lips, legs and spokes"), ["lip", "leg", "spoke"])

    def test_bm25_prefers_the_doc_with_the_rare_word(self):
        bm = P.Bm25([["spoke", "wheel"], ["wheel", "tyre"], ["box", "lid"]])
        s = bm.scores({"spoke": 1.0, "wheel": 1.0})
        self.assertGreater(s[0], s[1])
        self.assertNotIn(2, s)

    def test_kinds_from_words_and_scores_by_axis(self):
        k = P.compile_kinds(json.loads(json.dumps(KINDS)))
        self.assertEqual(P.query_kinds(k, "five spokes from the hub"), ["radial_array"])
        self.assertEqual(P.query_kinds(k, "a round band turned on a lathe with a raised edge"), ["rim", "turned"])
        m = k["_map"]
        self.assertEqual(P.kind_score({"radial_array": 1.0}, ["radial_array"], m), 1.0)
        self.assertEqual(P.kind_score({"linear_array": 1.0}, ["radial_array"], m), 0.5)  # a sibling: half
        self.assertEqual(P.kind_score({"turned": 1.0}, ["turned", "rim"], m), 0.5)  # two axes asked, one met
        self.assertEqual(P.kind_score({}, [], m), 0.0)
        self.assertEqual([P.strength(n) for n in (1, 2, 3, 9)], [0.5, 0.75, 1.0, 1.0])

    def test_top_three_hold_one_card_per_past_piece(self):
        rows = [(1.0 - i * 0.1, {"id": f"d{i}", "piece": p}, {}) for i, p in enumerate("AAABCA")]
        out = P.diversify(rows, 6)
        self.assertEqual([r[1]["piece"] for r in out[:3]], ["A", "B", "C"])
        self.assertEqual(len(out), 6)

    def test_interleave_round_robin_first_seen(self):
        a = [(1, {"id": "x"}, {}), (1, {"id": "y"}, {})]
        b = [(1, {"id": "x"}, {}), (1, {"id": "z"}, {})]
        self.assertEqual([r[1]["id"] for r in P.interleave([a, b], 3)], ["x", "y", "z"])

    def test_brief_splits_into_clauses(self):
        head, parts = P.split_brief("car wheel rim: a round alloy rim, five spokes from a centre hub (cast, 2.5 cm); "
                                    "raised lips at both edges. Machined finish")
        self.assertEqual(head, "car wheel rim")
        self.assertEqual([p["title"] for p in parts], ["a round alloy rim", "five spokes from a centre hub (cast, 2.5 cm)",
                                                       "raised lips at both edges", "Machined finish"])

    def test_sheet_answers_are_checked(self):
        text = ("---\nkind: parts-sheet\nlane: 3d\npiece: rim\ndate: 2026-11-09\n---\n# Parts sheet\n\n"
                "## 1. spokes\nkinds: radial_array (form)\n- [recipe] `3d/recipe/barrel/staves` staves\n"
                "answer: `3d/recipe/barrel/staves` - same loop, 5 copies\n\n"
                "## 2. lip\nkinds: rim (role)\n- [part] `3d/part/cup/body` body\nanswer: new - no past lip had a "
                "rolled bead\n\n## 3. hub\nkinds: none\n- [part] `3d/part/ladder/rungs`\nanswer: \n\n"
                "## 4. bolts\nkinds: none\n- [part] `3d/part/ladder/rungs`\nanswer: `3d/part/cup/body`\n\n"
                "## Other parts (no answer needed)\n- finish: kinds none\n")
        sheet = P.parse_sheet(text)
        self.assertEqual(sheet["piece"], "rim")
        self.assertEqual(sheet["parts"][0]["used"], ["3d/recipe/barrel/staves"])
        self.assertTrue(sheet["parts"][1]["new"])
        problems = P.check_sheet(sheet)
        self.assertEqual(len(problems), 2)  # part 3 unanswered; part 4 names a card it was never shown
        self.assertIn("part 3", problems[0])
        self.assertIn("part 4", problems[1])
        self.assertEqual(P.check_sheet(P.parse_sheet(text.replace("answer: new - no past lip had a rolled bead",
                                                                  "answer: new"))), problems[:0] + [
            "part 2 (lip): `new` needs why none of its cards fits"] + problems)

    def test_kappa(self):
        self.assertEqual(P.kappa([(1, 1), (0, 0), (1, 1), (0, 0)]), (1.0, 1.0))
        k, agree = P.kappa([(1, 1), (1, 0), (0, 0), (0, 0)])
        self.assertEqual(agree, 0.75)
        self.assertEqual(k, 0.5)
        self.assertEqual(P.kappa([]), (None, None))

    def test_verdict_values(self):
        self.assertEqual(P.verdict_value({"score": 10, "guessed": False}), 1.0)
        self.assertIsNone(P.verdict_value({"score": 9, "guessed": True}))  # a guessed number never counts
        self.assertEqual(P.verdict_value({"score": None, "direction": "redo"}), -1.0)


class LibraryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        v = os.path.join(self.root, "kit", "knowledge", "vault", "3d")
        for sub in ("lessons", "verdicts", "parts"):
            os.makedirs(os.path.join(v, sub))
        with open(os.path.join(v, "parts", "kinds.json"), "w", encoding="utf-8") as f:
            json.dump(KINDS, f)
        os.makedirs(os.path.join(self.root, "kit", "blender"))
        with open(os.path.join(self.root, "kit", "blender", "parts_3d.py"), "w", encoding="utf-8") as f:
            f.write(ADAPTER)
        with open(os.path.join(v, "lessons", "2026-11-01-staves-by-angle.md"), "w", encoding="utf-8") as f:
            f.write("---\nkind: lesson\narea: 3d\ndate: 2026-11-01\n---\n\nPlace staves by angle in one loop, never by "
                    "hand: copies round a circle stay even.\n")
        self.verdicts = os.path.join(v, "verdicts")

    def tearDown(self):
        self.tmp.cleanup()

    def write_verdict(self, fname, *a, **k):
        with open(os.path.join(self.verdicts, fname), "w", encoding="utf-8") as f:
            f.write(verdict(*a, **k))

    def index(self):
        return P.load_index(self.root, "3d", rebuild=True)

    def test_a_part_of_another_object_is_found_by_its_kind(self):
        idx = self.index()
        rows = P.search(idx, "five spokes from the hub", k=5)
        ids = [d["id"] for _s, d, _p in rows]
        self.assertEqual(ids[0], "3d/recipe/barrel/staves")  # the barrel's stave loop, by kind + code pattern
        self.assertIn("3d/part/ladder/rungs", ids)  # a sibling kind (copies along a line) ranks below
        self.assertLess(ids.index("3d/recipe/barrel/staves"), ids.index("3d/part/ladder/rungs"))
        self.assertNotIn("3d/part/cup/body", ids)  # nothing shared: not a card

    def test_the_planned_piece_never_lends_itself(self):
        idx = self.index()
        ids = [d["id"] for _s, d, _p in P.search(idx, "staves by angle", k=5, exclude="barrel")]
        self.assertFalse(any(i.startswith("3d/recipe/barrel") or i.startswith("3d/part/barrel") for i in ids))

    def test_owner_evidence_rules(self):
        self.write_verdict("barrel--1.md", "barrel", 9, "the iron hoops are great", "2026-11-02")
        self.write_verdict("cup--1.md", "cup", 9, "nice", "2026-11-02", source="inferred")  # a guessed number
        self.write_verdict("ladder--1.md", "ladder", 8, "good", "2026-11-01")
        self.write_verdict("ladder--2.md", "ladder", 2, "the rungs are too thin", "2026-11-03")  # newest: rejected
        self.write_verdict("ladder--3.md", "ladder", 10, "x", "2026-11-04", by="claude-code")  # not the owner's
        idx = self.index()
        doc = {d["id"]: d for d in idx.docs}
        hoops, staves = doc["3d/part/barrel/hoops"], doc["3d/recipe/barrel/staves"]
        self.assertTrue(hoops["owner"][-1]["part"])  # the owner's words name the hoops: full weight
        self.assertGreater(hoops["evidence"], 0.7)
        self.assertGreater(staves["evidence"], 0.7)  # the piece's verdict reaches its recipe at half weight
        cup = doc["3d/part/cup/body"]
        self.assertEqual(cup["evidence"], 0.0)  # the guessed 9 never counts
        self.assertTrue(cup["owner"][-1]["guessed"])
        rungs = doc["3d/part/ladder/rungs"]
        self.assertTrue(rungs["avoid"])  # the newest of the owner's verdicts rejects it
        self.assertEqual(len(rungs["owner"]), 2)  # the model's 10 is not there
        self.assertIn("AVOID", P.card(idx, rungs))

    def test_the_look_stays_hidden_unless_the_owner_allowed_it(self):
        idx = self.index()
        staves = next(d for d in idx.docs if d["id"] == "3d/recipe/barrel/staves")
        self.assertIn("look hidden", P.card(idx, staves, for_piece="rim"))
        self.assertNotIn("oak_scan", P.card(idx, staves, for_piece="rim"))
        self.assertIn("count=30", P.card(idx, staves, for_piece="rim"))  # mechanics always
        quiet(P.cmd_look_allow, self.root, "3d", ["rim", "keep", "the", "oak"], {"from": "barrel"})  # a proposal
        idx = self.index()
        self.assertNotIn("oak_scan", P.card(idx, staves, for_piece="rim"))
        quiet(P.cmd_look_allow, self.root, "3d", ["rim", "same", "oak", "as", "the", "barrel"],
              {"from": "barrel", "by": "owner"})
        idx = self.index()
        line = P.card(idx, staves, for_piece="rim")
        self.assertIn("LOOK REUSE", line)
        self.assertIn("oak_scan", line)
        self.assertNotIn("oak_scan", P.card(idx, staves, for_piece="crate"))  # only for the piece allowed

    def test_a_sheet_credits_what_it_built_from(self):
        os.makedirs(os.path.join(self.root, "build", "parts", "3d", "sheets"))
        with open(os.path.join(self.root, "build", "parts", "3d", "sheets", "rim" + P.SHEET_SUFFIX), "w",
                  encoding="utf-8") as f:
            f.write("---\nkind: parts-sheet\nlane: 3d\npiece: rim\ndate: 2026-11-05\n---\n\n## 1. spokes\n"
                    "kinds: radial_array\n- [recipe] `3d/recipe/barrel/staves`\nanswer: `3d/recipe/barrel/staves`\n")
        self.write_verdict("rim--old.md", "rim", 1, "before the sheet", "2026-11-01")  # older than the sheet
        idx = self.index()
        self.assertNotIn("credit", next(d for d in idx.docs if d["id"] == "3d/recipe/barrel/staves"))
        self.write_verdict("rim--1.md", "rim", 9, "spokes look right", "2026-11-06")
        idx = self.index()
        staves = next(d for d in idx.docs if d["id"] == "3d/recipe/barrel/staves")
        self.assertEqual(staves["credit"]["helpful"], 1)
        self.assertEqual(staves["credit"]["harmful"], 0)
        code, out = quiet(P.cmd_credit, self.root, "3d", idx, ["rim"])
        self.assertEqual(code, 0)
        self.assertIn("1 credited from its sheet", out["summary"])

    def test_plan_writes_a_sheet_and_never_overwrites_answers(self):
        idx = self.index()
        code, out = quiet(P.cmd_plan, self.root, "3d", idx, ["rim"],
                          {"brief": "wheel rim: a turned rim, five spokes from the hub, a row of bolts"})
        self.assertEqual(code, 0, out)
        path = os.path.join(self.root, out["sheet"])
        sheet = P.parse_sheet(read(path))
        self.assertEqual(len(sheet["parts"]), 3)
        spokes = next(p for p in sheet["parts"] if "spokes" in p["title"])
        self.assertIn("3d/recipe/barrel/staves", spokes["served"])
        self.assertEqual(quiet(P.cmd_plan, self.root, "3d", idx, ["rim"], {"check": True})[0], 1)  # unanswered
        text = read(path).replace("answer: ", "answer: new - nothing we made fits it", 1)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        code, out = quiet(P.cmd_plan, self.root, "3d", idx, ["rim"], {"brief": "wheel rim: a turned rim"})
        self.assertEqual(code, 1)  # a sheet holding answers is never overwritten
        self.assertIn("never overwritten", out["summary"])

    def test_the_index_rebuilds_when_a_source_changes(self):
        P.load_index(self.root, "3d", rebuild=True)
        self.assertFalse(P.load_index(self.root, "3d").rebuilt)
        self.write_verdict("cup--2.md", "cup", 8, "good cup", "2026-11-07")
        self.assertTrue(P.load_index(self.root, "3d").rebuilt)

    def test_a_rounds_verdict_reaches_its_candidates_and_research_is_never_judged(self):
        docs = [{"id": "c0", "type": "candidate", "piece": "Kick/r0/c0", "whole": True, "title": "c0", "text": ""},
                {"id": "c1", "type": "candidate", "piece": "Kick/r0/c1", "whole": True, "title": "c1", "text": ""},
                {"id": "ph", "type": "part", "piece": "Kick/r0", "research": True, "title": "strike", "text": ""}]
        by_piece = {"kick_r0": [{"name": "Kick/r0", "score": 1.0, "direction": None, "guessed": False,
                                 "words": "all bad: stilts", "date": "2026-11-04"}],
                    "kick_r0_c1": [{"name": "Kick/r0/c1", "score": 9.0, "direction": None, "guessed": False,
                                    "words": "this one", "date": "2026-11-05"}]}
        for d in docs:
            P.evidence_for(d, by_piece, {}, {})
        c0, c1, ph = docs
        self.assertTrue(c0["avoid"])  # the round's "all bad" reaches every candidate in it
        self.assertLess(c0["evidence"], 0)
        self.assertFalse(c1["avoid"])  # its own pick (the most specific verdict) wins over the round's
        self.assertGreater(c1["evidence"], 0)
        self.assertEqual((ph["evidence"], ph["avoid"], ph["owner"]), (0.0, False, []))  # research: never judged
        self.assertEqual(P._chain("Kick/r0/c1"), ["Kick/r0/c1", "Kick/r0", "Kick"])

    def test_same_day_verdicts_keep_their_order(self):
        # (review P0: "x--D-6.md" sorts BEFORE "x--D.md" by name, and a loved 9 read as older than the 2s it replaced)
        self.write_verdict("ladder--2026-11-03.md", "ladder", 2, "the rungs are too thin", "2026-11-03")
        self.write_verdict("ladder--2026-11-03-2.md", "ladder", 2, "still thin", "2026-11-03")
        self.write_verdict("ladder--2026-11-03-6.md", "ladder", 9, "FINALLY the rungs are right", "2026-11-03")
        idx = self.index()
        rungs = next(d for d in idx.docs if d["id"] == "3d/part/ladder/rungs")
        self.assertFalse(rungs["avoid"])  # the day's LAST verdict (the 9) is the newest
        self.assertEqual(rungs["owner"][-1]["score"], 9.0)
        self.assertEqual([v["seq"] for v in sorted(P.verdicts(self.root, "3d"), key=P.when)], [1, 2, 6])

    def test_a_planned_move_never_gets_its_own_candidates(self):
        docs = [{"id": "c0", "type": "candidate", "piece": "Kick/r0/c0", "title": "kick candidate", "text": "kick",
                 "kinds": {}, "toks": ["kick"], "evidence": 0.0},
                {"id": "o", "type": "candidate", "piece": "Punch/r0/c0", "title": "punch", "text": "kick",
                 "kinds": {}, "toks": ["kick"], "evidence": 0.0}]
        idx = P.Index(self.root, "3d", {"docs": docs}, P.compile_kinds(json.loads(json.dumps(KINDS))))
        self.assertEqual([d["id"] for _s, d, _p in P.search(idx, "kick", k=5, exclude="Kick")], ["o"])

    def test_no_look_value_leaks_through_a_cards_path(self):
        idx = self.index()
        d = {"id": "ui/part/Hud/Plate", "type": "part", "piece": "Hud", "title": "Hud: Plate", "kinds": {},
             "src": "library/ui/x/screens/Hud/parts/Hud.Plate.Art.png", "look": {"art": "parts/Hud.Plate.Art.png"}}
        line = P.card(idx, d, for_piece="NewHud")
        self.assertNotIn("Plate.Art.png", line)
        self.assertIn("look hidden", line)

    def test_an_owners_look_allow_for_a_move_covers_its_candidates(self):
        allows = [{"piece": "NewKick", "from": "Kick", "by": "owner", "words": "same snap"}]
        self.assertTrue(P.look_allowed(allows, "NewKick", "Kick/r2/c6"))
        self.assertFalse(P.look_allowed(allows, "NewKick", "Punch/r0/c0"))
        self.assertFalse(P.look_allowed([dict(allows[0], by="model-proposed")], "NewKick", "Kick/r2/c6"))

    def test_an_answer_may_only_build_from_cards_it_was_shown(self):
        text = ("---\nkind: parts-sheet\nlane: 3d\npiece: rim\ndate: 2026-11-09\n---\n\n## 1. spokes\nkinds: x\n"
                "- [recipe] `3d/recipe/barrel/staves`\nanswer: `3d/recipe/barrel/staves` and `3d/recipe/rim/own`\n\n"
                "## 2. lip\nkinds: x\n- [part] `3d/part/cup/body`\nanswer: new - unlike `3d/part/cup/body`, a rolled "
                "bead\n")
        sheet = P.parse_sheet(text)
        self.assertEqual(sheet["parts"][0]["used"], ["3d/recipe/barrel/staves"])  # never the unshown card
        self.assertEqual(sheet["parts"][1]["used"], [])  # `new` builds from (and credits) nothing
        problems = P.check_sheet(sheet)
        self.assertEqual(len(problems), 1)
        self.assertIn("not shown", problems[0])

    def test_answers_are_never_merged_onto_another_pool(self):
        P.save_json(P.questions_path(self.root, "3d"),
                    {"questions": [{"id": "3d-q01", "piece": "rim", "brief": "rim: five spokes from the hub"}]})
        idx = self.index()
        self.assertEqual(quiet(P.cmd_label, self.root, "3d", idx, {})[0], 0)
        work = os.path.join(self.root, "build", "parts", "3d", "label")
        P.save_json(os.path.join(work, "answers-a.json"), {"3d-q01": {"1": 1, "99": 0}})  # a stray number
        code, out = quiet(P.cmd_label, self.root, "3d", idx, {"merge": "a"})
        self.assertEqual(code, 1)
        self.assertIn("nothing merged", out["summary"])
        code, out = quiet(P.cmd_label, self.root, "3d", idx, {})  # a new pool while answers wait: refused
        self.assertEqual(code, 1)
        self.assertIn("not merged", out["summary"])
        key = json.loads(read(os.path.join(work, "key-a.json")))
        P.save_json(os.path.join(work, "answers-a.json"), {q: {n: 1 for n in nums} for q, nums in key.items()})
        self.assertEqual(quiet(P.cmd_label, self.root, "3d", idx, {"merge": "a"})[0], 0)
        self.assertFalse(os.path.isfile(os.path.join(work, "answers-a.json")))  # set aside once merged in full
        self.assertTrue(os.path.isfile(os.path.join(work, "answers-a.merged.json")))

    def test_look_assets_are_never_handed_over_unless_asked(self):
        kinds = json.loads(json.dumps(KINDS))
        kinds["look_types"] = ["texture"]
        with open(P.kinds_path(self.root, "3d"), "w", encoding="utf-8") as f:
            json.dump(kinds, f)
        with open(os.path.join(self.root, "kit", "blender", "parts_3d.py"), "a", encoding="utf-8") as f:
            f.write('\n_c = collect\ndef collect(root):\n    got = _c(root)\n    got["docs"].append({"id": "3d/texture/'
                    'spokes", "type": "texture", "piece": "tex", "title": "spoke texture", "text": "spokes spokes"})\n'
                    '    return got\n')
        idx = self.index()
        self.assertNotIn("3d/texture/spokes", [d["id"] for _s, d, _p in P.search(idx, "spokes", k=10)])
        self.assertIn("3d/texture/spokes", [d["id"] for _s, d, _p in P.search(idx, "spokes", k=10, types=("texture",))])

    def test_labels_merge_and_eval_counts(self):
        qpath = P.questions_path(self.root, "3d")
        P.save_json(qpath, {"questions": [{"id": "3d-q01", "piece": "rim", "brief": "rim: five spokes from the hub"}]})
        idx = self.index()
        code, out = quiet(P.cmd_label, self.root, "3d", idx, {})
        self.assertEqual(code, 0, out)
        work = os.path.join(self.root, "build", "parts", "3d", "label")
        for who in ("a", "b"):
            key = json.loads(read(os.path.join(work, f"key-{who}.json")))
            blind = read(os.path.join(work, f"blind-{who}.md"))
            self.assertNotIn("engine", blind.split("## 3d-q01")[1])  # no method named on the cards
            ans = {q: {n: (1 if "staves" in cid else 0) for n, cid in nums.items()} for q, nums in key.items()}
            P.save_json(os.path.join(work, f"answers-{who}.json"), ans)
            self.assertEqual(quiet(P.cmd_label, self.root, "3d", idx, {"merge": who})[0], 0)
        code, out = quiet(P.cmd_eval, self.root, "3d", idx, {})
        self.assertEqual(code, 0, out)
        self.assertEqual(out["n"], 1)
        self.assertFalse(out["measurable"])  # one question: not measurable yet
        self.assertIn("NOT MEASURABLE YET", out["summary"])
        self.assertGreaterEqual(out["methods"]["engine"]["strict"], 1)


class P1Test(unittest.TestCase):
    """P1 (3D): the study's Parts section is the lock, answered studies credit their cards, the owner's words reach
    parts by kind word, parts-review rows link to their builder family, know-how never repeats a shown card, and the
    re-ranker orders a sheet (or steps aside when no warm worker runs)"""

    setUp, tearDown = LibraryTest.setUp, LibraryTest.tearDown  # (the same fixture vault, not its tests again)
    write_verdict, index = LibraryTest.write_verdict, LibraryTest.index

    def test_the_studys_parts_section_is_the_lock(self):
        sys.path.insert(0, os.path.join(ROOT, "kit", "tools"))
        import study as S  # noqa: PLC0415

        part = ("### 1. spokes\nkinds: radial_array (form)\n- [recipe] `3d/recipe/barrel/staves` staves\n"
                "- know-how: [helper] `3d/helper/rbx_parts/rivet_ring` rivet_ring\nanswer: \n\n")
        study = "# x\n\n## Our version\n- what: x\n\n## Parts\n\n<!-- parts: 2026-11-09 (kit parts 3d plan) -->\n\n"
        self.assertEqual(len(S.parts_problems(study + part + "## Lessons applied\n")), 1)  # unanswered: refused
        done = part.replace("answer: ", "answer: `3d/helper/rbx_parts/rivet_ring` - the same ring of copies")
        self.assertEqual(S.parts_problems(study + done + "## Lessons applied\n"), [])  # a know-how card counts
        self.assertEqual(S.parts_problems("# x\n\n## Lessons applied\n- none: x\n"), [])  # an old study: none asked
        self.assertEqual(S.parts_problems(study.replace("<!-- parts: 2026-11-09 (kit parts 3d plan) -->", "")
                                          + part), [])  # (no section mark: written before the lock)

    def test_an_answered_study_credits_its_cards(self):
        home = os.path.join(self.root, "models")
        os.makedirs(home)
        with open(os.path.join(self.root, "kit", "blender", "parts_3d.py"), "a", encoding="utf-8") as f:
            f.write(f"\nSHEET_GLOBS = ['*.parts-sheet.md', '*.study.md']\ndef homes(root):\n    return [{home!r}]\n")
        with open(os.path.join(home, "rim.study.md"), "w", encoding="utf-8") as f:
            f.write("# rim\n\n## Parts\n\n<!-- parts: 2026-11-05 -->\n\n### 1. spokes\nkinds: radial_array\n"
                    "- [recipe] `3d/recipe/barrel/staves` staves\nanswer: `3d/recipe/barrel/staves`\n\n## Past cases\n")
        self.write_verdict("rim--1.md", "rim", 9, "the spokes look right", "2026-11-06")
        staves = next(d for d in self.index().docs if d["id"] == "3d/recipe/barrel/staves")
        self.assertEqual(staves["credit"]["helpful"], 1)
        self.assertEqual(staves["credit"]["pieces"], ["rim"])  # (the piece from the study's own file name)

    def test_the_owners_words_reach_a_part_by_its_kind_word(self):
        d = {"id": "p", "type": "part", "piece": "wheel", "title": "SpokeSet", "text": "", "kinds": {"rim": 1.0}}
        v = {"name": "wheel", "score": 2.0, "direction": None, "guessed": False, "words": "the rim is too thin",
             "date": "2026-11-09", "kinds": {"rim"}}
        P.evidence_for(d, {"wheel": [v]}, {}, {})
        self.assertTrue(d["owner"][-1]["part"])  # named by its kind word, not its name
        self.assertTrue(d["avoid"])

    def test_parts_review_rows_link_to_their_builder_family(self):
        sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
        import parts_3d as A  # noqa: PLC0415

        # (each recipe with its calls' own name templates, as the builder wrote them)
        recipes = {"3d/recipe/arp/Round": ["Round{k:02d}"], "3d/recipe/arp/SightRear": ["SightRear"],
                   "3d/recipe/arp/SightRearLine": ["SightRearLine{s}"], "3d/recipe/arp/Grip": ["Grip"],
                   "3d/recipe/arp/Hammer": ["Hammer"], "3d/recipe/arp/Pin": ["{n}Pin"], "3d/recipe/arp/Any": ["{a}{b}"]}
        self.assertEqual(A.recipe_for("Round10Bullet", "arp", recipes), "3d/recipe/arp/Round")  # an indexed loop's sub-part
        self.assertEqual(A.recipe_for("SightRearLineR", "arp", recipes), "3d/recipe/arp/SightRearLine")  # a side
        self.assertEqual(A.recipe_for("TriggerPin", "arp", recipes), "3d/recipe/arp/Pin")  # f"{n}Pin" over part names
        # (the fresh review's wrong links: a plain name never owns a different part that starts with it)
        self.assertIsNone(A.recipe_for("GripScrewTop", "arp", recipes))
        self.assertEqual(A.recipe_for("HammerPin", "arp", recipes), "3d/recipe/arp/Pin")
        self.assertIsNone(A.recipe_for("Trigger", "arp", recipes))  # ("{a}{b}" - all fields - claims nothing)
        self.assertEqual(A.recipe_for("Hammer", "arp", set(recipes)), "3d/recipe/arp/Hammer")  # exact, from a set

    def test_the_rerankers_order_and_its_fallback(self):
        idx = self.index()
        rows = P.search(idx, "five spokes from the hub", k=5)
        stub = type(sys)("parts_rerank")
        stub.scores_many = lambda pairs, cold=True: [1.0 if "rungs" in t else 0.0 for _q, t in pairs]
        sys.modules["parts_rerank"] = stub
        try:
            got = P.rerank_rows([("five spokes", rows)], 3)
            self.assertEqual(got[0][0][1]["id"], "3d/part/ladder/rungs")  # the model's choice leads
            stub.scores_many = lambda pairs, cold=True: None  # no warm worker, no cold load allowed
            self.assertIsNone(P.rerank_rows([("five spokes", rows)], 3, cold=False))
        finally:
            del sys.modules["parts_rerank"]

    def test_the_reranker_never_loads_silently_nor_twice(self):
        import parts_rerank as R  # noqa: PLC0415

        saved = (R.worker, R._remote, R._local)
        R._local = lambda prompts: (_ for _ in ()).throw(AssertionError("a second model load"))
        try:
            R.worker = lambda: {"port": 1, "token": "t", "loaded": False}  # up, but the model not loaded yet
            self.assertIsNone(R.scores_many([("q", "card")], cold=False))
            self.assertIn("has not loaded", R.LAST["why"])
            R.worker, R._remote = (lambda: {"port": 1, "token": "t", "loaded": True}), (lambda w, p: [0.5] * len(p))
            self.assertEqual(R.scores_many([("q", "a"), ("q", "b")], cold=False), [0.5, 0.5])  # warm: served
            R._remote = lambda w, p: None  # the worker fails this call
            self.assertIsNone(R.scores_many([("q", "a")], cold=True))  # never a second copy beside a live worker
            self.assertIn("failed", R.LAST["why"])
            R.worker = lambda: None
            self.assertIsNone(R.scores_many([("q", "a")], cold=False))  # no worker, no --rerank: plain
        finally:
            R.worker, R._remote, R._local = saved

    def test_loose_words_never_name_a_part(self):
        kinds = json.loads(json.dumps(KINDS))
        kinds.update({"part_axes": ["role"], "name_words_ignore": ["band", "body"]})
        kinds["kinds"].append({"id": "hoop", "axis": "role", "label": "hoop", "words": ["band", "hoop"]})
        with open(P.kinds_path(self.root, "3d"), "w", encoding="utf-8") as f:
            json.dump(kinds, f)
        self.write_verdict("barrel--1.md", "barrel", 1, "ye horrible (round-body + colour-band route)", "2026-11-09")
        hoops = next(d for d in self.index().docs if d["id"] == "3d/part/barrel/hoops")
        self.assertFalse(hoops["owner"][-1]["part"])  # "band" is a route's word here: the hoops are not named
        self.write_verdict("barrel--2.md", "barrel", 2, "the hoops are too thin", "2026-11-10")
        hoops = next(d for d in self.index().docs if d["id"] == "3d/part/barrel/hoops")
        self.assertTrue(hoops["owner"][-1]["part"])  # named by its own word

    def test_know_how_is_helpers_never_already_shown(self):
        with open(os.path.join(self.root, "kit", "blender", "parts_3d.py"), "a", encoding="utf-8") as f:
            f.write('\n_c2 = collect\ndef collect(root):\n    got = _c2(root)\n    got["docs"].append({"id": "3d/helper/'
                    'rbx_parts/rivet_ring", "type": "helper", "piece": "helper:rbx_parts", "title": "rivet_ring", '
                    '"text": "rivets placed evenly round a ring: copies round a circle"})\n    return got\n')
        idx = self.index()
        ids = [d["id"] for d in P.know_how(idx, ["radial_array"], shown=set())]
        self.assertEqual(ids, ["3d/helper/rbx_parts/rivet_ring"])  # (the stave recipe is a card, not know-how)
        self.assertEqual(P.know_how(idx, ["radial_array"], shown={"3d/helper/rbx_parts/rivet_ring"}), [])


class RimProbeTest(unittest.TestCase):
    """the plan's fair rim probe, fixed (P0): on the REAL 3D library, the rim brief's clauses ask for their kinds, and
    the spokes - know-how that sits in builder code, not in any lesson - reach a copies-round-a-circle card from code"""

    RIM = ("car wheel rim: a round alloy rim, five spokes from a centre hub out to the barrel, raised lips at both "
           "edges, lug nut holes on a bolt circle, machined metal finish")

    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(P.kinds_path(ROOT, "3d")):
            raise unittest.SkipTest("no 3D kinds in this kit home")
        cls.idx = P.load_index(ROOT, "3d")

    def test_the_rim_clauses_ask_for_their_kinds(self):
        _head, parts = P.breakdown(self.idx, None, "car_wheel_rim", self.RIM)
        kinds = {p["title"]: set(p["kinds"]) for p in parts}
        self.assertIn("radial_array", kinds["five spokes from a centre hub out to the barrel"])
        self.assertIn("hub", kinds["five spokes from a centre hub out to the barrel"])
        self.assertIn("lip", kinds["raised lips at both edges"])
        self.assertTrue({"holes", "fastener"} <= kinds["lug nut holes on a bolt circle"])
        self.assertIn("f_machined", kinds["machined metal finish"])

    def test_the_spokes_reach_a_radial_recipe_from_code(self):
        rows = P.search(self.idx, "five spokes from a centre hub out to the barrel", k=5, exclude="car_wheel_rim",
                        context="car wheel rim")
        code_cards = [d for _s, d, _p in rows if d["type"] in ("recipe", "helper") and "radial_array" in d["kinds"]]
        self.assertTrue(code_cards, [d["id"] for _s, d, _p in rows])


if __name__ == "__main__":
    unittest.main()
