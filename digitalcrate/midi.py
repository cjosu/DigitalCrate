"""Notes and chords -> MIDI with Spotify's basic-pitch (CoreML on Apple silicon).

transcribe(rel) -> dict(notes=[[start, end, pitch, velocity]], chords=[[start, end, 'Fm7']], midi=<lib-relative .mid>)
Cached in _data/midi/<hash>.mid + .json. Exports copy the .mid next to the audio.
"""
import hashlib
import json
import logging
import warnings

import numpy as np

from . import config as C

MIDI_DIR = C.DATA_DIR / "midi"
NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
CHORDS = {"": [0, 4, 7], "m": [0, 3, 7], "7": [0, 4, 7, 10], "maj7": [0, 4, 7, 11], "m7": [0, 3, 7, 10],
          "sus2": [0, 2, 7], "sus4": [0, 5, 7], "dim": [0, 3, 6], "m9": [0, 3, 7, 10, 2], "add9": [0, 4, 7, 2]}


def _model():
    global _M
    try:
        return _M
    except NameError:
        pass
    warnings.filterwarnings("ignore")
    logging.getLogger().setLevel(logging.ERROR)
    from basic_pitch import ICASSP_2022_MODEL_PATH
    from basic_pitch.inference import Model
    _M = Model(ICASSP_2022_MODEL_PATH)
    return _M


def chord_of(weights):
    """12-bin pitch-class weights -> best chord label (or '')."""
    w = np.asarray(weights, float)
    if w.sum() < 1e-6:
        return ""
    w = w / w.sum()
    best, bs = "", 0.0
    for root in range(12):
        for q, iv in CHORDS.items():
            tpl = np.zeros(12)
            tpl[[(root + i) % 12 for i in iv]] = 1
            score = (w * tpl).sum() - 0.6 * (w * (1 - tpl)).sum() - 0.02 * len(iv)
            if score > bs:
                best, bs = NAMES[root] + q, score
    return best if bs > 0.35 else ""


def chords(notes, dur, win=None):
    """Chord per window (default ~1 s, or one bar when bpm known)."""
    win = win or 1.0
    out = []
    t = 0.0
    while t < dur - 1e-3:
        w = np.zeros(12)
        for s, e, p, v in notes:
            ov = min(e, t + win) - max(s, t)
            if ov > 0:
                w[p % 12] += ov * (0.5 + v / 254)
        c = chord_of(w)
        if out and out[-1][2] == c:
            out[-1][1] = round(t + win, 3)
        else:
            out.append([round(t, 3), round(min(dur, t + win), 3), c])
        t += win
    return [c for c in out if c[2]]


def transcribe(rel, bpm=None):
    src = C.LIB_ROOT / rel
    h = hashlib.sha1(f"{rel}|{src.stat().st_mtime}".encode()).hexdigest()[:14]
    MIDI_DIR.mkdir(parents=True, exist_ok=True)
    js = MIDI_DIR / f"{h}.json"
    if js.exists():
        return json.loads(js.read_text())
    from basic_pitch.inference import predict
    import soundfile as sf
    import contextlib, io
    with contextlib.redirect_stdout(io.StringIO()):
        _, midi, events = predict(str(src), _model(), onset_threshold=0.5, frame_threshold=0.3,
                                  minimum_note_length=80, multiple_pitch_bends=False)
    dur = sf.info(str(src)).duration
    notes = sorted([[round(float(s), 3), round(float(e), 3), int(p), int(v * 127) if v <= 1 else int(v)]
                    for s, e, p, v, *_ in events], key=lambda n: (n[0], n[2]))
    if bpm:  # write the tempo so the MIDI lines up in Live
        midi.estimate_tempo = lambda: bpm
        try:
            import pretty_midi
            pm = pretty_midi.PrettyMIDI(initial_tempo=float(bpm))
            inst = pretty_midi.Instrument(0, name=src.stem[:40])
            inst.notes = [pretty_midi.Note(velocity=max(1, min(127, v)), pitch=p, start=s, end=e) for s, e, p, v in notes]
            pm.instruments.append(inst)
            midi = pm
        except Exception:
            pass
    mid = MIDI_DIR / f"{h}.mid"
    midi.write(str(mid))
    res = dict(notes=notes, chords=chords(notes, dur, (4 * 60 / bpm) if bpm else None), dur=round(dur, 3),
               midi=str(mid.relative_to(C.LIB_ROOT)))
    js.write_text(json.dumps(res))
    return res
