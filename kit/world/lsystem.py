"""lsystem.py - PLANTS GROWN BY A GRAMMAR (the owner's method list: "L-system plant generation").
A kit tree's branches were random walks: a trunk with limbs off it at chance angles. An L-system grows a plant the
way its kind grows: a short word (the seed) is rewritten a few times by the kind's own rules, and the word that
comes out is read by a turtle that walks, turns, forks and comes back.

  the word's letters:   F  grow one length forward (a piece of wood)      L  a leaf mass here
                        +  -  turn left / right        &  ^  pitch down / up        \\  /  roll
                        [  ]  start a branch / come back to where it started (thinner and shorter inside)
  a kind:  {"axiom": "FFA", "rules": {"A": "[&FLA]////[&FLA]////[&FLA]"}, "angle": 30, "turns": 3,
            "taper": 0.62, "shorten": 0.8, "wobble": 0.1}
           a rule may be several ways with their weights: "A": [[3, "..."], [1, "..."]] - then two plants of one
           kind differ in their forks, by their seed.
           taper: how much thinner wood is inside a branch; shorten: how much shorter; wobble: the share by which
           every turn and every length is off, by the seed (0 = a plant drawn with a ruler; unsaid = 0) - with it
           two plants of a kind whose rules have one way each still differ.

A plant is grown UP (the turtle starts facing +Y) and scaled so it stands `height` tall. A straight run of F is one
piece of wood, and a plant is refused past its budget of pieces.
Pure (no Blender, no numpy): kit/world/meshes_blender.py builds a tree mesh's wood from it when its recipe says
"grammar"; kit/test/python/test_world_lsystem.py holds it to its rules. The same kind, height and seed give the same
plant."""
import math

BUDGET = 90  # pieces of wood a plant may come to
LEAVES = 60  # leaf masses a plant may come to (each is a handful of leaf cards in the mesh)
DEPTH = 12  # branches inside branches
WIDE = 2.0  # a plant reaches no farther from its foot than this many times its height
WORD = 20000  # letters a word may grow to (a rule that multiplies itself is stopped here)
LETTERS = "FL+-&^\\/[]"

# the kinds the kit knows (each grown and counted in the tests: its pieces stay under the budget)
KINDS = {
    # a broad crown: at every fork three ways a third of a turn apart, pitched out; sometimes two
    "broadleaf": {"axiom": "FFA", "rules": {"A": [[3, "[&FLA]////[&FLA]////[&FLA]"], [1, "[&FLA]//////[&FLA]"]]},
                  "angle": 30, "turns": 3, "taper": 0.62, "shorten": 0.8, "wobble": 0.1},
    # a straight leader with whorls of three nearly level boughs; B grows one length a turn, so the oldest whorl,
    # lowest on the trunk, is the longest: a cone. Each whorl is turned against the one under it
    "conifer": {"axiom": "FFA", "rules": {"A": "[&&&BL]////[&&&BL]////[&&&BL]//FA", "B": "FB"},
                "angle": 29, "turns": 6, "taper": 0.4, "shorten": 0.62, "wobble": 0.05},
    # a bare tree: at every fork two ways, opposite each other, each fork turned a quarter against the last
    "dead": {"axiom": "FFA", "rules": {"A": [[2, "///[+FA]//////[+FA]"], [1, "///[+FA]//////[+F]"]]},
             "angle": 30, "turns": 4, "taper": 0.62, "shorten": 0.78, "wobble": 0.12},
    # a bush: forks from the ground, short wood
    "shrub": {"axiom": "A", "rules": {"A": "[&FLA]////[&FLA]////[&FL]"},
              "angle": 30, "turns": 3, "taper": 0.7, "shorten": 0.75, "wobble": 0.12},
}


def unsaid(rec, uploaded):
    """THE WORD A TREE SAYS (enforced where a game's tree meshes are made: kit/world/meshes_blender.py main). A tree
    recipe says how its wood grows - "grammar": "<kind>" (or a kind of its own) - or "grammar": false (limbs at
    chance angles, the older way, meant). Nothing else is a word: null, "", 0 are asked again.
    Not asked: a tree that is already in a game - its name is among the UPLOADED world meshes (`uploaded`: the names
    in the project's committed ids file) - and that has no "grammar" key at all. -> the line to say, or None"""
    if not isinstance(rec, dict) or rec.get("kind", "tree") != "tree":
        return None
    g = rec.get("grammar")
    if g is False or (isinstance(g, str) and g) or isinstance(g, dict):
        return None
    if "grammar" not in rec and rec.get("name") in (uploaded or ()):
        return None
    return (f'{rec.get("name")}: a new tree says how its wood grows - "grammar": "{" | ".join(sorted(KINDS))}" '
            '(grown by the rules of its kind: kit/world/lsystem.py) or "grammar": false (limbs at chance angles, meant)')


def wanted(rec):
    """the grammar a tree recipe asks for: its kind (a name or a dict), or None when it says none or false"""
    g = rec.get("grammar") if isinstance(rec, dict) else None
    return g if (isinstance(g, str) and g) or isinstance(g, dict) else None


def _whole(v, lo, hi):
    return not isinstance(v, bool) and isinstance(v, (int, float)) and v == v and lo <= v <= hi and v % 1 == 0


def _lcg(seed):
    """the kit's own small generator (the compiler's, started one further on so that seed 0 is a plant of its own): a
    plant is its seed's"""
    state = (int(seed) + 1) % 2147483647
    if state <= 0:
        state += 2147483646
    state = (state * 48271) % 2147483647
    state = (state * 48271) % 2147483647

    def rnd():
        nonlocal state
        state = (state * 48271) % 2147483647
        return state / 2147483647

    return rnd


def problems(kind):
    """what is wrong with a kind ([] = it can be grown)"""
    out = []
    if not isinstance(kind, dict):
        return ['a plant\'s kind is {"axiom", "rules", "angle", "turns", "taper"?, "shorten"?, "wobble"?} or one of the kit\'s names']
    if not isinstance(kind.get("axiom"), str) or not kind["axiom"]:
        out.append('kind.axiom is the plant\'s first word (a string, e.g. "FA")')
    if not isinstance(kind.get("rules"), dict) or not kind["rules"]:
        out.append('kind.rules is {"<letter>": "<what it becomes>"}')
    if out:
        return out
    for k in kind:
        if k not in ("axiom", "rules", "angle", "turns", "taper", "shorten", "wobble"):
            out.append(f"kind.{k}: a kind says axiom, rules, angle, turns, taper, shorten, wobble - nothing else")
    known = set()
    for letter in kind["rules"]:
        if not isinstance(letter, str) or len(letter) != 1 or letter in LETTERS:
            out.append(f'kind.rules: "{letter}" - a rule rewrites ONE letter that the turtle does not read itself (A, B, X ...)')
        else:
            known.add(letter)

    def word(text, where):
        if not isinstance(text, str):
            out.append(f"{where} is a word (a string)")
            return
        depth = 0
        for ch in text:
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth < 0:
                    out.append(f'{where}: a "]" with no "[" before it')
                    return
            elif ch not in LETTERS and ch not in known:
                out.append(f'{where}: the letter "{ch}" is neither the turtle\'s (F L + - & ^ \\ / [ ]) nor a rule\'s')
                return
        if depth != 0:
            out.append(f'{where}: a "[" that is never closed')

    word(kind["axiom"], "kind.axiom")
    for letter, rule in kind["rules"].items():
        if isinstance(rule, list):
            if not rule:
                out.append(f"kind.rules.{letter} is a word, or a list of [weight, word]")
            for i, way in enumerate(rule):
                if (not isinstance(way, (list, tuple)) or len(way) != 2 or isinstance(way[0], bool)
                        or not isinstance(way[0], (int, float)) or not 0 < way[0] < math.inf):
                    out.append(f"kind.rules.{letter}[{i}] is [weight over 0, word]")
                else:
                    word(way[1], f"kind.rules.{letter}[{i}]")
        else:
            word(rule, f"kind.rules.{letter}")

    def rng(name, lo, hi, whole=False, needed=True):
        v = kind.get(name)
        if v is None and not needed:
            return
        bad = isinstance(v, bool) or not isinstance(v, (int, float)) or not (lo <= v <= hi) or (whole and v % 1 != 0)
        if bad:
            out.append(f"kind.{name} is {lo} to {hi}{' (a whole number)' if whole else ''} (got {v!r})")

    rng("angle", 1, 90)
    rng("turns", 1, 7, whole=True)
    rng("taper", 0.3, 1, needed=False)
    rng("shorten", 0.3, 1, needed=False)
    rng("wobble", 0, 0.3, needed=False)
    return out


def word(kind, rnd):
    """the word after `turns` rewrites: every letter with a rule becomes its rule's word (one of its ways, by
    weight) -> the word, or None when it grows past WORD letters"""
    text = kind["axiom"]
    for _ in range(int(kind["turns"])):
        out, length = [], 0
        for ch in text:
            rule = kind["rules"].get(ch)
            becomes = ch
            if isinstance(rule, str):
                becomes = rule
            elif isinstance(rule, list):
                pick = rnd() * sum(w[0] for w in rule)
                becomes = rule[-1][1]
                for w in rule:
                    pick -= w[0]
                    if pick < 0:
                        becomes = w[1]
                        break
            out.append(becomes)
            length += len(becomes)
            if length > WORD:
                return None
        text = "".join(out)
    return text


def _rotate(a, b, deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return ([a[i] * c + b[i] * s for i in range(3)], [b[i] * c - a[i] * s for i in range(3)])


def grow(kind, height, seed=1, trunk=None):
    """THE PLANT. kind = one of KINDS' names or a kind dict; height = studs it stands; seed.
    trunk = the stem's radius at its foot (unsaid: 0.035 of the height).
    -> ({"wood": [{"from": [x, y, z], "to": [x, y, z], "radius", "tip" (its radius at its far end), "depth" (0 = not
         inside any branch), "foot" (True: it starts on the ground)}] - wood[0] is THE STEM: of the pieces that start
         on the ground the one least deep in branches, the first of equals (a shrub has several stems: each says
         foot) -, "leaves": [{"pos"}], "height", "pieces"}, None) standing on (0, 0, 0) - or (None, why)"""
    if isinstance(kind, str):
        if kind not in KINDS:
            return None, f'no plant kind "{kind}": the kit\'s are {", ".join(sorted(KINDS))}'
        kind = KINDS[kind]
    wrong = problems(kind)
    if wrong:
        return None, wrong[0]
    if isinstance(height, bool) or not isinstance(height, (int, float)) or height != height or height < 2 or height > 400:
        return None, f"a plant's height is 2 to 400 studs (got {height!r})"
    if not _whole(seed, 0, 65535):
        return None, f"a plant's seed is a whole number 0 to 65535 (got {seed!r})"
    if trunk is not None and (isinstance(trunk, bool) or not isinstance(trunk, (int, float))
                              or not (0 < trunk <= height / 4)):
        return None, f"a plant's trunk is its radius at the foot, over 0 and at most a quarter of its height (got {trunk!r})"
    rnd = _lcg(seed)
    off = _lcg(seed + 70001)  # (the wobble's own numbers: a kind's forks are the same with and without it)
    wobble = kind.get("wobble", 0)

    def near(v):
        return v * (1 + wobble * (2 * off() - 1)) if wobble else v

    text = word(kind, rnd)
    if text is None:
        return None, f"this kind's word grows past {WORD} letters in {kind['turns']} turns: fewer turns, or rules that grow less"
    taper, shorten = kind.get("taper", 0.7), kind.get("shorten", 0.8)
    pos = [0.0, 0.0, 0.0]
    H, L, U = [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 0.0, 1.0]
    depth = 0
    stack, wood, leaves = [], [], []
    run = None  # (a straight run of F is ONE piece)

    def close():
        nonlocal run
        if run is not None:
            wood.append(run)
            run = None

    over = f"this plant comes to over {BUDGET} pieces of wood: fewer turns, or rules that fork less"
    for ch in text:
        if ch == "F":
            step = near(shorten ** depth)
            to = [pos[i] + H[i] * step for i in range(3)]
            if run is not None:
                run["to"] = to
            else:
                run = {"from": pos, "to": to, "depth": depth}
            pos = to
        elif ch == "L":
            close()
            leaves.append({"pos": pos})
            if len(leaves) > LEAVES:
                return None, f"this plant comes to over {LEAVES} leaf masses: fewer turns, or fewer L in its rules"
        elif ch == "[":
            close()
            stack.append((pos, H, L, U, depth))
            depth += 1
            if depth > DEPTH:
                return None, f"this plant has branches inside branches over {DEPTH} deep"
        elif ch == "]":
            close()
            pos, H, L, U, depth = stack.pop()
        elif ch in "+-":
            close()
            H, L = _rotate(H, L, near(kind["angle"] if ch == "+" else -kind["angle"]))
        elif ch in "&^":
            close()
            H, U = _rotate(H, U, near(kind["angle"] if ch == "&" else -kind["angle"]))
        elif ch in "\\/":
            close()
            L, U = _rotate(L, U, near(kind["angle"] if ch == "\\" else -kind["angle"]))
        if len(wood) > BUDGET:
            return None, over
    close()
    if not wood:
        return None, 'this kind grows no wood (no "F" is ever reached)'
    if len(wood) > BUDGET:
        return None, over
    top = max(max(w["from"][1], w["to"][1]) for w in wood)
    top = max([top] + [leaf["pos"][1] for leaf in leaves])
    low = min(min(w["from"][1], w["to"][1]) for w in wood)
    if top <= 1e-6:
        return None, "this kind does not grow upward: its highest point is at its foot"
    if low < -1e-6:
        return None, "this kind grows into the ground: some of its wood is under its foot"
    if any(leaf["pos"][1] <= 1e-6 for leaf in leaves):
        return None, "this kind has a leaf mass at its foot, on the ground: an L before any wood"
    if any(dist_(w["from"], w["to"]) <= top * 1e-6 for w in wood):
        return None, "this kind grows a piece of wood of no length (branches inside branches shorten it to nothing)"
    reach = max(math.hypot(p[0], p[2]) for w in wood for p in (w["from"], w["to"]))
    if reach > WIDE * top:
        return None, f"this kind reaches over {WIDE:g} times its height sideways: it is no standing plant"
    scale = height / top
    base = trunk if trunk is not None else height * 0.035  # (the stem's radius at its foot)
    twig = min(0.12, base)  # (never under a twig's width - nor over the stem's own)

    def thick(depth_, y):
        # thinner inside a branch (taper) and thinner toward the plant's top
        return max(twig, base * taper ** depth_ * (1 - 0.6 * y / height))

    # the stem first: of the pieces that start on the ground, the one least deep in branches
    feet = [k for k, w in enumerate(wood) if abs(w["from"][1]) <= 1e-9 and math.hypot(w["from"][0], w["from"][2]) <= 1e-9]
    if not feet:
        return None, "this kind's wood does not start at its foot"
    stem = min(feet, key=lambda k: wood[k]["depth"])
    order = [stem] + [k for k in range(len(wood)) if k != stem]
    out = {"wood": [], "leaves": [], "height": height, "pieces": len(wood)}
    for k in order:
        w = wood[k]
        a, b = [v * scale for v in w["from"]], [v * scale for v in w["to"]]
        thickness = thick(w["depth"], a[1])
        # (a bough that droops is no thicker at its tip than where it starts)
        out["wood"].append({"from": a, "to": b, "radius": thickness, "tip": min(thickness, thick(w["depth"], b[1])),
                            "depth": w["depth"], "foot": k in feet})
    for leaf in leaves:
        out["leaves"].append({"pos": [v * scale for v in leaf["pos"]]})
    return out, None


def dist_(a, b):
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))
