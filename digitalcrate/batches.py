"""What to mine next, and how much of the library has been mined: used by the Processing page (/activity) and
research/next_batch.py, research/diverse_batch.py.

Two ways to pick a batch of unmined songs, both from the quick scout pass ("promise" = how exposed the singing is,
how pad-like and how sparse the song is):
  breadth    one song per artist, artists never mined first (artists with 5+ mined songs sit out), the batch shared
             between genres by the square root of how many untouched artists each has. Classical is capped at a
             fifth, because every conductor and orchestra counts as its own "artist" there, and untagged songs
             (mostly electronic and indie) at a twentieth.
  promising  the most promising songs overall, R&B and jazz boosted; at most 3 per album and 6 per artist.
  like       songs that sound like (Discogs-style embedding) the ones you've liked samples from; 2 per album, 3 per
             artist, no genre over 40%.
Songs MusicBrainz credits as sampling other records (mbz.py, `digitalcrate credits`) are never picked.
Electronic and Hip-Hop are left out by default (often built on samples already), and Rock & Indie (you asked not to
prioritise them); the page lets you change that.
"""
import collections
import json
import time

import numpy as np

from . import config as C
from .db import connect
from .genre import family, overrides, artist_consensus
from .styles import families

DEFAULT_SKIP = ["Electronic", "Hip-Hop", "Rock & Indie"]
MAX_DONE = 5
BATCH_DIR = C.DATA_DIR / "batches"


def _pool(con):
    ov, cons, sty = overrides(), artist_consensus(), families(con)
    from .mbz import flagged
    sampled = flagged(con)  # MusicBrainz says these are built on samples
    rows = [r for r in con.execute("""SELECT id, artist, album, title, genre, scout_vocal, scout_pad, scout_sparse FROM tracks
                          WHERE status = 'new' AND COALESCE(policy,'source') != 'reference'
                          AND scout_done=1""").fetchall() if r["id"] not in sampled]
    fam = [family(r["artist"], r["genre"], ov, cons, r["id"], sty) or "Unknown" for r in rows]
    z = lambda a: (a - a.mean()) / (a.std() + 1e-9) if len(a) else a
    col = lambda k: z(np.array([r[k] or 0 for r in rows], float))
    promise = 0.5 * col("scout_vocal") + 0.3 * col("scout_pad") + 0.2 * col("scout_sparse")
    return rows, fam, promise


def _done_by_artist(con):
    return collections.Counter((r["artist"] or "").strip().lower() for r in con.execute(
        "SELECT artist FROM tracks WHERE status='done' AND COALESCE(policy,'source')!='reference'"))


def breadth(n=200, skip=DEFAULT_SKIP, con=None):
    con = con or connect()
    rows, fam, promise = _pool(con)
    done = _done_by_artist(con)
    best = {}
    for i, r in enumerate(rows):
        a = (r["artist"] or "").strip().lower()
        if not a or a in ("various artists", "unknown artist") or fam[i] in skip or done[a] >= MAX_DONE:
            continue
        if a not in best or promise[i] > promise[best[a]]:
            best[a] = i
    by_fam = collections.defaultdict(list)
    for a, i in best.items():
        by_fam[fam[i]].append((done[a] > 0, -promise[i], i))
    for f in by_fam:
        by_fam[f].sort()
    share = {"Classical": 5, "Unknown": 20}  # at most 1/5 classical, 1/20 untagged (mostly electronic and indie)
    cap = {f: min(len(v), n // share[f]) if f in share else len(v) for f, v in by_fam.items()}
    w = {f: np.sqrt(sum(1 for t in v if not t[0]) or 0.5) for f, v in by_fam.items()}
    quota = {f: min(cap[f], int(n * w[f] / sum(w.values()))) for f in by_fam} if by_fam else {}
    while sum(quota.values()) < min(n, sum(cap.values())):  # hand out what genres that ran short left over
        f = max((f for f in by_fam if quota[f] < cap[f]), key=lambda f: w[f] / (quota[f] + 1))
        quota[f] += 1
    pick = sorted((t[2] for f in by_fam for t in by_fam[f][:quota[f]]), key=lambda i: -promise[i])
    return _summary("breadth", rows, fam, pick, done, skip)


def promising(n=200, skip=DEFAULT_SKIP, con=None):
    con = con or connect()
    rows, fam, promise = _pool(con)
    boost = {"Soul & R&B": 0.8, "Jazz": 0.8}
    order = np.argsort(-(promise + np.array([boost.get(f, 0) for f in fam])))
    per_alb, per_art, pick = collections.Counter(), collections.Counter(), []
    for i in order:
        if len(pick) >= n:
            break
        r = rows[i]
        a = (r["artist"] or "").lower()
        al = a + "|" + (r["album"] or "").lower()
        if fam[i] in skip or per_alb[al] >= 3 or per_art[a] >= 6:
            continue
        per_alb[al] += 1; per_art[a] += 1; pick.append(int(i))
    return _summary("promising", rows, fam, pick, _done_by_artist(con), skip)


def _summary(mode, rows, fam, pick, done, skip):
    arts = collections.Counter(rows[i]["artist"] for i in pick)
    return dict(mode=mode, ids=[rows[i]["id"] for i in pick], n=len(pick), artists=len(arts),
                new_artists=sum(done[(a or "").strip().lower()] == 0 for a in arts),
                genres=collections.Counter(fam[i] for i in pick).most_common(), skip=list(skip),
                examples=[f"{rows[i]['artist']} – {rows[i]['title']}" for i in pick[:12]])


def like_favourites(n=200, skip=DEFAULT_SKIP, con=None):
    """Unmined songs whose Discogs-style embedding is nearest the songs you've liked samples from (related.py), at
    most 2 per album and 3 per artist so one great album doesn't fill the batch."""
    from .related import like_mine
    con = con or connect()
    rows, fam, promise = _pool(con)
    pos = {r["id"]: i for i, r in enumerate(rows)}
    per_alb, per_art, per_fam, pick = collections.Counter(), collections.Counter(), collections.Counter(), []
    fam_cap = max(1, int(n * 0.4))  # the classical shelf is big and its slow movements sit close to ambient favourites
    for tid, _ in like_mine(len(rows), con):
        i = pos.get(tid)
        if i is None or fam[i] in skip:
            continue
        r = rows[i]
        a = (r["artist"] or "").lower()
        al = a + "|" + (r["album"] or "").lower()
        if per_alb[al] >= 2 or per_art[a] >= 3 or per_fam[fam[i]] >= fam_cap:
            continue
        per_alb[al] += 1; per_art[a] += 1; per_fam[fam[i]] += 1; pick.append(i)
        if len(pick) >= n:
            break
    return _summary("like favourites", rows, fam, pick, _done_by_artist(con), skip)


PICKERS = {"breadth": breadth, "promising": promising, "like": like_favourites}


def save_batch(plan):
    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    f = BATCH_DIR / f"{plan['mode'].replace(' ', '-')}_{time.strftime('%Y%m%d-%H%M%S')}.json"
    f.write_text(json.dumps(plan["ids"]))
    return f


def coverage(con=None):
    """How much has been mined: by genre, artists, recent songs, errors."""
    con = con or connect()
    ov, cons, sty = overrides(), artist_consensus(), families(con)
    fam_done, fam_all = collections.Counter(), collections.Counter()
    art_all, art_done = set(), set()
    for r in con.execute("SELECT id, artist, genre, status FROM tracks WHERE COALESCE(policy,'source')!='reference'"):
        f = family(r["artist"], r["genre"], ov, cons, r["id"], sty) or "Unknown"
        a = (r["artist"] or "").strip().lower()
        fam_all[f] += 1; art_all.add(a)
        if r["status"] == "done":
            fam_done[f] += 1; art_done.add(a)
    done = _done_by_artist(con)
    total = sum(done.values()) or 1
    shown = {(r[0] or "").strip().lower(): r[0] for r in con.execute("SELECT DISTINCT artist FROM tracks WHERE status='done'")}
    recent = [dict(r) for r in con.execute(
        """SELECT t.artist, t.title, t.processed_at, COUNT(s.id) AS n FROM tracks t LEFT JOIN samples s ON s.track_id=t.id
           WHERE t.status='done' AND COALESCE(t.policy,'source')!='reference' GROUP BY t.id
           ORDER BY t.processed_at DESC LIMIT 25""")]
    errors = [dict(r) for r in con.execute(
        "SELECT artist, title, substr(error,1,160) AS error FROM tracks WHERE status='error' ORDER BY rowid DESC LIMIT 20")]
    cats = con.execute("""SELECT category, COUNT(*) FROM samples WHERE path NOT LIKE '_Reference/%'
                          GROUP BY category ORDER BY 2 DESC""").fetchall()
    status = dict(con.execute("SELECT status, COUNT(*) FROM tracks GROUP BY status").fetchall())
    return dict(genres=[[f, fam_done[f], fam_all[f]] for f, _ in fam_all.most_common()],
                artists=len(art_all), artists_done=len(art_done),
                top_artists=[[shown.get(a, a), n] for a, n in done.most_common(10)],
                top10_share=round(sum(n for _, n in done.most_common(10)) / total, 2),
                recent=recent, errors=errors, categories=[list(c) for c in cats], status=status,
                samples=sum(c[1] for c in cats))
