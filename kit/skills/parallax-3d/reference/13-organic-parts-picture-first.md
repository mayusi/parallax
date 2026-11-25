<!-- reference for the parallax-3d route card: sculpted / organic hero parts, picture first (2026-11-12) -->

## Organic hero parts (a wolf's head, a wing, a mane, a beast): picture first, never typed

A sculpted part is NOT typed as shapes. The owner stopped that route on 2026-11-12 ("the tryouts look horrible ...
try something new"): seven rounds of typed feathers gave a slab of lozenges, exactly as the dragon sword and the skull
had shown before. The look comes from a PICTURE the local image model draws from the owner's own reference; the 3D
shape comes from a generator fed that picture; the detail comes back from pictures again. Each step ends in a picture
the owner can judge in seconds — show it before the next step. Typed shapes (`a.cad`, `a.sculpt`) stay for machined
parts and simple repeats.

First run: the Gjallarhorn's winged wolf. In its reference the wolf is 282 x 125 px; the launcher's old wolf (made
straight from that crop) read as a melted lion. The owner on this route's first part: "Wow, I'm actually kind of
amazed"; then: "You have to get it correct from every angle."

### 1. Redraw the reference large — 33 s
The feature in the reference is too small to build from (the model sheet refuses under 2 px per mm). Put its crop on
plain grey, scale it to about 1 megapixel, and have the image model redraw the SAME design large:

    lune run kit vision plate "A sharp, highly detailed studio photograph of <what it is>. Same design, pose and
        proportions as the reference. Plain neutral grey background, soft even light, no text."
        --from <crop.png> --n 2 --steps 4 -o <folder>

Two seeds in one load (FLUX.2 klein, 8.8 GB). It keeps the design; the fine detail is INVENTED — never measure
from it. `kit vision edit` (Qwen) needs 22 GB of free memory and rarely starts. **Show the owner the redraw beside the
crop. Go on only on his yes.**

A redraw that comes out mirror-polished is redrawn once more FROM ITSELF as matte bronze (the same layout, 31 s)
before anything is generated from it: a highlight is light, not shape (the heel wolf's first redraw).

### 2. Generate the part from that ONE picture — about 2 minutes
    lune run kit vision cutout <plate.png> --rgba -o <cut.png>
    lune run kit gen <name> --image <cut_rgba.png>            # TRELLIS.2 -> assets/models/<name>.gen.glb

(A design that is not ours never goes into the repo: run `kit/gen/trellis2_run.py <cut_rgba.png> <out.glb>` in the
trellis2 environment with an output path outside it.) From a side picture of a head with a wing it builds the whole
symmetric piece: one head, a wing each side.

- **Several views must come from ONE design.** Two views redrawn separately disagree (a beard in one, none in the
  other) and a multi-view generator (`kit gen views`) merges them into a muddy head. One picture, or renders of one
  part.
- **A colour key is not a cut-out**: a face in shadow is eaten. Crop tight and let the image model isolate it.
- **The generator's mesh is a thin crust with an inner wall** (both wolves: 99% of the surface one voxel thick).
  Where the crust has gaps the two walls are one surface, and a remesh keeps both: half the triangles and half the
  colour map on an inside nobody sees (the nose wolf: 446,224 triangles, 98.5% of them a double wall). The new skin
  of step 4 sheds the inner wall and closes the gaps (the same part: 229,472 triangles, 0 open, 0 pinched); its
  line says so ("made solid: ... its inner wall of N faces removed"). A part sharpened before 2026-11-12 still has
  the double wall: sharpen it again.
- **A stray piece** (a rod, a strut, a stand: the heel wolf came out with a thin rod along its top, read off its
  picture's back edge) is cut away before any fit: `--drop`, below.

### 3. Check the SHAPE from every angle before any detail
Crop the feature from EVERY view the reference has (side, front, both front corners, top) at full size, render the
part from the same angles, and lay them side by side, view by view. The chart is what says one head or two, where the
wings lie, how wide it is. A generator fans paired wings out in a V (27.8 degrees each side on the wolf: as wide as it
was long) where the real ones lie along the housing:

    lune run kit sharpen <part.glb> --fold ...                # lays the pair straight back first (step 4 follows)

The fits `--fold` takes, each read off the reference and eased so nothing creases:

| fit | what it does | the wolf |
|---|---|---|
| `--flare 1.59` | the wings move out to the width of what they lie on; the head keeps its own width | stretching the WHOLE part to reach round the 96 mm housing made the face 1.59 times too broad ("Fix the face first") |
| `--snout 1.15` | the muzzle lengthened (what lies ahead of the eyes) | its head was 53 mm long x 72 tall against the reference's 55 x 50 |
| `--nod 18` | the head pitched down about a hinge in the neck | a generator sets a head level; the reference's looks down, and from the front a level head shows a short broad face |
| `--tail 2.2` | what lies behind the head is made that many times as long, eased in (the part is then sized by its whole length as before) | a generator draws a head about as long as its wings: the nose wolf was 85 mm from nose to brow where the chart has 43, on the right overall length |
| `--level 0.68` | a part generated as ONE solid piece is a wedge (it widens to its tail): its body behind the head is brought to one width, a share of its length, so it lies on flat flanks | the heel wolf on the 47 mm stock: its front half sank inside the stock and only the wing tips showed; `--flare` would have pushed the tail half a width off |
| `--drop x0,x1,a0,a1,z0,z1` | FIRST a box of the part is cut away and the cut capped (fractions of its own box: across, along from the nose, up) | the heel wolf's rod: `--drop 0.44,0.56,0.38,0.80,0.715,0.92`, 10,222 faces |
| `--keep 40` | how much of the splay stays: a solid piece has no pair of wings to lay back | the heel wolf (splayed 34 degrees a side, kept) |
| `--faces 160000` | thinned to a triangle budget, its UV seams welded first so the skin stays closed | thinned as a GLB is read, the second wolf's skin opened along every seam: 38,201 open edges, its build refused |

The fits run the head's first (`--snout`, `--nod`: they read the part as it was generated), then `--tail`, then
`--level` (it reads the final length).

Measure before you fit - the part's whole length AND its parts against each other (the head against the wing), in
mm, through the same window as the reference: the nose wolf was sized by its whole length alone for five rounds, and
its `--nod 18` was judged from the front view, 11 degrees too far by the side view. Try a fit as a PREVIEW on
the built model first: dropping the part onto the built file and rendering four close-ups takes about 20 s, a full
build of the launcher 11 minutes.

ANOTHER PLACE on the model is another part until its own reference says otherwise. The launcher has two wolves,
the big one on its nose and a small one at the stock's heel, and they are two sculpts: the heel wolf has a bigger
head and a slimmer wing. The nose wolf fitted small for the heel (rounds 6-7) read as a wing with a beak under it;
made from ITS OWN picture - the heel cut out of the chart's side view, 182 x 100 px, steps 1-4 again (31 s + 114 s +
6 min) - it read as a wolf at once. Only when the reference shows the SAME sculpture again is the sharpened part
fitted a second time, its maps kept, in seconds:

    lune run kit sharpen <part>.sharp.glb --fit-only [--level ..] [--nod ..] --faces 160000 --out <second>.glb

Either way it is PLACED FROM THE REFERENCE'S OWN MILLIMETRES, never by eye from a close-up: cut the reference
through a window of the model's own frame (the scale from the silhouette's length, the origin at its front end and
its axis, a mm grid on it) and render the build through the same window at the same pixels per mm, side by side.
Three eyeballed previews put the heel wolf 50 mm too far back and 20 degrees too steep; one same-window pair put its
nose on the right point and showed that the build's whole frame round it was misread. Then its own box
(`stretch=True`), what it should not have cut off (`crop=`: the heel wolf's base slab), its own texture group.

Detail cannot fix a shape: a sharp redraw of a muddy head is a sharp muddy head.

### 4. Sharpen — six views, about 55 s each
    lune run kit sharpen <part.glb> --about "<what it is>" --detail "<what must be crisp>" [--fold] [--metal gold]

View after view (left side, front, right side, both front corners, top): render the part as it is now -> the image
model redraws THAT render sharp (the redraw keeps the render's layout, so it lines up with the shape) -> the redraw is
projected back through the same camera into the part's own colour map, weighted by how squarely the view sees each
point and only where it really sees it. Each view builds on the ones before. Then the maps of a game material —
colour (its own, or its light and dark carried onto gold), roughness, a tangent-space normal map — and a closed
skin: `<part>.sharp.glb`.

- The normal map is the colour's light and dark, not a measured height: its strength is low on purpose (at 2.5 a
  redraw's speckle read as a crust on the wolf's gold). Look at it lit.
- The part gets a NEW SKIN first (one watertight surface, its colour baked across): a generator's skin folds through
  itself, and a build's import then leaves holes or winds patches inward - black cracks over the whole part.
- `kit vision relief` on the big redraw keeps every feather but is shallow as geometry: its detail is colour too.

### 5. Into the build, at the reference's MEASURED size
    a.import_mesh("Wolf", "<part>.sharp.glb", size=(...), stretch=True, pos=..., rot=(0, 180, 0), ground=False,
                  group="wolf")                                # NO mat=: the part keeps its own maps

Measure the feature in the reference against a known length (the wolf: 273 px of a 1,720 px = 1,231 mm launcher =
195 mm, not the 270 mm its first box had). What the part sits on keeps its own shape under it (the housing's full
width under the wings); a core that filled an older part's hollow is cut back, or it shows as a flat plate. Then
close-ups of the part ON the model, from the reference's angles, beside the reference and beside the build before.

The MODEL it goes onto must have declared its own reference first (`a.trace_match`, the chart's view traced with
`kit trace --cutout` when the object is pale: a plain trace took the launcher's ivory for backdrop). The launcher's
build never had, so the kit's outline check never ran on it, and the heel wolf's seat - the stock's thumbhole, built
as a trigger guard with a pistol grip behind it - was only found when the wolf would not sit.

### What each step costs (RTX 5070)
| step | tool | time |
|---|---|---|
| redraw the reference large | `kit vision plate --from` | 33 s for 2 |
| cut out | `kit vision cutout` | 18 - 28 s |
| generate | `kit gen` (TRELLIS.2) | 128 s |
| fold | `kit sharpen --fold` | seconds |
| fit a sharpened part again | `kit sharpen --fit-only` | about 20 s |
| sharpen, 6 views | `kit sharpen` | about 6 min |
| the model's build | `kit asset` | its own |
