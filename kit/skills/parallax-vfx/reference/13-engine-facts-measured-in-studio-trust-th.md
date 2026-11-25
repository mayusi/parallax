<!-- reference for the parallax-vfx route card; verbatim from the skill page (2026-10-16) -->

## Engine facts (measured in Studio — trust these)
The full page with every measurement and its capture: `kit/knowledge/vault/vfx/refs/engine-facts.md` (probe:
`kit/vfx/facts.luau`). The ones that change how you build (2026-10-16):
- Studio IGNORES an EditableMesh's per-vertex alpha (VfxMesh `fadeIn` / `fadeOut` / `fadeSides` / `erode`) and the
  alpha of its `TextureID` / `TextureContent`: a mesh shell draws its whole texture square, opaque. The player shows
  both, so player and booth disagree on mesh layers. Only a SurfaceAppearance (ColorMap + AlphaMode Transparency)
  gives a mesh alpha, and a game script cannot set ColorMap (Plugin capability): author them ahead, clone at runtime.
- Vertex RGB renders (Neon 253 -> 29), but black still occludes: darkening is not fading.
- Wobble costs ~0.25 ms of Luau per 697-vertex flame per frame: 60 wobbling layers = 14-17 ms = the whole frame.
- Highlight outlines work on runtime meshes; VfxMesh cards + `cell()` flip cells (0.017 ms a call).
- A Beam texture's VERTICAL axis runs along the beam, horizontal across the width (author strips upright).
- `FaceCamera = false` makes a Beam a ONE-SIDED wall: width along Attachment0's Y, seen only from its -Z side
  (`plane: "up"` draws both faces for you).
- `Players:CreateHumanoidModelFromDescription` works in edit mode; the rig's joints are AnimationConstraints
  (not Motor6Ds): pose by FK over the rig attachments (child = parent * a0 * rot * a1^-1) with parts anchored.
- Additive layers ADD UP: near the beam, glows + curtain + waves + halo + bloom go flat white. Keep the sprites
  that ride a beam few and small; judge from the camera that will be nearest.
- Particles do NOT draw EditableImage textures (accepted, invisible): upload real textures.
- An uploaded image is usable in Studio within seconds; preload (`VfxStage.preload`) or the first burst is lost.
- Attachments: parent first, then set `WorldPosition` (before parenting it is read as a local position).
- Studio edit mode ticks ~20 Hz when unfocused: the booth freezes on exact times, so captures stay correct.
