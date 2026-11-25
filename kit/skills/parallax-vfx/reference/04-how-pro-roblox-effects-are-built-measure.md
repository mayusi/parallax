<!-- reference for the parallax-vfx route card; verbatim from the skill page (2026-10-16) -->

## How pro Roblox effects are built (measured studies of published effects; apply them)
- **Many layers, one sprite each**: a single slash hit is 40-60 layers; median emit count 1. Stack sprites timed in
  place, 25-50 ms apart. Nothing fires at the same time.
- **Brightness + bloom**: hot layers run `brightness` 5-50 (median 9); a white-hot core 50-150 for 0.03-0.1 s. Glows
  and halos: `lightEmission` 1 at brightness 1-6. Hard cel shapes: `lightEmission` 0 or negative.
- **Value**: bright reads only against dark — `twin` (a black / dim copy, same texture, zOffset -0.25..-1), dark
  tails in colour gradients, dark smoke against fire. White is a thin shape (rings, flares), not a fill.
- **Orientation**: `FacingCamera` puffs/glows, `VelocityPerpendicular` flat rings/crescents (needs speed > 0, even
  0.001), `VelocityParallel` + `squash` 2-3 streaks (sparks, speed lines, rising light).
- **Timing**: intensity only goes down after the hit, but an explosion's MASS keeps growing 0.25-1.3 s. Lifetimes:
  flash 0.03-0.15 · crescents 0.15-0.4 · body 0.35-1.2 · rings/debris 0.4-1.4 · smoke/marks 1-3 (scorch to 6).
  Anticipation 0.1-0.6 s (ultimates up to 2.5): energy gathers INWARD (`shape.inOut: "Inward"`).
- **Palette**: ~5 colours, saturated energy + desaturated matter (dust, rock) — always pair the two.
