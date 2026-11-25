# kit contract self-test fixture

A tiny hero (fx_sword + FxSet) whose sources `kit contract` reads: `../good/fx_sword.json` was written from them by `kit contract new` and must pass `kit contract check`; `../bad/fx_sword.json` is that contract with its opener's hit frame moved (the anim lane retimed the clip after the contract was signed) and must fail by name. Never edit these to make the self-test pass.
