"""kit/refs/dossier.py — the object's DOSSIER: facts graded from their sources, a typed number counting only once a
script found it in the cited source (or two reviewers, one blind, confirmed it), pictures and models checked against the
facts (the Glock 17's 7%-short scan and the Gen4's 204 mm would both have been caught), two keys per item, the owner's
approval going stale when anything graded changes. No network: every source's text is put in the cache first."""

import contextlib
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "refs"))
import dims  # noqa: E402
import dossier as D  # noqa: E402

MAKER = "https://eu.glock.com/en/products/pistols/g17_gen5"
MANUAL = "https://eu-assets.contentstack.com/v3/assets/bltf7171cc1cfc1a31f/blt7e0/x/GLOCK_Owners_Manual.pdf"
PAGE = ("Dimension 1 LENGTH (OVERALL)* 202 mm | 7.95 inch 2 SLIDE LENGTH 186 mm | 7.32 inch 3 WIDTH (OVERALL) 34 mm | "
        "1.34 inch 4 SLIDE WIDTH 25,5 mm | 1.00 inch 5 HEIGHT INCL. MAG. 139 mm | 5.47 inch")
MANUAL_TEXT = "XVI. Component parts 1 Slide 2 Barrel 3 Recoil spring assembly* 17 Frame 26 Trigger with trigger bar"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="kit_dossier_")
        know = os.path.join(self.tmp, "knowledge")
        shutil.copytree(os.path.join(ROOT, "kit", "knowledge", "categories"), os.path.join(know, "categories"))
        shutil.copy(os.path.join(ROOT, "kit", "knowledge", "sources.json"), know)
        self.saved = (D.KNOW, D.PRIVATE, D.EVIDENCE, dims.STORE, os.environ.get("KIT_BUILD"))
        D.KNOW, D.PRIVATE, D.EVIDENCE = know, os.path.join(self.tmp, "private"), os.path.join(self.tmp, "evidence")
        dims.STORE = os.path.join(self.tmp, "real_specs")
        os.environ["KIT_BUILD"] = os.path.join(self.tmp, "build")
        self.page(MAKER, PAGE)
        self.page(MANUAL, MANUAL_TEXT)

    def tearDown(self):
        D.KNOW, D.PRIVATE, D.EVIDENCE, dims.STORE, build = self.saved
        if build is None:
            os.environ.pop("KIT_BUILD", None)
        else:
            os.environ["KIT_BUILD"] = build
        shutil.rmtree(self.tmp, ignore_errors=True)

    def page(self, url, text):
        """a source's words, as if fetched once already (source_text reads the cache first)"""
        key = hashlib.sha1(url.encode()).hexdigest()[:16]
        os.makedirs(os.path.join(D.EVIDENCE, "_sources"), exist_ok=True)
        with open(os.path.join(D.EVIDENCE, "_sources", f"{key}.txt"), "w", encoding="utf-8") as fh:
            fh.write(text)

    def dossier(self, **kw):
        d = {"schema": 1, "object": "glock 17 gen5", "slug": "glock_17_gen5", "category": "pistol", "private": True,
             "identity": {"maker": "GLOCK", "maker_domains": ["glock.com",
                                                             "eu-assets.contentstack.com/v3/assets/bltf7171cc1cfc1a31f"],
                          "aliases": ["g17 gen5"], "family": ["glock 17"], "tells": []},
             "sources": [], "parts": [], "markings": [], "evidence": [], "reviews": [], "approval": None}
        d.update(kw)
        D.save(d)
        return d

    def row(self, value, source, part="overall", dim="length", obj="glock 17 gen5", kind="published", quote=None,
            by="opus@claude-code", read_by="auto"):
        r = {"object": obj, "part": part, "dim": dim, "value": float(value), "unit": "mm", "source": source, "kind": kind,
             "note": "", "by": by}
        if read_by == "auto" and kind in ("wikipedia", "wikidata"):
            r["read_by"] = "kit"  # (as kit refs dims wikipedia / wikidata store what they read)
        if quote:
            r["quote"] = quote
        dims.add_rows([r])
        return dims.row_id(obj, part, dim, float(value), source)

    def graded(self, d, key="overall.length"):
        return D.grade_facts(d, D.annotate_rows(d, offline=True))[key]

    def picture(self, name, length, height, w=1200, h=900, scale=4.0):
        from PIL import Image, ImageDraw

        im = Image.new("RGB", (w, h), (255, 255, 255))
        x0, y0 = 100, 200
        ImageDraw.Draw(im).rectangle([x0, y0, x0 + int(length * scale) - 1, y0 + int(height * scale) - 1],
                                     fill=(30, 30, 30))
        path = os.path.join(self.tmp, name)
        im.save(path)
        return path

    @staticmethod
    def review(d, by, items, blind=False):
        d.setdefault("reviews", []).append({"id": f"r{len(d['reviews']) + 1}", "by": by, "blind": blind,
                                            "items": items})


class TestFacts(Base):
    def test_the_makers_own_words_found_in_its_page_grade_A(self):
        d = self.dossier()
        self.row(202, MAKER, quote="LENGTH (OVERALL)* 202 mm | 7.95 inch")
        f = self.graded(d)
        self.assertEqual((f["grade"], f["value"]), ("A", 202.0))
        self.assertEqual(f["rows"][0]["quote_check"], "verified")

    def test_a_typed_number_the_source_does_not_say_is_dropped(self):
        d = self.dossier()
        self.row(204, MAKER, quote="LENGTH (OVERALL)* 204 mm")  # (a model's memory: the page says 202)
        self.row(186, MAKER, part="slide", quote="SLIDE LENGTH 186 mm | 7.32 inch")
        self.row(25.0, MAKER, part="slide", dim="width", quote="SLIDE WIDTH 25,5 mm")  # (the quote, a wrong number)
        f = self.graded(d)
        self.assertIsNone(f["grade"])
        self.assertTrue(f["rows"][0]["quote_check"].startswith("failed"))
        self.assertEqual(self.graded(d, "slide.length")["grade"], "A")
        self.assertTrue(self.graded(d, "slide.width")["rows"][0]["quote_check"].startswith("failed (the number"))

    def test_quotes_hold_numbers_in_any_unit_the_source_writes(self):
        self.assertTrue(D.value_in(202, "mm", "7.95 inch"))
        self.assertTrue(D.value_in(25.5, "mm", "SLIDE WIDTH 25,5 mm"))
        self.assertTrue(D.value_in(0.63, "kg", "630 g | 22.22 oz"))
        self.assertFalse(D.value_in(202, "mm", "201 mm"))  # (a near number is not the number)
        self.assertEqual(D.numbers_in("1,000 rounds, 25,5 mm and 4.49 in."), [1000.0, 25.5, 4.49])

    def test_two_independent_sites_agreeing_grade_B_one_site_twice_is_C(self):
        d = self.dossier()
        self.row(202, "https://en.wikipedia.org/wiki/Glock", kind="wikipedia")
        self.row(202, "https://www.wikidata.org/wiki/Q1", kind="wikidata")
        self.assertEqual(self.graded(d)["grade"], "C")  # (Wikidata copies Wikipedia: one site — the Gen4 204 mm path)
        mag = "https://www.example-magazine.com/g17-gen5-review"
        self.page(mag, "Specifications: overall length 202 mm, barrel 114 mm.")
        self.row(202, mag, quote="overall length 202 mm")
        self.assertEqual(self.graded(d)["grade"], "B")
        d2 = self.dossier(object="glock 19 gen5", slug="glock_19_gen5", identity={"aliases": [], "tells": []})
        self.row(185, "https://en.wikipedia.org/wiki/Glock", obj="glock 19 gen5", kind="wikipedia")
        self.row(185.2, "https://de.wikipedia.org/wiki/Glock", obj="glock 19 gen5", kind="wikipedia")
        self.assertEqual(self.graded(d2)["grade"], "C")  # (wikipedia twice is one site)

    def test_the_familys_number_is_named_as_another_variants_never_used(self):
        d = self.dossier()
        self.row(202, MAKER, quote="LENGTH (OVERALL)* 202 mm")
        self.row(204, "https://www.wikidata.org/wiki/Q1", obj="glock 17", kind="wikidata")
        f = self.graded(d)
        self.assertEqual((f["grade"], f["value"]), ("A", 202.0))
        self.assertTrue(any("family" in n and "204" in n for n in f["notes"]), f["notes"])

    def test_a_primary_source_outvotes_secondaries_but_primaries_that_disagree_are_D(self):
        d = self.dossier()
        self.row(202, MAKER, quote="LENGTH (OVERALL)* 202 mm")
        self.row(204, "https://www.wikidata.org/wiki/Q2", kind="wikidata")
        f = self.graded(d)
        self.assertEqual(f["grade"], "A")
        self.assertTrue(any(n.startswith("outvoted 204") for n in f["notes"]), f["notes"])
        self.page(MANUAL, "LENGTH 210 mm")
        self.row(210, MANUAL, quote="LENGTH 210 mm")
        self.assertEqual(self.graded(d)["grade"], "D")

    def test_secondary_sites_that_disagree_are_D(self):
        d = self.dossier()
        self.row(202, "https://en.wikipedia.org/wiki/Glock", kind="wikipedia")
        self.row(204, "https://www.wikidata.org/wiki/Q1", kind="wikidata")
        self.assertEqual(self.graded(d)["grade"], "D")

    def test_an_unquoted_typed_row_counts_only_after_two_keys_one_blind_one_not_its_adder(self):
        d = self.dossier()
        rid = self.row(202, MAKER, by="opus@claude-code")  # (no quote: a model typed it)
        self.assertEqual(self.graded(d)["grade"], "C")
        self.review(d, "opus@claude-code", {f"row:{rid}": {"verdict": "accept", "why": "the page says it"}})
        self.review(d, "sonnet@claude-code", {f"row:{rid}": {"verdict": "accept", "why": "202 mm"}})
        self.assertEqual(self.graded(d)["grade"], "C")  # (two keys, nobody blind)
        self.review(d, "opus-fresh@claude-code", {f"row:{rid}": {"verdict": "accept", "why": "202 mm"}}, blind=True)
        self.assertEqual(self.graded(d)["grade"], "A")

    def test_a_blocked_site_counts_for_nothing_and_cannot_be_added(self):
        d = self.dossier()
        farm = "https://tr.arktimes.com/?p=7754"
        self.assertEqual(D.tier_of(farm, d), "blocked")
        self.assertEqual(D.tier_of("https://some.blog.example/?p=4360", d), "suspect")
        self.assertEqual(D.tier_of(MANUAL, d), "primary")  # (the maker's own CDN folder)
        self.assertEqual(D.tier_of("https://eu-assets.contentstack.com/v3/assets/someone_else/x.pdf", d), "secondary")
        self.row(202, farm, kind="wikidata")
        self.assertIsNone(self.graded(d)["grade"])
        with self.assertRaises(ValueError):
            D._refuse_blocked(d, farm)


class TestReviews(Base):
    def test_one_reject_drops_an_item_unless_another_accepts_then_a_third_decides(self):
        d = self.dossier()
        self.review(d, "a", {"e1": {"verdict": "reject", "why": "gen4"}})
        self.assertEqual(D.item_status(d, "e1"), "rejected")
        self.review(d, "b", {"e1": {"verdict": "accept", "view": "side-left", "why": "gen5"}}, blind=True)
        self.assertEqual(D.item_status(d, "e1"), "disputed")
        self.review(d, "c", {"e1": {"verdict": "accept", "view": "side-left", "why": "no finger grooves"}})
        self.assertEqual(D.item_status(d, "e1", views=True), "confirmed")

    def test_two_keys_must_agree_on_the_view(self):
        d = self.dossier()
        self.review(d, "a", {"e1": {"verdict": "accept", "view": "side-left", "why": "x"}})
        self.review(d, "b", {"e1": {"verdict": "accept", "view": "side-right", "why": "x"}}, blind=True)
        self.assertEqual(D.item_status(d, "e1", views=True), "disputed")

    def test_the_owners_photo_needs_one_review(self):
        d = self.dossier()
        self.review(d, "a", {"e1": {"verdict": "accept", "view": "side-left", "why": "x"}})
        self.assertEqual(D.item_status(d, "e1", need=1), "confirmed")
        self.assertEqual(D.item_status(d, "e1"), "pending")

    def test_answers_are_validated(self):
        d = self.dossier(evidence=[{"id": "e1", "kind": "picture", "scope": "measure-only"},
                                   {"id": "e2", "kind": "picture", "scope": "measure-only"}])
        for e in d["evidence"]:
            e["page"] = MAKER
        body, *_ = D.packet(d, "a")
        pk = body["packet"]
        n, problems = D.apply_answers(d, {"packet": pk, "items": {
            "e1": {"verdict": "accept", "variant": "wrong", "view": "side-left", "square": True, "why": "a gen4"},
            "e9": {"verdict": "accept", "why": "x"}}}, "a")
        self.assertEqual(n, 0)
        self.assertEqual(len(problems), 2, problems)
        n, problems = D.apply_answers(d, {"packet": pk, "items": {"e1": {
            "verdict": "limited", "view": "side-left", "square": True, "good_for": ["closeup:nope"], "why": "x"}}}, "a")
        self.assertEqual(n, 0)
        self.assertIn("unknown good_for", problems[0])
        n, problems = D.apply_answers(d, {"packet": pk, "items": {"e1": {
            "verdict": "limited", "view": "side-left", "square": True, "good_for": ["closeup:magazine"],
            "why": "x"}}}, "a")
        n, problems = D.apply_answers(d, {"packet": pk, "items": {"e1": {"verdict": "limited", "variant": "wrong",
                                                                         "view": "side-left", "square": True,
                                                                         "good_for": ["closeup:magazine"],
                                                                         "why": "a gen4 frame; the same magazine"},
                                                                  "e2": {"verdict": "?"}}}, "a")
        self.assertEqual((n, problems), (1, []))

    def test_a_blind_packet_hides_the_claims_and_the_earlier_verdicts(self):
        d = self.dossier()
        pic = self.picture("p.png", 202, 139)
        d["evidence"].append({"id": "e1", "kind": "picture", "scope": "measure-only", "file": pic,
                              "claimed": {"view": "side-left"}, "by": "a"})
        self.review(d, "a", {"e1": {"verdict": "accept", "view": "side-left", "why": "x"}})
        body, *_ = D.packet(d, "b", blind=True)
        it = next(i for i in body["items"] if i["id"] == "e1")
        self.assertNotIn("claimed", it)
        self.assertNotIn("earlier", it)
        self.assertTrue(body["blind"])
        open_body, *_ = D.packet(d, "c", blind=False)
        self.assertIn("claimed", next(i for i in open_body["items"] if i["id"] == "e1"))
        mine, *_ = D.packet(d, "a")
        self.assertFalse(any(i["id"] == "e1" for i in mine["items"]))  # (a reviewer never answers twice)

class TestEvidence(Base):
    def test_a_side_picture_is_measured_against_the_facts(self):
        d = self.dossier()
        self.row(202, MAKER, quote="LENGTH (OVERALL)* 202 mm")
        self.row(139, MAKER, dim="height incl. magazine", quote="HEIGHT INCL. MAG. 139 mm")
        good, short = self.picture("good.png", 202, 139), self.picture("short.png", 188, 139)  # (7% short)
        for i, p in enumerate((good, short)):
            d["evidence"].append({"id": f"e{i + 1}", "kind": "picture", "scope": "measure-only", "file": p,
                                  "claimed": {"view": "side-left"}})
        rep = D.check(d, offline=True)
        e1, e2 = rep["evidence"]
        self.assertAlmostEqual(e1["metrics"]["px_per_mm"], 4.0, places=1)
        self.assertLess(abs(e1["metrics"]["aspect_off"]), 0.01)
        self.assertFalse(any("proportions" in f for f in e1["flags"]))
        self.assertTrue(any("proportions off by -6.9%" in f for f in e2["flags"]), e2["flags"])

    def test_a_reference_model_with_a_short_scan_is_flagged(self):
        d = self.dossier()
        self.row(202, MAKER, quote="LENGTH (OVERALL)* 202 mm")
        self.row(139, MAKER, dim="height incl. magazine", quote="HEIGHT INCL. MAG. 139 mm")
        self.row(34, MAKER, dim="width", quote="WIDTH (OVERALL) 34 mm")
        for name, size in (("good", [34.0, 139.0, 202.0]), ("short", [34.0, 139.0, 188.0])):
            with open(os.path.join(self.tmp, f"{name}.measure.json"), "w") as fh:
                json.dump({"size_mm": size}, fh)
            d["evidence"].append({"id": f"m_{name}", "kind": "model", "scope": "measure-only", "page": MAKER,
                                  "measure": os.path.join(self.tmp, f"{name}.measure.json")})
        rep = D.check(d, offline=True)
        good, short = rep["evidence"]
        self.assertEqual(good["flags"], [])
        self.assertTrue(any(f.startswith("length/height off by -6.9%") for f in short["flags"]), short["flags"])

    def test_the_same_picture_from_two_sites_is_one_picture(self):
        d = self.dossier()
        p = self.picture("a.png", 202, 139)
        q = os.path.join(self.tmp, "b.jpg")
        from PIL import Image

        Image.open(p).convert("RGB").resize((600, 450)).save(q, quality=80)
        d["evidence"] += [{"id": "e1", "kind": "picture", "scope": "measure-only", "file": p},
                          {"id": "e2", "kind": "picture", "scope": "measure-only", "file": q}]
        rep = D.check(d, offline=True)
        self.assertIn("the same picture as e1", rep["evidence"][1]["flags"])

    def test_two_different_slivers_on_white_are_two_pictures(self):
        from PIL import Image, ImageDraw

        d = self.dossier()
        paths = []
        for k, poly in enumerate(([(580, 100), (620, 100), (640, 800), (560, 800)],    # a grip seen from behind
                                  [(585, 120), (615, 120), (615, 790), (585, 790)])):  # a muzzle end, narrower
            im = Image.new("RGB", (1200, 900), (255, 255, 255))
            ImageDraw.Draw(im).polygon(poly, fill=(25, 25, 25))
            ImageDraw.Draw(im).ellipse([590, 140 + 300 * k, 610, 160 + 300 * k], fill=(200, 200, 200))
            paths.append(os.path.join(self.tmp, f"end{k}.png"))
            im.save(paths[-1])
        d["evidence"] += [{"id": f"e{k + 1}", "kind": "picture", "scope": "measure-only", "file": p}
                          for k, p in enumerate(paths)]
        rep = D.check(d, offline=True)
        self.assertFalse(any("the same picture" in f for e in rep["evidence"] for f in e["flags"]))

    def test_a_picture_of_one_part_is_measured_against_that_parts_sizes(self):
        d = self.dossier()
        for part, dim, mm, q in (("overall", "length", 202, "LENGTH (OVERALL)* 202 mm"),
                                 ("overall", "width", 34, "WIDTH (OVERALL) 34 mm"),
                                 ("slide", "length", 186, "SLIDE LENGTH 186 mm"),
                                 ("slide", "width", 25.5, "SLIDE WIDTH 25,5 mm")):
            self.row(mm, MAKER, part=part, dim=dim, quote=q)
        top = self.picture("slide_top.png", 186, 25.5)  # (a patent's top view: the slide alone)
        d["evidence"] += [{"id": "e1", "kind": "drawing", "scope": "measure-only", "file": top,
                           "claimed": {"view": "top"}},
                          {"id": "e2", "kind": "drawing", "scope": "measure-only", "file": top, "of": "slide",
                           "claimed": {"view": "top"}}]
        e1, e2 = D.check(d, offline=True)["evidence"]
        self.assertTrue(any("proportions off by +2" in f for f in e1["flags"]), e1["flags"])  # (against 202 x 34)
        self.assertLess(abs(e2["metrics"]["aspect_off"]), 0.01)
        self.assertEqual(e2["metrics"]["measured_against"], "the slide's own sizes")

    def test_the_wrong_variant_never_covers_a_view(self):
        d = self.dossier()
        self.row(202, MAKER, quote="LENGTH (OVERALL)* 202 mm")
        self.row(139, MAKER, dim="height incl. magazine", quote="HEIGHT INCL. MAG. 139 mm")
        d["evidence"].append({"id": "e1", "kind": "picture", "scope": "measure-only", "page": MAKER,
                              "file": self.picture("s.png", 202, 139), "by": "a"})
        for by, blind in (("a", False), ("b", True)):
            self.review(d, by, {"e1": {"verdict": "limited", "view": "side-left", "square": True, "variant": "wrong",
                                       "good_for": ["outline:slide"], "why": "a gen4"}}, blind=blind)
        rep = D.check(d, offline=True)
        self.assertEqual(rep["evidence"][0]["status"], "confirmed")
        self.assertEqual(rep["coverage"]["views"]["side-left"], [])

    def test_coverage_counts_only_confirmed_square_pictures_at_enough_px_per_mm(self):
        d = self.dossier()
        self.row(202, MAKER, quote="LENGTH (OVERALL)* 202 mm")
        self.row(139, MAKER, dim="height incl. magazine", quote="HEIGHT INCL. MAG. 139 mm")
        d["evidence"].append({"id": "e1", "kind": "picture", "scope": "measure-only", "page": MAKER,
                              "file": self.picture("s.png", 202, 139), "by": "a"})
        self.assertEqual(D.check(d, offline=True)["coverage"]["views"]["side-left"], [])
        self.review(d, "a", {"e1": {"verdict": "accept", "view": "side-left", "good_for": ["silhouette"], "why": "x"}})
        self.review(d, "b", {"e1": {"verdict": "accept", "view": "side-left", "good_for": ["silhouette"],
                                    "why": "x"}}, blind=True)
        self.assertEqual(D.check(d, offline=True)["coverage"]["views"]["side-left"], [])  # (nobody said square-on)
        self.review(d, "a", {"e1": {"verdict": "accept", "view": "side-left", "square": True, "why": "x"}})
        self.review(d, "b", {"e1": {"verdict": "accept", "view": "side-left", "square": False, "why": "x"}}, blind=True)
        self.assertEqual(D.check(d, offline=True)["coverage"]["views"]["side-left"], [])  # (they disagree)
        self.review(d, "b", {"e1": {"verdict": "accept", "view": "side-left", "square": True, "why": "x"}}, blind=True)
        self.assertEqual(D.check(d, offline=True)["coverage"]["views"]["side-left"], [])  # (nobody said the variant)
        for by, blind in (("a", False), ("b", True)):
            self.review(d, by, {"e1": {"verdict": "accept", "view": "side-left", "square": True, "variant": "ok",
                                       "why": "x"}}, blind=blind)
        self.assertEqual(D.check(d, offline=True)["coverage"]["views"]["side-left"], ["e1"])


class TestApprovalAndCli(Base):
    def test_an_approval_goes_stale_when_a_graded_fact_changes(self):
        d = self.dossier()
        self.row(202, MAKER, quote="LENGTH (OVERALL)* 202 mm")
        d["approval"] = {"by": "owner", "sheet_sha": D.sheet_sha(d)}
        self.assertEqual(D.approval_state(d), {**D.approval_state(d), "approved": True, "stale": False})
        self.row(186, MAKER, part="slide", quote="SLIDE LENGTH 186 mm")
        self.assertTrue(D.approval_state(d)["stale"])

    def run_cli(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = D.main(list(argv))
        return code, json.loads(out.getvalue().strip().splitlines()[-1])

    def test_from_a_name_to_an_approved_dossier(self):
        code, r = self.run_cli("new", "Glock 17 Gen5", "--category", "pistol", "--maker-domain", "glock.com",
                               "--alias", "G17 Gen5", "--private", "--as", "opus@claude-code")
        self.assertEqual(code, 0, r)
        code, r = self.run_cli("fact", "glock 17 gen5", "--dim", "length", "--mm", "202", "--source", MAKER,
                               "--quote", "LENGTH (OVERALL)* 202 mm | 7.95 inch", "--as", "opus@claude-code")
        self.assertEqual((code, r["quote_check"]), (0, "verified"), r)
        code, r = self.run_cli("fact", "glock 17 gen5", "--dim", "length", "--mm", "203", "--source", MAKER,
                               "--quote", "LENGTH 203 mm", "--as", "opus@claude-code")
        self.assertEqual(code, 1, r)  # (said plainly: the page does not say it)
        code, r = self.run_cli("part", "glock 17 gen5", "--name", "Slide", "--no", "1", "--source", MANUAL,
                               "--quote", "1 Slide", "--as", "opus@claude-code")
        self.assertEqual((code, r["quote_check"]), (0, "verified"), r)
        code, r = self.run_cli("tell", "glock 17 gen5", "--text", "front slide serrations", "--vs", "glock 17 gen4",
                               "--source", "https://example.org/gen5", "--as", "opus@claude-code")
        self.assertEqual(r["quote_check"], "unquoted")
        code, r = self.run_cli("review", "glock 17 gen5", "--as", "fresh@claude-code", "--blind")
        self.assertEqual(code, 0, r)
        with open(r["answers"], encoding="utf-8") as fh:
            answers = json.load(fh)
        self.assertIn("t1", answers["items"])
        answers["items"]["t1"] = {"verdict": "accept", "why": "the maker's Gen5 page lists front serrations"}
        with open(r["answers"], "w", encoding="utf-8") as fh:
            json.dump(answers, fh)
        code, r = self.run_cli("review", "glock 17 gen5", "--apply", r["answers"], "--as", "fresh@claude-code")
        self.assertEqual(code, 0, r)
        d = D.load("g17 gen5")  # (an alias finds it too)
        self.assertTrue(d["reviews"][0]["blind"])
        code, r = self.run_cli("approve", "glock 17 gen5", "--as", "opus@claude-code", "--note", "x")
        self.assertEqual(code, 1)  # (only the owner approves)
        code, r = self.run_cli("sheet", "glock 17 gen5", "--offline")
        self.assertEqual(code, 0, r)
        with open(r["sheet"], encoding="utf-8") as fh:
            self.assertIn("202 mm", fh.read())
        code, r = self.run_cli("approve", "glock 17 gen5", "--as", "owner", "--note", "owner said yes in chat")
        self.assertEqual(code, 1, r)  # (no --sheet: which sheet did the owner see?)
        shown = D.sheet_id(D.check(D.load("glock 17 gen5"), offline=True))
        code, r = self.run_cli("approve", "glock 17 gen5", "--as", "owner", "--sheet", shown, "--note", "owner: yes")
        self.assertEqual(code, 0, r)
        s = D.summary_for("glock 17 gen5")
        self.assertTrue(s["approved"])
        self.assertFalse(s["stale"])
        self.assertEqual(s["facts"]["overall.length"]["grade"], "A")



class TestReviewFindings(Base):
    """each confirmed finding of the fresh-context review (2026-10-08), kept fixed"""

    def test_a_kind_label_never_skips_the_quote_check(self):
        d = self.dossier()
        self.row(250, MAKER, kind="wikipedia", read_by=None)  # (labelled wikipedia: a typed number on the maker's site)
        f = self.graded(d)
        self.assertEqual(f["grade"], "C")
        self.assertEqual(f["rows"][0]["quote_check"], "unquoted")

    def test_a_file_path_is_no_owner_and_only_the_owner_is_the_owner(self):
        d = self.dossier()
        note = os.path.join(self.tmp, "my_note.txt")
        with open(note, "w") as fh:
            fh.write("length 250 mm")
        self.row(250, note, kind="measured", quote="length 250 mm")
        self.assertIsNone(self.graded(d)["grade"])  # (a local path counts for nothing)
        self.row(202, "owner", kind="measured", by="owner")
        self.assertEqual(self.graded(d)["grade"], "A")
        with self.assertRaises(ValueError):
            D._resolve_source(d, "owner", by="opus@claude-code")
        with self.assertRaises(ValueError):
            D._resolve_source(d, note, by="opus@claude-code")

    def test_one_site_is_one_vote_whatever_its_spelling(self):
        self.assertEqual(D.site("https://x.example.com./a"), "example.com")
        self.assertEqual(D.site("https://web.archive.org/web/2024/https://eu.glock.com/en/x"), "glock.com")
        self.assertEqual(D.site("https://www.wikidata.org/wiki/Q1"), D.site("https://en.wikipedia.org/wiki/G"))
        d = self.dossier()
        self.assertEqual(D.tier_of("https://data.mbrp.com./?p=1", d), "blocked")
        self.assertEqual(D.tier_of("https://web.archive.org/web/2024/https://eu.glock.com/en/x", d), "primary")

    def test_quotes_are_whole_words_long_enough_and_about_the_item(self):
        self.assertFalse(D.quote_in("length 20", "the overall length 202 mm")[0])
        self.assertFalse(D.quote_in("mm", "202 mm")[0])
        self.assertTrue(D.quote_in("1 Slide", "Component parts 1 Slide 2 Barrel")[0])
        self.assertFalse(D.value_in(202, "mm", "weight 202 g"))
        self.assertTrue(D.value_in(0.63, "kg", "Weight without magazine 630 g | 22.22 oz"))
        self.assertTrue(D.check_quote(MAKER, "SLIDE LENGTH 186 mm", about="no finger grooves").startswith(
            "failed (the quote does not share two words"))
        d = self.dossier()
        code, r = self.cli("part", "glock 17 gen5", "--name", "Slide", "--no", "1", "--source", MANUAL, "--quote",
                           "1 Slide", "--as", "a")
        self.assertEqual(code, 0, r)
        code, r = self.cli("part", "glock 17 gen5", "--name", "Slide", "--no", "1", "--source", MANUAL, "--quote",
                           "1 Slide", "--as", "a")
        self.assertEqual(code, 1, r)  # (one part, once)
        code, r = self.cli("tell", "glock 17 gen5", "--text", "no finger grooves", "--source", MAKER, "--quote",
                           "SLIDE LENGTH 186 mm", "--as", "a")
        self.assertEqual(code, 1, r)
        self.assertEqual(len(D.load("glock 17 gen5")["identity"]["tells"]), 0)  # (a failed quote is never stored)

    def cli(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = D.main(list(argv))
        return code, json.loads(out.getvalue().strip().splitlines()[-1])

    def two_keys(self, d, iid, **v):
        for by, blind in (("a", False), ("b", True)):
            self.review(d, by, {iid: {"verdict": "accept", "view": "side-left", "square": True, "variant": "ok",
                                      "good_for": ["closeup:sights"], "why": "x", **v}}, blind=blind)

    def test_blocked_suspect_and_pathless_evidence_counts_for_nothing(self):
        d = self.dossier()
        self.row(202, MAKER, quote="LENGTH (OVERALL)* 202 mm")
        self.row(139, MAKER, dim="height incl. magazine", quote="HEIGHT INCL. MAG. 139 mm")
        pic = self.picture("s.png", 202, 139)
        for i, page in enumerate(("https://some.blog.example/?p=12", "https://tr.arktimes.com/x", None)):
            d["evidence"].append({"id": f"e{i + 1}", "kind": "picture", "scope": "measure-only", "file": pic,
                                  **({"page": page} if page else {})})
            self.two_keys(d, f"e{i + 1}")
        rep = D.check(d, offline=True)
        self.assertEqual(rep["coverage"]["views"]["side-left"], [])
        self.assertEqual(rep["coverage"]["closeups"]["sights"], [])
        self.assertTrue(all(not e["counts"] for e in rep["evidence"]))

    def test_the_blind_flag_cannot_be_forged(self):
        d = self.dossier()
        d["evidence"].append({"id": "e1", "kind": "picture", "scope": "measure-only", "page": MAKER,
                              "file": self.picture("s.png", 202, 139), "claimed": {"view": "side-left"}})
        fake = os.path.join(self.tmp, "fake.json")
        with open(fake, "w") as fh:
            json.dump({"blind": True, "by": "b", "items": [{"id": "e1"}]}, fh)
        ans = {"verdict": "accept", "view": "side-left", "square": True, "why": "x"}
        for packet_id in (fake, "0123456789ab", None):
            n, problems = D.apply_answers(d, {"packet": packet_id, "items": {"e1": ans}}, "b")
            self.assertEqual(n, 0, packet_id)
        body, path, *_ = D.packet(d, "b", blind=True)
        n, problems = D.apply_answers(d, {"packet": body["packet"], "items": {"e1": ans}}, "c")
        self.assertEqual(n, 0)  # (another reviewer's packet)
        with open(path, encoding="utf-8") as fh:
            tampered = json.load(fh)
        tampered["items"].append({"id": "e9"})
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(tampered, fh)
        n, problems = D.apply_answers(d, {"packet": body["packet"], "items": {"e1": ans}}, "b")
        self.assertEqual(n, 0)
        self.assertIn("changed after it was made", problems[0])

    def test_an_open_reviewer_cannot_turn_blind_on_the_same_item(self):
        d = self.dossier()
        d["evidence"].append({"id": "e1", "kind": "picture", "scope": "measure-only", "page": MAKER,
                              "file": self.picture("s.png", 202, 139)})
        ans = {"verdict": "accept", "view": "side-left", "square": True, "why": "x"}
        body, *_ = D.packet(d, "a")
        self.assertEqual(D.apply_answers(d, {"packet": body["packet"], "items": {"e1": ans}}, "a")[0], 1)
        blind, *_ = D.packet(d, "a", blind=True)
        self.assertEqual(blind["items"], [])
        n, problems = D.apply_answers(d, {"packet": blind["packet"], "items": {"e1": ans}}, "a")
        self.assertEqual(n, 0)
        self.assertIn("not in packet", problems[0])

    def test_a_blind_packet_says_nothing_that_depends_on_the_claimed_view(self):
        d = self.dossier()
        self.row(202, MAKER, quote="LENGTH (OVERALL)* 202 mm")
        self.row(139, MAKER, dim="height incl. magazine", quote="HEIGHT INCL. MAG. 139 mm")
        d["evidence"].append({"id": "e1", "kind": "picture", "scope": "measure-only", "page": MAKER,
                              "file": self.picture("short.png", 188, 139), "claimed": {"view": "side-left"}})
        body, *_ = D.packet(d, "b", blind=True)
        it = body["items"][0]
        self.assertFalse(set(it["metrics"]) - set(D.BLIND_METRICS), it["metrics"])
        self.assertFalse([f for f in it["flags"] if "side-left" in f or "proportions" in f], it["flags"])

    def test_staleness_follows_every_graded_field_and_the_site_list(self):
        d = self.dossier()
        rid = self.row(202, MAKER, quote="LENGTH (OVERALL)* 202 mm")
        d["approval"] = {"by": "owner", "sheet_sha": D.sheet_sha(d)}
        rows_file = os.path.join(dims.STORE, "glock_17_gen5.json")
        with open(rows_file, encoding="utf-8") as fh:
            rows = json.load(fh)
        rows[0]["kind"] = "drawing"
        with open(rows_file, "w", encoding="utf-8") as fh:
            json.dump(rows, fh)
        self.assertTrue(D.approval_state(d)["stale"], rid)
        key = D.check_key(d)
        reg = os.path.join(D.KNOW, "sources.json")
        with open(reg, encoding="utf-8") as fh:
            sites = json.load(fh)
        sites["blocked"]["glock.com"] = "test"
        with open(reg, "w", encoding="utf-8") as fh:
            json.dump(sites, fh)
        self.assertNotEqual(D.check_key(d), key)

    def test_a_changed_or_broken_picture_is_said_never_a_crash(self):
        d = self.dossier()
        pic = self.picture("s.png", 202, 139)
        broken = os.path.join(self.tmp, "broken.jpg")
        with open(broken, "wb") as fh:
            fh.write(b"not a picture at all")
        d["evidence"] += [{"id": "e1", "kind": "picture", "scope": "measure-only", "page": MAKER, "file": pic,
                           "file_sha256": "0" * 64},
                          {"id": "e2", "kind": "picture", "scope": "measure-only", "page": MAKER, "file": broken}]
        e1, e2 = D.check(d, offline=True)["evidence"]
        self.assertTrue(any("changed since" in f for f in e1["flags"]))
        self.assertTrue(any("unreadable" in f for f in e2["flags"]))

    def test_models_need_their_proportions_proven_and_reviewers_must_all_state_a_key(self):
        d = self.dossier()
        with open(os.path.join(self.tmp, "m.measure.json"), "w") as fh:
            json.dump({"size_mm": [34.0, 139.0, 202.0]}, fh)
        d["evidence"].append({"id": "m1", "kind": "model", "scope": "measure-only", "page": MAKER,
                              "measure": os.path.join(self.tmp, "m.measure.json")})
        for by, blind in (("a", False), ("b", True)):
            self.review(d, by, {"m1": {"verdict": "accept", "variant": "ok", "why": "x"}}, blind=blind)
        self.assertEqual(D.check(d, offline=True)["coverage"]["models"], [])  # (no facts: proportions unproven)
        self.review(d, "a", {"e9": {"verdict": "accept", "square": True, "why": "x"}})
        self.review(d, "b", {"e9": {"verdict": "accept", "why": "x"}}, blind=True)
        self.assertIsNone(D.agreed(d, "e9", "square"))  # (one voice is no agreement)

    def test_another_departments_knowledge_file_is_not_a_broken_dossier(self):
        # (kit/knowledge holds other lanes' files too — sfx_taste.json made every prop's plan say "cannot be read")
        os.makedirs(D.PRIVATE, exist_ok=True)
        with open(os.path.join(D.PRIVATE, "taste.json"), "w") as fh:
            json.dump({"verdicts": [], "leans": {}, "note": "a sound department's file"}, fh)
        self.assertIsNone(D.summary_for("a red fire hydrant"))

    def test_a_hand_broken_dossier_is_said_not_taken_for_none(self):
        os.makedirs(D.PRIVATE, exist_ok=True)
        with open(os.path.join(D.PRIVATE, "broken_thing.json"), "w") as fh:
            fh.write("{not json")
        with self.assertRaises(D.Broken):
            D.summary_for("broken thing")
        with open(os.path.join(D.PRIVATE, "broken_thing.json"), "w") as fh:
            json.dump({"schema": 1, "object": "broken thing", "slug": "broken_thing", "evidence": [{"kind": "x"}]},
                      fh)
        with self.assertRaises(D.Broken):
            D.load("broken thing")
        code, r = self.cli("review", "broken thing", "--apply")
        self.assertEqual(code, 1)

    def test_a_single_reject_gets_a_second_look_two_are_final(self):
        d = self.dossier()
        d["evidence"].append({"id": "e1", "kind": "picture", "scope": "measure-only", "page": MAKER,
                              "file": self.picture("s.png", 202, 139)})
        self.review(d, "a", {"e1": {"verdict": "reject", "why": "x"}})
        body, *_ = D.packet(d, "b", blind=True)
        self.assertEqual([i["id"] for i in body["items"]], ["e1"])
        self.review(d, "b", {"e1": {"verdict": "reject", "why": "x"}}, blind=True)
        body, *_ = D.packet(d, "c", blind=True)
        self.assertEqual(body["items"], [])

    def test_withdrawn_items_count_for_nothing(self):
        d = self.dossier()
        code, r = self.cli("part", "glock 17 gen5", "--name", "Slide", "--no", "1", "--source", MANUAL, "--quote",
                           "1 Slide", "--as", "a")
        self.assertEqual(code, 0, r)
        code, r = self.cli("withdraw", "glock 17 gen5", "p1", "--why", "wrong list", "--as", "a")
        self.assertEqual(code, 0, r)
        rep = D.check(D.load("glock 17 gen5"), offline=True)
        self.assertEqual(rep["parts"], [])



class TestReReviewFindings(Base):
    """the second fresh-context review (2026-10-08): each finding, kept fixed"""

    cli = TestReviewFindings.cli

    def test_a_facts_quote_names_its_part_and_dim_and_its_number_has_its_unit(self):
        self.assertTrue(D.check_quote(MAKER, "SLIDE LENGTH 186 mm", 186, fact=("barrel", "length")).startswith(
            "failed (the quote does not name barrel length"))
        self.assertTrue(D.check_quote(MAKER, "LENGTH (OVERALL)* 202 mm", 0.202, "kg", fact=("overall", "mass"))
                        .startswith("failed"))
        self.assertTrue(D.check_quote(MAKER, "7.95 inch 2 SLIDE LENGTH", 2, fact=("slide", "length")).startswith(
            "failed"))
        self.assertEqual(D.check_quote(MAKER, "SLIDE LENGTH 186 mm", 186, fact=("slide", "length")), "verified")
        self.page("https://g.example/x", "Weight without magazine 630 g | 22.22 oz")
        self.assertEqual(D.check_quote("https://g.example/x", "Weight without magazine 630 g", 0.63, "kg",
                                       fact=("overall", "mass without magazine")), "verified")

    def test_a_decimal_comma_or_point_is_no_word_edge(self):
        self.assertFalse(D.quote_in("SLIDE WIDTH 25", PAGE)[0])
        self.assertFalse(D.quote_in("5 mm | 1.00 inch", PAGE)[0])
        self.assertTrue(D.quote_in("SLIDE WIDTH 25,5 mm", PAGE)[0])

    def test_an_items_quote_shares_two_of_its_words(self):
        self.assertTrue(D.check_quote(MAKER, "SLIDE LENGTH 186 mm", about="front slide serrations").startswith(
            "failed"))
        self.assertEqual(D.check_quote(MANUAL, "1 Slide 2 Barrel", about="Slide"), "verified")

    def test_one_part_name_once_whatever_its_number(self):
        self.dossier()
        self.assertEqual(self.cli("part", "glock 17 gen5", "--name", "Slide", "--no", "1", "--source", MANUAL,
                                  "--quote", "1 Slide", "--as", "a")[0], 0)
        self.assertEqual(self.cli("part", "glock 17 gen5", "--name", "Slide", "--no", "2", "--source", MANUAL,
                                  "--quote", "1 Slide", "--as", "a")[0], 1)

    def test_the_owners_evidence_is_added_for_the_owner_and_a_page_is_a_web_address(self):
        d = self.dossier()
        pic = self.picture("p.png", 202, 139)
        with self.assertRaisesRegex(ValueError, "for the owner"):
            D.add_evidence(d, ["--file", pic, "--scope", "owner"], "opus@claude-code")
        with self.assertRaisesRegex(ValueError, "web address"):
            D.add_evidence(d, ["--file", pic, "--scope", "measure-only", "--page", "owner"], "opus@claude-code")
        e = D.add_evidence(d, ["--file", pic, "--scope", "owner", "--note", "sent in chat"], "owner")
        self.assertEqual(e["scope"], "owner")

    def test_an_open_look_is_never_blind_later_and_the_adder_is_never_the_blind_key(self):
        d = self.dossier()
        d["evidence"].append({"id": "e1", "kind": "picture", "scope": "measure-only", "page": MAKER, "by": "adder",
                              "file": self.picture("s.png", 202, 139)})
        D.packet(d, "b")  # (b looks openly: the claims, the earlier verdicts)
        blind, *_ = D.packet(d, "b", blind=True)
        self.assertEqual(blind["items"], [])
        self.review(d, "adder", {"e1": {"verdict": "accept", "view": "side-left", "why": "x"}}, blind=True)
        self.review(d, "b", {"e1": {"verdict": "accept", "view": "side-left", "why": "x"}})
        self.assertEqual(D.item_status(d, "e1", "adder", views=True), "pending")

    def test_wayback_without_a_timestamp_is_still_its_original(self):
        d = self.dossier()
        self.assertEqual(D.site("https://web.archive.org/web/https://en.wikipedia.org/wiki/Glock"), "wikipedia.org")
        self.assertEqual(D.tier_of("https://web.archive.org/web/https://tr.arktimes.com/x", d), "blocked")
        self.assertEqual(D.tier_of("https:///nohost", d), "unknown")

    def test_a_dropped_rows_reason_never_replaces_the_facts_own(self):
        d = self.dossier()
        rid = self.row(165, "https://us.example-gun-site.com/g17", dim="length between sights")
        self.review(d, "a", {f"row:{rid}": {"verdict": "reject", "why": "the page answers 404"}})
        mag = "https://www.example-magazine.com/g17"
        self.page(mag, "Length Between Sights: 165 mm / 6.49 in.")
        self.row(165, mag, dim="length between sights", quote="Length Between Sights: 165 mm")
        f = self.graded(d, "overall.length between sights")
        self.assertEqual((f["grade"], f["why"]), ("C", "one source"))
        self.assertIn("rejected in review", f["notes"][0])

    def test_only_the_kits_own_reads_are_read(self):
        d = self.dossier()
        self.row(204, "https://en.wikipedia.org/wiki/Glock", kind="wikipedia", read_by=None)
        self.assertEqual(self.graded(d)["rows"][0]["quote_check"], "unquoted")

    def test_an_approval_goes_stale_when_a_grade_changes_without_any_input_changing(self):
        d = self.dossier()
        self.row(202, MAKER, quote="LENGTH (OVERALL)* 202 mm")
        rep_ = D.check(d, offline=True)
        d["approval"] = {"by": "owner", "sheet_sha": rep_["sheet_sha"], "outcome_sha": D.outcome_sha(rep_)}
        self.assertFalse(D.check(d, offline=True)["approval"]["stale"])
        reg = os.path.join(D.KNOW, "sources.json")
        with open(reg, encoding="utf-8") as fh:
            sites = json.load(fh)
        sites["blocked"]["glock.com"] = "test"
        with open(reg, "w", encoding="utf-8") as fh:
            json.dump(sites, fh)
        self.assertTrue(D.check(d, offline=True)["approval"]["stale"])

    def test_a_models_measurement_is_pinned_and_it_needs_the_right_variant(self):
        d = self.dossier()
        for dim, mm, q in (("length", 202, "LENGTH (OVERALL)* 202 mm"), ("width", 34, "WIDTH (OVERALL) 34 mm"),
                           ("height incl. magazine", 139, "HEIGHT INCL. MAG. 139 mm")):
            self.row(mm, MAKER, dim=dim, quote=q)
        m = os.path.join(self.tmp, "m.measure.json")
        with open(m, "w") as fh:
            json.dump({"size_mm": [34.0, 139.0, 202.0]}, fh)
        e = D.add_evidence(d, ["--kind", "model", "--measure", m, "--scope", "measure-only", "--page", MAKER], "x")
        for by, blind, var in (("a", False, "unsure"), ("b", True, "unsure")):
            self.review(d, by, {e["id"]: {"verdict": "accept", "variant": var, "why": "x"}}, blind=blind)
        self.assertEqual(D.check(d, offline=True)["coverage"]["models"], [])  # (unsure is not the right variant)
        for by, blind in (("a", False), ("b", True)):
            self.review(d, by, {e["id"]: {"verdict": "accept", "variant": "ok", "why": "x"}}, blind=blind)
        self.assertEqual(D.check(d, offline=True)["coverage"]["models"], [e["id"]])
        with open(m, "w") as fh:
            json.dump({"size_mm": [34.0, 139.0, 205.0]}, fh)
        rep_ = D.check(d, offline=True)
        self.assertEqual(rep_["coverage"]["models"], [])
        self.assertTrue(any("measurement changed" in f for f in rep_["evidence"][0]["flags"]))

    def test_odd_shapes_are_said_never_a_crash(self):
        d = self.dossier()
        m = os.path.join(self.tmp, "list.measure.json")
        with open(m, "w") as fh:
            json.dump([1, 2, 3], fh)
        d["evidence"].append({"id": "m1", "kind": "model", "scope": "measure-only", "page": MAKER, "measure": m})
        D.check(d, offline=True)
        d["evidence"].append({"id": "e1", "kind": "picture", "scope": "measure-only", "page": MAKER,
                              "file": self.picture("s.png", 202, 139)})
        body, *_ = D.packet(d, "a")
        for gf in (5, [5]):
            n, problems = D.apply_answers(d, {"packet": body["packet"], "items": {"e1": {
                "verdict": "accept", "view": "side-left", "square": True, "good_for": gf, "why": "x"}}}, "a")
            self.assertEqual(n, 0)
            self.assertTrue("good_for is a list of words" in problems[0] or "wrong kind of answer for good_for" in
                            problems[0], problems)

    def test_a_broken_file_is_said_when_no_dossier_names_the_object(self):
        os.makedirs(D.PRIVATE, exist_ok=True)
        with open(os.path.join(D.PRIVATE, "some_other_slug.json"), "w") as fh:
            fh.write("{broken")
        with self.assertRaises(D.Broken):
            D.summary_for("g17 gen5")



class TestThirdReviewFindings(Base):
    """the third fresh-context review (2026-10-08): each finding, kept fixed"""

    cli = TestReviewFindings.cli

    def test_the_label_stands_before_its_number_and_names_every_word_of_the_dim(self):
        page = PAGE + " Sight Radius POLYMER 165 mm | 6.50 inch Sight Radius STEEL 164 mm | 6.46 inch"
        self.page("https://g.example/spec", page + " Weight without magazine 630 g Weight with magazine 705 g")
        u = "https://g.example/spec"
        bad = (("LENGTH (OVERALL)* 202 mm | 7.95 inch 2 SLIDE LENGTH", 202, "mm", ("overall", "height")),
               ("Sight Radius STEEL 164 mm", 164, "mm", ("sights", "sight radius (polymer)")),
               ("Weight with magazine 705 g", 0.705, "kg", ("overall", "mass without magazine")),
               ("HEIGHT INCL. MAG. 139 mm", 139, "mm", ("overall", "height incl. magazine incl. sights")))
        for quote, v, unit, fact in bad:
            self.assertTrue(D.check_quote(u, quote, v, unit, fact=fact).startswith("failed"), quote)
        good = (("HEIGHT INCL. MAG. 139 mm | 5.47 inch", 139, "mm", ("overall", "height incl. magazine")),
                ("Sight Radius POLYMER 165 mm | 6.50 inch", 165, "mm", ("sights", "sight radius (polymer)")),
                ("Weight without magazine 630 g", 0.63, "kg", ("overall", "mass without magazine")),
                ("LENGTH (OVERALL)* 202 mm | 7.95 inch", 202, "mm", ("overall", "length")))
        for quote, v, unit, fact in good:
            self.assertEqual(D.check_quote(u, quote, v, unit, fact=fact), "verified", quote)

    def test_b_needs_agreement_end_to_end(self):
        d = self.dossier()
        for i, (v, q) in enumerate(((202, "overall length 202 mm"), (203.2, "overall length 8.0 in"),
                                    (204, "overall length 204 mm"))):
            u = f"https://site{i}.example/g17"
            self.page(u, f"Spec: {q}.")
            self.row(v, u, quote=q)
        self.assertEqual(self.graded(d)["grade"], "D")  # (202 | 203.2 | 204: the Gen5 / Gen4 split, not B 203.2)

    def test_a_part_is_named_in_full_once(self):
        d = self.dossier()
        self.page("https://g.example/parts", "24 Connector 25 Trigger spring 26 Trigger with trigger bar")
        u = "https://g.example/parts"
        self.assertEqual(self.cli("part", "glock 17 gen5", "--name", "Trigger bar", "--source", u, "--quote",
                                  "25 Trigger spring", "--as", "a")[0], 1)
        self.assertEqual(self.cli("part", "glock 17 gen5", "--name", "Trigger with trigger bar", "--no", "26",
                                  "--source", u, "--quote", "26 Trigger with trigger bar", "--as", "a")[0], 0)
        self.assertEqual(self.cli("part", "glock 17 gen5", "--name", "the trigger with trigger bar.", "--source", u,
                                  "--quote", "26 Trigger with trigger bar", "--as", "a")[0], 1)
        self.assertEqual(len(D.load("glock 17 gen5")["parts"]), 1)

    def test_a_given_box_is_checked_and_never_overrides_a_measured_one(self):
        d = self.dossier()
        pic = self.picture("s.png", 202, 139)  # (1200 x 900, plain white)
        for bad in ("0,0,inf,10", "0,0,1300,10", "50,50,40,60", "a,b,c,d"):
            with self.assertRaises(ValueError, msg=bad):
                D.add_evidence(d, ["--file", pic, "--scope", "measure-only", "--page", MAKER, "--box", bad], "a")
        e = D.add_evidence(d, ["--file", pic, "--scope", "measure-only", "--page", MAKER, "--box", "0,0,900,700"],
                           "a")
        self.assertEqual(D.picture_metrics(D._evidence_file(d, e), e["box"])["box_from"], "background")

    def test_close_ups_need_the_right_variant(self):
        d = self.dossier()
        d["evidence"].append({"id": "e1", "kind": "picture", "scope": "measure-only", "page": MAKER,
                              "file": self.picture("g.png", 202, 139)})
        for by, blind in (("a", False), ("b", True)):
            self.review(d, by, {"e1": {"verdict": "limited", "variant": "wrong", "view": "detail", "square": False,
                                       "good_for": ["closeup:grip_texture"], "why": "a gen4 grip"}}, blind=blind)
        self.assertEqual(D.check(d, offline=True)["coverage"]["closeups"]["grip_texture"], [])

    def test_the_owner_approves_the_outcomes_they_saw(self):
        d = self.dossier()
        self.row(202, MAKER, quote="LENGTH (OVERALL)* 202 mm")
        seen = D.sheet_id(D.check(d, offline=True))
        reg = os.path.join(D.KNOW, "sources.json")
        with open(reg, encoding="utf-8") as fh:
            sites = json.load(fh)
        sites["blocked"]["glock.com"] = "test"
        with open(reg, "w", encoding="utf-8") as fh:
            json.dump(sites, fh)
        self.assertNotEqual(D.sheet_id(D.check(d, offline=True)), seen)  # (a stale sheet id is refused by approve)

    def test_the_check_cache_follows_the_cached_pages(self):
        d = self.dossier()
        self.row(202, MAKER, quote="LENGTH (OVERALL)* 202 mm")
        key = D.check_key(d)
        import time  # noqa: PLC0415

        time.sleep(0.05)
        self.page(MAKER, "LENGTH (OVERALL)* 210 mm")
        self.assertNotEqual(D.check_key(d), key)

    def test_archive_mirrors_and_proxies_are_suspect(self):
        d = self.dossier()
        for u in ("https://archive.ph/AbCd1", "https://archive.today/2024/https://eu.glock.com/x",
                  "https://eu-glock-com.translate.goog/en/x", "https://webcache.googleusercontent.com/search?q=x"):
            self.assertEqual(D.tier_of(u, d), "suspect", u)

    def test_answers_need_a_recorded_packet_and_typed_fields(self):
        d = self.dossier()
        d["evidence"].append({"id": "e1", "kind": "picture", "scope": "measure-only", "page": MAKER,
                              "file": self.picture("s.png", 202, 139)})
        body, path, *_ = D.packet(d, "b")
        d["packets"] = []  # (a packet file the dossier never recorded)
        n, problems = D.apply_answers(d, {"packet": body["packet"], "items": {"e1": {
            "verdict": "accept", "view": "side-left", "square": True, "why": "x"}}}, "b")
        self.assertEqual(n, 0)
        self.assertIn("not recorded", problems[0])
        body, *_ = D.packet(d, "b")
        n, problems = D.apply_answers(d, {"packet": body["packet"], "items": {"e1": {
            "verdict": "accept", "view": ["side-left"], "square": True, "why": "x"}}}, "b")
        self.assertEqual(n, 0)
        self.assertIn("wrong kind of answer", problems[0])

    def test_a_source_is_a_web_address(self):
        d = self.dossier()
        self.assertEqual(self.cli("source", "glock 17 gen5", "--url", "owner", "--kind", "other", "--as", "a")[0], 1)
        d = D.load("glock 17 gen5")
        d["sources"].append({"id": "s9", "url": "owner"})
        with self.assertRaises(ValueError):
            D._resolve_source(d, "s9", by="a")



class TestFinalReviewFindings(Base):
    """the final review (2026-10-08): honest mistakes and real formats"""

    cli = TestReviewFindings.cli

    def test_a_forgotten_part_never_makes_an_overall_size(self):
        self.dossier()
        code, r = self.cli("fact", "glock 17 gen5", "--dim", "length", "--mm", "114", "--source", MAKER, "--quote",
                           "Barrel Length 114 mm | 4.49 inch", "--as", "a")
        self.assertEqual(code, 1, r)  # (no --part: overall — but the label names the barrel)
        self.page(MAKER, PAGE + " Barrel Length 114 mm | 4.49 inch")
        code, r = self.cli("fact", "glock 17 gen5", "--part", "barrel", "--dim", "length", "--mm", "114", "--source",
                           MAKER, "--quote", "Barrel Length 114 mm | 4.49 inch", "--as", "a")
        self.assertEqual((code, r.get("quote_check")), (0, "verified"), r)

    def test_every_word_of_the_part(self):
        self.page("https://g.example/sights", "FRONT SIGHT HEIGHT 5.0 mm REAR SIGHT HEIGHT 6.5 mm")
        u = "https://g.example/sights"
        self.assertTrue(D.check_quote(u, "REAR SIGHT HEIGHT 6.5 mm", 6.5, fact=("front sight", "height"))
                        .startswith("failed"))
        self.assertEqual(D.check_quote(u, "REAR SIGHT HEIGHT 6.5 mm", 6.5, fact=("rear sight", "height")), "verified")

    def test_real_spec_formats_verify(self):
        self.page("https://g.example/specs", "Overall Length: 7.95 in (202 mm) Length 202mm Barrel length: 114 mm "
                  "Weight (unloaded): 630 g Weight (oz) 22.22 Height w/ Mag 139 mm")
        u = "https://g.example/specs"
        for quote, v, unit, fact in (("Overall Length: 7.95 in (202 mm)", 202, "mm", ("overall", "length")),
                                     ("Length 202mm", 202, "mm", ("overall", "length")),
                                     ("Barrel length: 114 mm", 114, "mm", ("barrel", "length")),
                                     ("Weight (unloaded): 630 g", 0.63, "kg", ("overall", "mass")),
                                     ("Weight (oz) 22.22", 0.63, "kg", ("overall", "mass")),
                                     ("Height w/ Mag 139 mm", 139, "mm", ("overall", "height incl. magazine"))):
            self.assertEqual(D.check_quote(u, quote, v, unit, fact=fact), "verified", quote)

    def test_a_unit_less_or_mislabelled_number_proves_no_size(self):
        self.page("https://g.example/odd", "Barrel Length: 4.49 Weight (oz) 22.04")
        u = "https://g.example/odd"
        self.assertTrue(D.check_quote(u, "Barrel Length: 4.49", 4.49, fact=("barrel", "length")).startswith("failed"))
        self.assertTrue(D.check_quote(u, "Weight (oz) 22.04", 22.04, "kg", fact=("overall", "mass"))
                        .startswith("failed"))

    def test_a_parts_number_may_follow_its_name(self):
        self.assertTrue(D._name_in("Slide stop lever", "Slide stop lever ........ 28", "28"))
        self.assertFalse(D._name_in("Slide stop lever", "Slide stop lever ........ 27", "28"))

    def test_a_transparent_cut_out_is_boxed_from_its_alpha(self):
        from PIL import Image, ImageDraw

        im = Image.new("RGBA", (800, 600), (0, 0, 0, 0))
        ImageDraw.Draw(im).rectangle([100, 150, 100 + 404 - 1, 150 + 278 - 1], fill=(28, 28, 30, 255))
        path = os.path.join(self.tmp, "cut.png")
        im.save(path)
        m = D.picture_metrics(path)
        self.assertEqual((m["box_from"], m["box"]), ("alpha", [100, 150, 503, 427]))
        flat = os.path.join(self.tmp, "flat.png")
        Image.new("RGB", (400, 300), (30, 30, 30)).save(flat)
        self.assertEqual(D.picture_metrics(flat, [10, 10, 200, 100])["box_from"], "given")  # (nothing stood out)



class TestMeasuredOnEvidence(Base):
    """a size measured ON confirmed reference models (the Glock's body width: its published 34 mm is lever to lever):
    B at most, two independent sites agreeing, the number held by each model's own measurement; and a model or view
    passes against ANY A/B meaning of a size"""

    cli = TestReviewFindings.cli

    def model(self, d, eid, size, page, confirm=True):
        m = os.path.join(self.tmp, f"{eid}.measure.json")
        with open(m, "w") as fh:
            json.dump({"size_mm": size}, fh)
        d["evidence"].append({"id": eid, "kind": "model", "scope": "measure-only", "page": page, "measure": m,
                              "by": "adder"})
        if confirm:
            for by, blind in (("a", False), ("b", True)):
                self.review(d, by, {eid: {"verdict": "accept", "variant": "ok", "why": "x"}}, blind=blind)

    def derived(self, value, eid, by="opus", d=None, keys=True, **extra):
        """a measured-on row; keys: its meaning accepted by two reviewers (one blind, neither its adder)"""
        dims.add_rows([{"object": "glock 17 gen5", "part": "overall", "dim": "width without slide stop levers",
                        "value": float(value), "unit": "mm", "source": f"evidence:{eid}", "kind": "derived",
                        "by": by, "note": "", **extra}])
        rid = dims.row_id("glock 17 gen5", "overall", "width without slide stop levers", float(value),
                          f"evidence:{eid}")
        if d is not None and keys:
            for who, blind in (("a", False), ("b", True)):
                self.review(d, who, {f"row:{rid}": {"verdict": "accept", "why": "x"}}, blind=blind)
        return rid

    def test_two_sites_agreeing_make_b_one_site_twice_is_c(self):
        d = self.dossier()
        self.model(d, "e1", [32.2, 139.8, 202.0], "https://eu.glock.com/en/products/pistols/g17_gen5")
        self.model(d, "e2", [32.1, 138.2, 202.0], "https://eu.glock.com/en/products/pistols/g17-gen5-mos")
        self.derived(32.2, "e1", d=d)
        self.derived(32.1, "e2", d=d)
        f = self.graded(d, "overall.width without slide stop levers")
        self.assertEqual(f["grade"], "C")  # (two of GLOCK's own turntables: one site — and never A: our reading)
        self.model(d, "e3", [32.5, 138.5, 202.0], "https://sketchfab.com/3d-models/g17-x")
        self.derived(32.5, "e3", d=d)
        f = self.graded(d, "overall.width without slide stop levers")
        self.assertEqual(f["grade"], "B")
        self.assertTrue(all(r["quote_check"] == "measured" for r in f["rows"]), f["rows"])

    def test_unconfirmed_evidence_or_a_number_it_does_not_hold_counts_for_nothing(self):
        d = self.dossier()
        self.model(d, "e1", [32.2, 139.8, 202.0], "https://eu.glock.com/x", confirm=False)
        self.derived(32.2, "e1", d=d)
        f = self.graded(d, "overall.width without slide stop levers")
        self.assertTrue(f["rows"][0]["quote_check"].startswith("pending"))
        self.assertFalse(f["rows"][0]["confirmed"])
        D.save(d)
        code, r = self.cli("fact", "glock 17 gen5", "--dim", "width without slide stop levers", "--mm", "30",
                           "--from", "e1", "--as", "a")
        self.assertEqual(code, 1)
        self.assertIn("measures 32.2", r["summary"])
        code, r = self.cli("fact", "glock 17 gen5", "--dim", "width without slide stop levers", "--mm", "32.2",
                           "--from", "e9", "--as", "a")
        self.assertEqual(code, 1)

    def test_a_model_passes_against_either_meaning_of_the_width(self):
        d = self.dossier(identity={"maker_domains": ["glock.com"], "aliases": [], "tells": [],
                                   "frame": {"length": ["overall.length"],
                                             "height": ["overall.height incl. magazine"],
                                             "width": ["overall.width", "overall.width without slide stop levers"]}})
        self.row(202, MAKER, quote="LENGTH (OVERALL)* 202 mm")
        self.row(139, MAKER, dim="height incl. magazine", quote="HEIGHT INCL. MAG. 139 mm")
        self.row(34, MAKER, dim="width", quote="WIDTH (OVERALL) 34 mm")
        self.model(d, "e1", [32.2, 139.8, 202.0], "https://eu.glock.com/en/products/pistols/g17_gen5")
        self.model(d, "e2", [32.5, 138.5, 202.0], "https://sketchfab.com/3d-models/g17-x")
        self.model(d, "e3", [34.1, 139.0, 202.0], "https://sketchfab.com/3d-models/g17-scan")  # (levers kept)
        self.model(d, "e4", [29.0, 139.0, 202.0], "https://sketchfab.com/3d-models/g17-thin")
        rep_ = D.check(d, offline=True)
        flags = {e["id"]: e["flags"] for e in rep_["evidence"]}
        self.assertTrue(flags["e1"] and flags["e2"])  # (no body width yet: 34 is the only meaning)
        self.derived(32.2, "e1", d=d)
        self.derived(32.5, "e2", d=d)
        rep_ = D.check(d, offline=True)
        self.assertEqual(rep_["facts"]["overall.width without slide stop levers"]["grade"], "B")
        flags = {e["id"]: e["flags"] for e in rep_["evidence"]}
        self.assertEqual((flags["e1"], flags["e2"], flags["e3"]), ([], [], []))
        self.assertTrue(flags["e4"])  # (29 mm matches neither meaning)
        notes = {e["id"]: e.get("notes") or [] for e in rep_["evidence"]}
        self.assertTrue(any("measured ON" in n for n in notes["e1"]))  # (said: it rests on the references)
        self.assertEqual(notes["e3"], [])  # (34.1: checked against the maker's own 34)
        self.assertEqual(sorted(rep_["coverage"]["models"]), ["e1", "e2", "e3"])



class TestMirroredCopies(Base):
    """the turntable hull's front and rear outlines are one silhouette flipped: two files, one view's information"""

    def shape(self, name, flip=False, notch=True):
        from PIL import Image, ImageDraw

        im = Image.new("RGB", (400, 900), (255, 255, 255))
        dr = ImageDraw.Draw(im)
        dr.polygon([(150, 60), (240, 60), (260, 820), (140, 820)], fill=(20, 20, 20))
        if notch:
            dr.rectangle([230, 300, 300, 420], fill=(20, 20, 20))  # (a lever on one side only)
        if flip:
            im = im.transpose(Image.FLIP_LEFT_RIGHT)
        path = os.path.join(self.tmp, name)
        im.save(path)
        return path

    def test_a_flipped_copy_is_the_same_picture_and_covers_no_second_view(self):
        d = self.dossier()
        d["evidence"] += [{"id": "e1", "kind": "picture", "scope": "measure-only", "file": self.shape("front.png")},
                          {"id": "e2", "kind": "picture", "scope": "measure-only",
                           "file": self.shape("rear.png", flip=True)}]
        rep = D.check(d, offline=True)
        self.assertEqual(rep["evidence"][1].get("duplicate_of"), "e1")
        self.assertTrue(any("mirrored" in f for f in rep["evidence"][1]["flags"]))

    def test_a_different_outline_is_not_a_mirror(self):
        d = self.dossier()
        d["evidence"] += [{"id": "e1", "kind": "picture", "scope": "measure-only", "file": self.shape("a.png")},
                          {"id": "e2", "kind": "picture", "scope": "measure-only",
                           "file": self.shape("b.png", notch=False)}]
        rep = D.check(d, offline=True)
        self.assertFalse(any("the same picture" in f for e in rep["evidence"] for f in e["flags"]))



class TestMeasuredMeaning(Base):
    """the Glock hull's 32.2 mm 'without the slide stop levers' was its box: a lever on one side, the magwell on the
    other, a 0.6 degree tilt — a script can check a number, never what the number means"""

    cli = TestReviewFindings.cli
    model = TestMeasuredOnEvidence.model
    derived = TestMeasuredOnEvidence.derived

    def two_models(self):
        d = self.dossier()
        self.model(d, "e1", [32.2, 139.8, 202.0], "https://eu.glock.com/en/products/pistols/g17_gen5")
        self.model(d, "e2", [32.5, 138.5, 202.0], "https://sketchfab.com/3d-models/g17-x")
        return d

    def test_a_measured_size_counts_only_once_two_keys_accepted_its_meaning(self):
        d = self.two_models()
        self.derived(32.2, "e1", d=d, keys=False)
        self.derived(32.5, "e2", d=d, keys=False)
        f = self.graded(d, "overall.width without slide stop levers")
        self.assertNotEqual(f["grade"], "B")
        self.assertFalse(any(r["confirmed"] for r in f["rows"]))
        self.assertTrue(all(r["usable"] for r in f["rows"]))  # (open: a reviewer's job)

    def test_a_dispute_over_its_meaning_stops_it(self):
        d = self.two_models()
        r1 = self.derived(32.2, "e1", d=d, keys=False)
        self.derived(32.5, "e2", d=d)
        self.review(d, "a", {f"row:{r1}": {"verdict": "accept", "why": "x"}})
        self.review(d, "b", {f"row:{r1}": {"verdict": "reject", "why": "its box holds a lever"}}, blind=True)
        f = self.graded(d, "overall.width without slide stop levers")
        self.assertNotEqual(f["grade"], "B")
        row = next(r for r in f["rows"] if r["id"] == r1)
        self.assertEqual((row["review"], row["confirmed"]), ("disputed", False))

    def cut_measure(self, name, size, source, cut=True, whole=(32.2, 139.8, 202.0)):
        p = os.path.join(self.tmp, f"{name}.measure.json")
        with open(p, "w") as fh:
            json.dump({"size_mm": size, "source": source, "size_uncut_mm": list(whole),
                       **({"cut": {"length_mm": [45, 85], "height_mm": [98, 118]}} if cut else {})}, fh)
        return p

    def test_a_re_measurement_of_the_same_model_with_a_part_left_out(self):
        src = os.path.join(self.tmp, "hull.obj")
        d = self.dossier()
        self.model(d, "e1", [32.2, 139.8, 202.0], "https://eu.glock.com/en/products/pistols/g17_gen5")
        with open(d["evidence"][0]["measure"], "w") as fh:
            json.dump({"size_mm": [32.2, 139.8, 202.0], "obj": src}, fh)
        D.save(d)
        good = self.cut_measure("cut", [31.8, 139.8, 202.0], src)
        code, r = self.cli("fact", "glock 17 gen5", "--dim", "width without slide stop levers", "--mm", "31.8",
                           "--from", "e1", "--measure", good, "--as", "x")
        self.assertEqual(code, 0, r)
        self.assertEqual(r["quote_check"], "measured")
        row = next(x for x in D._rows_of(D.load("glock 17 gen5")) if x["value"] == 31.8)
        self.assertEqual(row["measure_sha256"], D._file_sha(good))
        for bad, why in ((self.cut_measure("nocut", [31.8, 139.8, 202.0], src, cut=False), "left out"),
                         (self.cut_measure("other", [31.8, 139.8, 202.0], os.path.join(self.tmp, "x.glb")),
                          "another model")):
            code, r = self.cli("fact", "glock 17 gen5", "--dim", "width without slide stop levers", "--mm", "31.8",
                               "--from", "e1", "--measure", bad, "--as", "x")
            self.assertEqual(code, 1)
            self.assertIn(why, r["summary"])
        code, r = self.cli("fact", "glock 17 gen5", "--dim", "width without slide stop levers", "--mm", "30",
                           "--from", "e1", "--measure", good, "--as", "x")
        self.assertEqual(code, 1)  # (the re-measurement says 31.8)
        other_scale = self.cut_measure("scale", [31.5, 138.4, 200.0], src, whole=(31.9, 138.4, 200.0))
        code, r = self.cli("fact", "glock 17 gen5", "--dim", "width without slide stop levers", "--mm", "31.5",
                           "--from", "e1", "--measure", other_scale, "--as", "x")
        self.assertEqual(code, 1)  # (re-measured at another length: not the evidence's model as reviewed)
        self.assertIn("whole model", r["summary"])
        code, r = self.cli("fact", "glock 17 gen5", "--part", "slide", "--dim", "width", "--mm", "31.8",
                           "--from", "e1", "--measure", good, "--as", "x")
        self.assertEqual(code, 1)  # (a whole model's box is no slide's width)
        self.assertIn("WHOLE", r["summary"])
        with open(good, "w") as fh:  # (changed after it was cited: the row counts for nothing)
            json.dump({"size_mm": [31.8, 139.8, 202.0], "source": src, "cut": {"length_mm": [0, 1]}}, fh)
        f = self.graded(D.load("glock 17 gen5"), "overall.width without slide stop levers")
        self.assertIn("changed", f["rows"][0]["quote_check"])

    def test_a_row_added_wrong_is_withdrawn_with_its_record_kept(self):
        d = self.two_models()
        r1 = self.derived(32.2, "e1", d=d)
        self.derived(32.5, "e2", d=d)
        before = D.sheet_sha(d)
        code, r = self.cli("withdraw", "glock 17 gen5", f"row:{r1}", "--why", "a reviewer's dislike", "--as", "x")
        self.assertEqual(code, 1)  # (only who added it, or the owner: a reviewer rejects instead)
        code, r = self.cli("withdraw", "glock 17 gen5", f"row:{r1}", "--why", "its box holds a lever", "--as", "opus")
        self.assertEqual(code, 0, r)
        d = D.load("glock 17 gen5")
        self.assertNotEqual(D.sheet_sha(d), before)  # (an approval of the sheet before goes stale)
        f = self.graded(d, "overall.width without slide stop levers")
        self.assertNotEqual(f["grade"], "B")
        row = next(x for x in f["rows"] if x["id"] == r1)
        self.assertEqual((row["usable"], row["confirmed"]), (False, False))
        self.assertIn("lever", row["quote_check"])
        code, r = self.cli("withdraw", "glock 17 gen5", f"row:{r1}", "--why", "again", "--as", "opus")
        self.assertEqual(code, 1)  # (once)
        code, r = self.cli("withdraw", "glock 17 gen5", "row:nosuchrow", "--why", "x", "--as", "owner")
        self.assertEqual(code, 1)

    def test_one_model_under_two_pages_is_one_site_and_one_model(self):
        d = self.dossier()
        self.model(d, "e1", [32.2, 139.8, 202.0], "https://sketchfab.com/3d-models/g17-x")
        self.model(d, "e2", [32.2, 139.8, 202.0], "https://www.cgtrader.com/3d-models/g17-x")
        d["evidence"][1]["measure"] = d["evidence"][0]["measure"]  # (the same file, added twice)
        D.save(d)
        self.derived(32.2, "e1", d=d)
        self.derived(32.25, "e2", d=d)
        f = self.graded(d, "overall.width without slide stop levers")
        self.assertNotEqual(f["grade"], "B")  # (one model is one site)
        rep_ = D.check(d, offline=True)
        e2 = next(e for e in rep_["evidence"] if e["id"] == "e2")
        self.assertEqual(e2.get("duplicate_of"), "e1")

    def test_rejected_evidence_fails_its_rows(self):
        d = self.dossier()
        self.model(d, "e1", [32.2, 139.8, 202.0], "https://sketchfab.com/3d-models/g17-x", confirm=False)
        for who, blind in (("a", False), ("b", True)):
            self.review(d, who, {"e1": {"verdict": "reject", "why": "another gun"}}, blind=blind)
        self.derived(32.2, "e1", d=d)
        f = self.graded(d, "overall.width without slide stop levers")
        self.assertTrue(f["rows"][0]["quote_check"].startswith("failed"))
        self.assertFalse(f["rows"][0]["usable"])

    def test_a_failed_or_cut_measurement_is_never_added_as_a_model(self):
        self.dossier()
        for name, extra, why in (("bad", {"status": "fail", "problems": ["clipped"]}, "FAILED"),
                                 ("cut", {"cut": {"length_mm": [1, 2]}}, "cut")):
            m = os.path.join(self.tmp, f"{name}.measure.json")
            with open(m, "w") as fh:
                json.dump({"size_mm": [32, 139, 202], **extra}, fh)
            code, r = self.cli("add", "glock 17 gen5", "--kind", "model", "--measure", m, "--scope", "measure-only",
                               "--page", "https://sketchfab.com/3d-models/x", "--as", "x")
            self.assertEqual(code, 1, r)
            self.assertIn(why, r["summary"])

    def pinned_model(self, d, eid, size, page, body=None):
        self.model(d, eid, size, page)
        e = d["evidence"][-1]
        with open(e["measure"], "w") as fh:
            json.dump(body or {"size_mm": size}, fh)
        e["measure_sha256"] = D._file_sha(e["measure"])
        D.save(d)
        return e

    def test_one_turntable_carved_twice_or_one_file_from_two_sites_is_one_model(self):
        photos = os.path.join(self.tmp, "turntable")
        os.makedirs(photos)
        glb_a, glb_b = os.path.join(self.tmp, "a.glb"), os.path.join(self.tmp, "b.glb")
        for g in (glb_a, glb_b):
            with open(g, "wb") as fh:
                fh.write(b"the same model bytes")
        for case, bodies in (("hull", ({"source": photos, "obj": os.path.join(self.tmp, "h1.obj")},
                                       {"source": photos, "obj": os.path.join(self.tmp, "h2.obj")})),
                             ("file", ({"source": glb_a}, {"source": glb_b}))):
            d = self.dossier()
            for eid, page, body, w in (("e1", "https://eu.glock.com/x", bodies[0], 32.2),
                                       ("e2", "https://sketchfab.com/3d-models/x", bodies[1], 32.3)):
                self.pinned_model(d, eid, [w, 139.8, 202.0], page, {"size_mm": [w, 139.8, 202.0], **body})
            self.derived(32.2, "e1", d=d)
            self.derived(32.3, "e2", d=d)
            f = self.graded(d, "overall.width without slide stop levers")
            self.assertNotEqual(f["grade"], "B", case)  # (one model is one site)
            e2 = next(e for e in D.check(d, offline=True)["evidence"] if e["id"] == "e2")
            self.assertEqual(e2.get("duplicate_of"), "e1", case)

    def test_a_measured_size_needs_evidence_of_this_variant(self):
        d = self.dossier()
        self.model(d, "e1", [32.2, 139.8, 202.0], "https://eu.glock.com/x", confirm=False)
        for who, blind in (("a", False), ("b", True)):
            self.review(d, who, {"e1": {"verdict": "limited", "variant": "wrong", "why": "the MOS sibling"}},
                        blind=blind)
        self.derived(32.2, "e1", d=d)
        f = self.graded(d, "overall.width without slide stop levers")
        self.assertIn("another variant", f["rows"][0]["quote_check"])
        self.assertFalse(f["rows"][0]["usable"])

    def test_the_evidences_own_measurement_and_the_cut_file_are_both_pinned_and_cached_on(self):
        src = os.path.join(self.tmp, "hull.obj")
        d = self.dossier()
        e = self.pinned_model(d, "e1", [32.2, 139.8, 202.0], "https://eu.glock.com/x",
                              {"size_mm": [32.2, 139.8, 202.0], "obj": src})
        good = self.cut_measure("cut", [31.8, 139.8, 202.0], src)
        code, r = self.cli("fact", "glock 17 gen5", "--dim", "width without slide stop levers", "--mm", "31.8",
                           "--from", "e1", "--measure", good, "--as", "x")
        self.assertEqual(code, 0, r)
        d = D.load("glock 17 gen5")
        key = D.check_key(d)
        with open(good, "a") as fh:
            fh.write(" ")  # (the cut file changes: a cached check must not be reused)
        self.assertNotEqual(D.check_key(d), key)
        with open(e["measure"], "w") as fh:
            json.dump({"size_mm": [32.2, 139.8, 202.0], "obj": os.path.join(self.tmp, "other.obj")}, fh)
        f = self.graded(D.load("glock 17 gen5"), "overall.width without slide stop levers")
        self.assertIn("own measurement changed", f["rows"][0]["quote_check"])

    def test_the_note_names_only_a_meaning_a_check_really_used(self):
        d = self.dossier()
        self.row(202, MAKER, quote="LENGTH (OVERALL)* 202 mm")
        self.row(139, MAKER, dim="height incl. magazine", quote="HEIGHT INCL. MAG. 139 mm")
        self.model(d, "e1", [32.2, 138.0, 202.0], "https://eu.glock.com/x")
        self.model(d, "e2", [32.3, 138.2, 202.0], "https://sketchfab.com/3d-models/x")
        for eid, v in (("e1", 138.0), ("e2", 138.2)):
            dims.add_rows([{"object": "glock 17 gen5", "part": "overall", "dim": "height", "value": v, "unit": "mm",
                            "source": f"evidence:{eid}", "kind": "derived", "by": "opus", "note": ""}])
            rid = dims.row_id("glock 17 gen5", "overall", "height", v, f"evidence:{eid}")
            for who, blind in (("a", False), ("b", True)):
                self.review(d, who, {f"row:{rid}": {"verdict": "accept", "why": "x"}}, blind=blind)
        p = self.picture("side.png", 202, 139)
        d["evidence"].append({"id": "e3", "kind": "picture", "scope": "measure-only", "file": p, "by": "adder",
                              "page": "https://eu.glock.com/x"})
        for who, blind in (("a", False), ("b", True)):
            self.review(d, who, {"e3": {"verdict": "accept", "view": "side-left", "square": True, "variant": "ok",
                                        "why": "x"}}, blind=blind)
        rep_ = D.check(d, offline=True)
        self.assertEqual(rep_["facts"]["overall.height"]["grade"], "B")
        e3 = next(e for e in rep_["evidence"] if e["id"] == "e3")
        self.assertIn("overall.height incl. magazine", e3["metrics"]["aspect_against"])
        self.assertEqual(e3.get("notes") or [], [])  # (checked against the maker's own height, not the measured one)

    def test_a_confirmed_copy_is_the_original_not_a_pending_one(self):
        d = self.dossier()
        p = self.picture("a.png", 202, 139)
        d["evidence"] += [{"id": "e1", "kind": "picture", "scope": "measure-only", "file": p, "by": "adder",
                           "page": "https://eu.glock.com/x"},
                          {"id": "e2", "kind": "picture", "scope": "measure-only", "file": p, "by": "adder",
                           "page": "https://sketchfab.com/3d-models/x"}]
        for who, blind in (("a", False), ("b", True)):
            self.review(d, who, {"e2": {"verdict": "accept", "view": "side-left", "square": True, "variant": "ok",
                                        "why": "x"}}, blind=blind)
        rep_ = D.check(d, offline=True)
        ev = {e["id"]: e for e in rep_["evidence"]}
        self.assertEqual(ev["e1"].get("duplicate_of"), "e2")  # (e1 is still pending: e2 is the one that counts)
        self.assertIsNone(ev["e2"].get("duplicate_of"))

    def test_a_packet_never_lists_a_withdrawn_tell(self):
        d = self.dossier()
        d["identity"]["tells"] = [{"id": "t1", "text": "front serrations"},
                                  {"id": "t2", "text": "front serrations again", "withdrawn": {"why": "twice"}}]
        D.save(d)
        for blind in (False, True):
            body = D.packet(d, f"r{int(blind)}", blind=blind)[0]
            self.assertEqual([t["id"] for t in body["identity"]["tells"]], ["t1"])


if __name__ == "__main__":
    unittest.main()
