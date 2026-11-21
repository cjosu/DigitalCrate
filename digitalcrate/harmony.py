"""Chord progressions that suit a sample: music theory + what the sample plays + its mood.

1. What sounds when: the sample is cut into steps (one or two bars). Each step gets a 12-note pitch profile from
   the basic-pitch transcription blended with an audio chroma (pads transcribe poorly).
2. Which chords fit a step: every chord in the key (plus a few borrowed ones) is scored by how much of the step's
   sound falls on its chord tones, what lands a semitone against them (clashes), and which tensions are fine.
3. Which sequences are good: a beam search over steps adds functional-harmony moves (ii-V-I, i-VI-VII...), smooth
   voice leading and a home-key start/finish; distinct options are kept, not near-copies of each other.
4. Flavour from mood: soulful -> 7ths, 9ths and 13ths; dark / melancholic -> minor 9ths and modal colour;
   ethereal / dreamy -> sus2, add9, maj7; otherwise plainer triads and add9.
5. Voicing: smooth voice leading, placed in a register away from the sample's own so they don't mask each other.
"""
import math

import numpy as np

from . import config as C

NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
FLATS = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
SHARP_KEYS = {("major", k) for k in (7, 2, 9, 4, 11, 6)} | {("minor", k) for k in (4, 11, 6, 1, 8)}
SUFFIX = {"": "", "m": "", "dim": "°", "m7b5": "ø7", "maj7": "maj7", "m7": "7", "7": "7", "sus2": "sus2", "sus4": "sus4",
          "add9": "add9", "madd9": "add9", "maj9": "maj9", "m9": "9", "9": "9", "13": "13", "m11": "11"}
MAJOR = [0, 2, 4, 5, 7, 9, 11]
MINOR = [0, 2, 3, 5, 7, 8, 10]
QUAL = {  # intervals; 'core' = what makes it that chord, the rest are colour tones
    "": [0, 4, 7], "m": [0, 3, 7], "dim": [0, 3, 6], "sus2": [0, 2, 7], "sus4": [0, 5, 7],
    "maj7": [0, 4, 7, 11], "m7": [0, 3, 7, 10], "7": [0, 4, 7, 10], "m7b5": [0, 3, 6, 10],
    "add9": [0, 4, 7, 14], "madd9": [0, 3, 7, 14], "maj9": [0, 4, 7, 11, 14], "m9": [0, 3, 7, 10, 14],
    "9": [0, 4, 7, 10, 14], "13": [0, 4, 10, 14, 21], "m11": [0, 3, 7, 10, 14, 17],
}
STYLE_QUALS = {
    "soulful": {"maj": ["maj7", "maj9", ""], "min": ["m7", "m9", "m11"], "dom": ["9", "13", "7"]},
    "dark": {"maj": ["maj7", "add9", ""], "min": ["m9", "madd9", "m7"], "dom": ["7", "sus4"]},
    "ethereal": {"maj": ["add9", "maj7", "sus2"], "min": ["madd9", "m7", "sus2"], "dom": ["sus4", "sus2"]},
    "plain": {"maj": ["", "add9", "sus4"], "min": ["m", "m7", "madd9"], "dom": ["", "7", "sus4"]},
}
STYLE_OF_MOOD = {"soulful": "soulful", "warm": "soulful", "dark": "dark", "melancholic": "dark", "eerie": "dark",
                 "cold": "dark", "ethereal": "ethereal", "dreamy": "ethereal", "dubby": "ethereal",
                 "hypnotic": "ethereal", "lofi": "soulful", "euphoric": "plain"}
ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII"]
# functional moves between scale degrees (0-based), log-ish bonuses; anything else is allowed but neutral
MOVES_MAJOR = {(0, 3): .6, (0, 4): .5, (0, 5): .6, (0, 1): .4, (1, 4): .9, (3, 4): .6, (3, 0): .5, (3, 1): .4,
               (4, 0): .9, (4, 5): .6, (5, 3): .7, (5, 1): .6, (2, 5): .6, (6, 0): .5, (5, 4): .3}
MOVES_MINOR = {(0, 3): .6, (0, 5): .7, (0, 6): .6, (0, 4): .4, (3, 4): .6, (3, 0): .5, (3, 6): .5, (5, 6): .8,
               (6, 0): .7, (6, 2): .6, (2, 5): .6, (4, 0): .9, (5, 3): .5, (1, 4): .7, (6, 5): .3}
PADS = ["warm", "glass", "strings", "rhodes"]


def _row(rel):
    from .db import connect
    return connect().execute("SELECT * FROM samples WHERE path=?", (rel,)).fetchone()


def _style(row):
    import json
    try:
        moods = json.loads(row["mood_sims"] or "{}")
    except Exception:
        moods = {}
    if not moods:
        return "plain", []
    top = sorted(moods, key=lambda k: -moods[k])[:3]
    for m in top:
        if m in STYLE_OF_MOOD:
            return STYLE_OF_MOOD[m], top
    return "plain", top


def _timbre(row, style):
    bright = (row["centroid"] or 1500) > 2200
    return {"soulful": "rhodes", "dark": "warm", "ethereal": "glass" if bright else "strings"}.get(style, "warm")


def _profiles(rel, step, n_steps, notes):
    """Per step: 12-bin pitch-class weights (transcribed notes + audio chroma), and the median MIDI pitch."""
    import librosa
    from .edit import _load
    y = _load(rel).mean(0)
    sr = C.SR
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=2048)
    fr = librosa.frames_to_time(np.arange(chroma.shape[1]), sr=sr, hop_length=2048)
    P = np.zeros((n_steps, 12))
    for k in range(n_steps):
        a, b = k * step, (k + 1) * step
        w = np.zeros(12)
        for s, e, p, v in notes:
            ov = min(e, b) - max(s, a)
            if ov > 0:
                w[p % 12] += ov * (0.5 + v / 254)
        m = (fr >= a) & (fr < b)
        c = chroma[:, m].mean(1) if m.any() else np.zeros(12)
        c = np.where(c > np.percentile(c, 50), c, 0)  # keep the notes that stand out, not the haze
        w = w / (w.sum() + 1e-9) if w.sum() else w
        c = c / (c.sum() + 1e-9) if c.sum() else c
        P[k] = 0.55 * w + 0.45 * c if w.sum() else c
    mid = float(np.median([p for _, _, p, _ in notes])) if notes else 64.0
    return P, mid


def _spell(pc, tonic, mode):
    return (NAMES if (mode, tonic) in SHARP_KEYS else FLATS)[pc]


def _vocab(tonic, mode, style):
    """[(degree, root_pc, quality, label, roman)] — diatonic chords in the style's colours + a few borrowed ones."""
    scale = MAJOR if mode == "major" else MINOR
    qs = STYLE_QUALS[style]
    out = []
    for d, iv in enumerate(scale):
        root = (tonic + iv) % 12
        third = (scale[(d + 2) % 7] - iv) % 12
        fifth = (scale[(d + 4) % 7] - iv) % 12
        if fifth == 6:
            kinds = ["m7b5"] if style != "plain" else ["dim"]
        elif third == 4:
            seventh = (scale[(d + 6) % 7] - iv) % 12
            kinds = qs["dom"] if seventh == 10 else qs["maj"]
        else:
            kinds = qs["min"]
        for q in kinds:
            out.append((d, root, q))
    # borrowed colour: iv and bVII in major; major V (harmonic minor) and IV (dorian) in minor
    if mode == "major":
        out += [(3, (tonic + 5) % 12, "m7" if style != "plain" else "m"), (6, (tonic + 10) % 12, "")]
    else:
        out += [(4, (tonic + 7) % 12, "7"), (3, (tonic + 5) % 12, "" if style == "plain" else "9")]
    res = []
    for d, root, q in out:
        minorish = (q.startswith("m") and not q.startswith("maj")) or q == "dim"
        roman = ROMAN[d].lower() if minorish else ROMAN[d]
        # degrees that sit a semitone below the major-scale degree get a flat (bIII, bVI, bVII in minor; bVII in major)
        if (root - tonic) % 12 != MAJOR[d]:
            roman = "b" + roman
        res.append(dict(deg=d, root=root, q=q, name=_spell(root, tonic, mode) + q, roman=roman + SUFFIX[q]))
    return res


def _fit(ch, w):
    """How well a chord sits over a step's pitch profile w (0..1 weights summing to ~1)."""
    if w.sum() < 1e-6:
        return 0.0
    tones = {(ch["root"] + i) % 12 for i in QUAL[ch["q"]]}
    core = {(ch["root"] + i) % 12 for i in QUAL[ch["q"]][:3]}
    on = sum(w[p] for p in tones)
    # a note a semitone above a chord tone (b9 against the root, 4 against a major 3rd...) clashes; others are tensions
    clash = sum(w[p] for p in range(12) if p not in tones and ((p - 1) % 12) in core)
    root_hit = w[ch["root"]]
    return on - 1.4 * clash + 0.3 * root_hit


def _voicing(ch, prev, low, high):
    """Notes for a chord between low..high, as close as possible to the previous voicing."""
    ivs = QUAL[ch["q"]]
    pcs = [(ch["root"] + i) % 12 for i in ivs]
    best, bc = None, 1e9
    for base in range(low, high - 6):
        notes, n = [], base
        for pc in pcs:
            while n % 12 != pc:
                n += 1
            notes.append(n)
            n += 1
        if notes[-1] > high:
            continue
        if prev:
            cost = sum(min(abs(a - b) for b in prev) for a in notes) + abs(np.mean(notes) - np.mean(prev)) * 0.5
        else:
            cost = abs(np.mean(notes) - (low + high) / 2)
        if cost < bc:
            best, bc = notes, cost
    bass = (ch["root"] % 12) + 12 * ((low - 12) // 12)  # root in the octave below, for weight
    while bass >= low:
        bass -= 12
    return [bass] + (best or [low + p for p in pcs])


def suggest(rel, bpm=None, bars_per_chord=1, n_options=4):
    from .conform import parse_key
    from .midi import transcribe
    row = _row(rel)
    if row is None:
        raise ValueError("not a library sample")
    if str(row["path"]).startswith("_Reference/"):
        raise ValueError("reference sounds are for comparison only, not for building on")
    loop = row["kind"] == "loop" and row["bpm"]
    tempo = float(row["bpm"]) if loop else float(bpm or 90)
    bar = 240 / tempo
    step = bar * bars_per_chord
    dur = float(row["dur"] or 8)
    n_steps = max(1, min(8, int(round(dur / step)) or 1))
    tr = transcribe(rel, tempo)
    notes = tr["notes"]
    P, mid = _profiles(rel, step, n_steps, notes)
    if row["key_from"] != "none" and row["key"]:
        tonic, mode = parse_key(row["key"] + ("m" if row["scale"] == "minor" else ""))
    else:  # no key on file: Krumhansl-style guess from the whole profile
        prof = P.sum(0)
        maj = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
        mnr = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
        sc = [(np.corrcoef(prof, np.roll(t, k))[0, 1], k, m) for k in range(12) for t, m in ((maj, "major"), (mnr, "minor"))]
        _, tonic, mode = max(sc)
    style, top_moods = _style(row)
    V = _vocab(tonic, mode, style)
    moves = MOVES_MAJOR if mode == "major" else MOVES_MINOR
    E = np.array([[_fit(ch, P[k]) for ch in V] for k in range(n_steps)])

    def trans(a, b):
        A, B = V[a], V[b]
        s = moves.get((A["deg"], B["deg"]), 0.0) * 0.35
        if A["root"] == B["root"]:
            s -= 0.25 if A["q"] == B["q"] else 0.05  # hold the same chord sparingly
        common = len({(A["root"] + i) % 12 for i in QUAL[A["q"]]} & {(B["root"] + i) % 12 for i in QUAL[B["q"]]})
        return s + 0.04 * common

    # beam search for whole progressions, then keep distinct ones
    beam = [((E[0, j] + (0.25 if V[j]["deg"] == 0 else 0.0)), [j]) for j in range(len(V))]
    beam = sorted(beam, key=lambda x: -x[0])[:60]
    for k in range(1, n_steps):
        nb = []
        for sc, path in beam:
            for j in range(len(V)):
                nb.append((sc + E[k, j] + trans(path[-1], j), path + [j]))
        beam = sorted(nb, key=lambda x: -x[0])[:200]
    if n_steps > 1:  # land somewhere that resolves: tonic, or V / VII leading back
        beam = sorted([(sc + (0.2 if V[p[-1]]["deg"] in (0, 4, 6) else 0.0), p) for sc, p in beam], key=lambda x: -x[0])
    picked = []
    for sc, path in beam:
        sig = [V[j]["root"] for j in path]
        if any(sum(a == b for a, b in zip(sig, [V[j]["root"] for j in q])) > max(1, n_steps // 2) for _, q in picked):
            continue
        picked.append((sc, path))
        if len(picked) >= n_options:
            break
    # register: under a high sample (vocals, leads), above a low one (bass)
    low, high = (48, 67) if mid >= 62 else (57, 76)
    best = picked[0][0] if picked else 1
    options = []
    for sc, path in picked:
        prev, chords = None, []
        for k, j in enumerate(path):
            v = _voicing(V[j], prev, low, high)
            prev = v[1:]
            chords.append(dict(name=V[j]["name"], roman=V[j]["roman"], notes=v, fit=round(float(E[k, j]), 2)))
        options.append(dict(chords=chords, score=round(float(sc / (best + 1e-9)), 3),
                            fit=round(float(np.mean([c["fit"] for c in chords])), 2)))
    return dict(key=_spell(tonic, tonic, mode) + ("m" if mode == "minor" else ""), mode=mode, style=style, moods=top_moods,
                timbre=_timbre(row, style), pads=PADS, tempo=round(tempo, 2), step=round(step, 4), steps=n_steps,
                bars_per_chord=bars_per_chord, loop=bool(loop), register=[low, high], options=options)


def write_midi(name, chords, step, tempo, reveal=True):
    """chords: [[midi notes]] one per step -> a .mid in the Ableton User Library (Chords/)."""
    import re
    import subprocess
    import pretty_midi
    pm = pretty_midi.PrettyMIDI(initial_tempo=float(tempo))
    inst = pretty_midi.Instrument(0, name="chords")
    for k, notes in enumerate(chords):
        for n in notes:
            inst.notes.append(pretty_midi.Note(velocity=80, pitch=int(n), start=k * step, end=(k + 1) * step))
    pm.instruments.append(inst)
    dest = C.ABLETON_SAMPLES / "Chords"
    dest.mkdir(parents=True, exist_ok=True)
    f = dest / (re.sub(r'[/:\\*?"<>|]+', "-", name)[:80] + ".mid")
    pm.write(str(f))
    if reveal:
        subprocess.run(["open", "-R", str(f)])
    return dict(path=str(f))
