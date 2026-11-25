"""clip_beats.py - a builder writes its own BEATS into the clip (the owner's V3 list, anim stage A.2; card j6x7).

A clip's `beats` are {phase: [t0, t1]} in seconds. The authored routes carried a move's own `beats` through (strike.py,
bake.py, gait.py); the PROCEDURAL builders (proc_blade, proc_kick, proc_strike's candidates, proc_react) wrote none,
so a candidate carried its Hit and nothing else and its sheet guessed its poses from where the motion nearly stops
(pose_sheet.extremes). Now each builder names the moments it built from - its own keys, by their names or by the
dossier's phases - and the sheet, the timing chart and the strip read them.

    from_keys([(t, name), ...], end)   consecutive keys of one name are one span, from its first key to the next
                                       name's first key (the last runs to `end`); a name met again later is a span
                                       of its own (`name_2`); a key with no name is left out; times rounded to 6 (the clip's own)
"""


def from_keys(keys, end, ndigits=6):
    """[(t, name)] in any order -> {name: [t0, t1]}; {} when no key has a name"""
    seq = sorted(((float(t), n) for t, n in keys if n), key=lambda k: k[0])
    if not seq:
        return {}
    runs = []                                                # [(name, t_first)] - a run per change of name
    for t, n in seq:
        if not runs or runs[-1][0] != n:
            runs.append((n, t))
    out, seen = {}, {}
    for i, (n, t0) in enumerate(runs):
        t1 = runs[i + 1][1] if i + 1 < len(runs) else max(float(end), t0)
        seen[n] = seen.get(n, 0) + 1
        key = n if seen[n] == 1 else f"{n}_{seen[n]}"
        out[key] = [round(t0, ndigits), round(t1, ndigits)]
    return out


def by_dossier(d, times, hit_t, end):
    """the key moments `times` of a clip named by its dossier's phases (proc_dossier.phases_for: by time while the clip
    is timed like its dossier, else by order round the Hit) -> {phase: [t0, t1]}; {} with no dossier phase to name"""
    import proc_dossier as PD
    names, _, _ = PD.phases_for(d, sorted(float(t) for t in times), hit_t)
    return from_keys(list(zip(sorted(float(t) for t in times), names)), end)
