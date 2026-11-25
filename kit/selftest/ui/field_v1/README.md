# field_v1 - the owner's FieldHud_v1 1/10 (2026-10-12: "AI slop, I asked realistic"), a bad example forever

- `FieldHud_v1.json` - the real rejected screen, byte for byte (`git show 77a8abd8:assets/ui/FieldHud.json`): the
  arcade checklist as plain nodes - a minimap panel `Map`, a kill feed panel `Feed`, an HP number `Hp` / `HpLbl` /
  `HpBar` and squad `Hp` bars, round pips `Rounds`, a `Reserve` count, two `plate` corner shades.
- `FieldHud_v2.json` - the screen the owner approved after it ("OK great", 2026-10-12), a copy of
  `assets/ui/FieldHud.json` on 2026-11-10: the control, it must compile.
- `identities/field.json` - a copy of the owner's realistic identity on 2026-11-10 with the `banned_components` he
  chose that day (card qfab): plate cutout chrome glow halo pill gloss (its own bans[0] / bans[2]) + map feed hp
  rounds reserve (his v1 verdict, bans[5]). The compass, the crosshair dot and hit markers stay allowed.

kit/cmd/qa.luau compiles v1 against it (`kit/ui/compile_fixture`): it must FAIL on each of those nodes; v2 must pass.
