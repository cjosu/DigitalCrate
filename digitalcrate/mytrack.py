"""Fits my track: drop in a bounce of something you're making and get the library's samples that would fit into it.

Unlike "feels like a track" (sounds similar), this asks what could go *in* it:
  - key: samples are conformed to the project key when you use them, so what counts is how far one has to move:
    0 semitones best, each semitone of shift costs a little, a sample in the other mode is read as its relative key
    (A minor fits C major as is). Unkeyed sounds (drums, most textures) are neutral;
  - tempo (loops): how much stretching it takes, half / double time included; one-shots don't care;
  - sound world: CLAP similarity to the track (its closest 10 s window, and the whole), so era, texture and mood fit;
  - a little of your taste model.
Each result says why (same key / shift +2 / stretch 4% / sounds like 1:20), and the track's key and tempo can become
the project's, so the sketchpad and exports conform to it.

Your track is only listened to: an uploaded file is analysed in a temporary folder and deleted, nothing is added to
the library, logged, or sent anywhere.
"""
import base64
import tempfile
from pathlib import Path

import numpy as np

from .db import connect

_ROWS = {}


def _meta(mat):
    """key / kind / tempo of every sample in the search matrix (cached with it)."""
    if _ROWS.get("sig") != mat["sig"]:
        con = connect()
        by = {r["id"]: r for r in con.execute("SELECT id, kind, bpm, key, scale, key_from FROM samples")}
        from .audio import pc_of
        pc, minor, keyed, loop, bpm = [], [], [], [], []
        for i in mat["ids"]:
            r = by.get(i)
            k = bool(r and r["key_from"] != "none" and r["key"])
            keyed.append(k)
            try:
                pc.append(pc_of(r["key"].rstrip("m")) if k else 0)
            except Exception:
                pc.append(0); keyed[-1] = False
            minor.append(bool(r and r["scale"] == "minor"))
            loop.append(bool(r and r["kind"] == "loop"))
            bpm.append(float(r["bpm"] or 0) if r else 0.0)
        _ROWS.update(sig=mat["sig"], pc=np.array(pc), minor=np.array(minor), keyed=np.array(keyed),
                     loop=np.array(loop), bpm=np.array(bpm))
    return _ROWS


def key_fit(pc, minor, keyed, t_pc, t_minor):
    """(fit 0..1, semitones to shift) per sample, for a track in t_pc / t_minor."""
    # a sample in the other mode is read as its relative key: A minor (9) -> C major (0); C major -> A minor
    rel = np.where(minor == t_minor, pc, np.where(minor, (pc + 3) % 12, (pc + 9) % 12))
    d = (t_pc - rel) % 12
    shift = np.where(d > 6, d - 12, d)
    fit = 1 - 0.11 * np.abs(shift) - 0.04 * (minor != t_minor)
    return np.where(keyed, fit, 0.75), np.where(keyed, shift, 0)


def tempo_fit(loop, bpm, t_bpm):
    """(fit 0..1, stretch %) per sample: loops by how far they'd be stretched (half / double time count)."""
    b = np.where(bpm > 0, bpm, t_bpm)
    r = np.stack([t_bpm / b, t_bpm / (2 * b), 2 * t_bpm / b])
    st = np.abs(np.log2(r)).min(0)  # in octaves of tempo
    pct = (2 ** st - 1) * 100
    fit = np.exp(-(pct / 7) ** 2)
    return np.where(loop, fit, 1.0), np.where(loop, pct, 0.0)


def match(path=None, name=None, b64=None, k=400):
    from scipy.signal import resample_poly
    from .analyze import track_tempo_key
    from .audio import PITCHES, decode, key_label
    from .models import clap
    from .search import matrix
    tmp = None
    try:
        if b64:  # dropped into the page: analysed here, then deleted
            tmp = tempfile.TemporaryDirectory(prefix="dc-mytrack-")
            path = Path(tmp.name) / ("track" + (Path(name or "").suffix or ".wav"))
            path.write_bytes(base64.b64decode(b64.split(",")[-1]))
        path = Path(path).expanduser()
        if not path.exists():
            raise ValueError("no such file")
        y = decode(path)
        tk = track_tempo_key(y)
        m = y.mean(0) if y.ndim > 1 else y
    finally:
        if tmp:
            tmp.cleanup()
    m48 = resample_poly(m, 160, 147).astype(np.float32)
    win = 48000 * 10
    starts = list(range(0, max(1, len(m48) - win), win))
    if len(starts) > 36:
        starts = [int(x) for x in np.linspace(0, len(m48) - win, 36)]
    clips = [m48[s:s + win] for s in starts if np.abs(m48[s:s + win]).max() > 1e-3] or [m48[:win]]
    W = clap().embed_audio(clips)
    W /= np.linalg.norm(W, axis=1, keepdims=True) + 1e-9
    mat = matrix()
    meta = _meta(mat)
    sims = mat["E"] @ W.T
    cen = W.mean(0)
    cen /= np.linalg.norm(cen) + 1e-9
    snd = 0.6 * sims.max(1) + 0.4 * (mat["E"] @ cen)
    snd_z = (snd - snd.mean()) / (snd.std() + 1e-9)
    t_minor = tk["scale"] == "minor"
    kf, shift = key_fit(meta["pc"], meta["minor"], meta["keyed"], tk["pc"], t_minor)
    tf, pct = tempo_fit(meta["loop"], meta["bpm"], tk["bpm"])
    try:
        from .taste import scores_payload
        t = scores_payload(None).get("score", {})
        taste = np.array([t.get(p, 0.0) for p in mat["paths"]])
    except Exception:
        taste = np.zeros(len(mat["paths"]))
    score = snd_z + 3.0 * (kf - 0.75) + 1.5 * (tf - 0.5) + 0.15 * np.clip(taste, -2, 3)
    score[np.char.startswith(np.array(mat["paths"]), "_Reference")] = -99
    order = np.argsort(-score)[:k]
    best = sims.argmax(1)
    out = []
    for i in order:
        why = []
        if meta["keyed"][i]:
            why.append("same key" if shift[i] == 0 and meta["minor"][i] == t_minor else
                       "relative key" if shift[i] == 0 else f"shift {int(shift[i]):+d}")
        if meta["loop"][i] and meta["bpm"][i]:
            why.append("on tempo" if pct[i] < 1 else f"stretch {pct[i]:.0f}%")
        b = starts[min(best[i], len(starts) - 1)] / 48000
        why.append(f"sounds like {int(b // 60)}:{int(b % 60):02d}")
        out.append(dict(path=mat["paths"][i], score=round(float(score[i]), 3), why=" · ".join(why)))
    key = key_label(tk["pc"], tk["scale"])
    return dict(name=name or path.name, key=key, camelot=tk["camelot"], bpm=round(tk["bpm"]),
                tempo_sure=tk["tempo_ok"], key_strength=round(tk["key_strength"], 2), results=out,
                pitches=PITCHES)
