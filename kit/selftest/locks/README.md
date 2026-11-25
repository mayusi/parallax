Selftest fixtures for the lane quality locks (kit/lib/lanelocks.luau, 2026-10-21). None of these files is in
board/locks.json's grandfathered lists, so each is a piece made after the locks, and each skipped its quality step:
- `sounds/new_sound.json`, `sounds/sets/new_set.json`: no owner-chosen reference (no `kit approve sfx`)
- `models/build_new_hero.py`: a hero brief the owner never approved; `models/build_no_brief.py`: no brief at all
- `models/build_no_study.py`: an answered prop brief but no reference study (`kit study`, the study lock of 2026-10-28)
- `worlds/NewWorld.json`: one still in its refs folder (needs >= 6) and no measured REFS.md
Every one must be refused.
- `open/assets/effects/open_*.json`: three vfx pieces made after the locks with no owner verdict - the verdict lock
  (`kit new` refuses at LaneLocks.OPEN_CAP = 3 unscored pieces per lane) must count all three.
- `lessons/assets/effects/new_effect.json`: a vfx piece made after the lessons lock with no answered lessons sheet - the
  lessons lock (enforced learning, rule 2: `kit answer <lane> <name>`) must refuse it.
