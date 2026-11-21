"""Rank unmined songs for the next mining batch: non-electronic, R&B and jazz first.

promise = how exposed the singing is (scout_vocal) + how pad-like / sparse it is, from the quick scout pass,
standardised; Soul & R&B and Jazz get a boost. Electronic and Hip-Hop (often built on samples already) are left
out. At most 3 songs per album and 6 per artist in one batch, so it isn't one record over and over."""
import sys, json, pathlib, collections
import numpy as np
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from digitalcrate.db import connect
from digitalcrate.genre import family, overrides, artist_consensus

N = int(sys.argv[1]) if len(sys.argv) > 1 else 200
BOOST = {"Soul & R&B": 0.8, "Jazz": 0.8}
SKIP = {"Electronic", "Hip-Hop"}
con = connect()
rows = con.execute("""SELECT id, artist, album, title, genre, scout_vocal, scout_pad, scout_sparse FROM tracks
                      WHERE status IN ('new','error') AND COALESCE(policy,'source') != 'reference' AND scout_done=1""").fetchall()
ov, cons = overrides(), artist_consensus()
fam = [family(r["artist"], r["genre"], ov, cons) or "Unknown" for r in rows]
z = lambda a: (a - np.nanmean(a)) / (np.nanstd(a) + 1e-9)
v = z(np.array([r["scout_vocal"] or 0 for r in rows], float))
p = z(np.array([r["scout_pad"] or 0 for r in rows], float))
s = z(np.array([r["scout_sparse"] or 0 for r in rows], float))
promise = 0.5 * v + 0.3 * p + 0.2 * s + np.array([BOOST.get(f, 0) for f in fam])
order = np.argsort(-promise)
# tiers: every remaining R&B song, then the best jazz, then the best of the rest (classical capped so it can't
# swamp the batch); same per-album / per-artist caps throughout
QUOTA = {"Soul & R&B": 10 ** 6, "Jazz": 90}
CAP = {"Classical": 40, "Rock & Indie": 0}  # you asked not to prioritise rock or indie
pick, per_alb, per_art, per_fam = [], collections.Counter(), collections.Counter(), collections.Counter()
def take(i):
    r = rows[i]
    a, al = (r["artist"] or "").lower(), ((r["artist"] or "") + "|" + (r["album"] or "")).lower()
    if per_alb[al] >= 3 or per_art[a] >= 6 or i in chosen:
        return False
    per_alb[al] += 1; per_art[a] += 1; per_fam[fam[i]] += 1; chosen.add(i); pick.append(i)
    return True
chosen = set()
for f, q in QUOTA.items():
    for i in order:
        if fam[i] == f and per_fam[f] < q and len(pick) < N:
            take(i)
for i in order:
    if len(pick) >= N:
        break
    if fam[i] in SKIP or fam[i] in QUOTA or per_fam[fam[i]] >= CAP.get(fam[i], 10 ** 6):
        continue
    take(i)
eligible = sum(f not in SKIP for f in fam)
print(f"{len(rows)} unmined scouted songs · {eligible} non-electronic · picking {len(pick)}")
print("by genre:", collections.Counter(fam[i] for i in pick).most_common())
print("artists:", ", ".join(f"{a} ({n})" for a, n in collections.Counter(rows[i]["artist"] for i in pick).most_common(25)))
print("first 12:", "; ".join(f"{rows[i]['artist']} – {rows[i]['title']}" for i in pick[:12]))
out = pathlib.Path(__file__).with_name("next_batch_ids.json")
out.write_text(json.dumps([rows[i]["id"] for i in pick]))
print(f"wrote {out}")
