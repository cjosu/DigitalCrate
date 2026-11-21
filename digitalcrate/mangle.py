"""Adaptive, generative sample manipulation.

Each source is profiled (vocal / sustained / transient / texture; length; attack density; brightness),
then a chain is *drawn at random* from technique families suited to that material, with parameters
sampled from ranges. Taste weights bias which techniques get drawn but never lock it to one sound.
Every render writes a .json sidecar with its exact chain so a good one can be reproduced.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
import librosa
import soundfile as sf
from scipy.signal import resample_poly

from . import config as C
from .audio import decode
from .transform import (smear, paulstretch, freeze, pitch, lowpass, highpass, wash, tape, loopify,
                        phase_loops, pulse, vinyl, _norm)

SR = C.SR

# How much you like each technique (edit freely; 1.0 = neutral). Seeded from your first listening:
# zauberberg > pop > freeze, micro not your usual vibe, paulstretch 'too modulated'.
TASTE = {
    "dark_phase": 3.0, "pop_phase": 2.0, "freeze": 1.3, "micro": 0.5, "paulstretch": 0.3,
    # vocals (D'Angelo session): big pitch-downs & phase-vocoder stretch sounded cheap, random chop+drop
    # terrible, reverse swell good. Now Rubber Band R3 + presence-keeping space; chops on a groove grid.
    # round 2: formant-preserved pitch-up = solid; tape wobble, pitch-down+stretch ('halloween'),
    # stretch, groove chop and heavy reverse swell = no. Fragments of phrases added (Burial-style short cuts).
    "varispeed_down": 0.0, "varispeed_up": 0.8, "formant_up": 3.0, "fragment": 2.5, "slow_stretch": 0.0,
    "chop": 0.0, "vowel_hold": 0.8, "reverse_swell": 0.7, "octave_bed": 1.0, "plain_space": 0.8,
    # gentle tuning to the vocal's own key with the tape-style engine (won the blind tuning test)
    "in_tune": 1.5,
}


def _key_after(key, semis):
    """'Fm' shifted by semis -> 'G#m' (None when the key is unknown)."""
    if not key:
        return None
    from .conform import parse_key
    from .audio import key_label
    pc, sc = parse_key(key)
    return key_label((pc + int(round(semis))) % 12, sc)


# ---------------------------------------------------------------- extra vocal techniques

def varispeed(y, semis):
    """Tape-speed change: pitch and duration move together (the classic pitched-up/down voice)."""
    ratio = 2 ** (semis / 12)
    up, down = int(round(1000 / ratio)), 1000
    return resample_poly(y, up, down, axis=1).astype(np.float32)


def _onsets(y):
    m = librosa.to_mono(y)
    on = librosa.onset.onset_detect(y=m, sr=SR, hop_length=512, backtrack=True, units="samples")
    return np.unique(np.concatenate([[0], on, [y.shape[1]]]))


def chop(y, rng, keep=(3, 7), stutter_p=0.35, reverse_p=0.2, cut_p=0.3):
    """Slice at syllables, reorder, stutter, reverse, truncate mid-word: the broken-up phrase."""
    b = _onsets(y)
    slices = [(a, e) for a, e in zip(b[:-1], b[1:]) if e - a > 0.08 * SR]
    if len(slices) < 2:
        return y
    n = int(rng.integers(keep[0], keep[1] + 1))
    out = []
    for _ in range(n):
        a, e = slices[int(rng.integers(len(slices)))]
        s = y[:, a:e].copy()
        if rng.random() < cut_p:
            s = s[:, : max(int(0.06 * SR), int(s.shape[1] * rng.uniform(0.3, 0.7)))]
        if rng.random() < reverse_p:
            s = s[:, ::-1].copy()
        f = min(int(0.006 * SR), s.shape[1] // 4)
        s[:, :f] *= np.linspace(0, 1, f)
        s[:, -f:] *= np.linspace(1, 0, f)
        reps = int(rng.integers(2, 4)) if rng.random() < stutter_p else 1
        for _ in range(reps):
            out.append(s)
        if rng.random() < 0.4:
            out.append(np.zeros((2, int(rng.uniform(0.05, 0.4) * SR)), np.float32))
    return np.concatenate(out, axis=1)


def vowel_hold(y, rng, hold=(1.5, 4.0)):
    """Find the most stable, voiced moment and hang on it, then let the phrase continue."""
    m = librosa.to_mono(y)
    S = np.abs(librosa.stft(m, n_fft=2048, hop_length=512))
    flux = np.r_[0, np.sqrt((np.diff(S, axis=1) ** 2).sum(0))]
    energy = S.sum(0)
    score = energy / (energy.max() + 1e-9) - flux / (flux.max() + 1e-9)
    i = int(np.argmax(score)) * 512
    i = min(i, max(0, y.shape[1] - 8192))
    held = freeze(y[:, max(0, i - 4096): i + 8192], at=0.5, seconds=float(rng.uniform(*hold)), n_fft=4096)
    xf = int(0.08 * SR)
    pre, post = y[:, :i], y[:, i:]
    held[:, :xf] *= np.linspace(0, 1, xf)
    held[:, -xf:] *= np.linspace(1, 0, xf)
    return np.concatenate([pre, _norm(held, np.abs(y).max()), post], axis=1)


def reverse_swell(y, rng):
    """Reversed reverb tail rising into the phrase."""
    head = y[:, : int(min(0.5, y.shape[1] / SR) * SR)][:, ::-1].copy()
    tail = wash(head, decay=float(rng.uniform(0.3, 0.6)), length=1.2, mix=1.0)[:, ::-1]
    tail = tail[:, -int(rng.uniform(0.4, 0.8) * SR):]
    return np.concatenate([_norm(tail, 0.35 * np.abs(y).max()), y], axis=1)


def _rb(y, time=1.0, semis=0.0, formant=False):
    """Rubber Band R3 engine (high-quality stretch / pitch, optional formant preservation)."""
    import subprocess, tempfile, os
    with tempfile.TemporaryDirectory() as td:
        a, b = os.path.join(td, "in.wav"), os.path.join(td, "out.wav")
        sf.write(a, y.T, SR, subtype="FLOAT")
        cmd = ["rubberband", "-3", "-q", "-t", f"{time:.4f}", "-p", f"{semis:.3f}"] + (["-F"] if formant else []) + [a, b]
        subprocess.run(cmd, check=True, capture_output=True)
        return sf.read(b, dtype="float32", always_2d=True)[0].T


GROOVES = [  # 16th-step positions over 2 bars (32 steps): syncopated, 2-step-ish
    [0, 3, 6, 10, 14, 16, 19, 22, 26], [0, 6, 10, 16, 22, 26, 28], [2, 6, 8, 14, 18, 22, 24, 30],
    [0, 3, 10, 16, 19, 26], [0, 7, 10, 13, 16, 23, 26, 29],
]


def groove_chop(y, rng, bpm=None):
    """Syllables kept in order, re-placed on a syncopated 2-bar 16th grid; some words cut short, some repeated."""
    bpm = bpm or float(rng.choice([128, 132, 136, 138, 140]))
    step = 60 / bpm / 4 * SR
    b = _onsets(y)
    sl = [(a, e) for a, e in zip(b[:-1], b[1:]) if e - a > 0.07 * SR]
    if len(sl) < 2:
        return y
    pat = GROOVES[int(rng.integers(len(GROOVES)))]
    n = int(32 * step)
    out = np.zeros((2, n + int(SR)), np.float32)
    # walk through the phrase in order, occasionally lingering on a syllable (repeat)
    k = int(rng.integers(0, max(1, len(sl) - len(pat) // 2)))
    for i, p in enumerate(pat):
        a, e = sl[k % len(sl)]
        nxt = pat[i + 1] if i + 1 < len(pat) else 32
        room = int((nxt - p) * step)
        seg = y[:, a:min(e, a + room + int(0.15 * SR))].copy()
        if rng.random() < 0.3:  # cut mid-word
            seg = seg[:, : max(int(0.05 * SR), int(seg.shape[1] * rng.uniform(0.35, 0.7)))]
        f = min(int(0.004 * SR), seg.shape[1] // 4)
        g = min(int(0.03 * SR), seg.shape[1] // 3)
        seg[:, :f] *= np.linspace(0, 1, f); seg[:, -g:] *= np.linspace(1, 0, g)
        st = int(p * step)
        out[:, st:st + seg.shape[1]] += seg[:, : out.shape[1] - st]
        if rng.random() > 0.35:
            k += 1
    return out[:, :n]


def fragment(y, rng, syl=(1, 3)):
    """A short piece of the phrase (1-3 syllables) cut at natural boundaries, with its own decay."""
    b = _onsets(y)
    sl = [(a, e) for a, e in zip(b[:-1], b[1:]) if e - a > 0.08 * SR]
    if len(sl) < 2:
        return y
    n = int(rng.integers(syl[0], syl[1] + 1))
    loud = [float(np.abs(y[:, a:e]).mean()) for a, e in sl]
    cands = [i for i in range(len(sl) - n + 1)]
    w = np.array([np.mean(loud[i:i + n]) for i in cands]) + 1e-9
    i = int(rng.choice(cands, p=w / w.sum()))
    a, e = sl[i][0], sl[i + n - 1][1]
    seg = y[:, a:min(y.shape[1], e + int(0.12 * SR))].copy()
    g = min(int(0.08 * SR), seg.shape[1] // 3)
    seg[:, -g:] *= np.linspace(1, 0, g)
    return seg


def vocal_space(y, rng):
    """Keep presence: trim lows/extreme highs only, airy pre-delayed reverb, light grit."""
    y = highpass(y, float(rng.uniform(140, 300)), 2)
    y = lowpass(y, float(rng.uniform(9000, 14000)), 1)
    pre = int(rng.uniform(0.02, 0.06) * SR)
    wet = wash(np.pad(y, ((0, 0), (pre, 0))), decay=float(rng.uniform(0.9, 2.2)), length=5.0, mix=1.0,
               tone=float(rng.uniform(5000, 9000)))
    dry = np.pad(y, ((0, 0), (0, wet.shape[1] - y.shape[1])))
    m = float(rng.uniform(0.3, 0.55))
    out = (1 - m) * _norm(dry) + m * _norm(wet)
    tag = "space"
    if rng.random() < 0.4:
        out = vinyl(tape(out, drive=1.1, wow_cents=0, flutter_cents=0, hiss_db=-58), crackle_per_s=6, level_db=-46); tag += "+crackle"
    return out.astype(np.float32), tag


def hq_vocal(sample_row, pad=1.0, engine="roformer"):
    """Re-isolate a vocal sample from its original track with MelBand RoFormer (excerpt only: fast)."""
    import tempfile, os
    from . import models
    from .db import connect
    con = connect()
    t = con.execute("SELECT path FROM tracks WHERE id=?", (sample_row["track_id"],)).fetchone()
    full = decode(t["path"])
    a = max(0, int((sample_row["start"] - pad) * SR))
    b = min(full.shape[1], int((sample_row["start"] + sample_row["dur"] + 0.25 + pad) * SR))
    with tempfile.TemporaryDirectory() as td:
        ex = os.path.join(td, "excerpt.wav")
        sf.write(ex, full[:, a:b].T, SR, subtype="PCM_24")
        v = models.roformer_vocals(ex, b - a, engine)
    lead = int(pad * SR) - int(0.03 * SR) if a > 0 else int(sample_row["start"] * SR)
    v = v[:, max(0, lead): max(0, lead) + int((sample_row["dur"] + 0.28) * SR)]
    f = int(0.004 * SR); v[:, :f] *= np.linspace(0, 1, f)
    return v


# ---------------------------------------------------------------- profiling

def profile(y, category=None):
    m = librosa.to_mono(y)
    m22 = librosa.resample(m, orig_sr=SR, target_sr=22050, res_type="soxr_qq")
    dur = len(m) / SR
    onset_rate = len(librosa.onset.onset_detect(y=m22, sr=22050)) / max(dur, 0.1)
    S = np.abs(librosa.stft(m22))
    flat = float(librosa.feature.spectral_flatness(S=S).mean())
    cent = float(librosa.feature.spectral_centroid(S=S, sr=22050).mean())
    if category in ("Vocals", "Vocal Atmospheres"):
        kind = "vocal"
    elif flat > 0.12 or category == "Textures & Field":
        kind = "texture"
    elif onset_rate > 2.5:
        kind = "transient"
    else:
        kind = "sustained"
    return dict(kind=kind, dur=dur, onset_rate=onset_rate, flatness=flat, centroid=cent)


# ---------------------------------------------------------------- generative chains

def _space(y, rng, prof, dark=None):
    """Shared 'where does it live' stage: filter, reverb, tape — parameters adapt to brightness."""
    dark = rng.random() < 0.6 if dark is None else dark
    cut = rng.uniform(1200, 2600) if dark else rng.uniform(3500, 7000)
    if prof["centroid"] < 1200:
        cut = max(cut, 2500)  # already dark: don't smother it
    y = highpass(lowpass(y, cut, 2), rng.uniform(40, 120))
    y = wash(y, decay=float(rng.uniform(0.8, 2.6)), length=float(rng.uniform(3, 7)),
             mix=float(rng.uniform(0.3, 0.7)), tone=cut * 1.3)
    if rng.random() < 0.75:
        y = tape(y, drive=float(rng.uniform(1.1, 2.0)), wow_cents=float(rng.uniform(1, 5)),
                 flutter_cents=float(rng.uniform(0.3, 1.2)), hiss_db=float(rng.uniform(-56, -44)))
    return y, ("dark" if dark else "airy")


def _vocal_core(y, rng, prof, steps):
    opts = [o for o in PLANS["vocal"] if TASTE.get(o, 1) > 0]
    if prof["dur"] < 1.0:
        opts = [o for o in opts if o not in ("fragment", "chop")]
    force = prof.get("force")
    picks = [force] if force else _draw(opts, rng)
    if force == "fragment":
        picks.append("formant_up" if rng.random() < 0.7 else "varispeed_up")
    for t in picks:
        k2 = lambda s_: f"→{_key_after(prof.get('key'), s_)}" if prof.get("key") else ""
        if t == "in_tune":            # tuned to its own key, natural glide (hard snap always lost by ear)
            if prof.get("key"):
                from .retune import tune
                if prof.get("slot", 0) % 2 == 0:
                    y = tune(y, prof["key"], strength=0.8, speed_ms=60); steps.append(f"tuned {prof['key']}")
                else:  # up a fourth = next door on the Camelot wheel, so it still fits the original's key
                    k4 = _key_after(prof["key"], 5)
                    y = tune(_rb(y, semis=5.0, formant=True), k4, strength=0.8, speed_ms=60)
                    steps.append(f"pitch+5F tuned {k4}")
            else:                     # no reliable key: fall back to the favourite pitch-up
                y = _rb(y, semis=3.0, formant=True); steps.append("pitch+3F")
        elif t == "varispeed_up":       # tape-style: pitch + speed together, formants move (androgynous)
            s_ = float([3, 2, 4, 5][prof.get("slot", int(rng.integers(4))) % 4])
            y = varispeed(y, s_); steps.append(f"tape+{s_:.0f}{k2(s_)}")
        elif t == "fragment":
            y = fragment(y, rng); steps.append("fragment")
        elif t == "formant_up":       # higher note, natural throat: same singer, higher
            ladder = [3, 5, 2, 4, 7, 1]
            s_ = float(ladder[prof.get("slot", int(rng.integers(6))) % len(ladder)])
            y = _rb(y, semis=s_, formant=True); steps.append(f"pitch+{s_:.0f}F{k2(s_)}")
        elif t == "varispeed_down":   # small drops only, formant-preserved
            s_ = float(rng.choice([-2, -3, -4]))
            y = _rb(y, semis=s_, formant=True); steps.append(f"pitch{s_:.0f}F{k2(s_)}")
        elif t == "slow_stretch":
            f = float(rng.uniform(1.3, 2.2))
            y = _rb(y, time=f); steps.append(f"stretch{f:.1f}x")
        elif t == "chop":
            y = groove_chop(y, rng); steps.append("groovechop")
        elif t == "vowel_hold":
            y = vowel_hold(y, rng); steps.append("hold")
        elif t == "reverse_swell":
            y = reverse_swell(y, rng); steps.append("revswell")
    return y


def _sustained_core(y, rng, prof, steps):
    t = prof.get("force") or _draw(["dark_phase", "pop_phase", "freeze", "micro", "paulstretch", "octave_bed",
                                    "plain_space"], rng)[0]
    if t == "dark_phase":
        f = float(rng.uniform(2.5, 4.5))
        y = pitch(smear(y, f), -12)
        L = sorted(rng.uniform(4, 12, 3).round(2))
        y = phase_loops(y, lengths=tuple(L), octave_layers=(0, 0, -12), seconds=32)
        steps += [f"smear{f:.1f}x", "oct-1", "phase" + "-".join(f"{x:g}" for x in L)]
        y, tone = _space(y, rng, prof, dark=True)
        steps.append(tone)
        if rng.random() < 0.6:
            bpm = float(rng.choice([108, 112, 116, 120, 124]))
            y = pulse(y, bpm=bpm, kick_db=float(rng.uniform(-8, -3)), duck=float(rng.uniform(0.25, 0.5)))
            steps.append(f"pulse{bpm:.0f}")
        return y
    if t == "pop_phase":
        f = float(rng.uniform(2, 3.5))
        L = sorted(rng.uniform(3, 10, 3).round(2))
        y = phase_loops(smear(y, f), lengths=tuple(L), octave_layers=(0, -12, 0), seconds=32)
        steps += [f"smear{f:.1f}x", "phase" + "-".join(f"{x:g}" for x in L)]
    elif t == "freeze":
        a, b = freeze(y, at=float(rng.uniform(0.2, 0.5)), seconds=24), freeze(y, at=float(rng.uniform(0.5, 0.9)), seconds=24)
        x = 0.5 + 0.5 * np.sin(np.linspace(0, 2 * np.pi * rng.uniform(0.7, 2), a.shape[1]))
        y = a * x + b * (1 - x); steps.append("freeze")
    elif t == "micro":
        L = sorted(rng.uniform(0.35, 1.8, 4).round(2))
        y = phase_loops(y, lengths=tuple(L), octave_layers=(0, 0, -12, 0), seconds=32, xfade=0.08)
        steps.append("micro" + "-".join(f"{x:g}" for x in L))
    elif t == "paulstretch":
        f = float(rng.uniform(3, 6))  # gentle — you found heavy stretch too modulated
        y = paulstretch(y[:, : int(6 * SR)], factor=f); steps.append(f"paul{f:.0f}x")
    elif t == "octave_bed":
        y = loopify(y + 0.7 * pitch(y, -12)); y = np.tile(y, (1, max(1, int(24 * SR / y.shape[1])))); steps.append("octbed")
    else:
        steps.append("plain")
    y, tone = _space(y, rng, prof)
    steps.append(tone)
    return y


def _transient_core(y, rng, prof, steps):
    """Piano/keys/plucks: hide the attacks first, else loops stutter."""
    t = prof.get("force") or _draw(["dark_phase", "freeze", "reverse_swell", "pop_phase"], rng)[0]
    if t == "reverse_swell":
        y = np.concatenate([y[:, ::-1], y], axis=1); steps.append("reverse")
        y = smear(y, float(rng.uniform(1.5, 3))); steps.append("smear")
        y, tone = _space(y, rng, prof); steps.append(tone)
        return y
    prof = dict(prof, force=t)
    return _sustained_core(smear(y, float(rng.uniform(2, 3))), rng, prof, steps)


def _texture_core(y, rng, prof, steps):
    s = {"vari_low": -12.0, "vari_mid": -5.0, "plain_space": 0.0}.get(prof.get("force"), float(rng.choice([-12, -7, -5, 0])))
    if s:
        y = varispeed(y, s); steps.append(f"vari{s:+.0f}")
    y = loopify(y)
    y = np.tile(y, (1, max(1, int(20 * SR / y.shape[1]))))
    y, tone = _space(y, rng, prof); steps.append(tone)
    if rng.random() < 0.4:
        y = vinyl(y); steps.append("vinyl")
    return y


def _draw(options, rng, k=1):
    w = np.array([TASTE.get(o, 1.0) for o in options], float)
    return list(rng.choice(options, size=min(k, len(options)), replace=False, p=w / w.sum()))


CORES = {"vocal": _vocal_core, "sustained": _sustained_core, "transient": _transient_core, "texture": _texture_core}


PLANS = {  # technique families per material, in the order they appear in a variation family
    "vocal": ["in_tune", "formant_up", "fragment", "varispeed_up", "vowel_hold", "reverse_swell",
              "varispeed_down", "slow_stretch", "chop"],
    "sustained": ["dark_phase", "pop_phase", "freeze", "octave_bed", "plain_space", "micro", "paulstretch"],
    "transient": ["dark_phase", "pop_phase", "freeze", "reverse_swell"],
    "texture": ["vari_low", "vari_mid", "plain_space"],
}
LABELS = {"in_tune": "In tune", "varispeed_down": "Pitch down", "varispeed_up": "Tape up", "formant_up": "Pitch up", "slow_stretch": "Slow stretch",
          "vowel_hold": "Vowel hold", "chop": "Chop", "reverse_swell": "Reverse swell", "dark_phase": "Dark phase",
          "pop_phase": "Pop phase", "freeze": "Freeze", "octave_bed": "Octave bed", "plain_space": "Space",
          "micro": "Micro loops", "fragment": "Fragment", "paulstretch": "Paulstretch", "vari_low": "Octave down", "vari_mid": "Slowed"}


def _learned_taste():
    """Technique weights from the taste model (Beta posterior means), falling back to TASTE."""
    try:
        from .taste import technique_posteriors
        post = technique_posteriors(TASTE)
        return {k: 4 * a / (a + b) for k, (a, b) in post.items() if ":" not in k} | \
               {k: 0.0 for k, v in TASTE.items() if v == 0 and post.get(k, [0, 1])[0] < 1.5}
    except Exception:
        return TASTE


def plan(kind, n):
    """Every suitable technique at least once (if n allows); extra slots by taste weight; family order kept."""
    T = _learned_taste()
    opts = [o for o in PLANS[kind] if T.get(o, 1.0) > 0]
    w = np.array([T.get(o, 1.0) for o in opts])
    counts = np.ones(len(opts), int) if n >= len(opts) else np.zeros(len(opts), int)
    if n < len(opts):
        for i in np.argsort(-w)[:n]:
            counts[i] = 1
    while counts.sum() < n:
        counts[int(np.argmax(w / (counts + 1)))] += 1
    return [o for o, c in zip(opts, counts) for _ in range(c)]


def mangle(y, category=None, seed=None, force=None, prof=None):
    seed = int(np.random.SeedSequence().entropy % 2**31) if seed is None else seed
    rng = np.random.default_rng(seed)
    prof = dict(prof or profile(y, category), force=force)
    steps = []
    out = CORES[prof["kind"]](y.astype(np.float32), rng, prof, steps)
    if prof["kind"] == "vocal":
        out, tone = vocal_space(out, rng); steps.append(tone)
    out = _norm(out)
    fo = min(int(1.0 * SR), out.shape[1] // 4)
    out[:, -fo:] *= np.linspace(1, 0, fo)
    return out, dict(seed=seed, profile={k: v for k, v in prof.items() if k != "force"},
                     technique=force, chain=steps)


def run(ids=(), files=(), category=None, top=5, variants=12, seed=None):
    """Render a variation family for each source into Variations/<category>/<source>/ and register it."""
    import os, re
    from .db import connect
    con = connect()
    con.execute("""CREATE TABLE IF NOT EXISTS variants (sample_id TEXT, idx INTEGER, technique TEXT,
                   chain TEXT, seed INTEGER, path TEXT, PRIMARY KEY(sample_id, idx))""")
    srcs = [(Path(f), None, None) for f in files]
    if ids:
        q = ",".join("?" * len(ids))
        srcs += [(C.LIB_ROOT / r["path"], r["category"], r["id"])
                 for r in con.execute(f"SELECT id, path, category FROM samples WHERE id IN ({q})", ids)]
    rows_by_id = {r["id"]: r for r in con.execute("SELECT * FROM samples")} if (ids or category) else {}
    if category:
        srcs += [(C.LIB_ROOT / r["path"], r["category"], r["id"]) for r in con.execute(
            """SELECT id, path, category FROM samples WHERE category=? AND path NOT LIKE '_Reference/%'
               ORDER BY quality DESC, RANDOM() LIMIT ?""", (category, top))]
    for src, cat, sid in srcs:
        y = sf.read(str(src), dtype="float32", always_2d=True)[0].T if src.suffix.lower() == ".wav" else decode(src)
        if y.shape[0] == 1:
            y = np.repeat(y, 2, 0)
        row = rows_by_id.get(sid)
        hq = False
        if row is not None and row["source"] == "vocals" and row["rendered_from"] != "mix":
            try:
                y = hq_vocal(row)
                hq = True
                print(f"  (re-isolated with MelBand RoFormer)")
            except Exception as e:
                print(f"  (RoFormer re-isolation failed, using stored stem: {e})")
        prof = profile(y, cat)
        if row is not None and row["key_from"] != "none" and row["key"]:
            prof["key"] = row["key"] + ("m" if row["scale"] == "minor" else "")  # for tuning + key labels
        stem = re.sub(r"^[A-Za-z]+(-Loop\d+)?_", "", src.stem)[:70]
        fam = C.LIB_ROOT / "Variations" / (cat or "Files") / stem
        if fam.exists():
            for f in fam.iterdir():
                f.unlink()
        fam.mkdir(parents=True, exist_ok=True)
        orig = fam / "00 ORIGINAL.wav"
        if hq:
            sf.write(str(orig), _norm(y).T, SR, subtype="PCM_24")
        else:
            try:
                os.link(src, orig)
            except OSError:
                sf.write(str(orig), y.T, SR, subtype="PCM_24")
        if sid:
            con.execute("DELETE FROM variants WHERE sample_id=?", (sid,))
        print(f"\n{src.name}  [{prof['kind']}]")
        seen = {}
        for k, tech in enumerate(plan(prof["kind"], variants), 1):
            seen[tech] = seen.get(tech, -1) + 1
            out, info = mangle(y, cat, None if seed is None else seed + k, force=tech, prof=dict(prof, slot=seen[tech]))
            detail = " · ".join(info["chain"])
            name = f"{k:02d} {LABELS[tech]} · {detail}"[:110].replace("/", "-") + ".wav"
            dst = fam / name
            sf.write(str(dst), out.T, SR, subtype="PCM_24")
            dst.with_suffix(".json").write_text(json.dumps(dict(source=str(src), **info), indent=1))
            if sid:
                con.execute("INSERT OR REPLACE INTO variants VALUES (?,?,?,?,?,?)",
                            (sid, k, tech, detail, info["seed"], str(dst.relative_to(C.LIB_ROOT))))
            print(f"  {name}")
        con.commit()
