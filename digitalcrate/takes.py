"""Alternate takes: samples from the same song that are the same thing again (the same drum hit another time, the
same sung words on another pass, the same chord or figure repeated), so you can play through them and pick one.

    groups(con)  -> [[sample_id, ...], ...]  each group in song order, every sample in at most one group

Two samples are takes of each other when they come from the same song and category, don't overlap in time, are of
similar length (within 1.6x), aren't the very same audio, and:
  - drums:   the same drum type, and close in sound (CLAP cosine >= 0.85);
  - vocals:  with words transcribed, at least half their words in common (filler words aside) and a similar sound
             (>= 0.75): "my love" sung twice groups even when the pitch differs; without words, as other sounds;
  - others:  very close in sound (>= 0.92) and playing the same notes (chroma cosine >= 0.9).
Groups form around the longest sample first. Computed at each build (well under a minute for 20,000 samples).
"""
import collections
import json
import re

import numpy as np

FILLER = {"the", "a", "and", "i", "to", "of", "you", "it", "in", "oh", "ah", "ooh", "yeah", "la", "na"}


def _toks(t):
    return set(re.findall(r"[a-z']+", (t or "").lower())) - FILLER


def same_take(a, b, sim, chroma_sim, ta, tb):
    """a, b: sample rows (category, subtype, start, dur) of one song and category."""
    da, db = a["dur"] or 0, b["dur"] or 0
    if a["start"] is None or b["start"] is None:
        return False
    if min(a["start"] + da, b["start"] + db) - max(a["start"], b["start"]) > 0.5 * min(da, db):
        return False  # mostly the same stretch of the song: an overlapping cut, not another take
    if max(da, db) / max(0.05, min(da, db)) > 1.6 or sim > 0.9995:
        return False
    if a["category"] == "Percussion":
        return a["subtype"] == b["subtype"] and sim >= 0.85
    if a["category"] in ("Vocals", "Vocal Atmospheres") and ta and tb:
        return len(ta & tb) / len(ta | tb) >= 0.5 and sim >= 0.75
    return sim >= 0.92 and chroma_sim >= 0.9


def groups(con):
    try:
        rows = con.execute("""SELECT s.id, s.track_id, s.category, s.subtype, s.start, s.dur, s.clap, s.chroma, w.text
                              FROM samples s LEFT JOIN words w ON w.sample_id = s.id
                              WHERE s.parent_id IS NULL AND s.clap IS NOT NULL""").fetchall()
    except Exception:  # no words table yet
        rows = con.execute("""SELECT id, track_id, category, subtype, start, dur, clap, chroma, NULL text
                              FROM samples WHERE parent_id IS NULL AND clap IS NOT NULL""").fetchall()
    by = collections.defaultdict(list)
    for r in rows:
        by[(r["track_id"], r["category"])].append(r)
    out = []
    for rs in by.values():
        if len(rs) < 2:
            continue
        E = np.stack([np.frombuffer(r["clap"], np.float16).astype(np.float32) for r in rs])
        E /= np.linalg.norm(E, axis=1, keepdims=True) + 1e-9
        Ch = np.array([json.loads(r["chroma"]) if r["chroma"] else [0.0] * 12 for r in rs], float)
        Ch /= np.linalg.norm(Ch, axis=1, keepdims=True) + 1e-9
        S, Cc, T = E @ E.T, Ch @ Ch.T, [_toks(r["text"]) for r in rs]
        order = sorted(range(len(rs)), key=lambda i: -(rs[i]["dur"] or 0))
        used = set()
        for i in order:
            if i in used:
                continue
            g = [i] + [j for j in order if j not in used and j != i
                       and same_take(rs[i], rs[j], S[i, j], Cc[i, j], T[i], T[j])]
            if len(g) > 1:
                used.update(g)
                out.append([rs[k]["id"] for k in sorted(g, key=lambda k: rs[k]["start"] or 0)])
    return out
