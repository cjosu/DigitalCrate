"""YouTube scout: search, listen to a minute of each result, score it for clean, intimate singing (and your taste),
and only then decide what to ingest — the Burial sourcing method, automated.

    python -m digitalcrate ytscout "acapella cover" [--n 15]

Only a ~60 s audio section of each candidate is fetched (into _data/scout_yt/), a 10 s preview snippet of its best
moment is kept, and nothing enters the library until you press "add source" in the app.
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

from . import config as C
from .db import connect

DIR = C.DATA_DIR / "scout_yt"
PRESETS = ["r&b acapella", "90s r&b acapella", "neo soul acapella", "r&b singer vocals only", "quiet storm acapella",
           "acapella cover", "singing in my car", "singing alone in my room", "choir rehearsal recording",
           "gospel acapella", "soul singer acapella", "old video game soundtrack ambient", "sacred harp singing",
           "bulgarian folk choir", "fado unaccompanied", "lullaby sung softly", "field recording church singing"]
VOCAL = ["a person singing alone with no accompaniment", "a cappella solo voice", "a woman singing softly",
         "a man singing softly", "a choir singing without instruments",
         "soulful r&b vocals with no music, a cappella"]
NEG = ["drums and bass, full band music", "people talking, speech, podcast", "loud crowd noise, applause",
       "electronic dance music with a beat", "video game sound effects and explosions"]
ROOM = ["singing recorded at home on a phone, intimate room sound", "reverberant church acoustics"]


def log(m):
    print(m, flush=True)


def _db():
    con = connect()
    con.execute("""CREATE TABLE IF NOT EXISTS yt_scout (id TEXT PRIMARY KEY, query TEXT, url TEXT, title TEXT,
                   channel TEXT, duration REAL, views INTEGER, score REAL, vocal REAL, neg REAL, taste REAL,
                   best_at REAL, snippet TEXT, status TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    return con


def _ytdlp():
    return str(Path(sys.executable).parent / "yt-dlp")


def search(query, n=15):
    out = subprocess.run([_ytdlp(), "--flat-playlist", "-J", f"ytsearch{n}:{query}"], capture_output=True, text=True,
                         check=True).stdout
    return [e for e in json.loads(out).get("entries", []) if e.get("id")]


def _fetch(vid, dur):
    DIR.mkdir(parents=True, exist_ok=True)
    a = 20 if (dur or 0) > 100 else 0
    b = min((dur or 80), a + 60)
    tmpl = str(DIR / f"{vid}.%(ext)s")
    subprocess.run([_ytdlp(), "--no-playlist", "-f", "bestaudio/best", "-x", "--audio-format", "m4a",
                    "--download-sections", f"*{a}-{b}", "-o", tmpl, f"https://www.youtube.com/watch?v={vid}"],
                   check=True, capture_output=True, text=True)
    f = DIR / f"{vid}.m4a"
    return f, a


def _taste_vec(con):
    rows = con.execute("""SELECT s.clap FROM favorites f JOIN samples s ON s.path=f.path
                          WHERE s.category IN ('Vocals','Vocal Atmospheres') AND s.clap IS NOT NULL""").fetchall()
    if not rows:
        return None
    E = np.stack([np.frombuffer(r["clap"], dtype=np.float16).astype(np.float32) for r in rows])
    v = E.mean(0)
    return v / (np.linalg.norm(v) + 1e-9)


def run(query, n=15):
    import soundfile as sf
    from scipy.signal import resample_poly
    from .audio import decode
    from .models import clap
    con = _db()
    cl = clap()
    tv, tn, tr = (cl.embed_text(tuple(x)) for x in (VOCAL, NEG, ROOM))
    taste = _taste_vec(con)
    log(f"searching YouTube: {query}")
    ents = search(query, n)
    seen = {r["id"] for r in con.execute("SELECT id FROM yt_scout")}
    for k, e in enumerate(ents, 1):
        vid, dur = e["id"], e.get("duration") or 0
        if vid in seen:
            con.execute("UPDATE yt_scout SET query=? WHERE id=?", (query, vid)); con.commit()
            log(f"[{k}/{len(ents)}] already scouted: {e.get('title')}"); continue
        if dur and (dur > 20 * 60 or dur < 30):
            log(f"[{k}/{len(ents)}] skip ({int(dur // 60)} min): {e.get('title')}"); continue
        try:
            log(f"[{k}/{len(ents)}] listening: {e.get('title')}")
            f, off = _fetch(vid, dur)
            y = decode(f)
            m48 = resample_poly(y.mean(0), 160, 147).astype(np.float32)
            W = 48000 * 10
            starts = list(range(0, max(1, len(m48) - W + 1), W // 2))
            clips = [m48[s:s + W] for s in starts]
            A = cl.embed_audio(clips)
            v = (A @ tv.T).max(1)
            ng = (A @ tn.T).max(1)
            rm = (A @ tr.T).max(1)
            ts = (A @ taste) if taste is not None else np.zeros(len(A))
            per = 2.0 * v - 1.2 * ng + 0.4 * rm + 0.8 * ts
            top = np.argsort(-per)[:3]
            score = float(per[top].mean())
            b = int(top[0])
            snip = DIR / f"{vid}_preview.wav"
            s0 = int(starts[b] / 48000 * C.SR)
            seg = y[:, s0:s0 + C.SR * 10].copy()
            fl = int(0.05 * C.SR)
            seg[:, :fl] *= np.linspace(0, 1, fl)
            seg[:, -fl:] *= np.linspace(1, 0, fl)
            sf.write(str(snip), (seg * 0.9 / (np.abs(seg).max() + 1e-9)).T, C.SR, subtype="PCM_16")
            f.unlink(missing_ok=True)
            con.execute("""INSERT OR REPLACE INTO yt_scout(id, query, url, title, channel, duration, views, score, vocal, neg,
                           taste, best_at, snippet, status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?, 'scored')""",
                        (vid, query, f"https://www.youtube.com/watch?v={vid}", e.get("title"),
                         e.get("channel") or e.get("uploader"), dur, e.get("view_count"), round(score, 4),
                         round(float(v[top].mean()), 4), round(float(ng[top].mean()), 4),
                         round(float(ts[top].mean()), 4), round(off + starts[b] / 48000, 1),
                         str(snip.relative_to(C.LIB_ROOT)), ))
            con.commit()
            log(f"    score {score:.2f} (voice {v[top].mean():.2f}, band/speech {ng[top].mean():.2f})")
        except Exception as ex:
            log(f"    failed: {str(ex)[:120]}")
    log("SCOUT DONE")


def results(query=None, limit=200):
    con = _db()
    q = "SELECT * FROM yt_scout" + (" WHERE query=?" if query else "") + " ORDER BY score DESC LIMIT ?"
    return [dict(r) for r in con.execute(q, ((query, limit) if query else (limit,)))]


def mark(vid, status):
    con = _db()
    con.execute("UPDATE yt_scout SET status=? WHERE id=?", (status, vid))
    con.commit()
