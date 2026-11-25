"""kit refs expand: an idea becomes real names (kit/refs/expand.py) — replayed from recorded answers, no network.
A model matching the idea, its family through a real product (one with a manufacturer), a person and a generic type
left out, sizes converted to mm / kg, Sketchfab models counted only when their title names the gun."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "refs"))
import expand  # noqa: E402


def ent(label, desc="", p31=(), p144=(), p279=(), p176=(), sizes=()):
    claims = {}
    for prop, ids in (("P31", p31), ("P144", p144), ("P279", p279), ("P176", p176)):
        if ids:
            claims[prop] = [{"mainsnak": {"datavalue": {"value": {"id": i}}}} for i in ids]
    for prop, amount, unit in sizes:
        claims.setdefault(prop, []).append({"mainsnak": {"datavalue": {"value": {
            "amount": amount, "unit": f"http://www.wikidata.org/entity/{unit}"}}}})
    return {"labels": {"en": {"value": label}}, "descriptions": {"en": {"value": desc}}, "claims": claims}


ENTS = {
    "Q1": ent("Silent Model One", "integrally suppressed pistol", p144=["Q2"], p176=["Q50"],
              sizes=[("P2043", "+8.5", "Q218593"), ("P2067", "+1120", "Q41803")]),
    "Q2": ent("Base Pistol", "semi-automatic pistol", p176=["Q50"], sizes=[("P2043", "+216", "Q174789")]),
    "Q3": ent("Base Pistol Commander", "semi-automatic pistol", p144=["Q2"], p176=["Q51"]),
    "Q4": ent("Silent Model One Carbine", "suppressed carbine", p279=["Q6"]),
    "Q6": ent("single shot pistol", "type of pistol"),  # a generic type: no manufacturer, never expanded
    "Q7": ent("Derringer", "small pistol", p279=["Q6"]),
    "Q9": ent("Ivan Designer", "weapons designer", p31=["Q5"]),  # a person
    "Q10": ent("Silent Night", "1999 film"),
}
SEARCH = {"suppressed pistol": ["Q1", "Q9", "Q10", "Q4"]}
FAMILY = {"Q2": ["Q1", "Q3"], "Q6": ["Q7", "Q4"]}
MODELS = {"Silent Model One": [{"uid": "u1", "title": "Silent Model One - game ready", "faces": 9000, "licence": "by", "author": "a"},
                               {"uid": "u2", "title": "Totally different gun", "faces": 99999, "licence": "by", "author": "b"}],
          "Base Pistol Commander": [{"uid": "u3", "title": "Base Pistol Commander", "faces": 40000, "licence": "cc0", "author": "c"}]}


class TestExpand(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.old = (expand._wd, expand.library.search, expand.CACHE_FILE, dict(expand._CACHE), expand.PACE)
        expand._CACHE.clear()
        expand.CACHE_FILE = os.path.join(tempfile.mkdtemp(), "cache.json")
        expand.PACE = 0

        def wd(params):
            self.calls.append(params)
            if params.get("action") == "wbgetentities":
                return {"entities": {i: ENTS[i] for i in params["ids"].split("|") if i in ENTS}}
            if params.get("action") == "wbsearchentities":
                return {"search": [{"id": i} for i in SEARCH.get(params["search"], [])[:1]]}
            q = params.get("srsearch", "")
            if q.startswith("haswbstatement:"):
                prop, qid = q.split(":", 1)[1].split("=")
                hits = FAMILY.get(qid, []) if prop in ("P144", "P279") else []
                return {"query": {"search": [{"title": h} for h in hits]}}
            return {"query": {"search": [{"title": h} for h in SEARCH.get(q, [])]}}

        expand._wd = wd
        expand.library.search = lambda q, n=24, pages_max=1, **kw: MODELS.get(q, [])

    def tearDown(self):
        expand._wd, expand.library.search, expand.CACHE_FILE, cache, expand.PACE = self.old
        expand._CACHE.clear()
        expand._CACHE.update(cache)

    def test_names_family_and_what_is_left_out(self):
        cands = {c["name"]: c for c in expand.expand("suppressed pistol", n=20)}
        self.assertIn("Silent Model One", cands)
        self.assertIn("Base Pistol Commander", cands)          # the family of its parent, a real product
        self.assertNotIn("Ivan Designer", cands)               # a person
        self.assertNotIn("Silent Night", cands)                # a film
        self.assertNotIn("Derringer", cands)                   # the family of a generic type
        self.assertEqual(cands["Base Pistol Commander"]["why"], "same family as Base Pistol")

    def test_sizes_in_mm_and_kg(self):
        c = {c["name"]: c for c in expand.expand("suppressed pistol", n=20)}["Silent Model One"]
        self.assertAlmostEqual(c["sizes"]["length_mm"], 215.9, places=1)   # 8.5 in
        self.assertAlmostEqual(c["sizes"]["mass_kg"], 1.12, places=3)      # 1120 g

    def test_models_counted_only_when_the_title_names_the_gun(self):
        c = {c["name"]: c for c in expand.expand("suppressed pistol", n=20)}
        self.assertEqual(c["Silent Model One"]["sketchfab"]["count"], 1)
        self.assertEqual(c["Silent Model One"]["sketchfab"]["best"]["uid"], "u1")
        self.assertEqual(expand.distinctive("Star S"), ["star"])
        self.assertEqual(expand.distinctive("Colt Delta Elite pistol"), ["colt", "delta", "elite"])
        self.assertTrue(expand.names("Hardballer .45 ACP", expand.distinctive("AMT Hardballer")))
        self.assertFalse(expand.names("AMT ammo crate", expand.distinctive("AMT Hardballer")))  # 'amt' is too short

    def test_a_builder_name_wikidata_does_not_know_is_kept(self):
        names = [c["name"] for c in expand.expand("suppressed pistol", also=["Mystery Can 9"], n=20)]
        self.assertIn("Mystery Can 9", names)


if __name__ == "__main__":
    unittest.main()
