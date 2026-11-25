"""kit/tools/docs.py - the Roblox API reference searched locally: an exact Class.member first, then words (a name word
counts more than a description word, an enum item less), HTML out of the descriptions, an event's own methods and
parameter notes left out, the declared type read from the type file's "declare extern type" blocks. A small fake
reference stands in for Studio's en-us.json. Run: python kit/test/python/run.py -k test_docs"""

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
import docs as D  # noqa: E402

REF = {
    "@roblox/globaltype/Players.PlayerAdded": {"documentation": "Fires when a player enters the experience."},
    "@roblox/globaltype/Players.PlayerAdded.Connect": {"documentation": "Connects a function."},
    "@roblox/globaltype/Players.PlayerAdded/param/0": {"documentation": "the player"},
    "@roblox/globaltype/RaycastParams.ExcludeInstances": {
        "documentation": "An optional array of instances whose <code>descendants</code> will be excluded."},
    "@roblox/global/task.wait": {"documentation": "Yields the current thread without throttling."},
    "@roblox/enum/PlayerExitReason.Left": {"documentation": "The player left the experience."},
    "@roblox/globaltype/WorldRoot.Raycast": {"documentation": "Casts a ray and returns what it hit."},
    "@roblox/globaltype/Player.SaveNumber": {"documentation": "Deprecated: saves a number to the player's data store."},
    "@roblox/globaltype/GlobalDataStore.SetAsync": {"documentation": "Sets the value of the data store for a key."},
}
TYPES = """declare extern type Players extends Instance with
\tPlayerAdded: RBXScriptSignal<Player>
\tfunction GetPlayers(self): { Player }
end
declare extern type WorldRoot extends Model with
\tfunction Raycast(self, origin: Vector3, direction: Vector3): RaycastResult?
end
declare extern type Workspace extends WorldRoot with
end
"""


class DocsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.src = os.path.join(self.tmp.name, "en-us.json")
        self.types = os.path.join(self.tmp.name, "t.d.luau")
        with open(self.src, "w", encoding="utf-8") as f:
            json.dump(REF, f)
        with open(self.types, "w", encoding="utf-8") as f:
            f.write(TYPES)

    def tearDown(self):
        self.tmp.cleanup()

    def run_docs(self, *q):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            D.main([*q, "--source", self.src, "--types", self.types])
        return json.loads(buf.getvalue().strip().splitlines()[-1])

    def test_an_exact_name_comes_first_with_its_type(self):
        r = self.run_docs("players.playeradded")
        self.assertEqual(r["rows"][0]["name"], "Players.PlayerAdded")
        self.assertEqual(r["rows"][0]["type"], "PlayerAdded: RBXScriptSignal<Player>")

    def test_events_own_methods_and_parameter_notes_are_left_out(self):
        names = set(D.entries(self.src))
        self.assertNotIn("Players.PlayerAdded.Connect", names)
        self.assertFalse(any("/param/" in n for n in names))
        self.assertIn("task.wait", names)

    def test_words_find_members_before_enum_items_and_html_is_stripped(self):
        r = self.run_docs("player", "experience")
        self.assertEqual(r["rows"][0]["name"], "Players.PlayerAdded")
        rc = self.run_docs("excluded", "descendants")
        self.assertNotIn("<code>", rc["rows"][0]["doc"])

    def test_an_inherited_member_is_found_on_its_parent(self):
        r = self.run_docs("Workspace.Raycast")
        self.assertEqual(r["rows"][0]["name"], "WorldRoot.Raycast")
        self.assertIn("Raycast(self", r["rows"][0]["type"])

    def test_plain_verbs_reach_the_engine_words_and_deprecated_sinks(self):
        joined = self.run_docs("player", "joined")
        self.assertEqual(joined["rows"][0]["name"], "Players.PlayerAdded")
        save = self.run_docs("datastore", "save")
        self.assertEqual(save["rows"][0]["name"], "GlobalDataStore.SetAsync")

    def test_no_reference_says_where_it_comes_from(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            D.main(["anything", "--source", os.path.join(self.tmp.name, "missing.json")])
        r = json.loads(buf.getvalue().strip().splitlines()[-1])
        self.assertEqual(r["status"], "fail")
        self.assertIn("Roblox Studio", r["summary"])


if __name__ == "__main__":
    unittest.main()
