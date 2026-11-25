"""direct_spark.py — the director's idea engine (v8.2): out-of-the-box on purpose. A director's first ideas are the
habitual ones (a bar, a panel, a glow); forced connections break the habit. A spark pairs an OBJECT of the game's
world with a MEDIUM from outside games, a VERB, a VOICE, a CONSTRAINT and an INVERSION - most sparks are wrong, a few
are the direction nobody would have reached by thinking straight.

    python kit/ui/direct_spark.py <brief> [--n 12] [--seed 7] [--game G]     (lune run kit ui direct spark ...)

Media already used by the brief's directions or named by an existing identity are left out (never re-skin the last
success). The sparks are written into the brief (`sparks`) so a direction can say which spark it grew from. One JSON
line: status / summary / next_action / sparks.
"""
import argparse
import json
import os
import random
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import direct  # noqa: E402

# concrete media from outside games: each one a thing with its own grammar a UI can borrow
MEDIA = [
    "a railway departure board", "a shrine talisman", "an emergency broadcast", "a museum label", "an x-ray film",
    "a tarot card", "a stadium scoreboard", "a weather map", "a receipt printer", "a vinyl record sleeve",
    "a stained-glass window", "an ECG monitor", "a fighter-jet cockpit HUD", "graffiti tags", "a theatre programme",
    "a banknote engraving", "a chess clock", "a seismograph", "a subway map", "police tape",
    "shadow puppets", "origami folds", "a tattoo flash sheet", "a circuit board", "a playing card", "a postage stamp",
    "a manga panel", "a film clapperboard", "a pachinko machine", "a karaoke lyric screen", "an omikuji fortune slip",
    "a ticket stub", "a wanted poster", "a field journal", "a star chart", "a tide table", "a barcode label",
    "a crossword grid", "a sumo banzuke ranking", "an airport flip board", "a hospital wristband", "a matchbox",
    "a temple bell", "a bus destination blind", "a passport stamp", "a sheet-music score", "a weather vane",
    "a war-room map table", "a lighthouse lamp", "a jukebox", "a cassette J-card", "a calligraphy scroll",
    "a vending machine panel", "a lottery ball draw", "a polaroid", "a sonar screen", "a pressure gauge",
    "a hanafuda card", "a festival lantern", "a manhole cover", "a traffic signal", "a kintsugi repair",
]
# real crafts and their physical processes - the animation IS the process (the owner loved: tally sticks notched and
# split, a chronicle stitched, breath on frosted glass, iron quenched; 2026-10-25)
CRAFTS = [
    ("tally-stick accounting", "a knife cuts notches, the stick splits down its grain"),
    ("embroidery", "a needle runs the outline, satin stitches fill it, the thread pulls tight"),
    ("blacksmithing", "iron glows, is struck, cools through cherry to black, hisses in the quench"),
    ("frost on a window", "ferns grow from the cold edge, breath fogs, a finger wipes it clear"),
    ("bookbinding", "signatures are folded, sewn through the spine, glued and pressed shut"),
    ("glassblowing", "a gather of glowing glass is turned, blown into a bubble, shaped and cracked off"),
    ("letterpress printing", "type is set backwards in a stick, inked, pressed into paper with a bite"),
    ("paper marbling", "drops of ink float on size, are combed into a pattern, a sheet lifts it off"),
    ("pottery on a wheel", "clay is centred, opened, pulled up into walls, cut off with a wire"),
    ("kiln firing", "glaze bubbles and melts, the colour shifts as it cools, crazing cracks appear"),
    ("weaving on a loom", "the shuttle passes, the beater packs the weft, a pattern rises row by row"),
    ("candle dipping", "a wick is dipped again and again, each layer thickening as it cools"),
    ("wax sealing", "wax drips, pools, a seal presses in and lifts, leaving its mark"),
    ("bread baking", "dough is scored with a blade, the score blooms open in the heat"),
    ("leather tooling", "a stamp is struck with a mallet, the leather darkens where it is burnished"),
    ("bell casting", "molten bronze pours into the mould, cools, the bell is struck and rings"),
    ("map engraving", "a burin cuts a line into copper, ink fills it, the plate prints"),
    ("woodblock printing", "a block is carved, inked with a brush, rubbed onto paper with a baren"),
    ("knot tying (quipu)", "cords are knotted in place values, a count read by touch"),
    ("rope making", "strands are twisted, laid up together, the rope tightens as it turns"),
    ("rubbing a gravestone", "paper over stone, charcoal rubbed until the carving appears"),
    ("cyanotype", "a sheet is exposed to the sun, washed, and the blue print develops"),
    ("darkroom developing", "a blank print in the tray, the image swims up, fixed and hung to dry"),
    ("clockmaking", "a spring is wound, the escapement ticks, a gear train turns a hand"),
    ("stone carving", "a chisel and mallet split chips away until the letter stands in relief"),
    ("fletching", "feathers are split, trimmed, bound to the shaft with thread"),
    ("lantern making", "paper is pasted over a bamboo frame, a candle is lit inside, it glows"),
    ("ice fishing", "an auger drills the ice, a line drops, the float jerks"),
]
CRAFT_MATERIALS = {"wood", "cloth", "ice", "metal", "paper", "ink", "stone", "leather", "glass", "fire", "plant"}

VERBS = ["stamps", "burns", "tears", "flips", "unrolls", "shatters", "breathes", "crawls", "rings", "prints", "peels",
         "melts", "freezes", "cuts", "inks", "pours", "folds", "glitches", "grows", "dissolves", "develops", "ticks",
         "stacks", "drips", "swings", "blooms", "rusts", "sparks", "rewinds", "fades"]
VOICES = ["the world itself", "the fighter", "a terrified bystander", "the enemy", "the system", "the city", "a god",
          "the crowd", "a narrator", "the weapon", "the dead", "a broadcaster"]
CONSTRAINTS = ["only two colours", "no rectangles anywhere", "every number is a physical object", "no text at all in a fight",
               "everything sits in the world, nothing on the screen edge", "it must work in black and white",
               "one shape repeated at every size", "it is drawn by hand, never typed", "it moves only on the beat",
               "the UI damages when you do", "it lies until the last moment", "the whole HUD is one object",
               "it fits inside a thumb's reach", "silence until something matters", "it is lit by the world, not by itself"]
INVERSIONS = ["what if the HUD showed only what the ENEMY knows?", "what if nothing is shown until it matters?",
              "what if the information were SOUND or SPACE instead of numbers?", "what if the UI got calmer as the fight got worse?",
              "what if your health were visible to everyone but you?", "what if the UI belonged to the place, not the player?",
              "what if winning made the UI disappear?", "what if every number counted DOWN to something?",
              "what if the UI were the opposite colour mood of the world?", "what if the UI remembered the whole round?"]


NOT_THINGS = {"battlegrounds", "anime", "manner", "showcase", "players", "player", "game", "games", "world", "lane",
              "kit's", "fourth", "third", "second", "first", "built", "night", "fight", "style", "genre", "source"}


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}, ensure_ascii=False))
    return 0 if status == "pass" else 1


def used_words(d):
    """the media words the brief's directions and every existing identity already use"""
    text = " ".join(str(x.get("medium", "")) + " " + str(x.get("world_object", "")) for x in d.get("directions") or [])
    text += " " + " ".join(str(i.get("about", "")) for i in direct.identities())
    return direct.content_words(text)


def sparks(d, n=12, seed=7):
    rng = random.Random(seed)
    objs = list((d.get("context") or {}).get("world_objects") or [])
    pitch = str((d.get("context") or {}).get("pitch") or "")
    # the pitch's things (not its adjectives or its genre words): plain nouns only
    if len(objs) < 4:  # (the blueprint's named parts are things; the pitch's words only when there are few)
        objs += [w for w in re.findall(r"\b[a-z]{4,}\b", pitch.lower())
                 if w not in direct.STOP and w not in NOT_THINGS and not re.search(r"(ing|ed|ly|al|ous|ive|ful)$", w)][:12]
    objs = sorted(set(re.sub(r"^(the|a|an) ", "", o) for o in objs if o)) or ["screen"]
    used = used_words(d)
    media = [m for m in MEDIA if not (direct.content_words(m) & used)]
    crafts = [c for c in CRAFTS if not (direct.content_words(c[0]) & used)]
    rng.shuffle(media)
    rng.shuffle(crafts)
    share = craft_share()
    out, seen = [], set()
    for i in range(n):
        o = rng.choice(objs)
        voice = rng.choice(VOICES)
        if crafts and (rng.random() < share or not media):
            c, process = crafts.pop()
            if (o, c) in seen:
                continue
            seen.add((o, c))
            out.append({"spark": f"the HUD IS the {o} made by {c}: its animation IS the process - {process}, spoken by {voice}",
                        "object": o, "craft": c, "process": process, "voice": voice,
                        "constraint": rng.choice(CONSTRAINTS), "inversion": rng.choice(INVERSIONS)})
            continue
        if not media:
            break
        m = media.pop()
        v = rng.choice(VERBS)
        if (o, m) in seen:
            continue
        seen.add((o, m))
        out.append({"spark": f"the HUD IS the {o} treated as {m}: it {v}, spoken by {voice}",
                    "object": o, "medium": m, "verb": v, "voice": voice,
                    "constraint": rng.choice(CONSTRAINTS), "inversion": rng.choice(INVERSIONS)})
    return out


def craft_share():
    """how many sparks come from a real craft process: weighted by what the OWNER liked (2026-10-25: the craft-process
    board 'all amazing original ideas', the neon signage board not liked) - read from every brief's owner_feedback"""
    liked = disliked = 0
    for bp in direct.glob_briefs():
        try:
            with open(bp, encoding="utf-8") as fh:
                bd = json.load(fh)
        except Exception:  # noqa: BLE001
            continue
        procs = {x.get("key"): bool(str(x.get("process") or "").strip()) or x.get("axes", {}).get("material") in CRAFT_MATERIALS
                 for x in bd.get("directions") or []}
        for fbk in bd.get("owner_feedback") or []:
            liked += sum(1 for k in fbk.get("liked") or [] if procs.get(k))
            disliked += sum(1 for k in fbk.get("disliked") or [] if procs.get(k))
    return max(0.3, min(0.85, 0.5 + 0.05 * (liked - disliked)))


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--game", default=None)
    a = ap.parse_args(argv)
    try:
        p, d = direct.load(a.name, a.game)
    except (OSError, json.JSONDecodeError) as e:
        return emit("fail", f"direct spark: {e}", f"lune run kit ui direct new {a.name} --ask \"...\"")
    got = sparks(d, a.n, a.seed)
    d["sparks"] = {"seed": a.seed, "list": got}
    direct.save(p, d)
    lead = got[0]["spark"] if got else "none"
    return emit("pass", f"direct spark {a.name}: {len(got)} forced connection(s) - e.g. '{lead}'",
                "read them against the brief; a direction grown from one names it (\"spark\": <n>); another round: --seed <n>",
                sparks=got)


if __name__ == "__main__":
    sys.exit(main())
