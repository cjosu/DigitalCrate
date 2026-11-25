"""Sustain loops: where a pad, drone or held chord can loop seamlessly, so it holds for as long as a key is down.

    find_loop(y, sr)  -> dict(start, end, q, xf) in seconds (q: how seamless, 0..1; xf: crossfade to bake), or None
    bake(y, sr, lp)   -> the sample with the crossfade baked in, so a plain loop from start to end is seamless
    run(all=False)    the library pass: every sustained sample (pads, textures, chords, vocal atmospheres)

How: the loop stays inside the steady part of the sound (after the attack, before it fades), as long as possible.
For candidate ends near the end of that part, the waveform around the end is matched against every position earlier
on (normalised cross-correlation via FFT, so the jump back is phase-aligned to the sample), and the level and timbre
either side of the seam must agree. A near-perfect match loops as is; a good one gets a short crossfade, baked into
the file (the loop's last few ms blended with what comes just before its start) so any sampler loops it cleanly.
"""
import numpy as np

from . import config as C
from .db import connect

KEEP = ("Pads & Atmospheres", "Strings & Orchestral", "Textures & Field", "Chords & Keys", "Vocal Atmospheres")
MIN_Q = 0.55  # below this the seam is audible even with a crossfade: no loop


def _rms(y, n=2048, hop=512):
    if len(y) < n:
        return np.array([np.sqrt(np.mean(y ** 2) + 1e-12)])
    fr = np.lib.stride_tricks.sliding_window_view(y, n)[::hop]
    return np.sqrt((fr ** 2).mean(1) + 1e-12)


def _ncc(x, t):
    """Normalised cross-correlation of template t at every position of x ('valid')."""
    from scipy.signal import fftconvolve
    t = t - t.mean()
    num = fftconvolve(x, t[::-1], mode="valid")
    c = np.concatenate([[0.0], np.cumsum(x ** 2)])
    c1 = np.concatenate([[0.0], np.cumsum(x)])
    n = len(t)
    var = (c[n:] - c[:-n]) - (c1[n:] - c1[:-n]) ** 2 / n
    return num / (np.sqrt(np.maximum(var, 1e-12)) * np.linalg.norm(t) + 1e-12)


def _spec(y, a, sr, w=0.12):
    """Log-magnitude spectrum of ~120 ms around sample a (timbre either side of the seam)."""
    n = int(w * sr)
    seg = y[max(0, a - n // 2):a + n // 2]
    if len(seg) < 256:
        return None
    s = np.log1p(np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 4096))[:1024])
    return s / (np.linalg.norm(s) + 1e-9)


def seam(y, sr, lp, n=1024, hop=256):
    """How much the sound jumps at the loop point, against its usual frame-to-frame change (1 = not at all)."""
    a, b = int(lp["start"] * sr), int(lp["end"] * sr)
    yb = bake(y, sr, lp)
    seq = np.concatenate([yb[a:b]] * 3)
    if len(seq) < 4 * n:
        return 9.0
    fr = np.lib.stride_tricks.sliding_window_view(seq, n)[::hop] * np.hanning(n)
    S = np.log1p(np.abs(np.fft.rfft(fr, axis=1)))
    fl = np.sqrt((np.diff(S, axis=0) ** 2).sum(1))
    L = b - a
    at = max(fl[max(0, k - 2):k + 3].max() for k in ((L - n // 2) // hop, (2 * L - n // 2) // hop))
    return float(at / (np.median(fl) + 1e-9))


MAX_SEAM = 2.2  # a seam that jumps more than this (vs the sound's own movement) is audible: no loop


def find_loop(y, sr, min_len=0.5):
    y = np.asarray(y, np.float32)
    if y.ndim > 1:
        y = y.mean(0)
    dur = len(y) / sr
    if dur < 2 * min_len + 0.3:
        return None
    hop = 512
    env = _rms(y, hop=hop)
    mid = env[len(env) // 5: 4 * len(env) // 5]
    ref = np.median(mid) if len(mid) else np.median(env)
    if ref < 1e-4:
        return None
    on = np.where(env >= 0.5 * ref)[0]
    if not len(on):
        return None
    peak = int(np.argmax(env[:max(1, len(env) // 3)]))  # the attack: the loop starts after it settles
    t0 = max((peak + 4) * hop, int(0.15 * sr), on[0] * hop)
    t1 = min(on[-1] * hop + 2048, len(y) - int(0.05 * sr))  # before it fades
    if (t1 - t0) / sr < min_len:
        return None
    W = int(0.012 * sr)  # 12 ms either side of the seam
    best = None
    for b in np.linspace(t1 - 0.3 * (t1 - t0), t1 - W, 12).astype(int):
        lo, hi = t0, b - int(min_len * sr)
        if hi - lo < W * 2:
            continue
        T = y[b - W:b + W]
        if np.abs(T).max() < 1e-4:
            continue
        c = _ncc(y[lo - W:hi + W], T)  # c[i] matches T against y[lo - W + i : lo + W + i]: candidate start lo + i
        rb = env[min(len(env) - 1, b // hop)]
        sb = _spec(y, b, sr)
        # a few best candidates by waveform, then judged on level and timbre, longer loops preferred
        from scipy.signal import find_peaks
        pk, _ = find_peaks(c, distance=W)  # distinct candidates, not neighbours of one peak
        if not len(pk):
            continue
        top = pk[np.argpartition(-c[pk], min(10, len(pk) - 1))[:10]]
        for i in top:
            a = lo + int(i)
            ra = env[min(len(env) - 1, a // hop)]
            sa = _spec(y, a, sr)
            timb = float(sa @ sb) if sa is not None and sb is not None else 0.0
            lvl = abs(np.log((ra + 1e-9) / (rb + 1e-9)))
            length = (b - a) / sr
            s = float(c[i]) - 0.8 * lvl - 2.0 * (1 - timb) + 0.08 * min(length, 6)
            if best is None or s > best[0]:
                best = (s, a, b, float(c[i]), lvl, timb)
    if not best:
        return None
    s, a, b, c, lvl, timb = best
    q = float(np.clip(0.5 * c + 0.5 * (1 - 6 * (1 - timb)) - 0.5 * lvl, 0, 1))
    if q < MIN_Q:
        return None
    xf = 0.0 if c > 0.97 and timb > 0.97 else min(0.12, 0.2 * (b - a) / sr, a / sr * 0.9)
    lp = dict(start=round(a / sr, 5), end=round(b / sr, 5), q=round(q, 3), xf=round(float(xf), 4))
    return lp if seam(y, sr, lp) <= MAX_SEAM else None


def bake(y, sr, lp):
    """Blend the loop's last xf seconds with what comes just before its start, so jumping end -> start is seamless."""
    y = np.array(y, np.float32, copy=True)
    a, b, F = int(lp["start"] * sr), int(lp["end"] * sr), int((lp.get("xf") or 0) * sr)
    if F <= 0 or a - F < 0:
        return y
    g = np.sin(np.linspace(0, np.pi / 2, F)) ** 2  # equal-power-ish
    if y.ndim == 1:
        y[b - F:b] = y[b - F:b] * (1 - g) + y[a - F:a] * g
    else:
        y[:, b - F:b] = y[:, b - F:b] * (1 - g) + y[:, a - F:a] * g
    return y


def write_smpl(path, start, end, unity=60):
    """Add a RIFF 'smpl' chunk (one forward loop, start..end in frames, end inclusive) to a WAV file: the standard
    place samplers (Logic, Kontakt, Bitwig, hardware) read loop points from."""
    import struct
    sr = __import__("soundfile").info(str(path)).samplerate
    body = struct.pack("<9I", 0, 0, int(1e9 / sr), unity, 0, 0, 0, 1, 0)
    body += struct.pack("<6I", 0, 0, int(start), int(end), 0, 0)
    chunk = b"smpl" + struct.pack("<I", len(body)) + body
    with open(path, "r+b") as f:
        data = f.read()
        if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
            raise ValueError("not a WAV file")
        data = data + chunk
        data = data[:4] + struct.pack("<I", len(data) - 8) + data[8:]
        f.seek(0)
        f.write(data)
        f.truncate()


def export_loop(out, r, src_frames, root=None):
    """An exported sustained sample (conformed or not) with its loop baked in, a smpl chunk, and a Simpler preset
    next to it. r: the sample's row (loop_start / loop_end / loop_xf, in seconds of the original)."""
    import soundfile as sf
    from .ableton import simpler
    y, sr = sf.read(str(out), dtype="float32", always_2d=True)
    k = len(y) / max(1, src_frames)  # conformed copies are stretched or re-pitched: the loop scales with them
    lp = dict(start=r["loop_start"] * k, end=min(len(y) / sr, r["loop_end"] * k), xf=(r["loop_xf"] or 0) * k)
    if lp["end"] - lp["start"] < 0.05:
        return None
    y = bake(y.T, sr, lp).T
    sf.write(str(out), y, sr, subtype="PCM_24")
    a, b = int(lp["start"] * sr), int(lp["end"] * sr) - 1
    write_smpl(out, a, b)
    try:
        return simpler(out, out.stem[:60], out.with_suffix(".adv"), loop=(a, b), root=root)
    except FileNotFoundError:  # no Live installed: the WAV still carries its loop
        return None


def _db():
    con = connect()
    cols = {r[1] for r in con.execute("PRAGMA table_info(samples)")}
    for c in ("loop_start", "loop_end", "loop_q", "loop_xf"):
        if c not in cols:
            con.execute(f"ALTER TABLE samples ADD COLUMN {c} REAL")
    return con


def todo(con, redo=False):
    q = f"""SELECT id, path FROM samples WHERE category IN ({','.join('?' * len(KEEP))}) AND kind != 'loop'
            AND dur >= 1.5 {'' if redo else 'AND loop_q IS NULL'}"""
    return con.execute(q, KEEP).fetchall()


def run(redo=False):
    """Find sustain loops for sustained samples without one (loop_q = 0: looked, no clean loop)."""
    from .audio import decode
    con = _db()
    rows = todo(con, redo)
    print(f"TASK finding sustain loops in {len(rows)} samples", flush=True)
    found = 0
    for k, r in enumerate(rows, 1):
        f = C.LIB_ROOT / r["path"]
        try:
            lp = find_loop(decode(f).mean(0), C.SR) if f.exists() else None
        except Exception as e:
            print(f"    {r['path']}: {str(e)[:80]}", flush=True)
            lp = None
        if lp:
            found += 1
            con.execute("UPDATE samples SET loop_start=?, loop_end=?, loop_q=?, loop_xf=? WHERE id=?",
                        (lp["start"], lp["end"], lp["q"], lp["xf"], r["id"]))
        else:
            con.execute("UPDATE samples SET loop_q=0 WHERE id=?", (r["id"],))
        con.commit()  # right away: a write lock held across the next item's audio work blocks the app (saving, ratings) for minutes
        if k % 50 == 0:
            print(f"loops: {k}/{len(rows)} [{found} loopable]", flush=True)
    con.commit()
    print(f"TASK DONE {found} of {len(rows)} loop cleanly", flush=True)
