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
# two kinds of scouting: raw singing, or pads & textures (ambient, sustained, no drums or talking)
PRESETS = {
    "voice": ["r&b acapella", "90s r&b acapella", "neo soul acapella", "r&b singer vocals only", "quiet storm acapella",
              "acapella cover", "singing in my car", "singing alone in my room", "choir rehearsal recording",
              "gospel acapella", "soul singer acapella", "sacred harp singing", "bulgarian folk choir",
              "fado unaccompanied", "lullaby sung softly", "field recording church singing"],
    "pads": ["old video game soundtrack ambient", "ps1 ambient soundtrack", "70s synth soundtrack", "1980s new age synth",
             "nature documentary score", "dark ambient drone", "tape loop ambient", "organ drone",
             "string quartet slow movement", "shoegaze guitar ambient", "japanese environmental music",
             "music box lullaby"],
}
PAD = ["a slow ambient synth pad", "a warm sustained drone", "soft atmospheric soundtrack music with no drums",
       "dreamy video game ambient music", "slow sustained strings", "an ethereal reverb-drenched texture"]
PAD_NEG = ["drums and a beat", "people talking, speech, podcast", "a person singing", "loud crowd noise, applause",
           "video game sound effects and explosions"]
PAD_ROOM = ["lo-fi warm tape sound", "vintage analog synthesizer"]
VOCAL = ["a person singing alone with no accompaniment", "a cappella solo voice", "a woman singing softly",
         "a man singing softly", "a choir singing without instruments",
         "soulful r&b vocals with no music, a cappella"]
NEG = ["drums and bass, full band music", "people talking, speech, podcast", "loud crowd noise, applause",
       "electronic dance music with a beat", "video game sound effects and explosions"]
ROOM = ["singing recorded at home on a phone, intimate room sound", "reverberant church acoustics"]
# guided: listen for your styles (Discogs styles of the songs you've liked samples from), not a kind of sound
GUIDED_NEG = ["people talking, speech, podcast", "loud crowd noise, applause", "video game sound effects and explosions",
              "hip hop beat with rapping"]


def log(m):
    print(m, flush=True)


def _db():
    con = connect()
    con.execute("""CREATE TABLE IF NOT EXISTS yt_scout (id TEXT PRIMARY KEY, query TEXT, url TEXT, title TEXT,
                   channel TEXT, duration REAL, views INTEGER, score REAL, vocal REAL, neg REAL, taste REAL,
                   best_at REAL, snippet TEXT, status TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    cols = {r[1] for r in con.execute("PRAGMA table_info(yt_scout)")}
    for c in ("queries", "mode", "style"):  # every search a video turned up in; voice or pads scoring
        if c not in cols:
            con.execute(f"ALTER TABLE yt_scout ADD COLUMN {c} TEXT")
    return con


def _ytdlp():
    return str(Path(sys.executable).parent / "yt-dlp")


def search(query, n=15):
    out = subprocess.run([_ytdlp(), "--flat-playlist", "-J", f"ytsearch{n}:{query}"], capture_output=True, text=True,
                         check=True).stdout
    return [e for e in json.loads(out).get("entries", []) if e.get("id")]


def _fetch(vid, dur):
    DIR.mkdir(parents=True, exist_ok=True)
    # a minute from the middle of long uploads (hour-long ambient mixes, full albums); else from 20 s in
    a = int(dur / 2 - 30) if (dur or 0) > 20 * 60 else 20 if (dur or 0) > 100 else 0
    b = min((dur or 80), a + 60)
    tmpl = str(DIR / f"{vid}.%(ext)s")
    subprocess.run([_ytdlp(), "--no-playlist", "-f", "bestaudio/best", "-x", "--audio-format", "m4a",
                    "--download-sections", f"*{a}-{b}", "-o", tmpl, f"https://www.youtube.com/watch?v={vid}"],
                   check=True, capture_output=True, text=True)
    f = DIR / f"{vid}.m4a"
    return f, a


def _taste_vec(con, mode="voice"):
    cats = ("'Vocals','Vocal Atmospheres'" if mode == "voice"
            else "'Pads & Atmospheres','Textures & Field','Chords & Keys','Vocal Atmospheres'" if mode == "pads"
            else "'Vocals','Vocal Atmospheres','Pads & Atmospheres','Textures & Field','Chords & Keys','Melodies & Leads'")
    rows = con.execute(f"""SELECT s.clap FROM favorites f JOIN samples s ON s.path=f.path
                          WHERE s.category IN ({cats}) AND s.clap IS NOT NULL""").fetchall()
    if not rows:
        return None
    E = np.stack([np.frombuffer(r["clap"], dtype=np.float16).astype(np.float32) for r in rows])
    v = E.mean(0)
    return v / (np.linalg.norm(v) + 1e-9)


def run(query, n=15, mode="voice", style=None):
    import soundfile as sf
    from scipy.signal import resample_poly
    from .audio import decode
    from .models import clap
    con = _db()
    cl = clap()
    pos, neg_, room = {"voice": (VOCAL, NEG, ROOM), "pads": (PAD, PAD_NEG, PAD_ROOM)}.get(mode, (VOCAL, GUIDED_NEG, ROOM))
    tv, tn, tr = (cl.embed_text(tuple(x)) for x in (pos, neg_, room))
    if mode == "guided":
        from .related import target
        from . import styles as S
        T, cent = target(style, con)
    taste = _taste_vec(con, mode)
    seen = {r["id"]: r["queries"] or r["query"] or "" for r in con.execute("SELECT id, query, queries FROM yt_scout")}
    # dig past what's already been scouted, so repeating a search brings up to n *new* candidates
    known = sum(1 for q in seen.values() if query in q.split("|"))
    depth = min(100, n + known + n)
    log(f"searching YouTube ({dict(voice='voice', pads='pads & textures').get(mode, 'guided by ' + (style or 'your styles'))}): {query}")
    ents = search(query, depth)
    st = dict(found=len(ents), listened=0, already=0, too_short=0, failed=0)
    for k, e in enumerate(ents, 1):
        if st["listened"] >= n:
            break
        vid, dur = e["id"], e.get("duration") or 0
        if vid in seen:  # remember that this search found it too; don't re-listen
            qs = [q for q in seen[vid].split("|") if q]
            if query not in qs:
                con.execute("UPDATE yt_scout SET queries=? WHERE id=?", ("|".join(qs + [query]), vid)); con.commit()
            st["already"] += 1
            continue
        if dur and dur < 30:
            st["too_short"] += 1
            continue
        try:
            st["listened"] += 1
            log(f"[{st['listened']}/{n}] listening{f' ({int(dur // 60)} min, from the middle)' if dur > 1200 else ''}: {e.get('title')}")
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
            if mode == "guided":  # how much each 10 s window sounds like your styles (Discogs-EffNet)
                m16 = resample_poly(m48, 1, 3).astype(np.float32)
                sty, emb = [], []
                for s16 in starts:
                    r = S.predict([m16[s16 // 3:(s16 + W) // 3]])
                    pr, ev = r if r else (np.zeros(len(T), np.float32), np.zeros(1280, np.float32))
                    sty.append(float(pr @ T)); emb.append(float(ev @ cent / (np.linalg.norm(ev) + 1e-9)) if cent is not None else 0.0)
                v = np.array(sty)
                per = 3.0 * v + 1.5 * (np.array(emb) - 0.6) + 0.8 * ts - 1.2 * ng
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
                           taste, best_at, snippet, status, queries, mode, style) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?, 'scored',?,?,?)""",
                        (vid, query, f"https://www.youtube.com/watch?v={vid}", e.get("title"),
                         e.get("channel") or e.get("uploader"), dur, e.get("view_count"), round(score, 4),
                         round(float(v[top].mean()), 4), round(float(ng[top].mean()), 4),
                         round(float(ts[top].mean()), 4), round(off + starts[b] / 48000, 1),
                         str(snip.relative_to(C.LIB_ROOT)), query, mode, style if mode == "guided" else None))
            con.commit()
            log(f"    score {score:.2f} ({'style' if mode == 'guided' else 'fit'} {v[top].mean():.2f}, unwanted {ng[top].mean():.2f})")
        except Exception as ex:
            st["failed"] += 1
            log(f"    failed: {str(ex)[:120]}")
    log("SUMMARY " + json.dumps(st))
    log("SCOUT DONE")


def results(query=None, limit=200):
    """All scouted videos, best first; with query, only those that search turned up (now or earlier)."""
    con = _db()
    if query:
        q = "SELECT * FROM yt_scout WHERE '|' || COALESCE(queries, query) || '|' LIKE ? ORDER BY score DESC LIMIT ?"
        return [dict(r) for r in con.execute(q, (f"%|{query}|%", limit))]
    return [dict(r) for r in con.execute("SELECT * FROM yt_scout ORDER BY score DESC LIMIT ?", (limit,))]


def mark(vid, status):
    con = _db()
    con.execute("UPDATE yt_scout SET status=? WHERE id=?", (status, vid))
    con.commit()
