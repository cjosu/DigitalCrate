"""Stretch / repitch shootout: render the same samples through every candidate method, loudness-matched, so they
can be compared blind in the browser (/shootout). Votes are stored in the `shootout_votes` table; the winners per
material become the conform defaults.

    python -m digitalcrate shootout            # render (cached) + print the manifest
    python -m digitalcrate shootout --results  # vote tally per method and material

Methods
  rb3        Rubber Band R3 "finer" engine (current default; formant-preserving on vocals)
  rb2perc    Rubber Band R2, percussive/crisp settings (drums only)
  signal     Signalsmith Stretch (open source, 2023+)
  vari       varispeed / Re-Pitch: plain resampling, pitch and tempo move together (no processing artifacts)
  world      WORLD vocoder: analyse pitch + spectral envelope, resynthesise (monophonic voice only)
  neural     PC-NSF-HiFiGAN neural vocoder: mel + new pitch -> waveform (monophonic voice only)
  granular   overlapping grains (pads / textures)
  slice      cut at each hit and re-place the hits on the new grid, no stretching (drums only)
"""
import json
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

from . import config as C
from .db import connect

SR = C.SR
OUT = C.DATA_DIR / "shootout"
VOCODER = C.MODELS_DIR / "pcnsf" / "pc_nsf_hifigan_44.1k_hop512_128bin_2025.02.onnx"

# (id, material, label, [tasks]); task = (name, semitones, speed) where speed > 1 = faster
SET = [
    ("a59109", "vocal", "Aaliyah – R&B phrase", [("pitch +3", 3, 1), ("pitch −4", -4, 1), ("80→100 bpm", 0, 1.25)]),
    ("1994d9", "vocal", "Sufjan Stevens – soft male phrase", [("pitch +3", 3, 1), ("pitch −4", -4, 1)]),
    ("6ec934", "vocal", "Hildegard von Bingen – chant in a big room", [("pitch +3", 3, 1)]),
    ("30cb41", "vocal", "The-Dream – vocal atmosphere loop", [("pitch +3", 3, 1), ("72→90 bpm", 0, 1.25)]),
    ("c0a7ba", "pad", "Markus Guentner – pad", [("pitch +3", 3, 1), ("half speed", 0, 0.5)]),
    ("1c399c", "keys", "Sufjan Stevens – piano chords", [("pitch +3", 3, 1)]),
    ("1fe9dc", "loop", "Aaliyah – melody loop", [("pitch +3", 3, 1), ("80→100 bpm", 0, 1.25)]),
    ("047b97", "drums", "Mkwaju Ensemble – percussion break", [("156→128 bpm", 0, 128 / 156.24)]),
    ("ca4634", "drums", "Yellow Magic Orchestra – drum loop", [("102→124 bpm", 0, 124 / 101.85)]),
]
METHODS = {
    "vocal": ["rb3", "signal", "vari", "world", "neural"],
    "pad": ["rb3", "signal", "vari", "granular"],
    "keys": ["rb3", "signal", "vari", "granular"],
    "loop": ["rb3", "signal", "vari"],
    "drums": ["rb3", "rb2perc", "signal", "vari", "slice"],
}
ABOUT = {
    "rb3": "Rubber Band R3 (current default)", "rb2perc": "Rubber Band R2, percussive mode",
    "signal": "Signalsmith Stretch", "vari": "Varispeed / Re-Pitch (tape-style)", "world": "WORLD vocoder",
    "neural": "Neural vocoder (PC-NSF-HiFiGAN)", "granular": "Granular", "slice": "Slice & re-place hits",
}


# ---------------------------------------------------------------- engines
def rb(y, semis, speed, formant=False, r2perc=False):
    with tempfile.TemporaryDirectory() as td:
        a, b = f"{td}/i.wav", f"{td}/o.wav"
        sf.write(a, y.T, SR, subtype="FLOAT")
        eng = ["--crisp", "6", "--centre-focus"] if r2perc else ["-3", "-q"]
        cmd = ["rubberband", *eng, "-t", f"{1 / speed:.5f}", "-p", f"{semis:.3f}"] + (["-F"] if formant else []) + [a, b]
        subprocess.run(cmd, check=True, capture_output=True)
        return sf.read(b, dtype="float32", always_2d=True)[0].T


def signalsmith(y, semis, speed):
    import python_stretch as ps
    s = ps.Signalsmith.Stretch(7)
    s.preset(y.shape[0], float(SR))
    s.setTransposeSemitones(float(semis))
    s.setTimeFactor(float(speed))
    return s.process(np.ascontiguousarray(y, dtype=np.float32))


def vari(y, semis, speed):
    """Tape-style: one resampling ratio. A pitch task changes length; a tempo task changes pitch."""
    from scipy.signal import resample_poly
    from fractions import Fraction
    r = 2 ** (semis / 12) if semis else speed
    f = Fraction(1 / r).limit_denominator(400)
    return resample_poly(y, f.numerator, f.denominator, axis=1).astype(np.float32)


def _f0(m, hop):
    import pyworld as pw
    x = m.astype(np.float64)
    f0, t = pw.harvest(x, SR, f0_floor=60, f0_ceil=1100, frame_period=hop / SR * 1000)
    return f0, t, x


def world(y, semis, speed):
    import pyworld as pw
    m = y.mean(0)
    f0, t, x = _f0(m, 220.5)  # 5 ms
    sp = pw.cheaptrick(x, f0, t, SR)
    ap = pw.d4c(x, f0, t, SR)
    z = pw.synthesize(f0 * 2 ** (semis / 12), sp, ap, SR, frame_period=5.0 / speed)
    return np.repeat(z[None].astype(np.float32), 2, 0)


_sess = None


def _mel(x):
    import librosa
    pad = (2048 - 512) // 2
    xp = np.pad(x, (pad, pad), mode="reflect")
    S = np.abs(librosa.stft(xp, n_fft=2048, hop_length=512, win_length=2048, window="hann", center=False))
    fb = librosa.filters.mel(sr=SR, n_fft=2048, n_mels=128, fmin=40, fmax=16000)  # slaney scale + norm
    return np.log(np.clip(fb @ S, 1e-5, None)).T.astype(np.float32)  # frames x 128


def neural(y, semis, speed):
    global _sess
    import onnxruntime as ort
    if _sess is None:
        _sess = ort.InferenceSession(str(VOCODER), providers=["CPUExecutionProvider"])
    m = y.mean(0)
    mel = _mel(m)
    f0, _, _ = _f0(m, 512)
    n = min(len(f0), len(mel))
    mel, f0 = mel[:n], f0[:n]
    v = f0 > 0
    if v.any():  # the vocoder wants a continuous pitch curve: bridge unvoiced gaps
        idx = np.arange(n)
        f0 = np.interp(idx, idx[v], f0[v])
    else:
        f0 = np.full(n, 200.0)
    f0 = f0 * 2 ** (semis / 12)
    if speed != 1:
        k = max(2, int(round(n / speed)))
        src = np.linspace(0, n - 1, k)
        mel = np.stack([np.interp(src, np.arange(n), mel[:, j]) for j in range(128)], 1).astype(np.float32)
        f0 = np.interp(src, np.arange(n), f0)
    out = _sess.run(None, {"mel": mel[None], "f0": f0[None].astype(np.float32)})[0][0]
    return np.repeat(out[None].astype(np.float32), 2, 0)


def granular(y, semis, speed, grain=0.12, overlap=4, jitter=0.02, seed=3):
    from scipy.signal import resample
    rng = np.random.default_rng(seed)
    g = int(grain * SR)
    hop = g // overlap
    rate = 2 ** (semis / 12)
    src_len = int(g * rate)
    n_out = int(y.shape[1] / speed)
    out = np.zeros((2, n_out + g), np.float32)
    w = np.hanning(g).astype(np.float32)
    for o in range(0, n_out, hop):
        p = int(o * speed + rng.uniform(-jitter, jitter) * SR)
        p = int(np.clip(p, 0, max(0, y.shape[1] - src_len - 1)))
        seg = y[:, p:p + src_len]
        if seg.shape[1] < 8:
            continue
        seg = resample(seg, g, axis=1).astype(np.float32) if seg.shape[1] != g else seg
        out[:, o:o + g] += seg * w
    return out[:, :n_out] / (overlap / 2)


def slice_(y, semis, speed):
    import librosa
    on = librosa.onset.onset_detect(y=y.mean(0), sr=SR, hop_length=256, backtrack=True, units="samples").tolist()
    b = sorted(set([0] + on + [y.shape[1]]))
    n_out = int(y.shape[1] / speed)
    out = np.zeros((2, n_out + SR), np.float32)
    for a, e in zip(b[:-1], b[1:]):
        dst = int(a / speed)
        L = min(e - a, int((e - a) / speed)) if speed > 1 else e - a
        seg = y[:, a:a + L].copy()
        f = min(int(0.006 * SR), seg.shape[1] // 3)
        if f:
            seg[:, -f:] *= np.linspace(1, 0, f, dtype=np.float32)
        out[:, dst:dst + seg.shape[1]] += seg
    return out[:, :n_out]


def run_method(meth, y, semis, speed, material):
    if meth == "rb3":
        return rb(y, semis, speed, formant=material == "vocal")
    if meth == "rb2perc":
        return rb(y, semis, speed, r2perc=True)
    return {"signal": signalsmith, "vari": vari, "world": world, "neural": neural, "granular": granular,
            "slice": slice_}[meth](y, semis, speed)


# ---------------------------------------------------------------- render + votes
def _db():
    con = connect()
    con.execute("""CREATE TABLE IF NOT EXISTS shootout_votes (clip TEXT, sample TEXT, task TEXT, method TEXT,
                   material TEXT, rating INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    return con


def _match(z, ref):
    rr = np.sqrt(np.mean(ref ** 2)) + 1e-9
    z = z * (rr / (np.sqrt(np.mean(z ** 2)) + 1e-9))
    pk = np.abs(z).max()
    return z * (0.97 / pk) if pk > 0.97 else z


def _fade(z, s=0.01):
    f = min(int(s * SR), z.shape[1] // 4)
    if f:
        z[:, :f] *= np.linspace(0, 1, f, dtype=np.float32)
        z[:, -f:] *= np.linspace(1, 0, f, dtype=np.float32)
    return z


def _level(files):
    """Same RMS for every clip of a task: the loudest level all of them reach without exceeding -0.3 dBFS."""
    ys = [sf.read(str(f), dtype="float32")[0] for f in files]
    if not ys:
        return
    tgt = min(0.97 * np.sqrt(np.mean(y ** 2)) / (np.abs(y).max() + 1e-9) for y in ys)
    for f, y in zip(files, ys):
        sf.write(str(f), y * (tgt / (np.sqrt(np.mean(y ** 2)) + 1e-9)), SR, subtype="PCM_16")


def render(force=False, log=print):
    from .edit import _load
    import time
    OUT.mkdir(parents=True, exist_ok=True)
    con = connect()
    items = []
    for sid, mat, label, tasks in SET:
        r = con.execute("SELECT path, key, scale, bpm FROM samples WHERE id=?", (sid,)).fetchone()
        if not r:
            log(f"missing sample {sid}"); continue
        y = _load(r["path"])
        orig = OUT / f"{sid}_orig.wav"
        if force or not orig.exists():
            sf.write(str(orig), y.T, SR, subtype="PCM_16")
        rng = np.random.default_rng(int(sid, 16))
        for tname, semis, speed in tasks:
            clips = []
            for meth in METHODS[mat]:
                tag = f"{sid}_{tname.replace(' ', '').replace('→', '-').replace('−', 'm').replace('+', 'p')}_{meth}"
                f = OUT / f"{tag}.wav"
                if force or not f.exists():
                    t0 = time.time()
                    try:
                        z = run_method(meth, y, semis, speed, mat)
                    except Exception as ex:
                        log(f"  {tag}: FAILED {ex}"); continue
                    sf.write(str(f), _fade(_match(z, y)).T, SR, subtype="PCM_16")
                    log(f"  {tag}: {time.time() - t0:.1f}s")
                clips.append(dict(clip=tag, method=meth, file=f.name))
            _level([OUT / c["file"] for c in clips])
            order = rng.permutation(len(clips)).tolist()
            items.append(dict(sample=sid, material=mat, label=label, task=tname, orig=orig.name, path=r["path"],
                              clips=[dict(c, letter="ABCDEFGH"[i]) for i, c in enumerate(clips[j] for j in order)]))
    man = dict(items=items, about=ABOUT)
    (OUT / "manifest.json").write_text(json.dumps(man, indent=1))
    return man


# ---------------------------------------------------------------- round 2: vocal tuning engines
TUNE_SET = [("a59109", "Aaliyah – R&B phrase"), ("1994d9", "Sufjan Stevens – soft male phrase"),
            ("6ec934", "Hildegard von Bingen – chant"), ("a6b54d", "The-Dream – R&B phrase"),
            ("d41487", "Brian Eno – Shadow")]
TUNE_SETTINGS = [("natural: 80%, 60 ms glide", dict(strength=0.8, speed_ms=60)),
                 ("hard: 100%, instant", dict(strength=1.0, speed_ms=0))]
TUNE_ABOUT = {"orig": "Untouched original (hidden reference)", "rb_formant": "Rubber Band R3 + formants (current)",
              "rb": "Rubber Band R3, no formant mode", "psola": "Praat PSOLA",
              "vari": "Tape-style variable speed"}


def render_tune(force=False, log=print):
    from .edit import _load
    from .retune import tune, ENGINES
    import time
    OUT.mkdir(parents=True, exist_ok=True)
    con = connect()
    items = []
    for sid, label in TUNE_SET:
        r = con.execute("SELECT path, key, scale FROM samples WHERE id=?", (sid,)).fetchone()
        if not r:
            log(f"missing sample {sid}"); continue
        key = r["key"] + ("m" if r["scale"] == "minor" else "")
        y = _load(r["path"])
        orig = OUT / f"{sid}_orig.wav"
        if force or not orig.exists():
            sf.write(str(orig), y.T, SR, subtype="PCM_16")
        rng = np.random.default_rng(int(sid, 16) + 7)
        for k, (tname, kw) in enumerate(TUNE_SETTINGS):
            clips = []
            for meth in ("orig",) + ENGINES:
                tag = f"{sid}_tune{k}_{meth}"
                f = OUT / f"{tag}.wav"
                if force or not f.exists():
                    t0 = time.time()
                    try:
                        z = y.copy() if meth == "orig" else tune(y, key, engine=meth, **kw)
                    except Exception as ex:
                        log(f"  {tag}: FAILED {ex}"); continue
                    sf.write(str(f), _fade(_match(z, y)).T, SR, subtype="PCM_16")
                    log(f"  {tag}: {time.time() - t0:.1f}s")
                clips.append(dict(clip=tag, method=meth, file=f.name))
            _level([OUT / c["file"] for c in clips])
            order = rng.permutation(len(clips)).tolist()
            items.append(dict(sample=sid, material="tune", label=label, task=f"tune to {key} · {tname}",
                              orig=orig.name, path=r["path"],
                              clips=[dict(c, letter="ABCDEFGH"[i]) for i, c in enumerate(clips[j] for j in order)]))
    man = dict(items=items, about=TUNE_ABOUT)
    (OUT / "manifest_tune.json").write_text(json.dumps(man, indent=1))
    return man


def manifest(rnd=None):
    f = OUT / ("manifest_tune.json" if rnd == "tune" else "manifest.json")
    return json.loads(f.read_text()) if f.exists() else (render_tune() if rnd == "tune" else render())


def vote(clip, rating):
    man = manifest("tune" if "_tune" in clip else None)
    for it in man["items"]:
        for c in it["clips"]:
            if c["clip"] == clip:
                con = _db()
                con.execute("DELETE FROM shootout_votes WHERE clip=?", (clip,))
                if rating:
                    con.execute("INSERT INTO shootout_votes(clip, sample, task, method, material, rating) "
                                "VALUES (?,?,?,?,?,?)", (clip, it["sample"], it["task"], c["method"], it["material"],
                                                         int(rating)))
                con.commit()
                return True
    return False


def votes():
    return {r["clip"]: r["rating"] for r in _db().execute("SELECT clip, rating FROM shootout_votes")}


def results():
    rows = _db().execute("""SELECT material, method, AVG(rating) avg, COUNT(*) n FROM shootout_votes
                            GROUP BY material, method ORDER BY material, avg DESC""").fetchall()
    return [dict(r) for r in rows]
