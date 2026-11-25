<!-- reference for the parallax-systems route card; verbatim from the skill page (2026-10-16) -->

## A new game
`kit new game <Pascal>` (= `kit game new`) → the folder above, then `<Name>Server` / `<Name>Client` entry points; every service is a ModuleScript in
`<Name>Services` (`return { deps = { "DataService" }, init = fn(self, services), start = fn(self, services) }`), run
by `kit.Loader` in dependency order (cycles and unknown deps named); `DataService` (ProfileStore session-locked saves
once `kit add profilestore`; memory + one warning before); tunables in `src/shared/<Name>Config` read LIVE through
`Configs.bind("<Name>", <Name>Config)` (Experience Configs: change values without a republish; a wrong-typed / NaN /
negative live value falls back to the code's).
