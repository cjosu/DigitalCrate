"""Mashup, the stem mixer: drums, bass, vocals and "other" from different songs, on one tempo and key (docs/plans/stems.md).

    prepare(n_random)             the library pass: separate songs and keep their stems + what the mixer needs to know
    library()                     {track_id: meta}
    render(track, stem, bar0, n, bpm, semis)   -> a cached WAV of those bars, exactly n bars long at bpm
    pick(stem, state)             a part for a slot that fits what's playing (scored, drawn with some randomness)
    info(state)                   the key shift of each slot and how well the pitched parts fit together
    log(kind, state, stem)        what you did with a combination; weights() learns from it

A part is (track, stem, bar0, n, k): n mixer bars of one stem starting at the song's bar bar0. k is how many of the
song's bars fill one mixer bar: 1 normally, 2 when the song is about twice the mixer's tempo (played "half-time": two
of its bars per bar), 0.5 when it's about half (one of its bars over two). state is what the mixer is playing:
{bpm, key, slots: {slot id: {stem, track, bar0, n, k, off}}} (off: your own semitone offset on top of the key
shift). There can be any number of slots, several of one stem; a slot without "stem" is the stem its id names.
"""
import hashlib
import json
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

import numpy as np

from . import config as C
from .db import connect

DIR = C.DATA_DIR / "stems"
CACHE = DIR / "cache"
PEAK_RATE = 400
STEMS = ("drums", "bass", "vocals", "other")
PITCHED = ("bass", "vocals", "other")
NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
STRETCH = {"drums": (0.8, 1.25), "bass": (0.7, 1.4), "vocals": (0.75, 1.33), "other": (0.7, 1.4)}  # src bpm / bpm
# the score of a candidate part: w . [active, -|log stretch| (and a little for half/double time), -|semitones|,
# harmony fit, like - dislike sound, how still its own harmony is (1 = one chord)]
FEATURES = ["active", "stretch", "shift", "fit", "sound", "still"]
W0 = np.array([1.0, 4.0, 0.25, 3.0, 2.0, 1.0])
MULTS = (1, 2, 0.5)


# ---------------------------------------------------------------- the library

def _meta_path(tid):
    return DIR / f"t{tid}" / "meta.json"


_LIB = {"at": 0, "n": -1, "lib": {}}


SILENT_DB = -30.0   # a stem this far below its song's loudest stem isn't really there (the "drums" of a horn trio)
TARGET_RMS = 0.08   # every rendered part is brought to this loudness (about -22 dBFS), like sketchpad lanes


def _levels(tid, m):
    """Each stem's loudness (dBFS, the RMS of its loudest bars); stems that are all but silent in the song are
    dropped from what the mixer offers. Worked out once per song and kept in its meta."""
    import soundfile as sf
    lv = {}
    for k in STEMS:
        f = DIR / f"t{tid}" / f"{k}.flac"
        if not f.exists():
            continue
        y, sr = sf.read(str(f), dtype="float32", always_2d=True)
        mono = y.mean(1)
        e = (np.array(m["bars"]) * sr).astype(int)
        rms = np.array([np.sqrt(np.mean(mono[a:b] ** 2) + 1e-12) for a, b in zip(e[:-1], e[1:]) if b > a])
        lv[k] = round(float(20 * np.log10(np.quantile(rms, 0.9) + 1e-9)), 1) if len(rms) else -120.0
    top = max(lv.values()) if lv else 0.0
    m["level"] = lv
    m["stems"] = [k for k in m["stems"] if lv.get(k, -120) >= top + SILENT_DB and lv.get(k, -120) > -55]
    _meta_path(tid).write_text(json.dumps(m))
    return m


def library():
    """Every prepared song's meta, by track id (re-read when a song is added)."""
    files = sorted(DIR.glob("t*/meta.json")) if DIR.exists() else []
    if len(files) != _LIB["n"]:
        lib = {}
        for f in files:
            try:
                m = json.loads(f.read_text())
                if "level" not in m:  # prepared before levels were kept
                    m = _levels(int(m["track"]), m)
                lib[int(m["track"])] = m
            except Exception:
                pass
        _LIB.update(n=len(files), lib=lib)
    return _LIB["lib"]


def prepare_track(con, row, separate=True):
    """Separate one song and keep its stems (FLAC) and meta. Returns the meta, or None if it can't be used (no steady
    4/4 found: nothing to line up)."""
    import librosa
    import soundfile as sf
    from . import models
    from .analyze import SourceFeat, bars, track_tempo_key
    from .audio import decode, to_mono48
    from .policy import classify_track
    y = decode(row["path"])
    tk = track_tempo_key(y)
    bt, _ = bars(tk, y, SourceFeat(y))
    bt = np.asarray(bt, float)
    if not tk["tempo_ok"] or len(bt) < 17:
        return None
    if separate:
        st = models.separate(y)
    else:  # tests: no separator, rough stand-ins from the mix
        h, p = librosa.effects.hpss(y.mean(0))
        st = dict(drums=np.stack([p, p]), bass=np.stack([h, h]) * 0.5, vocals=np.stack([h, h]) * 0.5, other=np.stack([h, h]))
    d = DIR / f"t{row['id']}"
    d.mkdir(parents=True, exist_ok=True)
    nb = len(bt) - 1
    edges = (bt * C.SR).astype(int)
    act, emb = {}, {}
    cl = models.clap()
    for k in STEMS:
        s = np.clip(st[k], -1, 1).astype(np.float32)
        sf.write(str(d / f"{k}.flac"), s.T, C.SR, format="FLAC", subtype="PCM_16")
        m = s.mean(0)
        rms = np.array([np.sqrt(np.mean(m[edges[b]:edges[b + 1]] ** 2) + 1e-12) for b in range(nb)])
        ref = np.quantile(rms, 0.9) + 1e-9
        act[k] = np.clip(rms / ref, 0, 1).round(3).tolist()
        b0 = int(np.argmax(np.convolve(rms, np.ones(4), "valid"))) if nb >= 4 else 0  # its busiest 4 bars
        seg = m[edges[b0]:edges[min(nb, b0 + 4)]][:C.SR * 10]
        emb[k] = cl.embed_audio([to_mono48(seg)])[0].astype(np.float16) if len(seg) > C.SR else None
    harm = (st["bass"] + st["vocals"] + st["other"]).mean(0)
    hop = 2048
    cq = librosa.feature.chroma_cqt(y=harm, sr=C.SR, hop_length=hop)
    chroma = []
    for b in range(nb):
        seg = cq[:, edges[b] // hop:max(edges[b] // hop + 1, edges[b + 1] // hop)].mean(1)
        chroma.append((seg / (np.linalg.norm(seg) + 1e-9)).round(3).tolist())
    np.save(d / "emb.npy", np.stack([emb[k] if emb[k] is not None else np.zeros(512, np.float16) for k in STEMS]))
    policy = row["policy"] or classify_track(row["artist"], row["genre"], row["path"])
    meta = dict(track=row["id"], artist=row["artist"] or "", title=row["title"] or "", bpm=round(float(tk["bpm"]), 2),
                pc=int(tk["pc"]), scale=tk["scale"], camelot=tk["camelot"], bars=bt.round(4).tolist(), act=act,
                chroma=chroma, stems=["vocals"] if policy == "vocals_only" else list(STEMS), separated=bool(separate))
    return _levels(row["id"], meta)


def choose(con, n_random=40):
    """Songs to prepare: the sources of your favorites first, then random mined songs. Never reference-only artists."""
    have = set(library())
    ok = "status='done' AND COALESCE(policy,'source') != 'reference' AND tempo_ok=1"
    fav = [r[0] for r in con.execute(f"""SELECT DISTINCT s.track_id FROM favorites f JOIN samples s ON s.path = f.path
                                        JOIN tracks t ON t.id = s.track_id WHERE {ok.replace('status', 't.status')}""")]
    rnd = [r[0] for r in con.execute(f"SELECT id FROM tracks WHERE {ok} AND id IN (SELECT track_id FROM samples) "
                                     "ORDER BY random() LIMIT ?", (n_random * 3,))]
    out = [t for t in fav if t not in have]
    out += [t for t in rnd if t not in have and t not in set(out)][:n_random]
    return out


def prepare(n_random=40, limit=None, separate=True):
    from .memguard import breathe
    con = connect()
    ids = choose(con, n_random)
    ids = ids[:limit] if limit else ids
    print(f"TASK preparing stems of {len(ids)} songs for Mashup", flush=True)
    done = 0
    for k, tid in enumerate(ids, 1):
        breathe()
        row = con.execute("SELECT * FROM tracks WHERE id=?", (tid,)).fetchone()
        try:
            m = prepare_track(con, row, separate)
            done += m is not None
            if m is None:
                print(f"    {row['artist']} - {row['title']}: no steady 4/4, skipped", flush=True)
        except Exception as e:
            print(f"    {row['artist']} - {row['title']}: {str(e)[:100]}", flush=True)
        print(f"stems: {k}/{len(ids)} [{done} ready]", flush=True)
    print(f"TASK DONE {done} songs added to Mashup ({len(library())} in all)", flush=True)


# ---------------------------------------------------------------- rendering a part

def src_bars(n, k):
    """How many of the song's bars a part of n mixer bars takes."""
    return max(1, int(n * k + 0.5))


@contextmanager
def _cache_output(out):
    """Publish completed audio and picture files even when requests overlap."""
    with tempfile.NamedTemporaryFile(dir=out.parent, suffix=out.suffix, delete=False) as tmp:
        path = Path(tmp.name)
    try:
        yield path
        path.replace(out)
    finally:
        path.unlink(missing_ok=True)


def render(track, stem, bar0, n, bpm, semis=0.0, k=1, *, legacy=False):
    """n mixer bars of a stem from the song's bar bar0 (n * k of its bars), as a WAV exactly n bars long at bpm,
    shifted by semis. Legacy saves retain the source span they played before track editing. -> path"""
    import soundfile as sf
    from .stretch import signalsmith
    track, requested = int(track), int(bar0)
    m = library()[track]
    semis = round(float(semis), 2) or 0.0
    bt = m["bars"]
    n, k = max(1, int(n)), float(k or 1)
    nb = len(bt) - 1
    old_ns = min(max(1, round(n * k)), max(1, nb - 1))
    ns = old_ns if legacy else min(src_bars(n, k), nb)
    bar0 = max(0, min(requested, nb - ns))

    def cached(start, pitch, version):
        key = f"{track}|{stem}|{start}|{n}|{k}|{float(bpm):.2f}|{pitch}|{version}"
        return CACHE / f"{hashlib.sha1(key.encode()).hexdigest()[:16]}.wav"

    old_geometry = legacy and ns != min(src_bars(n, k), nb)
    out = cached(bar0, f"{semis:.2f}", "v4-legacy" if old_geometry else "v4")
    if out.exists():
        return out
    source = DIR / f"t{track}" / f"{stem}.flac"
    # A prepared stem may have vanished while its previously rendered loop is still playable.
    if (legacy or (ns == old_ns and not source.exists())) and semis.is_integer() and (stem != "drums" or semis == 0):
        old = cached(bar0, int(semis), "v3")
        if old.is_file():
            return old
    CACHE.mkdir(parents=True, exist_ok=True)
    a, b = int(bt[bar0] * C.SR), int(bt[bar0 + ns] * C.SR)
    y, _ = sf.read(str(source), start=a, frames=b - a, dtype="float32", always_2d=True)
    y = y.T
    N = int(round(n * 240.0 / float(bpm) * C.SR))
    if semis or abs(N / max(1, y.shape[1]) - 1) > 1e-3:
        y = signalsmith(y, semis, N / max(1, y.shape[1]))
    if y.shape[1] >= N:
        y = y[:, :N]
    else:
        y = np.pad(y, ((0, 0), (0, N - y.shape[1])))
    rms, peak = float(np.sqrt(np.mean(y ** 2) + 1e-12)), float(np.abs(y).max() + 1e-9)
    y = y * min(TARGET_RMS / rms, 0.9 / peak, 60.0)  # equally loud parts: a quiet recording isn't lost under a loud one
    f = int(0.002 * C.SR)  # 2 ms in and out: the loop point never clicks
    ramp = np.linspace(0, 1, f, dtype=np.float32)
    y[:, :f] *= ramp
    y[:, -f:] *= ramp[::-1]
    with _cache_output(out) as tmp:
        sf.write(str(tmp), y.T, C.SR, subtype="PCM_16")
    return out


def peaks(track, stem):
    """The whole stem's waveform, one normalized peak byte per 1/400 second."""
    import soundfile as sf

    track = int(track)
    m = library()[track]
    if stem not in STEMS:
        raise KeyError(stem)
    source = DIR / f"t{track}" / f"{stem}.flac"
    out = source.with_suffix(".pk")
    modified = source.stat().st_mtime_ns
    with sf.SoundFile(source) as audio:
        sr = audio.samplerate
        dur = audio.frames / sr
        n = (audio.frames * PEAK_RATE + sr - 1) // sr
        try:
            cached = out.stat()
        except FileNotFoundError:
            cached = None
        if not cached or cached.st_size != n or cached.st_mtime_ns < modified:
            peak = np.empty(n, dtype=np.float32)
            starts = np.arange(PEAK_RATE) * sr // PEAK_RATE
            for i, block in enumerate(audio.blocks(blocksize=sr, dtype="float32", always_2d=True)):
                values = np.maximum.reduceat(np.abs(block.mean(axis=1)), starts[starts < len(block)])
                offset = i * PEAK_RATE
                peak[offset:offset + len(values)] = values
            scale = (np.percentile(peak, 99.9) or peak.max()) if n else 0
            raw = (np.clip(peak / scale, 0, 1) * 255).astype(np.uint8) if scale else np.zeros(n, dtype=np.uint8)
            with _cache_output(out) as tmp:
                tmp.write_bytes(raw.tobytes())
    return dict(path=out, rate=PEAK_RATE, n=n, dur=dur, bars=m["bars"])


def sub_share(path):
    """The share of a rendered part's energy below 100 Hz: near 1 for a pure sub-bass, which small speakers can't
    play (it looks loud and sounds silent on a laptop)."""
    import soundfile as sf
    y, sr = sf.read(str(path), dtype="float32", always_2d=True)
    m = y.mean(1)
    S = np.abs(np.fft.rfft(m)) ** 2
    f = np.fft.rfftfreq(len(m), 1 / sr)
    return round(float(S[f < 100].sum() / (S.sum() + 1e-12)), 3)


# ---------------------------------------------------------------- harmony

def parse_key(key):
    """'Fm' / 'F#' / 'A#m' -> (pitch class, 'minor' | 'major'), or None."""
    if not key:
        return None
    k = key.strip()
    minor = k.endswith("m")
    name = k[:-1] if minor else k
    flats = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}
    name = flats.get(name, name)
    return (NOTES.index(name), "minor" if minor else "major") if name in NOTES else None


def key_semis(m, target):
    """The smallest shift that brings a song's key to target (pc, scale); relative major / minor count as the same."""
    if not target:
        return 0
    tpc, tsc = target
    if m["scale"] != tsc:
        tpc = (tpc + 9) % 12 if m["scale"] == "minor" else (tpc + 3) % 12
    return ((tpc - m["pc"] + 6) % 12) - 6


def _role(sid, p):
    """The stem a slot plays (older states keyed slots by stem and had no "stem")."""
    return (p or {}).get("stem") or sid


def _parts(state, lib=None):
    """[(slot id, stem, part)] of the slots that hold a prepared song's part."""
    lib = library() if lib is None else lib
    return [(sid, _role(sid, p), p) for sid, p in (state.get("slots") or {}).items()
            if p and p.get("track") is not None and int(p["track"]) in lib]


def target_key(state, skip=None):
    """The mixer's key: the one you set, else the key of the first pitched slot playing (other, bass, vocals)."""
    k = parse_key(state.get("key"))
    if k:
        return k
    lib = library()
    parts = _parts(state, lib)
    for want in ("other", "bass", "vocals"):  # skip: a slot id that is being replaced
        for sid, stem, p in parts:
            if stem == want and sid != skip:
                m = lib[int(p["track"])]
                return ((m["pc"] + int(p.get("off") or 0)) % 12, m["scale"])
    return None


def _chroma(m, bar0, n, semis, k=1):
    """The part's harmony per mixer bar: the song's per-bar chromas, paired up (k = 2) or repeated (k = 0.5)."""
    c = np.array(m["chroma"][bar0:bar0 + src_bars(n, k)], float)
    if not len(c):
        return c
    if k == 2:
        c = np.array([c[i:i + 2].mean(0) for i in range(0, len(c), 2)])
        c /= np.linalg.norm(c, axis=1, keepdims=True) + 1e-9
    elif k == 0.5:
        c = np.repeat(c, 2, axis=0)[:n]
    return np.roll(c, semis, axis=1)


def still(m, bar0, n, k=1):
    """How still the part's own harmony is: each bar's chroma against the part's mean (1 = one chord throughout)."""
    c = _chroma(m, bar0, n, 0, k)
    if len(c) < 2:
        return 1.0
    mean = c.mean(0)
    mean /= np.linalg.norm(mean) + 1e-9
    return float(np.mean(c @ mean))


def fit(a, b):
    """How well two parts' harmony agrees, 0..1: the mean cosine of their per-bar chromas after transposition, each
    looped to a common length. a, b: (meta, bar0, n, semis[, k])."""
    ca, cb = _chroma(*a), _chroma(*b)
    if not len(ca) or not len(cb):
        return 0.0
    L = int(np.lcm(len(ca), len(cb)))
    L = min(L, 16)
    ia, ib = np.arange(L) % len(ca), np.arange(L) % len(cb)
    return float(np.mean(np.sum(ca[ia] * cb[ib], axis=1)))


def _semis(state, stem, part, lib, target=None):
    off = int(part.get("off") or 0)
    if stem == "drums":
        return off
    return key_semis(lib[int(part["track"])], target or target_key(state)) + off


def info(state):
    """Per slot: the semitones it is shifted by (key shift + your offset). And the fit of the pitched parts playing."""
    lib, tk = library(), target_key(state)
    out, parts = {}, []
    for sid, s, p in _parts(state, lib):
        m = lib[int(p["track"])]
        sm = _semis(state, s, p, lib, tk)
        out[sid] = dict(semis=sm, src_bpm=m["bpm"], key=NOTES[m["pc"]] + ("m" if m["scale"] == "minor" else ""))
        if s in PITCHED:
            parts.append((m, int(p["bar0"]), int(p["n"]), sm, float(p.get("k") or 1)))
    fits = [fit(parts[i], parts[j]) for i in range(len(parts)) for j in range(i + 1, len(parts))]
    return dict(slots=out, fit=round(float(np.mean(fits)), 3) if fits else None,
                key=(NOTES[tk[0]] + ("m" if tk[1] == "minor" else "")) if tk else None)


# ---------------------------------------------------------------- learning what you like

def _db():
    con = connect()
    con.execute("""CREATE TABLE IF NOT EXISTS stem_events (ts REAL, kind TEXT, stem TEXT, track INTEGER, bar0 INTEGER,
                   n INTEGER, x TEXT, y INTEGER, w REAL)""")
    return con


_EMB = {}


def _emb(tid, stem):
    if tid not in _EMB:
        f = DIR / f"t{tid}" / "emb.npy"
        _EMB[tid] = np.load(f).astype(np.float32) if f.exists() else np.zeros((4, 512), np.float32)
    e = _EMB[tid][STEMS.index(stem)]
    return e / (np.linalg.norm(e) + 1e-9)


def _taste(con):
    """Per stem: the centre of the sounds you liked and of those you didn't (weighted), from the events."""
    acc = {}
    for r in con.execute("SELECT stem, track, y, w FROM stem_events"):
        try:
            e = _emb(r["track"], r["stem"])
        except Exception:
            continue
        d = acc.setdefault(r["stem"], [np.zeros(512), np.zeros(512)])
        d[1 if r["y"] else 0] += r["w"] * e
    return {s: tuple(v / (np.linalg.norm(v) + 1e-9) if np.linalg.norm(v) else None for v in d) for s, d in acc.items()}


def weights(con=None):
    """(weights, how many ratings they're learned from). The starting guesses until there are a dozen ratings, then a
    ridge logistic regression pulled toward the guesses (so a few ratings nudge, many decide)."""
    con = con or _db()
    rows = con.execute("SELECT x, y, w FROM stem_events WHERE x IS NOT NULL").fetchall()
    if len(rows) < 12:
        return W0.copy(), len(rows)
    X = np.array([(json.loads(r["x"]) + [0.0] * len(W0))[:len(W0)] for r in rows], float)  # older rows: fewer features
    y = np.array([r["y"] for r in rows], float)
    sw = np.array([r["w"] for r in rows], float)
    w, b, lam = W0.copy(), 0.0, 2.0
    for _ in range(400):
        p = 1 / (1 + np.exp(-(X @ w + b)))
        g = X.T @ (sw * (p - y)) / sw.sum() + lam * (w - W0) / len(rows)
        w -= 0.5 * g
        b -= 0.5 * float((sw * (p - y)).sum() / sw.sum())
    return np.maximum(w, 0), len(rows)  # every feature is "more is better": a negative weight would be noise


def best_k(m, bpm, stem):
    """How the song's bars map onto the mixer's (k of its bars per mixer bar): the mapping needing the least stretch.
    -> (k, ratio) or None when no mapping is within what the stem stretches well."""
    lo, hi = STRETCH[stem]
    opts = [(abs(np.log(m["bpm"] / (float(bpm) * k))), k) for k in MULTS]
    d, k = min(opts)
    r = m["bpm"] / (float(bpm) * k)
    return (k, r) if lo <= r <= hi else None


def features(stem, m, bar0, n, state, lib, taste, target, k=1, slot=None):
    """[active, -|log stretch|, -|semitones|, harmony fit, like - dislike sound, still] of a candidate part here."""
    ns = src_bars(n, k)
    act = float(np.mean(m["act"][stem][bar0:bar0 + ns]))
    ratio = m["bpm"] / (float(state.get("bpm") or m["bpm"]) * k)
    semis = 0 if stem == "drums" else key_semis(m, target)
    fits = []
    if stem in PITCHED:
        for sid, s, p in _parts(state, lib):
            if sid != slot and s in PITCHED:
                o = lib[int(p["track"])]
                fits.append(fit((m, bar0, n, semis, k), (o, int(p["bar0"]), int(p["n"]),
                                                        _semis(state, s, p, lib, target), float(p.get("k") or 1))))
    like, dis = taste.get(stem, (None, None))[::-1] if stem in taste else (None, None)
    e = _emb(m["track"], stem)
    snd = (float(e @ like) if like is not None else 0.0) - (float(e @ dis) if dis is not None else 0.0)
    st = still(m, bar0, n, k) if stem in ("bass", "other") else 0.5  # a moving vocal line is fine; drums have none
    x = [act, -abs(float(np.log(ratio))) - (0.05 if k != 1 else 0.0), -abs(semis), float(np.mean(fits)) if fits else 0.5,
         snd, st]
    return x, semis, ratio


def _candidates(stem, state, lib, taste, target, w, n, skip, only=None, any_tempo=False, slot=None, per=4):
    """Scored candidate parts: per song its four most active stretches (on 4-bar phrases), each also tried starting
    1-3 bars later when there's harmony to fit (the chords may line up better a bar or two on)."""
    ctx = stem in PITCHED and any(sid != slot and s_ in PITCHED for sid, s_, _ in _parts(state, lib))
    cands = []
    for tid, m in lib.items():
        if stem not in m["stems"] or tid in skip or (only is not None and tid != only):
            continue
        kr = best_k(m, state.get("bpm") or m["bpm"], stem)
        if kr is None:
            if not any_tempo:
                continue
            kr = min(((abs(np.log(m["bpm"] / (float(state["bpm"]) * k))), k) for k in MULTS))[1], None
        k = kr[0]
        ns, nb = src_bars(n, k), len(m["bars"]) - 1
        if ns > nb:
            continue
        step = 4 if ns >= 4 else ns
        wins = [(float(np.mean(m["act"][stem][b:b + ns])), b) for b in range(0, nb - ns + 1, step)]
        for a, b in sorted(wins, reverse=True)[:per]:
            if a < 0.45 and only is None:
                continue
            best = None
            for sh in (range(0, min(4, step)) if ctx else (0,)):
                if b + sh + ns > nb:
                    break
                x, semis, _ = features(stem, m, b + sh, n, state, lib, taste, target, k, slot)
                sc = float(w @ np.array(x)) - 0.02 * sh  # the phrase start, unless a later bar clearly fits better
                if best is None or sc > best[0]:
                    best = (sc, tid, b + sh, semis, x, k)
            if best and not (stem == "vocals" and abs(best[3]) > 4 and only is None):
                cands.append(best)
    return cands


def pick(stem, state, avoid=(), n=None, rng=None, track=None, slot=None):
    """A part of this stem for a slot (slot: its id; the stem's name when left out): scored against what the other
    slots play, drawn from the best with some randomness. track: from this song (you chose it): its best-fitting
    bars, whatever its tempo."""
    slot = slot or stem
    rng = rng or np.random.default_rng()
    lib, con = library(), _db()
    w, n_rated = weights(con)
    taste = _taste(con)
    cur = (state.get("slots") or {}).get(slot) or {}
    n = int(n or cur.get("n") or 4)
    target = target_key(state, skip=slot)
    if track is not None:
        cands = _candidates(stem, state, lib, taste, target, w, n, set(), only=int(track), any_tempo=True, slot=slot)
    else:
        # a part from a song that's already playing in another slot wouldn't be recombining: only if nothing else fits
        playing = {int(p["track"]) for sid, _, p in _parts(state, lib) if sid != slot}
        cands = _candidates(stem, state, lib, taste, target, w, n, set(avoid) | playing | {cur.get("track")}, slot=slot) \
            or _candidates(stem, state, lib, taste, target, w, n, {cur.get("track")}, slot=slot)
    if not cands:
        return None
    cands.sort(key=lambda c: -c[0])
    if track is not None:
        k_ = 0
        top = cands
    else:
        top = cands[:max(6, len(cands) // 8)]
        s = np.array([c[0] for c in top])
        p = np.exp((s - s.max()) / 0.35)
        k_ = int(rng.choice(len(top), p=p / p.sum()))
    sc, tid, b, semis, x, k = top[k_]
    m = lib[tid]
    return dict(stem=stem, track=tid, bar0=b, n=n, k=k, off=0, artist=m["artist"], title=m["title"], semis=semis,
                bars=len(m["bars"]) - 1, why=dict(zip(FEATURES, [round(float(v), 3) for v in x])), score=round(sc, 3),
                rated=n_rated, of=len(cands))


def alts(state, slot):
    """Other stretches of the same stem in the same song as the slot's part, best-fitting first (up to 8, the part
    playing among them): for stepping through a song's takes of a part."""
    lib, con = library(), _db()
    cur = (state.get("slots") or {}).get(slot) or {}
    if cur.get("track") is None or int(cur["track"]) not in lib:
        return []
    stem, tid, n = _role(slot, cur), int(cur["track"]), int(cur.get("n") or 4)
    w, _ = weights(con)
    cands = _candidates(stem, state, lib, _taste(con), target_key(state, skip=slot), w, n, set(), only=tid,
                        any_tempo=True, slot=slot, per=8)
    cands.sort(key=lambda c: -c[0])
    m = lib[tid]
    out = [dict(stem=stem, track=tid, bar0=b, n=n, k=k, semis=semis, artist=m["artist"], title=m["title"],
                bars=len(m["bars"]) - 1, why=dict(zip(FEATURES, [round(float(v), 3) for v in x])), score=round(sc, 3))
           for sc, _, b, semis, x, k in cands]
    if not any(o["bar0"] == int(cur["bar0"]) for o in out):
        out.insert(0, dict(stem=stem, track=tid, bar0=int(cur["bar0"]), n=n, k=float(cur.get("k") or 1), artist=m["artist"],
                           title=m["title"], bars=len(m["bars"]) - 1))
    return out


def log(kind, state, stem=None):
    """What you did. like / dislike / save: the whole combination (every slot). reroll: the slot's part thrown out
    within a few seconds (weak no). remove: you took it out. kept: it played a good while, or you locked it (weak yes).
    snap: a snapshot was taken with this part in it (weak yes)."""
    y, wgt = {"like": (1, 1.0), "dislike": (0, 1.0), "reroll": (0, 0.4), "kept": (1, 0.4), "lock": (1, 0.6),
              "save": (1, 1.2), "remove": (0, 0.6), "snap": (1, 0.6)}[kind]
    con, lib = _db(), library()
    taste, target = _taste(con), target_key(state)
    n = 0
    for sid, s, p in _parts(state, lib):  # stem: here a slot id (or, in older calls, the stem itself)
        if stem and sid != stem:
            continue
        x, _, _ = features(s, lib[int(p["track"])], int(p["bar0"]), int(p["n"]), state, lib, taste, target,
                           float(p.get("k") or 1), sid)
        con.execute("INSERT INTO stem_events VALUES (?,?,?,?,?,?,?,?,?)",
                    (time.time(), kind, s, int(p["track"]), int(p["bar0"]), int(p["n"]), json.dumps(x), y, wgt))
        n += 1
    con.commit()
    return n


# ---------------------------------------------------------------- one-shots
# A one-shot slot plays a library sample (a vocal chop, a short phrase, a stab) at chosen steps of a cycle of bars,
# instead of looping a stem. The sample is shifted to the mixer's key by the browser (the conform endpoint), so here
# it only has to be chosen: by how well its notes sit on the chords of some bar, and by your taste model's score.

_OS = {"n": -1}


def _oneshots(con):
    n = con.execute("SELECT COUNT(*) FROM samples").fetchone()[0]
    if _OS["n"] != n:
        rows = con.execute(r"""SELECT s.id, s.path, s.category, s.subtype, s.kind, s.dur, s.key, s.scale, s.key_from,
                               s.chroma, t.artist, t.title FROM samples s JOIN tracks t ON t.id = s.track_id
                               WHERE s.parent_id IS NULL AND s.path NOT LIKE '\_Reference%' ESCAPE '\'
                               AND s.chroma IS NOT NULL AND (s.kind = 'oneshot'
                               OR (s.category IN ('Vocals', 'Vocal Atmospheres') AND s.dur <= 8))""").fetchall()
        ch = np.array([json.loads(r["chroma"]) for r in rows], float).reshape(len(rows), 12)
        ch /= np.linalg.norm(ch, axis=1, keepdims=True) + 1e-9
        _OS.update(n=n, rows=[dict(r) for r in rows], ch=ch)
    return _OS


def cycle_harmony(state, n, lib=None):
    """The harmony the pitched slots make in each bar of an n-bar cycle: (n, 12) unit chromas, or None with none."""
    lib = library() if lib is None else lib
    target = target_key(state)
    H = np.zeros((n, 12))
    for sid, stem, p in _parts(state, lib):
        if stem in PITCHED:
            c = _chroma(lib[int(p["track"])], int(p["bar0"]), int(p["n"]), _semis(state, stem, p, lib, target),
                        float(p.get("k") or 1))
            if len(c):
                H += c[np.arange(n) % len(c)]
    if not H.any():
        return None
    return H / (np.linalg.norm(H, axis=1, keepdims=True) + 1e-9)


def oneshot(state, n=1, avoid=(), rng=None, path=None):
    """A library sample for a one-shot slot with a cycle of n bars: drawn from the best by fit + taste (or `path`:
    the one you chose). Comes with the bar it fits best (its first hit goes there) and its fit to every bar."""
    rng = rng or np.random.default_rng()
    con = _db()
    O = _oneshots(con)
    rows, ch = O["rows"], O["ch"]
    if not rows:
        return None
    n = max(1, int(n or 1))
    bar = 240.0 / float(state.get("bpm") or 100)
    target = target_key(state)
    semis = np.zeros(len(rows), int)
    if target:
        for i, r in enumerate(rows):
            if r["key_from"] != "none" and r["key"] in NOTES and r["category"] != "Percussion":
                semis[i] = key_semis(dict(pc=NOTES.index(r["key"]), scale=r["scale"] or "major"), target)
    H = cycle_harmony(state, n)
    if H is None:
        F = np.full((len(rows), n), 0.5)
    else:
        F = np.zeros((len(rows), n))
        for sft in np.unique(semis):
            m = semis == sft
            F[m] = np.roll(ch[m], int(sft), axis=1) @ H.T
    try:  # the taste scores as last fitted: a click never waits for a refit (that takes seconds)
        from .taste import cached_scores
        sc = cached_scores() or {}
        bad = {r[0] for r in con.execute("SELECT path FROM events WHERE type='dislike' GROUP BY path "
                                         "HAVING MAX(ts) = MAX(CASE WHEN value = 1 THEN ts END)")}
    except Exception:
        sc, bad = {}, set()
    t = np.array([sc.get(r["path"], np.nan) for r in rows], float)
    z = (t - np.nanmean(t)) / (np.nanstd(t) + 1e-9) if np.isfinite(t).any() else np.zeros(len(rows))
    z = np.clip(np.nan_to_num(z), -2, 2)  # your favorites score far above the rest: capped, or they'd be all you get
    best = F.argmax(1)
    score = 4.0 * F.max(1) + 0.35 * z
    if path is not None:
        idx = [i for i, r in enumerate(rows) if r["path"] == path]
        if not idx:
            return None
        k = idx[0]
    else:
        # the dice goes by harmony, so it leaves single drum hits out (you can still choose one yourself)
        # (shifting to the key is tape-style, so it changes the length: down a tritone is 41% longer)
        long = np.array([r["dur"] for r in rows]) * 2.0 ** (-semis / 12.0)
        ok = np.array([long[i] <= 2 * bar + 0.05 and r["path"] not in bad and r["path"] not in avoid
                       and r["category"] != "Percussion" and r["kind"] != "loop" for i, r in enumerate(rows)])  # a loop isn't a hit
        if not ok.any():
            return None
        cand = np.where(ok)[0]
        top = cand[np.argsort(-score[cand])[:40]]
        p = np.exp((score[top] - score[top].max()) / 0.35)
        k = int(rng.choice(top, p=p / p.sum()))
    r = rows[k]
    return dict(stem="oneshot", sample=r["path"], sid=r["id"], artist=r["artist"] or "", title=r["title"] or "",
                sub=r["subtype"], cat=r["category"], dur=round(float(r["dur"]), 2), n=n, steps=[int(best[k]) * 16], every=1,
                off=0, semis=int(semis[k]), key=(r["key"] + ("m" if r["scale"] == "minor" else "")) if r["key_from"] != "none" else None,
                fit=[round(float(v), 3) for v in F[k]],
                why=dict(fit=round(float(F[k].max()), 3), taste=round(float(z[k]), 2)))


# ---------------------------------------------------------------- to Ableton Live (docs/plans/mashup-ableton.md)

ROLE_CAT = dict(drums="Percussion", bass="Bass & Sub", vocals="Vocals", other="Chords & Keys", oneshot="Vocal Atmospheres")


def oneshot_warp(path, key, trim, beats, bpm, semis=0):
    """A one-shot's piece (trim: [from, to] as fractions of the sample shifted to the key) stretched to exactly
    `beats` at bpm, its pitch kept (plus `semis`, your own offset, also without changing the length). -> cached WAV.
    Stretches beyond 2.5x or under 0.4x smear: refused."""
    import soundfile as sf
    from .conform import render as conform
    from .stretch import signalsmith
    src, _ = conform(path, key=key or None)
    semis = round(float(semis), 2) or 0.0
    t = trim if trim and trim[1] - trim[0] > 0.005 else [0, 1]
    h = hashlib.sha1(f"{path}|{src.stat().st_mtime}|{key}|{t[0]:.5f}|{t[1]:.5f}|{beats}|{float(bpm):.2f}|{semis}".encode()).hexdigest()[:16]
    out = CACHE / f"os-{h}.wav"
    if out.exists():
        return out
    CACHE.mkdir(parents=True, exist_ok=True)
    y, sr = sf.read(str(src), dtype="float32", always_2d=True)
    y = y.T
    if y.shape[0] == 1:
        y = np.repeat(y, 2, 0)
    y = np.ascontiguousarray(y[:, int(t[0] * y.shape[1]):int(t[1] * y.shape[1])])
    N = int(round(float(beats) * 60.0 / float(bpm) * sr))
    ratio = N / max(1, y.shape[1])
    if not 0.4 <= ratio <= 2.5:
        raise ValueError(f"that would stretch it {ratio:.1f}x: trim it closer to the length, or choose another length")
    y = signalsmith(y, float(semis or 0), ratio)
    y = y[:, :N] if y.shape[1] >= N else np.pad(y, ((0, 0), (0, N - y.shape[1])))
    with _cache_output(out) as tmp:
        sf.write(str(tmp), y.T, sr, subtype="PCM_24")
    return out


def oneshot_loop(p, bpm, key, out):
    """A one-shot slot's pattern as a loop: its sample (shifted to the key, trimmed, at your pitch offset) at each of
    its steps, in a file exactly as long as the pattern takes to come round (cycle x every). -> beats"""
    import soundfile as sf
    from .conform import render as conform
    from .stretch import repitch
    warped = bool(p.get("warp"))
    semis = float(p.get("off") or 0) + float(p.get("ct") or 0) / 100
    src = oneshot_warp(p["sample"], key, p.get("trim"), p["warp"], bpm, semis) if warped \
        else conform(p["sample"], key=key or None)[0]
    y, sr = sf.read(str(src), dtype="float32", always_2d=True)
    y = y.T
    if y.shape[0] == 1:
        y = np.repeat(y, 2, 0)
    if sr != C.SR:
        from scipy.signal import resample_poly
        y = resample_poly(y, C.SR, sr, axis=1).astype(np.float32)
    if not warped:
        t = p.get("trim") or [0, 1]
        if t[1] - t[0] > 0.005:
            y = y[:, int(t[0] * y.shape[1]):int(t[1] * y.shape[1])]
        if semis:
            y = repitch(y, semis)  # as the mixer plays it: pitch and length together
    y = y.copy()
    for ms, tail in ((p.get("fin") or 3, False), (p.get("fout") or 3, True)):  # your fades (3 ms at least: no clicks)
        f = min(int(max(3.0, float(ms)) / 1000 * C.SR), y.shape[1] // 2)
        if f:
            ramp = np.linspace(0, 1, f, dtype=np.float32)
            if tail:
                y[:, -f:] *= ramp[::-1]
            else:
                y[:, :f] *= ramp
    n, every = int(p.get("n") or 1), int(p.get("every") or 1)
    beats = n * every * 4
    N = int(round(beats * 60.0 / float(bpm) * C.SR))
    loop = np.zeros((2, N), np.float32)
    step = 60.0 / float(bpm) / 4 * C.SR
    for st in p.get("steps") or []:
        a = int(round(st * step))
        seg = y[:, :max(0, N - a)]
        loop[:, a:a + seg.shape[1]] += seg
        if y.shape[1] > N - a:  # it rings past the end: into the start of the next time round
            tail = y[:, N - a:N - a + N]
            loop[:, :tail.shape[1]] += tail
    sf.write(str(out), np.clip(loop, -1, 1).T, C.SR, subtype="PCM_24")
    return beats


def export(name, bpm, key, sections, bars=8, reveal=True):
    """The mashup as a Live set, dry: a track per slot; the sections (the snapshots in order, or just the mixer as it
    is) laid end to end with a locator each; every part a looping clip of exactly its bars at the tempo. Parts and
    the set go to <Ableton samples>/Mashups/<name>/.

    sections: [{label, order: [slot ids], roles: {id: stem}, slots: {id: part with its mix settings}}]"""
    import shutil
    from .als import write_arrangement
    from .export import _safe
    lib = library()
    dest = C.ABLETON_SAMPLES / "Mashups" / _safe(name)
    (dest / "Parts").mkdir(parents=True, exist_ok=True)
    bars = max(1, int(bars))
    tracks, order = {}, []
    locators, n_clips = [], 0
    for si, sec in enumerate(sections):
        start = si * bars * 4
        locators.append((start, sec.get("label") or "ABCDEFGH"[si % 8]))
        slots = sec.get("slots") or {}
        state = dict(bpm=bpm, key=key, slots={i: p for i, p in slots.items() if p and p.get("track") is not None})
        inf = info(state)["slots"]
        for sid in sec.get("order") or list(slots):
            p = slots.get(sid)
            if not p or p.get("mute"):
                continue
            role = (sec.get("roles") or {}).get(sid) or p.get("stem") or sid
            if role == "oneshot":
                if not p.get("sample") or not p.get("steps"):
                    continue
                f = dest / "Parts" / (_safe(f"One-shot - {p.get('artist', '')} - {p.get('title', '')}")[:70] + f" {sid[-4:]}{si}.wav")
                beats = oneshot_loop(p, bpm, key, f)
                label = f"{p.get('artist', '')} — {p.get('title', '')} (one-shot)"
            elif p.get("track") is not None and int(p["track"]) in lib:
                m = lib[int(p["track"])]
                k, n = float(p.get("k") or 1), int(p.get("n") or 4)
                semis = (inf.get(sid) or {}).get("semis", 0) + float(p.get("ct") or 0) / 100
                legacy = bool(p.get("legacyLoop"))
                src = render(p["track"], role, p["bar0"], n, bpm, semis, k, legacy=legacy)
                b0 = int(p["bar0"])
                f = dest / "Parts" / (_safe(f"{role.capitalize()} - {m['artist']} - {m['title']}")[:64]
                                      + f" b{b0 + 1}-{b0 + src_bars(n, k)} {semis:+g}st{' legacy' if legacy else ''}.wav")
                if not f.exists():
                    shutil.copy2(src, f)
                beats = n * 4
                label = f"{m['artist']} — {m['title']} · bars {b0 + 1}–{b0 + src_bars(n, k)}"
            else:
                continue
            db = float(p.get("db") or 0)
            if sid not in tracks:
                order.append(sid)
                tracks[sid] = dict(label=role.capitalize() if role != "oneshot" else "One-shot", category=ROLE_CAT.get(role),
                                   volume=10 ** (db / 20), db=db, drums=role == "drums", clips=[], names=set())
            tr = tracks[sid]
            tr["names"].add(label.split(" · ")[0])
            tr["clips"].append(dict(file=f, start=start, end=start + bars * 4, beats=beats, gain=10 ** ((db - tr["db"]) / 20),
                                    label=label))
            n_clips += 1
    if not n_clips:
        raise ValueError("nothing to export: the mashup has no parts playing")
    out_tracks = []
    for sid in order:
        tr = tracks[sid]
        if len(tr["names"]) == 1:  # one song throughout: name the track after it
            tr["label"] = f"{tr['label']} · {next(iter(tr['names']))}"[:80]
        out_tracks.append(tr)
    als = write_arrangement(dest, _safe(name), out_tracks, float(bpm), len(sections) * bars * 4, locators)
    if reveal:
        import subprocess
        subprocess.run(["open", "-R", str(als)])
    return dict(dest=str(dest), als=als.name, tracks=len(out_tracks), clips=n_clips, sections=len(sections), bars=bars)


# ---------------------------------------------------------------- saved combinations

def _mixes(con):
    con.execute("CREATE TABLE IF NOT EXISTS stem_mixes (name TEXT PRIMARY KEY, state TEXT, "
                "updated_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    return con


def save_mix(name, state):
    con = _mixes(_db())
    con.execute("INSERT OR REPLACE INTO stem_mixes(name, state, updated_at) VALUES (?,?,datetime('now'))",
                (name, json.dumps(state)))
    con.commit()


def mixes():
    return [dict(name=r["name"], state=json.loads(r["state"]), updated_at=r["updated_at"])
            for r in _mixes(_db()).execute("SELECT * FROM stem_mixes ORDER BY updated_at DESC")]


def delete_mix(name):
    con = _mixes(_db())
    con.execute("DELETE FROM stem_mixes WHERE name=?", (name,))
    con.commit()
