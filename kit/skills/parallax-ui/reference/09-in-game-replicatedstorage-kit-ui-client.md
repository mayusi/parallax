<!-- reference for the parallax-ui route card; verbatim from the skill page (2026-10-16) -->

## In game — `ReplicatedStorage.kit.Ui` (client)
```lua
Ui.bar(Ui.find("RpgHud", "Hud.Vitals.Hp"), 0.42)      -- Fill snaps, the Ghost drains late
Ui.counter(Ui.find("RpgHud", "Hud.RpgBox.Souls"), 15210)   -- rolls with separators
Ui.text(Ui.find("RpgDeath", "Death.Died"), "YOU DIED")       -- tracked glyphs rebuilt
Ui.show(playerGui.RpgDeath, true)                            -- enters play in order; false fades out
Ui.transition(playerGui.RpgTitle, playerGui.RpgHud)
Ui.spring(frame, "Position", UDim2.fromScale(0.5, 0.5), 4, 0.6)  -- frequency Hz, damping (<1 pops)
Ui.setState(Ui.find("SimShop", "Shop.Window.Grid.Pack1.Buy"), "locked")   -- a designed state; nil = idle
Ui.path(Ui.find("RaceHud", "Hud.Dial.Boost"), 0.6)                      -- a vector line drawn to 60% of its length
Ui.burst(Ui.find("RushHud", "Hud.Callout"), "smash")               -- UI particles from the identity's preset
Ui.floater(StarterGui.RiffDamage, hitPosition, "128")                 -- a world-space damage number
Ui.attach(StarterGui.RiffNameplate, enemy.Head)                         -- a nameplate over a part
Ui.write(Ui.find("RiffNameplate", "Plate.Name"), player.DisplayName)   -- any text in the identity's lettering
Ui.track(Ui.find("Hud", "Hud.Goal"), workspace.Goal)               -- a world marker, pinned to the edge off screen
Ui.toast(Ui.find("Hud", "Hud.Toasts"), "Saved!", "good")           -- a queued toast
Ui.setReduceFlashing(true)                                          -- a player's setting
Ui.fx(node, "burn_in")                                   -- replay one fx (Ui.bind starts them all)
Ui.flash · Ui.punch · Ui.ring · Ui.push · Ui.reveal · Ui.scale · Ui.model
```
The UiMotion client binds every kit screen: hover / press / loops per node, the per-viewport scale, the enter
choreography the moment a screen is enabled.
