---
name: parallax-sharpen
description: Turn a vague request ("make it better", "add combat", "fix it", "make it look cool") into board tasks with checkable done-when criteria before building. Use whenever a request has no observable finish line.
---

# parallax-sharpen — vague request → tasks with finish lines

Never build straight from a vague prompt.

0. **Compile the raw words first:** `lune run kit prompt compile "<the owner's words>" [--model claude|codex|gemini|local]`
   (PROMPT-X). It finds the lanes, pulls the lanes' graveyard / golden records, lessons and past parts, fills what the
   repo already decides, and asks at most 3 taste or scope questions (answer them with `--answers "q1=A,q2=B"`; an
   unanswered one takes its starred default and says so). The packet (`build/prompt/last.json`) holds the prompt for
   your model, the tool prompts (FLUX.2 in positive words only) and the done-when commands; `--full` prints it. Two
   or more lanes: `--kickoff <Name>` seeds the brief and one task per lane. After the owner's verdict:
   `lune run kit prompt evolve build/prompt/last.json <0-10> "<their words>"` (a rule is learned only if the 10 real
   failed prompts in `kit prompt bench` still each carry their guardrail).
1. **Context (cheap, read-only):** `lune run kit status`, `board/BRIEF.md`, the last handoff, related tasks
   (`kit task list --area <area>`), the code/assets involved.
2. **Branch:** 2–3 concrete approaches, one line each: what changes, tradeoff, cost. Recommend one and say the
   deciding factor. Keep rejected options visible (they go in a `kit decide` record if the choice matters).
3. **Convert every vague word into a check.** "Better combat" → "hit registers within 0.1 s of click (playtest),
   damage validated server-side (audit clean), hit sound + spark VFX on impact (sfx/vfx gates pass)".
4. **Write it to the board:** one `kit task add` per shippable piece, each with `--done` criteria and
   `--depends` for order. Big = split. A task should fit in one session.
5. **Confirm with the human** when the choice is expensive or taste-driven (art direction, game design);
   otherwise state your pick in one line and go.
6. Build per the task (claim → work → verify → done). Scope grows mid-build? Add a new task; don't silently expand.
