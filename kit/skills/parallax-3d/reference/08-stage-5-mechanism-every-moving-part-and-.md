<!-- reference for the parallax-3d route card; verbatim from the skill page (2026-10-16) -->

## Stage 7 — Mechanism: every moving part, and the take-apart
Every part that moves in the real object is its own part with its joint (`a.joint` in the build calls of the shape stage:
slide, hinge, fixed; `after=` for a sequence), enclosed parts in `with a.internal():`, game attachment points with
`a.anchor`, bores and sight lines kept clear with `a.clear_path`. Declare the take-apart early: it finds geometry
errors no other check sees.
**Take-apart (assembly / disassembly)** — an object made of real parts comes apart in a real order, down to its
screws: declare it once every part exists, like a manual's field strip + detail strip:
```python
a.disassembly([
    {"name": "magazine out", "parts": ["Magazine", "Follower", "Round*"], "move": (0, -0.6, 0.2)},   # studs
    {"name": "rounds out of the magazine", "parts": ["Round*"], "path": [(0, 0.3, 0), (0, 0, -0.2)]},  # moves again
    {"name": "grips off", "parts": ["GripPanel"], "move": (0.1, 0, 0), "outward": True},  # left goes left
    {"name": "barrel out", "parts": ["Barrel"], "path": [                  # a part held at BOTH ends TURNS out:
        {"turn": 12, "axis": (1, 0, 0), "pivot": at(183.9, BORE_H)},       # tipped about the ring holding its muzzle,
        mv(df=-10, dh=-2.1), mv(dh=-40)]},                                  # back along its own axis, then down
], base=["Frame", "Magazine"])                       # what everything comes off (sub-assemblies' bases too)
```
The build checks every step comes out CLEAR along its path against where the other parts are at that step ("Barrel
runs into Frame at 4% of its path" = a real collision: take that part first, change the path, or cut the clearance
the real part has — a dovetail, an open slot), and that every part comes off (`disassembly`, an error at hero / aaa).
A jam says WHERE ("around (x, y, z) studs": the middle of the mover's colliding faces) — read it as the part's own
units and you see what is missing (the Silverballer's: a 1911 nose's keyhole for the barrel's lug, the rear sight's
dovetail, a grip safety's pocket open to the rear, a follower 0.2 mm wider than its magazine). A part taken off must
leave the others' way clear: out, then ASIDE (`"path": [mv(df=60), mv(dh=60)]` — a bushing parked in front of the
slide stops the barrel). SOFT parts squeeze past instead of jamming: a spring (named ...Spring) compresses, rubber /
silicone / leather / fabric / foam (the kit material its faces use) stretches — the step's row says `squeezed`, the
gate's line names it ("GripRubber squeezed past Frame"); the same part in steel jams.
It renders the steps (`build/renders/<asset>_strip.png`) and exports the ASSEMBLY: every part its own mesh with its
maps (`build/models/<asset>_assembly.fbx`; the steps in the manifest). Pins and screws need real holes to come out
through: a pin buried in a wall cannot be pushed out.
`lune run kit asset <asset> --schematic` renders the mechanism's views (asked for since 2026-11-11: every full build
rendered them, 17 of one hero's 20 minutes; the clearance check itself runs on every build), then
`lune run kit schematic <asset>` -> three sheets: GA drawing (third angle, hatched section, dimensions, parts list),
mechanism (exploded + every joint at full travel), model sheet. A kept set of views is marked stale when the model
changes; `kit schematic` then asks for them again instead of drawing an old model.

**THE CYCLE PLAYS IN THE GAME (2026-11-15, `rbx_cycleplay`).** Every `a.cycle` is also written for the game: the
manifest carries it as a table - EVERY moving joint's value over time (one the cycle does not key stands at rest,
as the build posed it when it checked the cycle), sampled from the same eased frames the build checked and thinned
to the keys a straight line cannot stand in for (within a quarter of a degree, two thousandths of a stud, or 2% of
the joint's own travel, at the frames) - the model file carries the table, and
`Models.play(model, "Cock and fire", { onMark = function(name) ... end })` moves the spawned model's joints through
it (`handle:Stop()`, `{ loop = true, speed = 2 }`, `Models.cycles("revolver")` for the names). BLENDING (stage P):
`{ fade = 0.25 }` fades the cycle in over a quarter second from wherever the joints stand - the cycle playing before,
a pose, rest - eased, every joint the new cycle does not key easing to rest (`ModelRules.blend`); without it a cycle
cuts to its start. The poses inside a fade are checked (2026-11-17, `rbx_cycleplay.fades`, the game's own blend: a
straight line in the joints): from REST into every cycle - every model spawns there - FAILS `cycle_fade` where a part
is driven into another (`build_cycle_fade.py`: a hold with the pin down, clear, but the way in from rest turns the
lug through the half-lowered pin); from a one-shot's end and from any moment of a loop into every other cycle is
SAID (`cycle_fade_between`, a warning: the build cannot know the game plays that change - never play it with a
fade, or key the two to meet). A mark of the cycle
(`marks={"fire": 26}`) calls back by name as it is passed - that is where the game fires the shot, plays the sound.
`a.cycle(..., loop=True)`: it plays round and round, so it must END where it BEGAN - `cycle_loop` fails the joint
that would jump (a wheel keyed 0 to 360 is back where it began). A mark must lie inside the cycle's own frames. A
second play on a model stops the first; a play on a model that has left the game stops by itself. Not built: a
cycle blended with another, or driven by anything but time (a trigger pulled half way is `Models.pose`); a
shape-only round (`--geo`) does not check the loop; nothing of the player was seen in Studio.

**THE ACTION CYCLE: the mechanism RUNS (2026-11-10, the owner: "It's really bad at making hero weapons ... especially
with detail and proper mechanisms").** `a.joint` alone checks each joint by itself, at stops set from its travel (2026-11-15, `rbx_travel`: between two
stops the group moves no further than half its own smallest depth, so a pin standing ACROSS its path is cut by its
surface at one stop at least - five stops whatever the travel let one through; 48 pieces at most, and a travel too
long for that is said in the facts as `<Joint>@coarse`, the path between two stops in studs. Not seen: a thing
thinner than that path which the group swallows whole, its faces never cut); nothing moved in the
.blend he judges, and two parts that each clear alone still meet when they move together. `a.cycle(name, keys, fps=24,
marks={...})` (kit/blender/rbx_cycle.py): keys `[(frame, {joint name: value | "min" | "max"})]`, each joint eased
between ITS OWN keys and held before / after them - one joint leading or lagging another IS the coupling, so HOLD a
joint with a key wherever it must stay put (a pin keyed only at frames 1 and 26 sinks the whole time between).
```python
a.cycle("Cock and fire", [
    (1, {"Hammer": 0, "Bolt": 0, "Cylinder": 0, "Trigger": 0}),
    (6, {"Hammer": 9, "Bolt": "max"}),     # the stop drops as the hammer starts
    (8, {"Cylinder": 0}),                  # held: the cylinder waits for the bolt
    (20, {"Cylinder": -60}),               # one chamber, clockwise seen from behind
    (21, {"Hammer": 46, "Bolt": "max"}),   # full cock; the bolt still down
    (24, {"Bolt": 0}),                     # and up into the next notch
    (34, {"Hammer": 46, "Trigger": 0}), (36, {"Trigger": 8}), (38, {"Hammer": 0}), (44, {"Trigger": 0}),
], marks={"cock": 1, "full cock": 21, "fire": 35})
```
Several cycles play one after another. The build checks the cycle with ALL the joints posed together (triangle
pairs + the surface-depth test the joint check uses), at poses picked by how far the parts MOVE: no moving group
goes further than half its own smallest depth between two checked poses (a pose can fall between two frames).
Two limits, both SAID when met (`cycle_coarse`, a warning, with how far a part went unseen and which part): one
frame-to-frame move is cut into 512 pieces at most, and a model's cycles into about 400 poses - a very fast
move of a very thin part, or a very long cycle, is checked more coarsely than the part asks: give the fast move
more frames. Gate `mechanism_cycle` names the frame, the two groups and where ("at frame 10.33 'pin' drives into
'wheel' ... Pin into Lug"), an error at hero / aaa; then keys every moving
group on the saved .blend's timeline with markers (the owner presses play), and writes the cycles to the manifest
for the game (Models.pose per key). Selftest: `cycle_pin_in_path` (caught) / `cycle_pin_timed` (spared) / `cycle_fast_pin` (a lug swung through a
pin between two frames: caught) / `cycle_fast_clear` (spared). A real
mechanism's cuts come with it: the channel a hammer's tail swings into, the frame's groove an ejector rod strokes
through - the cycle check finds each one missing.

**SOCKETS AND MATES** (`a.socket`, `a.at`, `a.mate`, 2026-11-15; `rbx_mate`; his D-R04). A SOCKET is a named
place on a part where another part meets it - a point, the direction it faces OUT of its part, and how far
across the hole or the pin is - on a part you built or one you generated / imported (the name is what makes a
shapeless piece's place usable). A MATE says two sockets meet.
```python
H = 1.0
a.box("Body", (2, H, 2), (0, H / 2, 0), "body")
a.socket("Well", "Body", (0, H, 0), axis=(0, 1, 0), size=0.5)          # from the SAME number as the box
x, y, z = a.at("Well")                                                # the meeting part FOLLOWS the socket
a.cylinder("Peg", 0.23, 0.8, (x, y + 0.4, z), "peg", axis="Y")
a.socket("PegFoot", "Peg", (x, y, z), axis=(0, -1, 0), size=0.46)
a.mate("Peg in Well", "PegFoot", "Well", fit=(0.01, 0.05))            # seated; 0.01 to 0.05 studs of room a side
```
`how="seat"` (default): the two at one place, facing each other. `how="slide"`: the plug anywhere on the
socket's LINE, the two directions along one line (a magazine in its well, a pin in its bore). `a.at(name,
out=0.2)` is the place 0.2 studs out along the socket; use it for `pos=` and for a joint's `pivot=`. In the game
each socket is an Attachment of its name on Root (its place; its direction is in the manifest, `sockets`).
A socket's name is an anchor's too: `a.anchor` may not reuse it. Held (`mates`, an error): a socket that no
longer lies ON its part's built surface (within 0.02 studs, or 1% of
the part) - the part changed and the socket did not - is failed by ITS name with how far off it is; a mate that
no longer holds says what is off and by how much (apart, turned, off the line, too tight, rattling). Say them at
the top level of the script. NOT done: nothing is MOVED for you (no solver re-places a part: `a.at` is how a part
follows; the check is how a forgotten one is found); a generated piece's sockets are not found for you - you name
them by looking at it. MEASURED (2026-11-17): each socket's HOLE or PIN is read off its part - just inside the
mouth, rays round it meet a hole's walls or leave a pin's side; a ROUND one only (a square peg, a slot or a flat
face is not read), a pin only where the part is narrow there. A size left out IS that width (`size_from:
measured`: a generated piece's socket gets its size from its own surface, and `fit=` reads it); a size given that
its part does not measure within 10% is said (`socket_size`, a warning). The middle of a hole's mouth counts as
on its part (its nearest surface is the wall round it: it was called off).

**A CHAIN POSED BY ITS TIP** (`a.reach`, 2026-11-15; `rbx_ik`; inverse kinematics). A crane's boom, an
excavator's arm, a desk lamp, a walker's leg: joints made with `a.joint`, each carried by the one before. Say
where the tip should be and the joints' values are found:
```python
a.reach("Arm", ["Shoulder", "Elbow"], tip=(0, 5.3, 0.7), poses={"out": (3, 2.5, 0.7), "stowed": (0.8, 2.6, 0.7)})
```
`joints` runs from the base outward (each one's parent is the group the one before it moves: the build stops
otherwise); `tip` is the point the last joint carries, where the model is built. Each named pose is solved at
build time (joint by joint from the tip back, held to the limits; from several starts when the first does not
get there), replayed through the kit's own joint rule, and written to the manifest (`chains`). Held: `reach`
FAILS when a pose you named cannot be met - a place past the chain's length is said as that; otherwise the
reason is PROVEN where it can be (2026-11-17): every joint swept through its limits gives a bound no pose there
comes nearer than, and swept again with the hinges free all round it tells "its joints' limits stop it, proven"
from "the chain cannot turn its tip there at any angle, proven" (a place off the way its joints turn). Since
2026-11-18 a chain of ANY length is proven too: where the grid sweep stops (more than 4 joints) or cannot rule a
pose out, branch and bound splits the joints' values and rules out only by the same bound; with the hinges free,
a pose the solver finds proves "the limits stop it", a FLAT chain (every hinge parallel) has its plane as an
exact bound, and a TURRET carrying a flat arm (a crane, an excavator, a desk lamp) is bounded at every angle of
its turret. Only a proof that runs out of its budget keeps the solver's reading and says "not proven"; one that
finds a pose the solver missed says so as a kit fault. Say `a.reach` at the top level of the
script (not inside a.frame / a.mirror / a.repeat: its tip and targets are the model's own frame); a joint of a
chain may not follow another (`a.couple`). A chain joint with `after=` is posed with the joints it waits on at
their `after=` values (the `reach_clear` check below: a cover slid away first, then the arm lifts - it was posed with
the cover still shut and called driven in); the GAME's `Models.reach` does not move them for you. In the game:
```lua
Models.reach(model, "Arm", "stowed")                 -- a pose the build solved
local miss = Models.reach(model, "Arm", somePart.Position)   -- any place in the world: studs it falls short by
```
The game solves with the same steps and the same starts (`ModelRules.reach`), going on from the pose the chain
is in; a Tool reaches from its Handle and a model resized with ScaleTo from its own scale. Held too
(`reach_clear`, an error; 2026-11-17, stage P): every solved pose with the WHOLE model posed together - the
chain's joints and the joints that follow them - from rest into the pose, every part against every other (each
joint's own travel is checked alone by `mechanism`; a chain folded can still drive one link into the body or into
a third part: the fixture's forearm comes down through a bollard each joint alone swings clear of). NOT checked:
a pose reached from another pose rather than from rest.

**ONE JOINT FOLLOWS ANOTHER** (`a.couple`). `a.couple("Wrist", drives="Elbow", ratio=-1.0)`: the follower's
value is ratio x the driver's + offset - a gear turned by its neighbour, a wrist that stays level, a second door
leaf. Posing the driver in the game poses its followers (`Models.pose`). The build stops when the driver's
travel would push the follower past its own limits. The travel check (`mechanism`) sweeps a follower WITH its
driver (2026-11-17): at each stop of the driver's travel every follower - and what rides on it - is posed by the
rule, and its surface is tested too ("Arm at 45° (its follower Hand at 45°) drives into ..."); a follower's own
travel is not swept alone (it never moves alone: `<name>@follows` in the facts). Before, each was swept on its
own: a hand that doubles its arm's turn reached a ceiling neither reached alone. A cycle (`a.cycle`) keys its
joints itself: key the follower there too. `a.joint` refuses limits given the wrong way round (min past max).

**THE RIG'S OTHER WORDS, FOR A KIT MODEL.** A kit model is RIGID groups on joints: its "skeleton" is the joint
tree (`a.joint`'s `parent=`), its "bone placement" each joint's `pivot` and `axis`, its "constraints" the
limits, `kind="fixed"`, `after=` and `a.couple`. Nothing bends, so there is no skin to weigh and no joint to
deform across: a joint is tested by its travel (collisions along the whole of it). ROOT MOTION - a cycle that
moves the whole model - is the game's to apply to the model it spawned; a cycle keys joints only. RETARGETING -
one model's cycle on another - is NOT built: `Models.play` plays a model's OWN asset's cycles and nothing maps
one rig onto another (two assets that should move alike are given the same `a.cycle` in their scripts).
