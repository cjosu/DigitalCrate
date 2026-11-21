"""Formant-aware vocal (re)tuning to a key, with deliberate imperfection.

    tune(y, key="Fm", strength=0.8, speed_ms=60, detune_cents=0, drift_cents=0, scale="key")

- pitch is tracked with pYIN, each voiced frame is pulled toward the nearest note of the scale by `strength`
  (1 = fully corrected), smoothed with a `speed_ms` time constant (0 = hard/robotic snap, 150+ = natural glide)
- `detune_cents` shifts everything a little sharp/flat (the slightly-off, wistful quality); `drift_cents`
  adds a slow wandering (tape-like, human) on top
- Rubber Band R3 applies the time-varying pitch map with formants preserved, so the voice keeps its character.
"""
import os
import subprocess
import tempfile

import numpy as np
import soundfile as sf

from . import config as C

SCALES = {"major": [0, 2, 4, 5, 7, 9, 11], "minor": [0, 2, 3, 5, 7, 8, 10],
          "pentatonic_minor": [0, 3, 5, 7, 10], "pentatonic_major": [0, 2, 4, 7, 9], "chromatic": list(range(12))}


def pitch_track(y, sr=C.SR, hop=256):
    import librosa
    from scipy.signal import resample_poly
    m = resample_poly(y.mean(0), 1, 2).astype(np.float32)   # 22.05 kHz
    f0, voiced, prob = librosa.pyin(m, fmin=70, fmax=1100, sr=sr // 2, frame_length=1024, hop_length=hop // 2 * 1)
    t = np.arange(len(f0)) * (hop // 2) / (sr // 2)
    return t, f0, voiced & (prob > 0.3)


def correction_curve(t, f0, voiced, tonic, scale, strength, speed_ms, detune_cents, drift_cents, seed=0):
    pcs = np.array(SCALES[scale])
    notes = np.array([tonic + p + 12 * o for o in range(0, 10) for p in pcs], float)
    midi = np.where(voiced, 69 + 12 * np.log2(np.maximum(f0, 1e-3) / 440), np.nan)
    raw = np.zeros_like(t)
    for i, mm in enumerate(midi):
        if np.isfinite(mm):
            raw[i] = (notes[np.argmin(np.abs(notes - mm))] - mm) * strength
    # smoothing: one-pole with time constant speed_ms; unvoiced frames relax toward 0
    dt = t[1] - t[0] if len(t) > 1 else 0.006
    a = np.exp(-dt / max(1e-4, speed_ms / 1000)) if speed_ms > 0 else 0.0
    rel = np.exp(-dt / 0.12)
    c = np.zeros_like(raw)
    prev = 0.0
    for i in range(len(raw)):
        prev = a * prev + (1 - a) * raw[i] if np.isfinite(midi[i]) else prev * rel
        c[i] = prev
    c += detune_cents / 100
    if drift_cents:
        rng = np.random.default_rng(seed)
        w = np.cumsum(rng.normal(0, 1, len(t)))
        from scipy.ndimage import gaussian_filter1d
        w = gaussian_filter1d(w, max(1, int(0.4 / dt)))
        w = (w - w.mean()) / (np.abs(w - w.mean()).max() + 1e-9)
        c += w * drift_cents / 100
    return c


def tune(y, key, strength=0.8, speed_ms=60, detune_cents=0.0, drift_cents=0.0, scale="key", seed=0,
         engine="vari"):  # tape-style won the blind tuning shootout (4.6 vs original 4.2)
    from .conform import parse_key
    tonic, mode = parse_key(key)
    sc = mode if scale == "key" else scale
    if sc in ("major", "minor") and scale == "key":
        sc = mode
    t, f0, v = pitch_track(y)
    if v.sum() < 3 and not detune_cents and not drift_cents:
        return y
    c = correction_curve(t, f0, v, tonic, sc, strength, speed_ms, detune_cents, drift_cents, seed)
    return apply_curve(y, t, c, engine)


ENGINES = ("rb_formant", "rb", "psola", "vari")


def apply_curve(y, t, c, engine="rb_formant"):
    """Apply a pitch-correction curve c (semitones at times t) to y (2, n)."""
    n = y.shape[1]
    if engine == "vari":
        z = _vari(y, t, c)
    elif engine == "psola":
        z = np.stack([_psola(ch, t, c) for ch in y]) if y.shape[0] > 1 and not np.allclose(y[0], y[1]) else \
            np.repeat(_psola(y[0], t, c)[None], 2, 0)
    else:
        z = _rb_map(y, t, c, formant=engine == "rb_formant")
    return (z[:, :n] if z.shape[1] >= n else np.pad(z, ((0, 0), (0, n - z.shape[1])))).astype(np.float32)


def _rb_map(y, t, c, formant=True):
    with tempfile.TemporaryDirectory() as td:
        a, b, pm = (os.path.join(td, n) for n in ("in.wav", "out.wav", "map.txt"))
        sf.write(a, y.T, C.SR, subtype="FLOAT")
        frames = (t * C.SR).astype(int)
        keep = np.r_[True, np.abs(np.diff(c)) > 0.002]          # thin the map
        with open(pm, "w") as fh:
            for fr, cc in zip(frames[keep], c[keep]):
                fh.write(f"{fr} {cc:.4f}\n")
        subprocess.run(["rubberband", "-3", "-q"] + (["-F"] if formant else []) + ["--pitchmap", pm, a, b],
                       check=True, capture_output=True)
        return sf.read(b, dtype="float32", always_2d=True)[0].T


def _vari(y, t, c, up=4):
    """Time-varying varispeed (tape-style): the read rate follows 2^(c/12). Corrections are small (< 1/2 semitone),
    so timing moves by a few % at most and nothing is resynthesised."""
    from scipy.signal import resample_poly
    n = y.shape[1]
    rate = 2 ** (np.interp(np.arange(n) / C.SR, t, c) / 12)
    pos = np.concatenate([[0.0], np.cumsum(rate)[:-1]])          # read position (input samples) per output sample
    pos = pos[pos < n - 1]
    Y = resample_poly(y, up, 1, axis=1)                            # 4x oversampled -> linear interp is clean
    idx = pos * up
    i0 = np.floor(idx).astype(int)
    fr = (idx - i0).astype(np.float32)
    i1 = np.minimum(i0 + 1, Y.shape[1] - 1)
    return Y[:, i0] * (1 - fr) + Y[:, i1] * fr


def _psola(x, t, c):
    """Praat's pitch-synchronous overlap-add: re-targets each glottal period, formants stay put by construction."""
    import parselmouth
    from parselmouth.praat import call
    snd = parselmouth.Sound(x.astype(np.float64), sampling_frequency=C.SR)
    man = call(snd, "To Manipulation", 0.01, 70, 1100)
    pt = call(man, "Extract pitch tier")
    npts = call(pt, "Get number of points")
    pts = [(call(pt, "Get time from index", i), call(pt, "Get value at index", i)) for i in range(1, npts + 1)]
    call(pt, "Remove points between", 0, snd.duration + 1)
    for tp, f in pts:
        call(pt, "Add point", tp, f * 2 ** (np.interp(tp, t, c) / 12))
    call([pt, man], "Replace pitch tier")
    return call(man, "Get resynthesis (overlap-add)").values[0].astype(np.float32)


def report(y, key):
    """How far the sample sits from the key, for the UI ('mostly in tune' / '+23 cents sharp' …)."""
    from .conform import parse_key
    tonic, mode = parse_key(key)
    t, f0, v = pitch_track(y)
    midi = 69 + 12 * np.log2(np.maximum(f0[v], 1e-3) / 440)
    if not len(midi):
        return dict(voiced=0)
    dev = (midi - np.round(midi)) * 100
    pcs = (np.round(midi).astype(int) - tonic) % 12
    in_key = np.isin(pcs, SCALES[mode]).mean()
    return dict(voiced=round(float(v.mean()), 2), cents=round(float(np.median(dev)), 1),
                spread=round(float(np.std(dev)), 1), in_key=round(float(in_key), 2))
