"""The kit's own detail tiers (src/kit/VfxBudget.luau `auto` / `layerAt`; kit/vfx/player/player.js `autoTiers` /
`layerAtLevel`; the owner's limitations file, F-R06): the game's rule and the player's are ONE rule - both are run on
EVERY version 3 preset of the kit (lune, node) and must give the same layers at every level - and what the rule does
to the kit's effects is held to numbers. No lune or no node: these FAIL, they are not skipped.
Run: python -m pytest kit/test/python/test_vfx_tiers.py -q"""
import glob
import json
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
PLAYER = os.path.join(ROOT, "kit", "vfx", "player", "player.js")
LEVELS = ("Low", "Medium", "High")

LUAU = """
local fs = require("@lune/fs")
local serde = require("@lune/serde")
local process = require("@lune/process")
local VfxBudget = require("@lune/luau").load(fs.readFile("%s.luau"), { debugName = "VfxBudget" })()
local out = {}
for _, path in serde.decode("json", fs.readFile(process.args[1])) do
	local layers = serde.decode("json", fs.readFile(path)).layers
	local per = {}
	for _, level in { "Low", "Medium", "High" } do
		local kept = {}
		local plan = VfxBudget.auto(layers)
		for i, el in layers do
			local got = VfxBudget.layerAt(el, level, plan[i])
			if got ~= nil then
				table.insert(kept, { i - 1, got.count or false, got.rate or false, if type(got.twin) == "table" then got.twin.count or false else false })
			end
		end
		per[level] = kept
	end
	table.insert(out, per)
end
print(serde.encode("json", out))
"""
JS = """
const fs = require("fs");
const out = [];
for (const path of JSON.parse(fs.readFileSync(process.argv[2], "utf8"))) {
  const layers = JSON.parse(fs.readFileSync(path, "utf8")).layers, per = {};
  for (const level of ["Low", "Medium", "High"]) {
    const kept = [], plan = autoTiers(layers);
    layers.forEach((el, i) => { const got = layerAtLevel(el, level, plan[i]); if (got != null) kept.push([i, got.count ?? false, got.rate ?? false, got.twin && typeof got.twin === "object" ? (got.twin.count ?? false) : false]); });
    per[level] = kept;
  }
  out.push(per);
}
console.log(JSON.stringify(out));
"""


def presets():
    found = []
    # the project's effects and the kit's own starters (kit/starter/vfx holds version 3 presets too)
    for f in sorted(glob.glob(os.path.join(ROOT, "assets", "effects", "*.json"))) + sorted(
            glob.glob(os.path.join(ROOT, "kit", "starter", "vfx", "*.json"))):
        if os.path.basename(f).startswith("_"):
            continue
        try:
            d = json.load(open(f, encoding="utf-8"))
        except ValueError:
            continue
        if isinstance(d, dict) and d.get("version") == 3 and isinstance(d.get("layers"), list) and d["layers"]:
            found.append(f.replace(os.sep, "/"))
    return found


def both(paths):
    """-> (what the game's rule keeps, what the player's keeps): [{level: [[index, count, rate, twin count], ...]}] a preset"""
    text = open(PLAYER, encoding="utf-8").read()
    a, b = text.index("const TIER_RANK"), text.index("// (end of the tier rule)")
    with tempfile.TemporaryDirectory() as tmp:
        listed = os.path.join(tmp, "presets.json")
        with open(listed, "w", encoding="utf-8") as fh:
            json.dump(paths, fh)
        luau, js = os.path.join(tmp, "game.luau"), os.path.join(tmp, "player.cjs")
        with open(luau, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(LUAU % os.path.join(ROOT, "src", "kit", "VfxBudget").replace(os.sep, "/"))
        with open(js, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text[a:b].replace("export function", "function") + JS)
        game = subprocess.run(["lune", "run", luau, listed], capture_output=True, text=True, timeout=300, check=False, cwd=ROOT)
        player = subprocess.run(["node", js, listed], capture_output=True, text=True, timeout=300, check=False, cwd=ROOT)
        got = json.loads(game.stdout.strip().splitlines()[-1])
        for per in got:                                                  # (lune writes an empty list as {})
            for level in LEVELS:
                per[level] = per[level] or []
        return got, json.loads(player.stdout.strip().splitlines()[-1])


class OneRule(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paths = presets()
        if not cls.paths:
            raise unittest.SkipTest("no version 3 preset in assets/effects or kit/starter/vfx")
        cls.game, cls.player = both(cls.paths)

    def test_the_game_and_the_player_keep_the_same_layers_of_every_preset_at_every_level(self):
        # every version 3 preset found is checked, however few - the kit's own starters always among them (the
        # author's repo also floors its library at 100+, which only the author's own library meets; a project's
        # presets are each checked here)
        self.assertGreaterEqual(sum(1 for p in self.paths if "/kit/starter/vfx/" in p), 2)
        # and every version 3 preset of the project is among them (counted a second way, so a glob that finds
        # nothing cannot pass for "a project with no effects")
        fx = os.path.join(ROOT, "assets", "effects")
        mine = set()
        for f in os.listdir(fx) if os.path.isdir(fx) else []:
            if f.endswith(".json") and not f.startswith("_"):
                try:
                    d = json.load(open(os.path.join(fx, f), encoding="utf-8"))
                except ValueError:
                    continue
                if isinstance(d, dict) and d.get("version") == 3 and isinstance(d.get("layers"), list) and d["layers"]:
                    mine.add(f)
        self.assertEqual({os.path.basename(p) for p in self.paths if "/assets/effects/" in p}, mine)
        self.assertEqual(len(self.game), len(self.paths))
        for path, g, p in zip(self.paths, self.game, self.player):
            for level in LEVELS:
                self.assertEqual(g[level], p[level], (os.path.basename(path), level))

    def test_high_is_the_whole_effect_and_every_level_holds_the_one_below(self):
        for path, g in zip(self.paths, self.game):
            whole = len(json.load(open(path, encoding="utf-8"))["layers"])
            self.assertEqual(len(g["High"]), whole, path)
            low, mid, high = ({row[0] for row in g[level]} for level in LEVELS)
            self.assertTrue(low <= mid <= high, path)

    def test_what_the_rule_does_to_the_kits_effects(self):
        kind = {}
        for path in self.paths:
            kind[path] = [el.get("kind") if isinstance(el, dict) else None for el in json.load(open(path, encoding="utf-8"))["layers"]]
        meshes = {level: sum(sum(1 for row in g[level] if kind[p][row[0]] == "mesh") for p, g in zip(self.paths, self.game)) for level in LEVELS}
        if len(self.paths) >= 100:  # (shares of a LIBRARY: the kit's two version 3 starters cannot hold one)
            self.assertLess(meshes["Low"], 0.85 * meshes["High"])        # a low device builds clearly fewer meshes
            self.assertGreater(meshes["Low"], 0.5 * meshes["High"])      # and not a husk of the effect
            self.assertLess(meshes["Medium"], meshes["High"])
        never = {"sound", "shake", "screen", "fov", "impact", "world", "lens", "highlight", "glow", "crater", "decal", "beam", "trail"}
        for p, g in zip(self.paths, self.game):
            kept = {row[0] for row in g["Low"]}
            for i, k in enumerate(kind[p]):
                if k in never:
                    self.assertIn(i, kept, (p, i, k))                    # what carries the beat and the feel plays at every level
            had = [i for i, k in enumerate(kind[p]) if k == "mesh"]
            if had:
                self.assertTrue(any(i in kept for i in had), p)          # no effect loses every mesh
            lights = [i for i, k in enumerate(kind[p]) if k == "light"]
            if lights:
                self.assertTrue(any(i in kept for i in lights), p)

    def test_no_element_is_dropped_whole_and_its_most_solid_shell_stays(self):
        """the review of the first rule: ranked by life x scale over a whole moment, it took hero things away whole (a
        beam's head, one of a pair of spheres, 53 of 62 cores) - a level thins the SHELLS of one thing, never the thing"""
        def moment(el):
            at = el.get("at")
            return at if isinstance(at, str) else str(int(((at if isinstance(at, (int, float)) else 0) * 10 + 0.5) // 1))
        def vec(v):
            return tuple(int((x * 100 + 0.5) // 1) if isinstance(x, (int, float)) else 0 for x in (list(v) + [0, 0, 0])[:3]) if isinstance(v, list) else ()
        def least(v):
            if isinstance(v, (int, float)):
                return v
            got = [k[1] if isinstance(k, list) else k for k in v] if isinstance(v, list) else []
            got = [x for x in got if isinstance(x, (int, float))]
            return min(got) if got else 0
        for p, g in zip(self.paths, self.game):
            layers = json.load(open(p, encoding="utf-8"))["layers"]
            kept = {row[0] for row in g["Low"]}
            things = {}
            for i, el in enumerate(layers):
                if isinstance(el, dict) and el.get("kind") == "mesh":
                    seq = el.get("params", {}).get("seq") if isinstance(el.get("params"), dict) else None
                    things.setdefault((moment(el), el.get("shape"), vec(el.get("point")), vec(el.get("aim")), seq if isinstance(seq, str) else ""), []).append(i)
            for key, members in things.items():
                self.assertTrue(any(i in kept for i in members), (os.path.basename(p), key))
                solid = min(members, key=lambda i: (least(layers[i].get("transparency")), i))
                if not any(layers[i].get("tier") or layers[i].get("tierCount") for i in members):
                    best = least(layers[solid].get("transparency"))
                    self.assertTrue(any(i in kept and least(layers[i].get("transparency")) == best for i in members), (os.path.basename(p), key))
        # (which shell READS best is not in the data: a layer named "core" is the most solid one in some effects and the
        # pale fill inside a dark edge in others - so the rule goes by what is solid, and the owner's eye by --detail)
        named = {os.path.basename(p): (json.load(open(p, encoding="utf-8"))["layers"], {row[0] for row in g["Low"]}) for p, g in zip(self.paths, self.game)}
        for preset, names in (("kamehameha_v4.json", ("head_core", "beam_core")), ("flame_arc_v2.json", ("arc_core",))):
            if preset in named:
                layers, kept = named[preset]
                for name in names:
                    self.assertTrue(any(i in kept for i, el in enumerate(layers) if isinstance(el, dict) and el.get("name") == name), (preset, name))

    def test_naming_one_layers_tier_never_moves_another_and_a_critical_layer_is_never_tiered(self):
        def low(layers):
            with tempfile.TemporaryDirectory() as tmp:
                f = os.path.join(tmp, "made.json").replace(os.sep, "/")
                json.dump({"version": 3, "layers": layers}, open(f, "w", encoding="utf-8"))
                game, player = both([f])
            self.assertEqual(game, player)
            return [row[0] for row in game[0]["Low"]]
        def mesh(name, life, t, **more):
            return dict({"name": name, "kind": "mesh", "at": 0, "life": life, "point": [0, 0, 0], "shape": "sphere", "transparency": t}, **more)
        plain = [mesh("a", 3, 0.0), mesh("b", 2, 0.2), mesh("c", 1, 0.5)]
        self.assertEqual(low(plain), [0])
        self.assertEqual(low([plain[0], plain[1], mesh("c", 1, 0.5, tier="Low")]), [0, 2])      # c named: a stays, nothing else moves
        self.assertEqual(low([mesh("a", 3, 0.0, tier="High"), plain[1], plain[2]]), [])         # a named away: b is NOT promoted in its place
        self.assertEqual(low([plain[0], plain[1], mesh("c", 1, 0.5, critical=True)]), [0, 2])   # a critical cue is never tiered
        lights = [{"name": "fill", "kind": "light", "at": 0, "life": 1, "range": 60, "brightness": 18},
                  {"name": "key", "kind": "light", "at": 0, "life": 1, "range": 60, "brightness": [[0, 0], [0.1, 34], [1, 0]]}]
        self.assertEqual(low(lights), [1])                                                       # the strongest light stays, not the first listed


if __name__ == "__main__":
    unittest.main()
