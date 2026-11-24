"""YouTube scout: search, listen to a minute of each result, score it for clean, intimate singing (and your taste),
and only then decide what to ingest — the Burial sourcing method, automated.

    python -m digitalcrate ytscout "acapella cover" [--n 15]

Only a ~60 s audio section of each candidate is fetched (into _data/scout_yt/), a 10 s preview snippet of its best
moment is kept, and nothing enters the library until you press "add source" in the app.
"""
import json
import re
import subprocess
import time
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
    # queries: every search a video turned up in; mode: voice / pads / guided scoring; emb: CLAP of its best
    # moments (what ✕ and add source learn from); moments: up to 3 previews; auto/seen: the daily inbox
    for c, t in (("queries", "TEXT"), ("mode", "TEXT"), ("style", "TEXT"), ("emb", "BLOB"), ("moments", "TEXT"),
                 ("channel_id", "TEXT"), ("auto", "INTEGER"), ("seen", "INTEGER"), ("via", "TEXT"),
                 ("expanded", "INTEGER")):
        if c not in cols:
            con.execute(f"ALTER TABLE yt_scout ADD COLUMN {c} {t}")
    return con


def _ytdlp():
    return str(Path(sys.executable).parent / "yt-dlp")


def _flat(target, n):
    out = subprocess.run([_ytdlp(), "--flat-playlist", "-J", "--playlist-end", str(n), target], capture_output=True,
                         text=True, check=True).stdout
    return [e for e in (json.loads(out).get("entries") or []) if e.get("id")]


def search(query, n=15):
    return _flat(f"ytsearch{n}:{query}", n)



def _fetch(vid, dur):
    DIR.mkdir(parents=True, exist_ok=True)
    # a minute from the middle of long uploads (hour-long ambient mixes, full albums); else from 20 s in
    a = int(dur / 2 - 30) if (dur or 0) > 20 * 60 else 20 if (dur or 0) > 100 else 0
    b = min((dur or 80), a + 60)
    tmpl = str(DIR / f"{vid}.%(ext)s")
    subprocess.run([_ytdlp(), "--no-playlist", "-f", "bestaudio/best", "-x", "--audio-format", "m4a",
                    "--download-sections", f"*{a}-{b}", "-o", tmpl, f"https://www.youtube.com/watch?v={vid}"],
                   check=True, capture_output=True, text=True)
    return DIR / f"{vid}.m4a", a


# what isn't worth a listen: playlists and DJ mixes (other people's sequencing, huge downloads), and label releases
# (music videos, official audio: produced, often sample-based, and easy to find anyway)
JUNK = re.compile(r"play ?list|compilation|non-?stop|\bdj mix\b|\btop \d+\b|greatest hits|\bbest of\b|\bm/v\b|"
                  r"\bmv\b|official (hd |4k |music |lyric )*(video|audio)|lyric video|\(lyrics?\)|full album", re.I)


# what a title promises, per mode: listened to first when going through a channel
PROMISE = {"voice": re.compile(r"a ?cc?app?ella|vocals? only|voice only|isolated vocals?|unaccompanied|choir", re.I),
           "pads": re.compile(r"ambient|drone|pad|soundtrack|\bost\b|new age|synth|atmospher|texture", re.I)}


def unwanted(title, channel, dur, mode):
    """Why a search result isn't worth listening to, or None."""
    from .policy import classify_track
    m = JUNK.search(title or "")
    if m and not (mode == "pads" and m.group(0).lower() == "full album"):  # whole ambient albums are fine
        return "playlist, mix or music video"
    if dur and dur > 30 * 60 and mode != "pads":
        return "over 30 minutes"
    for who in ((title or "").split(" - ")[0], re.sub(r"(?i)\s*-\s*topic$|vevo$", "", channel or "")):
        if who.strip() and classify_track(who.strip(), "", "") == "reference":
            return "reference-only artist"
    return None


_ART = {}


def library_artist(title, channel, con):
    """The artist of yours a video is by, if any (shown, not filtered: an acapella of a song you own is still a find)."""
    if "set" not in _ART:
        _ART["set"] = {(r[0] or "").strip().lower() for r in con.execute("SELECT DISTINCT artist FROM tracks")} - {""}
    for who in ((title or "").split(" - ")[0], re.sub(r"(?i)\s*-\s*topic$|vevo$|\s*official$", "", channel or "")):
        w = who.strip().lower()
        if len(w) > 2 and w in _ART["set"]:
            return who.strip()
    return None


def _taste_vec(con, mode="voice"):
    cats = ("'Vocals','Vocal Atmospheres'" if mode == "voice"
            else "'Pads & Atmospheres','Textures & Field','Chords & Keys','Vocal Atmospheres'" if mode == "pads"
            else "'Vocals','Vocal Atmospheres','Pads & Atmospheres','Strings & Orchestral','Textures & Field','Chords & Keys','Melodies & Leads'")
    rows = con.execute(f"""SELECT s.clap FROM favorites f JOIN samples s ON s.path=f.path
                          WHERE s.category IN ({cats}) AND s.clap IS NOT NULL""").fetchall()
    if not rows:
        return None
    E = np.stack([np.frombuffer(r["clap"], dtype=np.float16).astype(np.float32) for r in rows])
    v = E.mean(0)
    return v / (np.linalg.norm(v) + 1e-9)


def _snip(y, s0, path):
    """10 s from sample s0 of y, faded and normalised, as a preview wav."""
    import soundfile as sf
    seg = y[:, s0:s0 + C.SR * 10].copy()
    fl = int(0.05 * C.SR)
    seg[:, :fl] *= np.linspace(0, 1, fl)
    seg[:, -fl:] *= np.linspace(1, 0, fl)
    sf.write(str(path), (seg * 0.9 / (np.abs(seg).max() + 1e-9)).T, C.SR, subtype="PCM_16")


def _backfill(con, cl):
    """Older finds have no embedding: take it from their preview, so ✕ and add source on them still teach."""
    from scipy.signal import resample_poly
    from .audio import decode
    rows = con.execute("SELECT id, snippet FROM yt_scout WHERE emb IS NULL AND snippet IS NOT NULL").fetchall()
    for r in rows:
        f = C.LIB_ROOT / r["snippet"]
        if not f.exists():
            continue
        try:
            y = decode(f)
            e = cl.embed_audio([resample_poly(y.mean(0), 160, 147).astype(np.float32)])[0]
            con.execute("UPDATE yt_scout SET emb=? WHERE id=?", (e.astype(np.float16).tobytes(), r["id"]))
        except Exception:
            pass
    con.commit()


def _listen(label, ents, n, mode, style, auto=False, via=None):
    """Listen to up to n new videos from ents and score them; label is the search they're filed under."""
    from scipy.signal import resample_poly
    from .audio import decode
    from .models import clap
    con = _db()
    cl = clap()
    _backfill(con, cl)
    pos, neg_, room = {"voice": (VOCAL, NEG, ROOM), "pads": (PAD, PAD_NEG, PAD_ROOM)}.get(mode, (VOCAL, GUIDED_NEG, ROOM))
    tv, tn, tr = (cl.embed_text(tuple(x)) for x in (pos, neg_, room))
    if mode == "guided":
        from .related import target
        from . import styles as S
        T, cent = target(style, con)
    taste = _taste_vec(con, mode)
    seen = {r["id"]: r["queries"] or r["query"] or "" for r in con.execute("SELECT id, query, queries FROM yt_scout")}
    st = dict(found=len(ents), listened=0, already=0, too_short=0, filtered=0, failed=0)
    for e in ents:
        if st["listened"] >= n:
            break
        vid, dur = e["id"], e.get("duration") or 0
        if vid in seen:  # remember that this search found it too; don't re-listen
            qs = [q for q in seen[vid].split("|") if q]
            if label not in qs:
                con.execute("UPDATE yt_scout SET queries=? WHERE id=?", ("|".join(qs + [label]), vid)); con.commit()
                seen[vid] = "|".join(qs + [label])
            st["already"] += 1
            continue
        if dur and dur < 30:
            st["too_short"] += 1
            continue
        why = unwanted(e.get("title"), e.get("channel") or e.get("uploader"), dur, mode)
        if why:
            st["filtered"] += 1
            log(f"    skipped ({why}): {e.get('title')}")
            continue
        try:
            st["listened"] += 1
            log(f"[{st['listened']}/{n}] listening{f' ({int(dur // 60)} min, from the middle)' if dur > 1200 else ''}: {e.get('title')}")
            f, off = _fetch(vid, dur)
            y = decode(f)
            m48 = resample_poly(y.mean(0), 160, 147).astype(np.float32)
            W = 48000 * 10
            starts = list(range(0, max(1, len(m48) - W + 1), W // 2))
            A = cl.embed_audio([m48[s:s + W] for s in starts])
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
            best = []  # up to 3 moments at least 10 s apart (windows overlap by half)
            for i in np.argsort(-per):
                if all(abs(int(i) - j) >= 2 for j in best):
                    best.append(int(i))
                if len(best) == 3:
                    break
            moments = []
            for k, b in enumerate(best):
                snip = DIR / (f"{vid}_preview.wav" if k == 0 else f"{vid}_m{k}.wav")
                _snip(y, int(starts[b] / 48000 * C.SR), snip)
                moments.append([round(off + starts[b] / 48000, 1), str(snip.relative_to(C.LIB_ROOT))])
            ev = A[top].mean(0)
            ev /= np.linalg.norm(ev) + 1e-9
            f.unlink(missing_ok=True)
            con.execute("""INSERT OR REPLACE INTO yt_scout(id, query, url, title, channel, duration, views, score, vocal, neg,
                           taste, best_at, snippet, status, queries, mode, style, emb, moments, channel_id, auto, seen, via)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?, 'scored',?,?,?,?,?,?,?,?,?)""",
                        (vid, label, f"https://www.youtube.com/watch?v={vid}", e.get("title"),
                         e.get("channel") or e.get("uploader"), dur, e.get("view_count"), round(score, 4),
                         round(float(v[top].mean()), 4), round(float(ng[top].mean()), 4),
                         round(float(ts[top].mean()), 4), moments[0][0], moments[0][1], label, mode,
                         style if mode == "guided" else None, ev.astype(np.float16).tobytes(), json.dumps(moments),
                         e.get("channel_id"), int(auto), 0 if auto else 1, via))
            con.commit()
            log(f"    score {score:.2f} ({'style' if mode == 'guided' else 'fit'} {v[top].mean():.2f}, unwanted {ng[top].mean():.2f})")
        except Exception as ex:
            st["failed"] += 1
            log(f"    failed: {str(ex)[:120]}")
    log("SUMMARY " + json.dumps(st))
    return st


def run(query, n=15, mode="voice", style=None, auto=False):
    con = _db()
    known = sum(1 for r in con.execute("SELECT query, queries FROM yt_scout")
                if query in (r["queries"] or r["query"] or "").split("|"))
    # dig past what's already been scouted (and what the filters drop), so repeating a search brings n *new* ones
    depth = min(100, 2 * n + known + n)
    log(f"searching YouTube ({dict(voice='voice', pads='pads & textures').get(mode, 'guided by ' + (style or 'your styles'))}): {query}")
    _listen(query, search(query, depth), n, mode, style, auto)
    if not auto:
        log("SCOUT DONE")


def _clean(title):
    """A video title as a search: no brackets, no 'acapella / official / lyrics' words."""
    t = re.sub(r"[\(\[【].*?[\)\]】]", " ", title or "")
    t = re.sub(r"(?i)\b(a ?cc?app?ella|official|video|audio|lyrics?|hd|hq|version|remaster(ed)?|full)\b", " ", t)
    return " ".join(re.sub(r"[^\w' -]", " ", t).split()[:6])


def more(vid, n=15, auto=False):
    """More like a good find: its channel's other uploads (a channel that posts one great acapella usually posts
    more), interleaved with a search built from its title, scored the way it was."""
    con = _db()
    r = con.execute("SELECT * FROM yt_scout WHERE id=?", (vid,)).fetchone()
    if not r:
        raise SystemExit("no such find")
    mode, style = r["mode"] or "voice", r["style"]
    ch = r["channel_id"]
    if not ch:
        try:
            ch = subprocess.run([_ytdlp(), "--skip-download", "--print", "channel_id", r["url"]], capture_output=True,
                                text=True, check=True).stdout.strip()
            con.execute("UPDATE yt_scout SET channel_id=? WHERE id=?", (ch, vid))
        except Exception:
            ch = None
    a, b = [], []
    if ch:
        log(f"listening through {r['channel']}'s channel")
        try:
            a = _flat(f"https://www.youtube.com/channel/{ch}/videos", 60)
        except Exception as ex:
            log(f"    couldn't list the channel: {str(ex)[:100]}")
    hint = {"voice": "acapella", "pads": "ambient"}.get(mode, "")
    qs = [(_clean(r["title"]) + " " + hint).strip()]
    if " - " in (r["title"] or ""):  # the artist's other ones too
        qs.append((_clean(r["title"].split(" - ")[0]) + " " + hint).strip())
    lists = [a]
    for q in dict.fromkeys(qs):
        log(f"and searching: {q}")
        lists.append(search(q, 30))
    ents, ids = [], set()
    for k in range(max(map(len, lists))):  # interleave channel and searches
        for L in lists:
            if k < len(L) and L[k]["id"] not in ids:
                ids.add(L[k]["id"]); ents.append(L[k])
    want = PROMISE.get(mode)
    if want:  # titles that say what we're after first ("acapella", "drone"…), in their order otherwise
        ents.sort(key=lambda e: not want.search(e.get("title") or ""))
    con.execute("UPDATE yt_scout SET expanded=1 WHERE id=?", (vid,))
    con.commit()
    _listen("more like: " + (r["title"] or vid)[:60], ents, n, mode, style, auto, via=vid)
    if not auto:
        log("SCOUT DONE")


# ---- the daily inbox: a few searches run by themselves, picked from what you've added
AUTO = C.DATA_DIR / "scout_auto.json"


def auto_state():
    try:
        return dict(dict(enabled=True, last=0), **json.loads(AUTO.read_text()))
    except Exception:
        return dict(enabled=True, last=0)


def set_auto(**kw):
    s = dict(auto_state(), **kw)
    AUTO.parent.mkdir(parents=True, exist_ok=True)
    AUTO.write_text(json.dumps(s))
    return s


def auto_due(hours=20):
    s = auto_state()
    return s["enabled"] and time.time() - s["last"] > hours * 3600


def auto_plan(con=None):
    """Up to 3 searches: more like your latest add, your most productive search again (it digs deeper), and one
    you haven't tried, in the mode you add from most."""
    con = con or _db()
    rows = [dict(r) for r in con.execute("SELECT id, query, mode, style, status, expanded FROM yt_scout")]
    plan = []
    added = [r for r in rows if r["status"] == "ingested"]
    fresh = [r for r in added if not r["expanded"]]
    if fresh:
        plan.append(dict(kind="more", id=fresh[-1]["id"]))
    by = {}
    for r in rows:
        q = r["query"] or ""
        if q and not q.startswith("more like: "):
            d = by.setdefault(q, dict(query=q, mode=r["mode"] or "voice", style=r["style"], adds=0, n=0))
            d["n"] += 1
            d["adds"] += r["status"] == "ingested"
    good = sorted((d for d in by.values() if d["adds"]), key=lambda d: -d["adds"] / d["n"])
    if good:
        plan.append(dict(kind="search", **{k: good[0][k] for k in ("query", "mode", "style")}))
    modes = sorted(("voice", "pads", "guided"), key=lambda m: -sum(r["mode"] == m for r in added))
    ideas = []
    for m in modes:
        if m == "guided":
            try:
                from .related import guided_queries
                ideas += [dict(query=g["query"], mode="guided", style=g["style"]) for g in guided_queries(con)]
            except Exception:
                pass
        else:
            ideas += [dict(query=q, mode=m, style=None) for q in PRESETS[m]]
    for i in ideas:
        if len(plan) >= 3:
            break
        if i["query"] not in by:
            plan.append(dict(kind="search", **i))
    return plan


def auto_run(n=8):
    set_auto(last=time.time())
    for p in auto_plan():
        try:
            if p["kind"] == "more":
                more(p["id"], n, auto=True)
            else:
                run(p["query"], n, p["mode"], p["style"], auto=True)
        except Exception as ex:
            log(f"    failed: {str(ex)[:120]}")
    log("SCOUT DONE")


# ---- results
def _unit(v):
    return v / (np.linalg.norm(v) + 1e-9)


def results(query=None, limit=400):
    """Every find, ranked within its own mode (voice, pads and style scores aren't on one scale) plus what your ✕
    and add source have taught it: closer to what you added, further from what you dismissed."""
    con = _db()
    rows = [dict(r) for r in con.execute("SELECT * FROM yt_scout")]
    newly = [r["id"] for r in rows if r["status"] == "scored" and unwanted(r["title"], r["channel"], r["duration"], r["mode"])]
    if newly:  # finds from before the filters
        con.executemany("UPDATE yt_scout SET status='filtered' WHERE id=?", [(i,) for i in newly])
        con.commit()
        for r in rows:
            if r["id"] in newly:
                r["status"] = "filtered"
    E = {r["id"]: np.frombuffer(r["emb"], dtype=np.float16).astype(np.float32) for r in rows if r["emb"]}
    pos = [E[r["id"]] for r in rows if r["status"] == "ingested" and r["id"] in E]
    neg = [E[r["id"]] for r in rows if r["status"] == "skipped" and r["id"] in E]
    P = _unit(np.mean(pos, 0)) if pos else None
    N = _unit(np.mean(neg, 0)) if neg else None
    raw = {i: (e @ P if P is not None else 0.0) - (e @ N if N is not None else 0.0) for i, e in E.items()}
    mid = float(np.mean(list(raw.values()))) if raw else 0.0  # relative to the average find, not a constant lift
    for r in rows:
        r["picks"] = round(float(5 * (raw[r["id"]] - mid)), 3) if r["id"] in raw and (pos or neg) else 0.0
    for m in {r["mode"] or "voice" for r in rows}:
        grp = [r for r in rows if (r["mode"] or "voice") == m]
        live = np.array([r["score"] or 0 for r in grp if r["status"] not in ("skipped", "filtered")] or [0.0])
        for r in grp:
            r["rank"] = round(float(((r["score"] or 0) - live.mean()) / (live.std() + 1e-9) + r["picks"]), 3)
        ranks = np.array([r["rank"] for r in grp if r["status"] not in ("skipped", "filtered")] or [0.0])
        for r in grp:  # percentile among the finds you can see
            r["pct"] = int(round(100 * (ranks <= r["rank"]).mean()))
    for r in rows:
        r.pop("emb", None)
        try:
            r["moments"] = json.loads(r["moments"]) if r["moments"] else [[r["best_at"] or 0, r["snippet"]]]
        except Exception:
            r["moments"] = [[r["best_at"] or 0, r["snippet"]]]
        r["mine"] = None if r["status"] == "ingested" else library_artist(r["title"], r["channel"], con)
    if query:
        rows = [r for r in rows if query in (r["queries"] or r["query"] or "").split("|")]
    rows.sort(key=lambda r: -r["rank"])
    return rows[:limit]


def learned(con=None):
    con = con or _db()
    r = con.execute("SELECT COALESCE(SUM(status='ingested'),0), COALESCE(SUM(status='skipped'),0) FROM yt_scout").fetchone()
    return dict(added=r[0], dismissed=r[1])


def mark(vid, status):
    con = _db()
    con.execute("UPDATE yt_scout SET status=?, seen=1 WHERE id=?", (status, vid))
    con.commit()


def mark_seen(ids):
    con = _db()
    con.executemany("UPDATE yt_scout SET seen=1 WHERE id=?", [(i,) for i in ids])
    con.commit()
