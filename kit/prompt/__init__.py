"""PROMPT-X (LIMITATIONS_FIXES_V4 section 9 / 13.7): the owner's raw, informal prompt -> a model-adapted, repo-grounded
prompt packet. Built from scratch on the standard library only (no prompt SDK), deterministic and offline:

    route -> clarify -> expand -> compile -> subprompts        (evolve learns from verdicts afterwards)

Run it through `lune run kit prompt compile|clarify|evolve` (kit/cmd/prompt.luau) or `python kit/prompt/cli.py`."""
