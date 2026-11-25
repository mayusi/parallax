<!-- reference for the parallax-sfx route card; verbatim from the skill page (2026-10-16) -->

## Recipe essentials
```json
{ "duration": 0.9, "variations": 3, "pitch_spread": 0.06, "weight": 0.5,
  "fx": { "reverb": 0.15, "loudness": -16, "transient": { "attack": 3, "sustain": -4 } },
  "layers": [
    { "role": "transient", "source": "noise", "seed": 12, "filter": { "type": "highpass", "cutoff": 2500 },
      "env": { "attack": 0.0002, "decay": 0.008 } },
    { "role": "tail", "source": "modal", "modes": [[820, 1.1, 1.0], [2262, 0.85, 0.7], [4431, 0.55, 0.45]], "gain": 0.45 },
    { "role": "body", "sample": ["lib:kenney.impact_metal_1", "lib:kenney.impact_metal_2"], "align": "peak", "weight_gain": 6 } ] }
```
Short noise bursts: give them a `seed` (the same noise every take; takes vary by pitch / strike) — unseeded, a 90 ms
brown thud swung 8 % → 38 % sub between takes. Sources: procedural, CC0 or royalty-free only (Kenney, Sonniss GDC,
Freesound CC0) — never Freesound-NC, BBC RemArc or Pixabay; index every pack with its licence (`kit sfx index`).
