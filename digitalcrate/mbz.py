"""MusicBrainz and ListenBrainz: which songs are built on samples themselves (so they're not mined), and which
artists are related to the ones you like (for guided YouTube scouting).

    digitalcrate credits [--limit N]    check unmined songs' sample credits on MusicBrainz

Sample credits: MusicBrainz's "samples material" relationships. Tested on ten famous sample-based songs, it knew
four (Daft Punk, Moby, J Dilla, Burial; not Kanye's "Through the Wire", the Avalanches or Portishead), so a clean
result doesn't prove a song is sample-free: it's a filter on top of leaving out hip-hop and electronic. MusicBrainz
allows one request a second and a song takes about five (a search, then each studio recording of it), so only the
genres where sampling is likely are checked: pop, soul & R&B, ambient, experimental, other and untagged (about
1,500 songs, two hours). Hip-hop and electronic, left out of runs by default, aren't checked unless asked.

Similar artists: ListenBrainz's "similar artists" (from what its listeners play in the same sessions).

Requests carry only the artist and song names and a generic app name; nothing about you.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from .db import connect

UA = {"User-Agent": "DigitalCrate/0.3 (local sample-library tool)", "Accept": "application/json"}
MB = "https://musicbrainz.org/ws/2"
LB_SIMILAR = ("https://labs.api.listenbrainz.org/similar-artists/json?artist_mbids={}&algorithm="
              "session_based_days_7500_session_300_contribution_5_threshold_10_limit_100_filter_True_skip_30")
RISKY = ["Pop", "Soul & R&B", "Ambient", "Experimental", "Other", "Unknown"]  # + Hip-Hop/Electronic: --families
_last = [0.0]


def _get(url, pace=1.05):
    for k in range(6):
        wait = _last[0] + pace - time.time()
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30))
        except urllib.error.HTTPError as e:
            if e.code in (429, 503):  # rate limited or busy: back off
                time.sleep(2 * (k + 1))
                continue
            if e.code == 404:
                return None
            raise
        except (urllib.error.URLError, TimeoutError):
            time.sleep(3 * (k + 1))
    return None


def _db(con):
    con.execute("""CREATE TABLE IF NOT EXISTS mb (track_id INTEGER PRIMARY KEY, recordings TEXT, samples TEXT,
                   artist_mbid TEXT, checked_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    con.execute("""CREATE TABLE IF NOT EXISTS mb_artist (name TEXT PRIMARY KEY, mbid TEXT, similar TEXT,
                   checked_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    return con


def _q(s):
    return (s or "").replace('"', "").strip()


def credits(artist, title, duration=None, max_recs=3):
    """(studio recording ids, [what it samples], artist mbid) for one song."""
    q = f'artist:"{_q(artist)}" AND recording:"{_q(title)}"'
    r = _get(f"{MB}/recording?query={urllib.parse.quote(q)}&limit=10&fmt=json") or {}
    recs = []
    for x in r.get("recordings", []):
        dis = (x.get("disambiguation") or "").lower()
        if x.get("score", 0) < 90 or any(w in dis for w in ("live", "remix", "demo", "dj-mix", "instrumental")):
            continue
        if duration and x.get("length") and abs(x["length"] / 1000 - duration) > 15:
            continue
        recs.append(x)
    recs = recs[:max_recs]
    hits, mbid = [], None
    for x in recs:
        if not mbid and x.get("artist-credit"):
            mbid = x["artist-credit"][0]["artist"]["id"]
        d = _get(f"{MB}/recording/{x['id']}?inc=recording-rels+release-rels&fmt=json") or {}
        for rel in d.get("relations", []):
            if "sampl" in rel.get("type", "") and rel.get("direction") == "forward":
                o = rel.get("recording") or rel.get("release") or {}
                ac = o.get("artist-credit") or []
                hits.append(o.get("title", "?") + (f" ({ac[0]['name']})" if ac else ""))
    return [x["id"] for x in recs], sorted(set(hits)), mbid


def run(limit=None, families=None, con=None):
    from tqdm import tqdm
    from .batches import _pool
    con = _db(con or connect())
    rows, fam, promise = _pool(con)
    fams = set(families or RISKY)
    seen = {r[0] for r in con.execute("SELECT track_id FROM mb")}
    todo = sorted((i for i in range(len(rows)) if fam[i] in fams and rows[i]["id"] not in seen), key=lambda i: -promise[i])
    todo = todo[:limit]
    dur = {r[0]: r[1] for r in con.execute("SELECT id, duration FROM tracks")}
    flagged = 0
    for i in tqdm(todo, desc="credits", mininterval=5):
        r = rows[i]
        try:
            recs, hits, mbid = credits(r["artist"], r["title"], dur.get(r["id"]))
        except Exception as e:
            print(f"  {r['artist']} - {r['title']}: {e}")
            continue
        con.execute("INSERT OR REPLACE INTO mb (track_id, recordings, samples, artist_mbid) VALUES (?,?,?,?)",
                    (r["id"], json.dumps(recs), json.dumps(hits), mbid))
        con.commit()
        if hits:
            flagged += 1
            print(f"SAMPLES {r['artist']} - {r['title']}: {'; '.join(hits[:3])}", flush=True)
    print(f"checked {len(todo)} songs; {flagged} are built on samples (left out of mining runs from now on)")


def flagged(con=None):
    """track ids MusicBrainz says sample other recordings."""
    con = _db(con or connect())
    return {r[0] for r in con.execute("SELECT track_id FROM mb WHERE samples != '[]'")}


# ---- related artists ------------------------------------------------------------------------------------------------

def artist_mbid(name, con):
    r = con.execute("SELECT mbid FROM mb_artist WHERE name=?", (name.lower(),)).fetchone()
    if r and r[0]:
        return r[0]
    q = urllib.parse.quote(f'artist:"{_q(name)}"')
    d = _get(f"{MB}/artist?query={q}&limit=3&fmt=json") or {}
    a = next((x for x in d.get("artists", []) if x.get("score", 0) >= 95), None)
    mbid = a["id"] if a else None
    con.execute("INSERT OR REPLACE INTO mb_artist (name, mbid, similar) VALUES (?,?,?)",
                (name.lower(), mbid, None))
    con.commit()
    return mbid


def similar(name, con=None, refresh=False):
    """[{name, mbid, score, comment}] artists ListenBrainz listeners play alongside `name` (cached)."""
    con = _db(con or connect())
    r = con.execute("SELECT similar FROM mb_artist WHERE name=?", (name.lower(),)).fetchone()
    if r and r[0] and not refresh:
        return json.loads(r[0])
    mbid = artist_mbid(name, con)
    if not mbid:
        return []
    d = _get(LB_SIMILAR.format(mbid), pace=0.5) or []
    out = [dict(name=x["name"], mbid=x["artist_mbid"], score=x.get("score", 0), comment=x.get("comment") or "")
           for x in d if isinstance(x, dict) and x.get("name")]
    con.execute("UPDATE mb_artist SET similar=? WHERE name=?", (json.dumps(out), name.lower()))
    con.commit()
    return out


def related_artists(n_seed=8, per=12, con=None):
    """Artists you don't have, that listeners pair with the artists whose samples you like most:
    [{name, because: [your artists], score}]."""
    from .related import track_weights
    con = _db(con or connect())
    w = track_weights(con)
    by_artist = {}
    for r in con.execute("SELECT id, artist FROM tracks"):
        if w.get(r["id"], 0) > 0 and r["artist"]:
            by_artist[r["artist"]] = by_artist.get(r["artist"], 0) + w[r["id"]]
    have = {(r[0] or "").strip().lower() for r in con.execute("SELECT DISTINCT artist FROM tracks")}
    seeds = [a for a, _ in sorted(by_artist.items(), key=lambda x: -x[1])
             if a.lower() not in ("various artists", "unknown artist")][:n_seed]
    out = {}
    for s in seeds:
        for k, x in enumerate(similar(s, con)[:per]):
            if x["name"].strip().lower() in have or x["name"].startswith("["):  # [anonymous], [unknown]
                continue
            o = out.setdefault(x["name"], dict(name=x["name"], because=[], score=0.0, comment=x["comment"]))
            o["because"].append(s)
            o["score"] += 1.0 / (k + 1)
    return dict(seeds=seeds, artists=sorted(out.values(), key=lambda o: -o["score"]))
