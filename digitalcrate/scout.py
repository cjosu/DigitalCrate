"""Fast whole-library scouting: CLAP on a handful of snippets per track to rank where the
sample-worthy material is — exposed singing, sustained pads — and how close it sounds to the
reference set (e.g. Burial's vocals/pads extracted into _Reference)."""
import subprocess
import time

import numpy as np
from tqdm import tqdm

from .db import connect
from . import models
from .process import TYPE_PROMPTS, TYPE_KEYS, VOCAL_TYPES

N_SNIPS, SNIP_S = 6, 10

# Rankings used by `process --top N --for ...`. Pads exclude electronic genres: the point is to find
# raw acoustic material to transform, not other producers' finished ambient.
_ELECTRONIC = ["electronic", "electronica", "ambient", "techno", "house", "idm", "dub", "minimal", "dance",
               "footwork", "juke", "bass", "drone", "trance", "downtempo", "new age", "experimental"]
_RNB = ["r&b", "rnb", "soul", "funk", "gospel", "motown", "quiet storm", "neo soul", "disco", "doo wop"]
RANK_SQL = {
    # voices over drums: the drum penalty in scout_vocal is fine here, separation handles it
    "rnb": ("(" + " OR ".join(f"lower(coalesce(genre,'')) LIKE '%{g}%'" for g in _RNB) + ")",
            "scout_vocal DESC, RANDOM()"),
    "vocals": ("1=1", "scout_vocal * 0.7 + scout_sparse * 0.3 DESC, RANDOM()"),
    "pads": (" AND ".join(f"lower(coalesce(genre,'')) NOT LIKE '%{g}%'" for g in _ELECTRONIC),
             "scout_pad * 0.8 + scout_sparse * 0.2 DESC, RANDOM()"),
}
SING = ["vocal_female", "vocal_male", "vocal_choir"]
PADS = ["pad", "strings", "drone", "organ"]


def _snippet(path, start):
    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-ss", f"{start:.2f}", "-t", str(SNIP_S), "-i", path,
           "-map", "0:a:0", "-f", "f32le", "-ac", "1", "-ar", "48000", "-"]
    out = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(out, np.float32)


def reference_set(con):
    rows = con.execute("""SELECT s.clap, s.category, t.artist, t.title FROM samples s JOIN tracks t ON t.id=s.track_id
                          WHERE s.path LIKE '_Reference/%' AND s.kind != 'oneshot'""").fetchall()
    if not rows:
        return None, []
    E = np.stack([np.frombuffer(r["clap"], np.float16).astype(np.float32) for r in rows])
    return E, [f"{r['artist']} – {r['title']} ({r['category']})" for r in rows]


def scout(limit=None, redo=False, shuffle=False):
    con = connect()
    from .policy import apply
    apply()
    where = "COALESCE(policy,'source') != 'reference'" + ("" if redo else " AND scout_done IS NULL")
    # shuffle: a random sample across the whole collection (the first run), not the first N by id
    rows = con.execute(f"SELECT id, path, duration FROM tracks WHERE {where} ORDER BY {'RANDOM()' if shuffle else 'id'}").fetchall()
    if limit:
        rows = rows[:limit]
    cl = models.clap()
    T = cl.embed_text(tuple(TYPE_PROMPTS.values()))
    scale = float(cl.model.logit_scale_a.exp().clamp(max=100))
    R, rnames = reference_set(con)
    print(f"scouting {len(rows)} tracks; reference set: {0 if R is None else len(R)} sounds")
    t0 = time.time()
    for n, r in enumerate(tqdm(rows, desc="scout")):
        try:
            dur = r["duration"] or 0
            if dur < 20:
                con.execute("UPDATE tracks SET scout_done=1, scout_vocal=0, scout_pad=0, scout_sparse=0 WHERE id=?",
                            (r["id"],))
                continue
            starts = np.linspace(0.08 * dur, 0.92 * dur - SNIP_S, N_SNIPS)
            clips = [c for c in (_snippet(r["path"], s) for s in starts) if len(c) > 48000 * 3]
            if not clips:
                raise RuntimeError("no audio")
            E = cl.embed_audio(clips)
            lg = scale * E @ T.T
            P = np.exp(lg - lg.max(1, keepdims=True))
            P /= P.sum(1, keepdims=True)
            col = {k: P[:, TYPE_KEYS.index(k)] for k in TYPE_KEYS}
            nodrum = 1 - col["drums"]
            voc = sum(col[k] for k in SING) * nodrum
            pad = sum(col[k] for k in PADS) * nodrum
            top2 = lambda x: float(np.sort(x)[-2:].mean())
            ref, match = None, None
            if R is not None:
                sims = E @ R.T
                i, j = np.unravel_index(np.argmax(sims), sims.shape)
                ref, match = float(np.sort(sims.max(1))[-2:].mean()), rnames[j]
            con.execute("""UPDATE tracks SET scout_done=1, scout_vocal=?, scout_pad=?, scout_sparse=?,
                           scout_ref=?, scout_ref_match=? WHERE id=?""",
                        (top2(voc), top2(pad), float(nodrum.mean()), ref, match, r["id"]))
        except Exception as e:
            con.execute("UPDATE tracks SET scout_done=-1 WHERE id=?", (r["id"],))
            tqdm.write(f"  scout error {r['path']}: {e}")
        if n % 50 == 0:
            con.commit()
    con.commit()
    rank(con)
    print(f"scouted in {(time.time() - t0) / 60:.1f} min")


def rank(con=None):
    """Combine scout signals into one score (z-scored across the library)."""
    con = con or connect()
    rows = con.execute("SELECT id, scout_vocal, scout_pad, scout_sparse, scout_ref FROM tracks WHERE scout_done=1").fetchall()
    if not rows:
        return
    a = np.array([[r[1] or 0, r[2] or 0, r[3] or 0, r[4] if r[4] is not None else np.nan] for r in rows])
    z = lambda x: (x - np.nanmean(x)) / (np.nanstd(x) + 1e-9)
    potential = np.maximum(a[:, 0], 0.9 * a[:, 1])
    ref = np.nan_to_num(z(a[:, 3])) if not np.all(np.isnan(a[:, 3])) else 0
    score = z(potential) + 0.6 * ref + 0.3 * z(a[:, 2])
    con.executemany("UPDATE tracks SET scout_score=? WHERE id=?",
                    [(float(s), r["id"]) for s, r in zip(score, rows)])
    con.commit()
