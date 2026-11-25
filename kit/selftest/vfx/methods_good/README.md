The passing twin of kit/selftest/vfx/methods: a preset built from a MADE scene (three beats: a glint, a crescent of
flame, embers) whose chart carries a METHOD PLAN, approved in the owner's form with the plan he saw.

- beat 0 plans sprite + flipbook: its sprite layer plays a flipbook.
- beat 1 plans mesh + UV scrolling + hand-drawn: a ring mesh with `uvScroll`, and a sprite whose texture spec
  (textures/m_flame_ink.json) is of recipe "ink".
- beat 2's words say "fire" and its plan leaves hand-drawn out with a reason; the approval holds that reason, so the
  owner has seen it.

It must pass the method gate (kit/vfx/methods.py --gate, run by Content.vfxPresetsStep). The fixtures were written once
by a script; they are plain files now.
