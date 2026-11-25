"""kit/audio/clap.py + kit/audio/sfxlib.py find --describe - the sound library searched by DESCRIPTION: every sound
embedded once (by content and trim; a second index run embeds nothing), a sound whose file is gone left out and
counted, a description ranks the sounds, --describe lifts CLAP's similarity a little by the words of the sound's own
NAME (never by the ear's descriptors), the model never loads beside an unpinned weight file, and the eval sorts each
description by what the word search finds. Stub embedders stand in for LAION CLAP (no model is loaded).
Run: python kit/test/python/run.py -k test_clap"""

import contextlib
import io
import json
import os
import sys
import tempfile
import types
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "audio"))

CALLS = []


def stub_decode(path, trim=None):
    with open(path, encoding="utf-8") as fh:
        loud = float(fh.read().strip())
    return np.full(48000, loud, dtype=np.float32)


def stub_audio(arrays):
    """a 'loud' sound points one way, a 'quiet' one the other"""
    CALLS.append(len(arrays))
    out = [np.array([float(a.mean()), 1.0 - float(a.mean())], dtype=np.float32) for a in arrays]
    return np.stack([v / np.linalg.norm(v) for v in out])


def stub_text(texts):
    out = []
    for t in texts:
        loud = 1.0 if any(w in t for w in ("boom", "blast", "explosion")) else 0.0
        v = np.array([loud, 1.0 - loud], dtype=np.float32) + 0.01
        out.append(v / np.linalg.norm(v))
    return np.stack(out)


class ClapTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        self.index_dir = os.path.join(d, "clap")
        self.pack = os.path.join(d, "pack")
        os.makedirs(self.pack)
        self.sources = {"pack": {"folder": self.pack}}
        self.entries = []
        # as `sfx index` makes them: the file name's words + the ear's descriptors (the quiet wind measures "long")
        for name, loud, ear in (("big_boom", 0.9, ["short"]), ("explosion", 0.8, ["short"]),
                                ("soft_wind", 0.1, ["long", "dark"]), ("gone_one", 0.5, ["short"])):
            f = os.path.join(self.pack, f"{name}.ogg")
            if name != "gone_one":
                with open(f, "w", encoding="utf-8") as fh:
                    fh.write(str(loud))
            self.entries.append({"id": f"pack.{name}", "file": f, "trim": None, "licence": "CC0", "source": "pack",
                                 "words": sorted(set(name.split("_") + ear)),
                                 "ears": {"lufs": -14, "brightness_hz": 1000, "tail_ms": 100}})
        self.by_id = {e["id"]: e for e in self.entries}
        os.environ["KIT_SFX_CLAP"] = self.index_dir
        import clap as C  # noqa: PLC0415

        self.C = C
        C.INDEX_DIR = self.index_dir
        CALLS.clear()

    def tearDown(self):
        os.environ.pop("KIT_SFX_CLAP", None)
        self.tmp.cleanup()

    def build(self):
        return self.C.build(self.entries, self.index_dir, embed=stub_audio, decoder=stub_decode)

    def test_every_sound_is_embedded_once_and_a_gone_file_is_counted(self):
        st = self.build()
        self.assertEqual((st["sounds"], st["embedded"], st["missing"]), (3, 3, 1))
        self.assertEqual(self.build()["embedded"], 0)

    def test_a_description_ranks_the_sounds(self):
        self.build()
        hits = self.C.search("a huge blast", self.entries, 3, self.index_dir, embed=stub_text)
        self.assertEqual([e["id"] for _s, e in hits][:2], ["pack.big_boom", "pack.explosion"])
        self.assertEqual(hits[-1][1]["id"], "pack.soft_wind")

    def test_describe_lifts_the_sound_whose_name_the_description_says(self):
        self.build()
        import sfxlib as L  # noqa: PLC0415

        lib = os.path.join(self.tmp.name, "index.json")
        with open(lib, "w", encoding="utf-8") as fh:
            json.dump({"entries": self.by_id, "sources": self.sources}, fh)
        saved_index, saved_text = L.INDEX, self.C.embed_text
        L.INDEX, self.C.embed_text = lib, stub_text
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                r = L.find("explosion", 3, None, None, describe=True)
        finally:
            L.INDEX, self.C.embed_text = saved_index, saved_text
        self.assertEqual(r["status"], "pass")
        self.assertEqual(r["hits"][0]["id"], "pack.explosion")  # its own name lifts it past the louder big_boom
        self.assertIn("1 sound(s) CLAP has not heard", r["summary"])  # the gone file is said, not silently dropped

    def test_describe_never_lifts_by_the_ears_descriptors(self):
        import sfxlib as L  # noqa: PLC0415

        boom, wind = self.by_id["pack.big_boom"], self.by_id["pack.soft_wind"]
        self.assertEqual(L.name_words(wind, self.sources), ["soft", "wind"])  # "long" / "dark" are the ear's
        got = [(0.5, boom), (0.45, wind)]
        ranked = L.describe_rank("a long sound", [boom, wind], 0.15, got, self.sources)
        self.assertEqual(ranked[0][1]["id"], "pack.big_boom")  # the measured "long" lifts nothing
        self.assertEqual([e["id"] for _s, e in L.word_rank("long", self.entries)], ["pack.soft_wind"])  # plain keeps it
        ranked = L.describe_rank("wind", [boom, wind], 0.15, got, self.sources)
        self.assertEqual(ranked[0][1]["id"], "pack.soft_wind")  # its NAME lifts it

    def test_no_index_says_how_to_make_one(self):
        self.assertIsNone(self.C.search("boom", self.entries, 3, os.path.join(self.tmp.name, "none"), embed=stub_text))

    def test_a_weight_file_that_is_not_pinned_is_found(self):
        for f in ("pytorch_model.bin", "model.safetensors", "config.json"):
            with open(os.path.join(self.tmp.name, f), "w", encoding="utf-8"):
                pass
        self.assertEqual(self.C.unpinned_weights(self.tmp.name, {"pytorch_model.bin", "config.json"}),
                         ["model.safetensors"])

    def test_the_model_never_loads_beside_an_unpinned_weight_file(self):
        folder = os.path.join(self.tmp.name, "clap-general")
        os.makedirs(folder)
        for f in ("pytorch_model.bin", "config.json", "model.safetensors"):
            with open(os.path.join(folder, f), "w", encoding="utf-8"):
                pass
        fake = types.ModuleType("run")  # kit/vision/run.py: ensure() has checked the pinned files, nothing else
        fake.ensure = lambda name: folder
        fake._manifest = lambda: {"clap-general": {"files": [{"path": "pytorch_model.bin"}, {"path": "config.json"}]}}
        saved, saved_model = sys.modules.get("run"), self.C._model
        sys.modules["run"], self.C._model = fake, None
        try:
            with self.assertRaises(RuntimeError) as err:
                self.C._load()
        finally:
            self.C._model = saved_model
            if saved is None:
                sys.modules.pop("run", None)
            else:
                sys.modules["run"] = saved
        self.assertIn("model.safetensors", str(err.exception))

    def test_eval_sorts_each_description_by_what_the_word_search_finds(self):
        self.build()
        cases = [{"q": "explosion", "want": "explosion"}, {"q": "a huge blast", "want": "boom"},
                 {"q": "a dog barking", "want": "dog"}]
        r = self.C.evaluate(self.entries, cases, self.index_dir, embed=stub_text, sources=self.sources)
        self.assertEqual((r["heard"], r["unheard"], r["left_out"]), (3, 1, ["a dog barking"]))
        shared, unshared = r["groups"]["shared"], r["groups"]["unshared"]
        self.assertEqual(shared["words"], [1, 1, 1])  # "explosion" is the sound's own name
        self.assertEqual(shared["clap"], [0, 1, 1])  # CLAP alone hears big_boom as the louder blast
        self.assertEqual(shared["clap+0.15"], [1, 1, 1])  # the name lift puts it first
        self.assertEqual(unshared["words"], [0, 0, 1])  # no library word in "a huge blast": unshared, measured
        self.assertEqual(unshared["clap"], [1, 1, 1])


class FindArgsTest(unittest.TestCase):
    """sfx find's switches: --describe never takes the next word; an empty description and --describe with --like
    stop before any search"""

    def run_main(self, argv):
        import sfxlib as L  # noqa: PLC0415

        seen = {}

        def fake_find(words, n, like, licences, describe=False):
            seen.update(words=words, like=like, describe=describe)
            return {"status": "pass", "summary": "ok", "next_action": "-", "hits": []}

        saved = L.find
        L.find = fake_find
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = L.main(argv)
        finally:
            L.find = saved
        return code, seen, json.loads(buf.getvalue().strip().splitlines()[-1])

    def test_describe_first_keeps_the_whole_description(self):
        code, seen, _r = self.run_main(["find", "--describe", "a", "distant", "explosion"])
        self.assertEqual((code, seen["words"], seen["describe"]), (0, "a distant explosion", True))

    def test_an_empty_description_stops(self):
        code, seen, r = self.run_main(["find", "--describe"])
        self.assertEqual((code, seen), (1, {}))
        self.assertIn("describe the sound in words", r["summary"])

    def test_describe_and_like_together_stop(self):
        code, seen, r = self.run_main(["find", "boom", "--describe", "--like", "x.ogg"])
        self.assertEqual((code, seen), (1, {}))
        self.assertIn("not both", r["summary"])


if __name__ == "__main__":
    unittest.main()
