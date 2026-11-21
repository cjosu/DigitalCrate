"""Saved combinations (sketches) and aligned stem export.

save_pair: two samples that sound great together -> a sketch (the same thing the sketchpad saves), in the first
sample's key and tempo, ready to open from the Kits tab.
write_stems: each sketch lane rendered on its own in the browser (same timing, key and tempo as the sketch, same
length, starting on bar 1) -> one WAV per lane in Ableton's User Library, so they line up when dropped into a set.
"""
import base64
import io
import json
import re
import subprocess

import numpy as np
import soundfile as sf

from . import config as C
from .db import connect

_B = ['B', 'F#', 'Db', 'Ab', 'Eb', 'Bb', 'F', 'C', 'G', 'D', 'A', 'E']
_A = ['Abm', 'Ebm', 'Bbm', 'Fm', 'Cm', 'Gm', 'Dm', 'Am', 'Em', 'Bm', 'F#m', 'Dbm']
KEY_OF_CAM = {**{f"{k + 1}B": n for k, n in enumerate(_B)}, **{f"{k + 1}A": n for k, n in enumerate(_A)}}


def _safe(s):
    return re.sub(r'[/:\\*?"<>|]+', "-", s).strip() or "Sketch"


def _row(con, path):
    return con.execute("SELECT s.*, t.artist, t.title FROM samples s JOIN tracks t ON t.id=s.track_id WHERE s.path=?",
                       (path,)).fetchone()


def save_pair(src, partner, name=None):
    con = connect()
    a, b = _row(con, src), _row(con, partner)
    if a is None or b is None:
        raise ValueError("both samples must be in the library")
    key = next((KEY_OF_CAM.get(r["camelot"]) for r in (a, b) if r["key_from"] != "none"), None)
    bpm = next((round(r["bpm"]) for r in (a, b) if r["kind"] == "loop" and r["bpm"]), None) or 120
    bar = 240 / bpm

    def lane(r):
        loop = r["kind"] == "loop"
        every = 0 if loop else next((n for n in (1, 2, 4, 8, 16) if n * bar >= r["dur"] - 0.05), 16)
        return dict(path=r["path"], vol=0.8, mute=False, solo=False, every=every, offset=0)
    base = name or f"{a['artist']} + {b['artist']}"
    names = {r["name"] for r in con.execute("SELECT name FROM sketches")}
    name, k = base, 2
    while name in names:
        name, k = f"{base} ({k})", k + 1
    state = dict(key=key, bpm=bpm, lanes=[lane(a), lane(b)])
    con.execute("INSERT INTO sketches(name, state, updated_at) VALUES (?,?,CURRENT_TIMESTAMP)", (name, json.dumps(state)))
    con.commit()
    from .taste import log_event
    log_event(a["path"], "pair", 1, a["id"], {"with": b["path"]})  # a liked pairing: data for the pairing model
    return dict(name=name, key=key, bpm=bpm)


def write_stems(name, stems, key=None, bpm=None, reveal=True):
    """stems: [{label, wav (base64)}], all the same length. -> folder in the Ableton User Library."""
    folder = _safe(f"{name} ({', '.join(x for x in (key, f'{bpm:g} bpm' if bpm else None) if x)})")
    if not stems:
        raise ValueError("nothing to export: every lane is muted")
    dest = C.ABLETON_SAMPLES / "Sketches" / folder
    dest.mkdir(parents=True, exist_ok=True)
    audio = [sf.read(io.BytesIO(base64.b64decode(s["wav"])), dtype="float32", always_2d=True) for s in stems]
    n = min(len(y) for y, _ in audio)
    mix = sum(y[:n] for y, _ in audio)
    # one gain for every stem, so the balance you set in the sketchpad survives and nothing clips
    g = min(1.0, 0.89 / (max([np.abs(mix).max()] + [np.abs(y).max() for y, _ in audio]) + 1e-9))
    out = []
    for k, (s, (y, sr)) in enumerate(zip(stems, audio), 1):
        f = dest / f"{k:02d} {_safe(s['label'])[:60]}.wav"
        sf.write(str(f), y[:n] * g, sr, subtype="PCM_24")
        out.append(f.name)
    sr0 = audio[0][1] if audio else C.SR
    if audio:
        sf.write(str(dest / "00 mix (reference).wav"), mix * g, sr0, subtype="PCM_24")
    if reveal:
        subprocess.run(["open", str(dest)])
    return dict(dest=str(dest), files=out)
