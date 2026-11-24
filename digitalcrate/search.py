"""Sound search over the CLAP embeddings that already exist for every sample.

- text_search("lonely female voice, distant, rainy night")  -> ranked samples
- reference_search(url | file | "artist - title")            -> samples whose sound/vibe is closest to a reference
  track (the reference is only listened to, never sampled or catalogued)
- galaxy()                                                    -> 2D map of every sample by sound (t-SNE), cached
"""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

from . import config as C
from .db import connect

REF_DIR = C.FOUND_DIR / "References"
_M = {}


def matrix():
    """(paths, ids, unit-norm embedding matrix); reloaded when the sample set changes."""
    con = connect()
    sig = con.execute("SELECT COUNT(*), MAX(rowid) FROM samples WHERE clap IS NOT NULL").fetchone()
    if _M.get("sig") != tuple(sig):
        rows = con.execute("SELECT id, path, track_id, category, clap FROM samples WHERE clap IS NOT NULL").fetchall()
        E = np.stack([np.frombuffer(r["clap"], dtype=np.float16).astype(np.float32) for r in rows])
        E /= np.linalg.norm(E, axis=1, keepdims=True) + 1e-9
        _M.update(sig=tuple(sig), paths=[r["path"] for r in rows], ids=[r["id"] for r in rows],
                  tids=np.array([r["track_id"] for r in rows]),
                  cats=np.array([r["category"] for r in rows]), E=E)
    return _M


def _top(scores, k, extra=None):
    m = matrix()
    idx = np.argsort(-scores)[:k]
    return [dict(path=m["paths"][i], id=m["ids"][i], score=round(float(scores[i]), 4),
                 **({kk: v[i] for kk, v in extra.items()} if extra else {})) for i in idx]


SOURCE_WORDS = re.compile(r"\b(voice|vocal|vox|sing|singer|singing|choir|chant|speech|spoken|organ|piano|keys|rhodes|guitar|"
                          r"strings?|violin|cello|pad|synth|drone|bell|harp|flute|brass|horn|sax|bass|drum|kick|snare|"
                          r"hat|percussion|field|rain|birds?|bells?|choral|woman|female|man|male|girl|boy|child)\b", re.I)


CAT_HINTS = [
    (re.compile(r"\b(voice|vocals?|vox|sing\w*|singer|choir|chant\w*|speech|spoken|acapella|a cappella)\b", re.I),
     ["Vocals", "Vocal Atmospheres"]),
    (re.compile(r"\b(organ|piano|keys|rhodes|chords?|wurlitzer|harpsichord)\b", re.I), ["Chords & Keys"]),
    (re.compile(r"\b(drums?|kick|snare|hats?|hi-hat|percussion|breaks?|cymbal|clap|shaker|toms?)\b", re.I), ["Percussion"]),
    (re.compile(r"\b(pad|drone|atmosphere|ambien\w*)\b", re.I), ["Pads & Atmospheres", "Vocal Atmospheres"]),
    (re.compile(r"\b(strings?|orchestra\w*|violins?|cellos?|violas?|symphon\w*|classical)\b", re.I), ["Strings & Orchestral"]),
    (re.compile(r"\b(melody|lead|riff|line)\b", re.I), ["Melodies & Leads"]),
    (re.compile(r"\b(field recording|texture|noise|crackle|rain|birds?|room tone)\b", re.I), ["Textures & Field"]),
    (re.compile(r"\b(bass|sub)\b", re.I), ["Bass & Sub"]),
]


def text_search(q, k=400):
    from .models import clap
    q = q.strip()
    # "warm organ -drums": words after '-' are pushed away
    neg = [w[1:] for w in q.split() if w.startswith("-") and len(w) > 1]
    pos = " ".join(w for w in q.split() if not w.startswith("-"))
    cl = clap()
    m = matrix()
    # each comma-separated idea is its own prompt; z-scored so "female voice" and "rainy night" both count
    parts = [p.strip() for p in pos.split(",") if p.strip()] or [pos]
    Z, w = [], []
    for part in parts:
        t = cl.embed_text((part, f"the sound of {part}", f"a recording of {part}")).mean(0)
        t /= np.linalg.norm(t) + 1e-9
        x = m["E"] @ t
        Z.append((x - x.mean()) / (x.std() + 1e-9))
        w.append(2.0 if SOURCE_WORDS.search(part) else 1.0)   # what makes the sound matters most
    Z, w = np.stack(Z), np.array(w)[:, None]
    mu = (Z * w).sum(0) / w.sum()
    s = mu - (0.35 * Z.std(0) if len(parts) > 1 else 0)          # soft AND: reward matching every idea
    for rx, cats in CAT_HINTS:                                    # the words name a kind of sound: lean on our categories
        if rx.search(pos):
            s = s + 0.6 * np.isin(m["cats"], cats)
    s = np.where(np.char.startswith(np.array(m["paths"]), "_Reference"), -9, s)   # reference-only artists stay unsampled
    if neg:
        n = cl.embed_text(tuple(neg))
        n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-9
        s = s - 0.5 * np.clip(m["E"] @ n.T, 0, None).max(1)
    return dict(query=q, results=_top(s, k))


# ---------- reference tracks
def _resolve_ref(target):
    """URL -> downloaded audio; existing path -> itself; otherwise a library track matched by 'artist - title'."""
    target = target.strip().strip('"').strip("'")
    if re.match(r"^https?://", target):
        REF_DIR.mkdir(parents=True, exist_ok=True)
        ytdlp = str(Path(sys.executable).parent / "yt-dlp")
        info = json.loads(subprocess.run([ytdlp, "--no-playlist", "-J", target], capture_output=True, text=True,
                                         check=True).stdout)
        hits = list(REF_DIR.glob(f"*[[]{info['id']}[]].m4a"))
        if not hits:
            subprocess.run([ytdlp, "--no-playlist", "-f", "bestaudio/best", "-x", "--audio-format", "m4a",
                            "-o", str(REF_DIR / "%(title).80s [%(id)s].%(ext)s"), target],
                           check=True, capture_output=True, text=True)
            hits = list(REF_DIR.glob(f"*[[]{info['id']}[]].m4a"))
        return hits[0], info.get("title") or target, None
    p = Path(target).expanduser()
    if p.exists():
        con = connect()
        r = con.execute("SELECT id FROM tracks WHERE path=?", (str(p),)).fetchone()
        return p, p.stem, r["id"] if r else None
    con = connect()
    words = [w for w in re.split(r"[\s\-–—]+", target) if w]
    if not words:
        raise ValueError("give a URL, a file path, or 'artist - title'")
    where = " AND ".join("(artist LIKE ? OR title LIKE ?)" for _ in words)
    args = [x for w in words for x in (f"%{w}%", f"%{w}%")]
    r = con.execute(f"SELECT id, path, artist, title FROM tracks WHERE {where} ORDER BY length(title) LIMIT 1",
                    args).fetchone()
    if r is None:
        raise ValueError(f"no track in your library matches '{target}'")
    return Path(r["path"]), f"{r['artist']} — {r['title']}", r["id"]


def reference_search(target, k=400):
    from scipy.signal import resample_poly
    from .audio import decode
    from .models import clap
    path, name, tid = _resolve_ref(target)
    y = decode(path)
    m = y.mean(0) if y.ndim > 1 else y
    m48 = resample_poly(m, 160, 147).astype(np.float32)
    win, hop = 48000 * 10, 48000 * 10
    starts = list(range(0, max(1, len(m48) - win), hop))
    if len(starts) > 36:  # long tracks: spread 36 windows over the whole thing
        starts = [int(x) for x in np.linspace(0, len(m48) - win, 36)]
    clips = [m48[s:s + win] for s in starts if np.abs(m48[s:s + win]).max() > 1e-3]
    W = clap().embed_audio(clips)
    W /= np.linalg.norm(W, axis=1, keepdims=True) + 1e-9
    mat = matrix()
    sims = mat["E"] @ W.T                       # samples x windows
    cen = W.mean(0)
    cen /= np.linalg.norm(cen) + 1e-9
    score = 0.6 * sims.max(1) + 0.4 * (mat["E"] @ cen)
    score[np.char.startswith(np.array(mat["paths"]), "_Reference")] = -9   # reference-only artists stay unsampled
    if tid is not None:                        # never recommend cuts of the reference itself
        score[mat["tids"] == tid] = -9
    best = sims.argmax(1)
    at = np.array([f"{int(starts[b] / 48000 // 60)}:{int(starts[b] / 48000 % 60):02d}" for b in best])
    return dict(reference=name, windows=len(clips), results=_top(score, k, dict(at=at.tolist())))


# ---------- galaxy
_G = {}


def galaxy(full=False):
    """2D layout of every sample (PCA-50 -> t-SNE), cached on disk keyed by the sample set. `digitalcrate build`
    makes it (full=True, about 30 s on 20k samples). In between, samples that arrive (live updates) are placed among
    their nearest neighbours by sound and deleted ones dropped, instantly; the next build lays it all out again."""
    m = matrix()
    h = hashlib.sha1("".join(m["ids"]).encode()).hexdigest()[:12]
    cache = C.DATA_DIR / "galaxy.json"
    if _G.get("hash") == h and not (full and _G.get("approx")):
        return _G
    g = json.loads(cache.read_text()) if cache.exists() else None
    if g and g.get("hash") == h and not (full and g.get("approx")):
        _G.clear(); _G.update(g)
        return g
    if g and not full and g.get("xy"):
        old = g["xy"]
        have = np.array([p in old for p in m["paths"]])
        if have.sum() >= 0.8 * len(have):  # place the newcomers among their 8 nearest placed neighbours
            P = np.array([old[p] for p, k in zip(m["paths"], have) if k])
            Eh, new = m["E"][have], np.where(~have)[0]
            xy = {p: old[p] for p, k in zip(m["paths"], have) if k}
            for a in range(0, len(new), 512):
                idx = new[a:a + 512]
                sim = m["E"][idx] @ Eh.T
                nn = np.argsort(-sim, 1)[:, :8]
                for i, row in zip(idx, nn):
                    x, y = P[row].mean(0) + np.random.default_rng(i).normal(0, 0.004, 2)
                    xy[m["paths"][i]] = [round(float(x), 4), round(float(y), 4)]
            g = dict(hash=h, xy=xy, approx=int(len(new)) + int(g.get("approx", 0)))
            cache.write_text(json.dumps(g))
            _G.clear(); _G.update(g)
            return g
    from sklearn.decomposition import PCA
    from sklearn.manifold import TSNE
    X = PCA(50, random_state=0).fit_transform(m["E"])
    Y = TSNE(2, perplexity=35, init="pca", random_state=0, max_iter=1000).fit_transform(X)
    Y -= Y.min(0)
    Y /= Y.max(0) + 1e-9
    g = dict(hash=h, xy={p: [round(float(a), 4), round(float(b), 4)] for p, (a, b) in zip(m["paths"], Y)})
    cache.write_text(json.dumps(g))
    _G.clear(); _G.update(g)
    return g
