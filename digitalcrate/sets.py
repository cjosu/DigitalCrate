"""Sets: groups of your favourites that fit together, and what would complete each one (🧩 on the Favorites tab).

Fit is the same pairwise compatibility "goes well with" uses (build.compat_block: key on the Camelot wheel and the notes
actually played, tempo for loops, arrangement role, and sound). A set is grown greedily from the favourite with the
strongest links: each new member must fit EVERY member already in (its weakest link is what counts), so a set holds
together as a whole, not as a chain. Members prefer roles the set doesn't have yet.

"Completes it" looks across the whole library for samples that fit every member, favouring a missing role and what
the taste model rates highly.
"""
import collections

import numpy as np

from .db import connect

MIN_FIT = 0.28     # every pair in a set at least this (your favourites' top ~15% of pairs)
MAX_SIZE, MIN_SIZE = 6, 3
_D = {}


def _data(con):
    from .build import load
    key = tuple(con.execute("SELECT COUNT(*), MAX(rowid) FROM samples").fetchone())
    if _D.get("key") != key:
        d = load(con)
        _D.update(key=key, d=d, pos={r["path"]: k for k, r in enumerate(d["rows"])})
    return _D["d"], _D["pos"]


def _name(d, members):
    rows = [dict(d["rows"][k]) for k in members]  # sqlite rows: no .get
    cams = collections.Counter(r["camelot"] for r in rows if r.get("camelot") and r.get("category") != "Percussion")
    bpms = [d["bpm"][k] for k in members if d["loop"][k] and d["bpm"][k] > 0]
    cam = cams.most_common(1)[0][0] if cams else None
    key = next((f"{r['key']}{'m' if r.get('scale') == 'minor' else ''}" for r in rows if r.get("camelot") == cam), "")
    return " · ".join(x for x in [f"{cam} {key}".strip() if cam else "any key",
                                  f"{round(float(np.median(bpms)))} bpm" if bpms else "free tempo"] if x)


_CACHE = {}  # (library, collection, its samples) -> result


def sets(n_complete=4, collection=None):
    """Your favourites (or one collection's samples) grouped into sets. Cached until they or the library change."""
    con = connect()
    if collection:
        from .collections_ import _db as cdb
        paths = [r[0] for r in cdb().execute("SELECT path FROM collection_items WHERE collection=?", (collection,))]
    else:
        paths = [r[0] for r in con.execute("SELECT path FROM favorites")]
    key = (tuple(con.execute("SELECT COUNT(*), MAX(rowid) FROM samples").fetchone()), collection, tuple(sorted(paths)))
    if key not in _CACHE:
        if len(_CACHE) > 20:
            _CACHE.clear()
        _CACHE[key] = _sets(con, n_complete, paths)
    return _CACHE[key]


def _sets(con, n_complete, paths):
    d, pos = _data(con)
    from .build import compat_block
    fav = [pos[p] for p in paths if p in pos]
    if len(fav) < MIN_SIZE:
        return dict(sets=[], loose=len(fav), n_fav=len(fav), note=f"needs at least {MIN_SIZE} samples")
    F = np.array(fav)
    C = compat_block(d, F, F)["score"]
    np.fill_diagonal(C, 0)
    cat = [d["rows"][k]["category"] for k in F]
    song = [d["track"][k] for k in F]
    left = set(range(len(F)))
    out = []
    while len(left) >= MIN_SIZE:
        L = sorted(left)
        strength = {s: float(np.sort(C[s, L])[-3:].mean()) for s in L}
        seed = max(L, key=strength.get)
        S = [seed]
        while len(S) < MAX_SIZE:
            cands = [c for c in left if c not in S and song[c] not in {song[x] for x in S}]  # one sample per song
            if not cands:
                break
            gain = lambda c: C[c, S].min() + (0.06 if cat[c] not in {cat[x] for x in S} else 0)
            best = max(cands, key=gain)
            if C[best, S].min() < MIN_FIT:
                break
            S.append(best)
        if len(S) >= MIN_SIZE:
            out.append(S)
            left -= set(S)
        else:
            left.discard(seed)
    # what completes each set: fits every member, prefers a missing role, then your taste
    try:
        from .taste import scores_payload
        taste = scores_payload(None).get("score", {})
    except Exception:
        taste = {}
    favset = set(fav)
    result = []
    for S in out:
        members = F[S]
        fit_all = compat_block(d, members)["score"].min(0)  # weakest link against the whole library
        have = {d["rows"][k]["category"] for k in members}
        songs = {d["track"][k] for k in members}
        t = np.array([taste.get(r["path"], 0.0) for r in d["rows"]])
        rank = fit_all + 0.08 * np.array([r["category"] not in have for r in d["rows"]]) + 0.03 * np.clip(t, -2, 3)
        picks, used = [], set(songs)
        order = np.argsort(-rank)
        ok = lambda k: not (k in favset or fit_all[k] < MIN_FIT or d["track"][k] in used
                            or d["rows"][k]["path"].startswith("_Reference"))
        # a missing role first (up to two, one per role), then the best fits of any role
        new_roles = set()
        for k in order:
            c = d["rows"][k]["category"]
            if len(picks) >= 2:
                break
            if c not in have and c not in new_roles and ok(k):
                picks.append(dict(path=d["rows"][k]["path"], fit=round(float(fit_all[k]), 2), new_role=True))
                used.add(d["track"][k]); new_roles.add(c)
        for k in order:
            if len(picks) >= n_complete:
                break
            if ok(k):
                picks.append(dict(path=d["rows"][k]["path"], fit=round(float(fit_all[k]), 2),
                                  new_role=d["rows"][k]["category"] not in have))
                used.add(d["track"][k])
        sub = C[np.ix_(S, S)]
        result.append(dict(name=_name(d, members), members=[d["rows"][k]["path"] for k in members],
                           weakest=round(float(sub[np.triu_indices(len(S), 1)].min()), 2),
                           roles=sorted(have), complete=picks))
    loose = len(fav) - sum(len(s) for s in out)
    return dict(sets=result, loose=loose, n_fav=len(fav))
