Twelve presets the METHOD gate must refuse, each built from its own copy of a MADE scene (three beats: a glint, a
crescent of flame, embers; no real footage). Their twin that passes is kit/selftest/vfx/methods_good.

| Preset | What is wrong | The gate says |
|---|---|---|
| preset_methods_noplan | the chart's beats name no method | `beat 0 ("glint") names no method` |
| preset_methods_unused | beat 1 plans UV scrolling; the scrolling ring is a layer of beat 0 | `beat 1 plans "UV scrolling / panning" and nothing that plays in that beat uses it` |
| preset_methods_ask | beat 1's words say "flame"; the plan neither uses hand-drawn nor says why not | `beat 1 ("crescent of flame") shows "flame"` |
| preset_methods_dropped | the owner approved hand-drawn on beat 1; the plan dropped it afterwards | `was on the chart the owner approved and is gone from the plan` |
| preset_methods_unseen | a reason for leaving hand-drawn out, written after his approval | `is not on the chart the owner approved` |
| preset_methods_missing | beat 0 plans a method the kit has not built (a row made for this test: none of the owner's 104 is missing any more) | `"A made method the kit has not built" is not built in the kit yet` |
| preset_methods_fakeink | hand-drawn planned, and the sheet under the inked name is an imported one (textures/m_flame_ink.json: recipe "import") | `beat 1 plans "Hand-drawn effects animation" and nothing that plays in that beat uses it` |
| preset_methods_stray | every layer says beat 99, which the chart does not have | `name a beat the chart does not have` |
| preset_methods_muted | the inked layer (a real inked sheet, textures/m_flame_real.json) is muted by the preset's overlay: it never plays | `beat 1 plans "Hand-drawn effects animation" and nothing that plays in that beat uses it` |
| preset_methods_dead | the inked layer is fully transparent all its life: it draws nothing | the same |
| preset_methods_model | the chart, with its reason for the embers, was approved by a model, not the owner | `needs the OWNER's own approval of the chart that shows the reason` |
| preset_methods_rewritten | the reason the owner read was rewritten after his approval | `is not the one the owner read on the chart he approved` |

The fixtures were written once by a script; they are plain files now. Never edit them to make the gate pass.
