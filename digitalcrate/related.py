"""Related music, from the Discogs styles heard in the audio (styles.py) and what you like (favourites, dislikes and
listening, as in taste.py):

  profile()        your styles: which Discogs styles the songs behind your liked samples are, weighted by how much
                   more often they turn up there than in the collection as a whole (so a big classical shelf doesn't
                   make "Romantic" your style just by being big)
  like_mine()      unmined songs whose style embedding is closest to the songs you've liked samples from (for the
                   Processing page's "like my favourites" batch mode)
  guided_queries() YouTube searches built from your styles, for the scout's guided mode
  target()         what a guided scout listens for: your style profile, or one style
"""
import collections

import numpy as np

from .db import connect
from .styles import classes, embeddings

SKIP_PARENTS = {"Non-Music", "Children's"}
# styles that are mostly built from samples already: not worth searching for (see the sampling policy)
SAMPLE_BASED = {"Hip Hop", "Electronic"}
KEEP_ROCK = {"Shoegaze", "Dream Pop", "Post Rock", "Lo-Fi", "Experimental", "Folk Rock", "Psychedelic Rock", "Space Rock",
             "Krautrock", "Acoustic"}
KEEP_ELECTRONIC = {"Ambient", "Drone", "Dark Ambient", "Berlin-School", "New Age", "Musique Concrète", "Modern Classical"}


def track_weights(con=None):
    """track id -> how much you like what's been mined from it (positive) or not (negative)."""
    from .taste import item_labels
    con = con or connect()
    lab = item_labels(con)
    tid = {r["path"]: r["track_id"] for r in con.execute("SELECT path, track_id FROM samples")}
    w = collections.Counter()
    for p, (y, wt) in lab.items():
        if p in tid:
            w[tid[p]] += wt if y else -0.5 * wt
    return w


def _style_ok(name):
    parent, style = name.split("---", 1)
    if parent in SKIP_PARENTS:
        return False
    if parent == "Rock":  # you asked not to prioritise rock & indie; the dreamy and textural corners stay
        return style in KEEP_ROCK
    return parent not in SAMPLE_BASED or style in KEEP_ELECTRONIC


def hidden_styles():
    from . import config as C
    f = C.DATA_DIR / "hidden_styles.json"
    import json
    return set(json.loads(f.read_text())) if f.exists() else set()


def hide_style(full, hide=True):
    """Leave a style out of your profile (and the guided searches), or bring it back."""
    from . import config as C
    import json
    h = hidden_styles()
    (h.add if hide else h.discard)(full)
    (C.DATA_DIR / "hidden_styles.json").write_text(json.dumps(sorted(h)))
    return sorted(h)


_PROF = {}


def profile(con=None, top=16):
    """(cached until the styles, your favourites, ratings or hidden styles change)"""
    con = con or connect()
    key = (tuple(con.execute("SELECT COUNT(*) FROM styles WHERE probs IS NOT NULL").fetchone()),
           tuple(con.execute("SELECT COUNT(*), MAX(added_at) FROM favorites").fetchone()),
           tuple(con.execute("SELECT COUNT(*), MAX(ts) FROM events WHERE type != 'listen'").fetchone()),
           tuple(sorted(hidden_styles())), top)
    if _PROF.get("key") != key:
        _PROF.update(key=key, value=_profile(con, top))
    return _PROF["value"]


def _profile(con, top):
    names = classes()
    rows = con.execute("SELECT track_id, probs FROM styles WHERE probs IS NOT NULL").fetchall()
    if not rows:
        return dict(styles=[], liked_tracks=0, ready=False)
    ids = [r["track_id"] for r in rows]
    P = np.stack([np.frombuffer(r["probs"], np.float16).astype(np.float32) for r in rows])
    w = track_weights(con)
    lw = np.array([max(0.0, w.get(t, 0.0)) for t in ids])
    if lw.sum() == 0:
        return dict(styles=[], liked_tracks=0, ready=True)
    liked = (P * lw[:, None]).sum(0) / lw.sum()
    base = P.mean(0) + 1e-4
    lift = liked / base
    # distinctive first, but a style the collection barely has can't win on rarity alone (lift capped at 4: the model
    # hears some modern R&B as reggaeton or K-pop, and with almost none of those in the collection the lift explodes)
    score = liked * np.log(np.clip(lift, 1.0, 4.0)) + 1e-3 * liked
    hidden = hidden_styles()
    order = [i for i in np.argsort(-score) if _style_ok(names[i]) and names[i] not in hidden][:top]
    yr = {r[0]: r[1] for r in con.execute("SELECT id, year FROM tracks WHERE year IS NOT NULL")}
    def era(i):  # the decade your liked songs in this style come from, weighted
        ys = [(int(str(yr[t])[:4]), lw[k] * P[k, i]) for k, t in enumerate(ids)
              if lw[k] > 0 and str(yr.get(t, ""))[:4].isdigit() and 1900 < int(str(yr[t])[:4]) < 2100]
        if not ys:
            return None
        y = sum(a * b for a, b in ys) / (sum(b for _, b in ys) + 1e-9)
        return f"{int(y) // 10 * 10}s"
    return dict(ready=True, liked_tracks=int((lw > 0).sum()),
                styles=[dict(name=names[i].split("---", 1)[1], full=names[i], share=round(float(liked[i]), 3),
                             lift=round(float(lift[i]), 1), era=era(i)) for i in order])


def _liked_matrix(con):
    ids, E, _ = embeddings(con)
    w = track_weights(con)
    pos = [k for k, t in enumerate(ids) if w.get(t, 0) > 0]
    return ids, E, pos, w


def like_mine(n=200, con=None):
    """Unmined, not-reference track ids, nearest first (mean of the 5 best matches among the songs you liked
    samples from, so several different tastes each pull in their own neighbours)."""
    con = con or connect()
    ids, E, pos, w = _liked_matrix(con)
    if not pos:
        return []
    L = E[pos]
    new = {r[0] for r in con.execute("""SELECT id FROM tracks WHERE status='new'
                                        AND COALESCE(policy,'source')!='reference'""")}
    cand = [k for k, t in enumerate(ids) if t in new]
    if not cand:
        return []
    S = E[cand] @ L.T
    k = min(5, S.shape[1])
    sc = np.sort(S, 1)[:, -k:].mean(1)
    return [(ids[cand[i]], float(sc[i])) for i in np.argsort(-sc)[:n]]


TEMPLATES = ["{s} {era}", "rare {s}", "{s} deep cuts", "{s} private press", "{s} {era} full album"]
SPECIAL = {"Funk / Soul---Psychedelic": "psychedelic soul", "Folk, World, & Country---Gospel": "gospel",
           "Funk / Soul---Gospel": "gospel"}
PARENT_WORD = {"Classical": "classical", "Jazz": "jazz", "Folk, World, & Country": "folk",
               "Latin": "latin", "Blues": "blues", "Reggae": "reggae", "Stage & Screen": "soundtrack", "Pop": "pop"}


def phrase(full):
    """'Classical---Modern' -> 'modern classical'; 'Funk / Soul---Neo Soul' -> 'neo soul'."""
    if full in SPECIAL:
        return SPECIAL[full]
    parent, style = full.split("---", 1)
    w = PARENT_WORD.get(parent, "")
    s = style.lower()
    return s if not w or w in s else f"{s} {w}"


def guided_queries(con=None, n=12):
    """Searches from your styles: the top ones, each with a phrasing that tends to surface lesser-known uploads
    (rare, deep cuts, private press, the decade your liked songs in that style come from)."""
    prof = profile(con)
    out = []
    for k, s in enumerate(prof["styles"][:n]):
        t = TEMPLATES[k % len(TEMPLATES)]
        q = t.format(s=phrase(s["full"]), era=s.get("era") or "1970s")
        out.append(dict(query=q, style=s["full"]))
    return out


def target(style=None, con=None):
    """What guided scouting listens for: a 400-d style weighting (one style, or your profile) and the centroid of
    the style embeddings of the songs you liked samples from (None if nothing liked yet)."""
    con = con or connect()
    names = classes()
    T = np.zeros(len(names), np.float32)
    if style and style in names:
        T[names.index(style)] = 1.0
    else:
        for s in profile(con)["styles"]:
            T[names.index(s["full"])] = s["share"]
    T /= np.linalg.norm(T) + 1e-9
    ids, E, pos, w = _liked_matrix(con)
    c = None
    if pos:
        c = (E[pos] * np.array([w[ids[k]] for k in pos])[:, None]).sum(0)
        c /= np.linalg.norm(c) + 1e-9
    return T, c
