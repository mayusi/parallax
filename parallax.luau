-- parallax.luau — the Parallax brand entry point (PARALLAX_ENFORCEMENT_AND_ROUTING_SPEC §5.1 step 8, R1):
-- `lune run parallax <command> [args]` is `lune run kit <command> [args]` (same runner, same arguments, same exit
-- codes). Phase P1 moves kit/ to parallax/; until then this file only hands over to kit/init.luau.
require("./kit")
