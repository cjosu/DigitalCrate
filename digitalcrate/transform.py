"""Transformations that turn raw fragments into weather: stretch, smear, freeze, phase-loop,
darken, wash, tape. Recipes chain them. Everything works on (2, n) float32 @ 44.1 kHz."""
import json
from pathlib import Path

import numpy as np
import librosa
import soundfile as sf
from scipy.signal import butter, sosfilt, fftconvolve

from . import config as C
from .audio import decode

SR = C.SR
rng = np.random.default_rng()


def _norm(y, peak=0.89):
    return y * (peak / (np.abs(y).max() + 1e-9))


# ---------------------------------------------------------------- building blocks

def smear(y, factor=3.0):
    """Phase-vocoder stretch: keeps pitch & harmony, blurs attacks."""
    return np.stack([librosa.effects.time_stretch(ch, rate=1 / factor, n_fft=4096, hop_length=512) for ch in y])


def paulstretch(y, factor=12.0, window_s=0.5):
    """Paul Nasca's extreme-stretch algorithm: windowed spectra with randomised phase."""
    win = int(window_s * SR) // 2 * 2
    half = win // 2
    w = np.hanning(win)
    hop_in = half / factor
    n_out = int(y.shape[1] * factor) + win
    out = np.zeros((2, n_out))
    pos, opos = 0.0, 0
    while int(pos) + win < y.shape[1] and opos + win < n_out:
        for c in range(2):
            mag = np.abs(np.fft.rfft(y[c, int(pos):int(pos) + win] * w))
            ph = rng.uniform(0, 2 * np.pi, len(mag))
            out[c, opos:opos + win] += np.fft.irfft(mag * np.exp(1j * ph)) * w
        pos += hop_in
        opos += half
    return out[:, :opos].astype(np.float32)


def freeze(y, at=0.5, seconds=20.0, n_fft=8192):
    """Hold the spectrum of one moment indefinitely (randomised phase each frame)."""
    i = int(at * max(0, y.shape[1] - n_fft))
    win = np.hanning(n_fft)
    mags = [np.abs(np.fft.rfft(y[c, i:i + n_fft] * win)) for c in range(2)]
    hop = n_fft // 4
    n = int(seconds * SR)
    out = np.zeros((2, n + n_fft))
    for o in range(0, n, hop):
        for c in range(2):
            ph = rng.uniform(0, 2 * np.pi, len(mags[c]))
            out[c, o:o + n_fft] += np.fft.irfft(mags[c] * np.exp(1j * ph)) * win
    return out[:, :n].astype(np.float32)


def pitch(y, semitones):
    return np.stack([librosa.effects.pitch_shift(ch, sr=SR, n_steps=semitones, n_fft=4096) for ch in y])


def lowpass(y, hz=2800, order=2):
    return sosfilt(butter(order, hz, "low", fs=SR, output="sos"), y, axis=1).astype(np.float32)


def highpass(y, hz=60, order=1):
    return sosfilt(butter(order, hz, "high", fs=SR, output="sos"), y, axis=1).astype(np.float32)


def wash(y, decay=1.6, length=6.0, mix=0.65, tone=3500):
    """Long diffuse reverb from a decaying, decorrelated noise impulse response."""
    L = int(length * SR)
    t = np.arange(L) / SR
    ir = np.stack([rng.standard_normal(L) * np.exp(-t / decay) for _ in range(2)])
    ir = lowpass(ir, tone, 1)
    wet = np.stack([fftconvolve(y[c], ir[c])[:y.shape[1] + L // 2] for c in range(2)])
    dry = np.pad(y, ((0, 0), (0, wet.shape[1] - y.shape[1])))
    return ((1 - mix) * _norm(dry) + mix * _norm(wet)).astype(np.float32)


def tape(y, drive=1.6, wow_cents=3.0, flutter_cents=1.0, hiss_db=-48, wow=None, flutter=None):
    """Saturation + realistic wow/flutter (depth in cents, a few cents like real tape) + hiss."""
    n = y.shape[1]
    t = np.arange(n) / SR
    out = y
    if wow_cents or flutter_cents:
        # delay amplitude A gives peak pitch deviation 2*pi*f*A/SR  ->  A = dev*SR/(2*pi*f)
        dev = lambda c: 2 ** (c / 1200) - 1
        fw, ff = 0.5, 6.0
        mod = (dev(wow_cents) * SR / (2 * np.pi * fw)) * np.sin(2 * np.pi * fw * t + rng.uniform(0, 6)) + \
              (dev(flutter_cents) * SR / (2 * np.pi * ff)) * np.sin(2 * np.pi * ff * t)
        idx = np.clip(np.arange(n) - mod, 0, n - 1)
        out = np.stack([np.interp(idx, np.arange(n), ch) for ch in y])
    out = np.tanh(drive * _norm(out)) / np.tanh(drive)
    hiss = lowpass(rng.standard_normal((2, n)).astype(np.float32), 9000, 1) * 10 ** (hiss_db / 20)
    return (out + hiss).astype(np.float32)


def loopify(y, xfade=1.5):
    """Make a seamless loop by crossfading the tail into the head."""
    xf = min(int(xfade * SR), y.shape[1] // 3)
    body = y[:, :-xf].copy()
    f = np.linspace(0, 1, xf, dtype=np.float32)
    body[:, :xf] = body[:, :xf] * f + y[:, -xf:] * (1 - f)
    return body


def phase_loops(y, lengths=(3.7, 5.3, 7.9), octave_layers=(0, -12, 0), seconds=32.0, xfade=0.6):
    """Layer loops of incommensurate lengths cut from the same material (Eno/Basinski/Gas-style):
    the layers drift against each other so the texture never repeats exactly."""
    n = int(seconds * SR)
    out = np.zeros((2, n), np.float32)
    for k, (L, st) in enumerate(zip(lengths, octave_layers)):
        L = min(L, y.shape[1] / SR * 0.9)
        start = int(rng.uniform(0, max(1, y.shape[1] - L * SR)))
        seg = y[:, start:start + int(L * SR)]
        if st:
            seg = pitch(seg, st)
        seg = loopify(seg, min(xfade, L / 4))
        reps = int(np.ceil(n / seg.shape[1])) + 1
        lay = np.tile(seg, reps)[:, :n]
        pan = [0.5 + 0.35 * np.sin(k * 2.1), 0.5 - 0.35 * np.sin(k * 2.1)]
        out += lay * np.array(pan, np.float32)[:, None] * (0.8 if st else 1.0)
    return out


def pulse(y, bpm=118, kick_db=-6, duck=0.35):
    """Muffled four-to-the-floor kick with the pad breathing against it."""
    n = y.shape[1]
    beat = int(60 / bpm * SR)
    t = np.arange(int(0.35 * SR)) / SR
    f = 45 + 70 * np.exp(-t * 30)
    kick = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9)
    kick = lowpass(np.stack([kick, kick]).astype(np.float32), 180, 2)[0]
    env = np.ones(n, np.float32)
    k = np.zeros(n, np.float32)
    shape = 1 - duck * np.exp(-np.arange(beat) / (0.12 * SR))
    for b in range(0, n, beat):
        e = min(b + beat, n)
        env[b:e] = shape[:e - b]
        m = min(len(kick), n - b)
        k[b:b + m] += kick[:m]
    return (_norm(y) * env + k * 10 ** (kick_db / 20)).astype(np.float32)


def vinyl(y, crackle_per_s=12, level_db=-40):
    n = y.shape[1]
    c = np.zeros((2, n), np.float32)
    pos = rng.integers(0, n, int(crackle_per_s * n / SR))
    c[:, pos] = rng.uniform(-1, 1, (2, len(pos)))
    c = highpass(c, 1500, 2)
    return (y + _norm(c) * 10 ** (level_db / 20)).astype(np.float32)


# ---------------------------------------------------------------- recipes

def r_pop(y):
    """Gas 'Pop'-style: smear, layered phase loops, darken, wash, tape."""
    s = smear(y, 3.0)
    s = phase_loops(s, lengths=(4.1, 6.3, 9.7), octave_layers=(0, -12, 0), seconds=32)
    return tape(wash(highpass(lowpass(s, 2600)), decay=1.8, mix=0.6), drive=1.5)


def r_zauberberg(y):
    """Darker, lower, foggier: octave down, heavy low-pass, long reverb, ducking pulse."""
    s = pitch(smear(y, 4.0), -12)
    s = phase_loops(s, lengths=(5.3, 7.1, 11.3), octave_layers=(0, 0, -12), seconds=32)
    s = tape(wash(highpass(lowpass(s, 1400, 2), 40), decay=2.5, mix=0.7), drive=2.0, hiss_db=-44)
    return pulse(s, bpm=112, kick_db=-4, duck=0.45)


def r_glacier(y):
    """Paulstretch to a slow-moving glacier."""
    s = paulstretch(y[:, : int(6 * SR)], factor=10.0)
    return tape(wash(lowpass(s, 4000), decay=2.0, mix=0.45), drive=1.2, hiss_db=-52)


def r_freeze(y):
    """One moment held forever, slowly breathing."""
    a = freeze(y, at=0.4, seconds=24)
    b = freeze(y, at=0.7, seconds=24)
    t = np.linspace(0, 2 * np.pi, a.shape[1])
    x = 0.5 + 0.5 * np.sin(t * 1.5)
    return wash(lowpass(a * x + b * (1 - x), 5000), decay=1.5, mix=0.4)


def r_ghost(y):
    """Burial-style vocal ghost: pitched, airy, reverb tail, crackle."""
    s = pitch(y, rng.choice([-5, -3, 3, 5]))
    s = wash(highpass(lowpass(s, 6000), 250, 2), decay=1.2, length=4, mix=0.5, tone=6000)
    return vinyl(tape(s, drive=1.3, wow=0.004, hiss_db=-50), crackle_per_s=8)


def r_micro(y):
    """Sub-second fragments looped at incommensurate lengths: the orchestra starts to pulse."""
    s = phase_loops(y, lengths=(0.43, 0.71, 1.13, 1.67), octave_layers=(0, 0, -12, 0), seconds=32, xfade=0.08)
    return tape(wash(highpass(lowpass(s, 2400), 50), decay=1.4, mix=0.55), drive=1.5)


RECIPES = {"micro": r_micro, "pop": r_pop, "zauberberg": r_zauberberg, "glacier": r_glacier, "freeze": r_freeze, "ghost": r_ghost}


def render(src_path, recipe, out_dir=None, tag=None):
    src = Path(src_path)
    y = decode(src) if src.suffix.lower() not in (".wav",) else sf.read(str(src), dtype="float32", always_2d=True)[0].T
    if y.shape[0] == 1:
        y = np.repeat(y, 2, 0)
    out = _norm(RECIPES[recipe](y.astype(np.float32)))
    fi, fo = int(0.05 * SR), int(1.5 * SR)
    out[:, :fi] *= np.linspace(0, 1, fi)
    out[:, -fo:] *= np.linspace(1, 0, fo)
    out_dir = Path(out_dir or C.LIB_ROOT / "Processed" / recipe.capitalize())
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"{recipe.capitalize()}_{tag or src.stem}.wav"
    dst = out_dir / name
    sf.write(str(dst), out.T, SR, subtype="PCM_24")
    return dst


def run(recipes, ids=(), files=(), category=None, top=10):
    from .db import connect
    con = connect()
    srcs = [(Path(f), Path(f).stem) for f in files]
    if ids:
        q = ",".join("?" * len(ids))
        for r in con.execute(f"SELECT id, path FROM samples WHERE id IN ({q})", ids):
            srcs.append((C.LIB_ROOT / r["path"], Path(r["path"]).stem))
    if category:
        for r in con.execute("""SELECT path FROM samples WHERE category=? AND path NOT LIKE '_Reference/%'
                                AND kind != 'oneshot' ORDER BY quality DESC LIMIT ?""", (category, top)):
            srcs.append((C.LIB_ROOT / r["path"], Path(r["path"]).stem))
    for s, tag in srcs:
        for rc in recipes:
            print("→", render(s, rc, tag=tag))
