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


GEN_ROMAN = ["I", "bII", "II", "bIII", "III", "IV", "bV", "V", "bVI", "VI", "bVII", "VII"]


def _roman(root, q, tonic):
    r = GEN_ROMAN[(root - tonic) % 12]
    minorish = (q.startswith("m") and not q.startswith("maj")) or q == "dim"
    if minorish:
        r = r.replace("I", "i").replace("V", "v")
    return r + SUFFIX.get(q, q)


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
    """Bass root + upper voices, like a keyboard player: the root lives in the bass, so the upper voices leave it out
    once there are 4+ tones, and drop the 5th too for 9ths/11ths/13ths. The upper voices take the inversion closest
    to the previous chord (smooth voice leading) within about two octaves above `low`."""
    ivs = list(QUAL[ch["q"]])
    if len(ivs) >= 4:
        ivs = [i for i in ivs if i % 12 != 0]
    if len(ivs) >= 5:
        ivs = [i for i in ivs if i % 12 != 7]
    pcs = [(ch["root"] + i) % 12 for i in ivs]
    top = max(high, low + 24)
    cands = []
    for r in range(len(pcs)):  # each inversion: start from a different chord tone, stack upwards
        order = pcs[r:] + pcs[:r]
        for base in range(low - 2, top):
            notes, n = [], base
            for pc in order:
                while n % 12 != pc:
                    n += 1
                notes.append(n)
                n += 1
            if notes[0] >= low - 2 and notes[-1] <= top:
                cands.append(notes)
    def cost(v):
        if prev:
            return sum(min(abs(a - b) for b in prev) for a in v) + 0.5 * abs(np.mean(v) - np.mean(prev)) + 0.05 * (v[-1] - v[0])
        return abs(np.mean(v) - (low + high) / 2) + 0.05 * (v[-1] - v[0])
    best = min(cands, key=cost) if cands else None
    if best is None:  # stack upwards from low, each tone on its own pitch class
        best, n = [], low
        for pc in pcs:
            while n % 12 != pc:
                n += 1
            best.append(n)
            n += 1
    bass = ch["root"] + 12 * ((low - 12) // 12)
    while bass >= low - 3:
        bass -= 12
    return [bass] + sorted(best)


def own_chords(rel, win=0.5):
    """The sample's own chords: (start, end, root, quality) per change, from CQT chroma in short windows; plus how much
    of the sounding time carries a confident chord. Gaps take the chord before them."""
    import librosa
    from .edit import _load
    from .midi import CHORDS as MCH, NAMES as MN
    y = _load(rel).mean(0)
    sr, hop = C.SR, int(0.1 * C.SR)
    ch = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop)
    rms = librosa.feature.rms(y=y, frame_length=2 * hop, hop_length=hop)[0][: ch.shape[1]]
    T = np.arange(ch.shape[1]) * 0.1
    a = rms / (rms.max() + 1e-9)
    segs, active, sure = [], 0, 0
    for t0 in np.arange(0, T[-1] + 1e-9, win):
        m = (T >= t0) & (T < t0 + win)
        if not m.any() or a[m].mean() < 0.05:
            continue
        active += 1
        w = (ch[:, m] * a[m]).sum(1)
        w = w / (w.sum() + 1e-9)
        best, bs = None, 0.35
        for root in range(12):
            for q, iv in MCH.items():
                tpl = np.zeros(12); tpl[[(root + i) % 12 for i in iv]] = 1
                sc = (w * tpl).sum() - 0.6 * (w * (1 - tpl)).sum() - 0.02 * len(iv)
                if sc > bs:
                    best, bs = (root, q), sc
        if best is None:
            if segs:
                segs[-1][1] = t0 + win
            continue
        sure += 1
        if segs and segs[-1][2:] == list(best):
            segs[-1][1] = t0 + win
        else:
            segs.append([t0, t0 + win, *best])
    if segs:
        segs[0][0] = 0.0
        for k in range(1, len(segs)):
            segs[k - 1][1] = segs[k][0]
        segs[-1][1] = len(y) / sr
    # very short blips (one window between two equal chords) fold into their neighbours
    out = []
    for sg in segs:
        if out and sg[1] - sg[0] <= win + 1e-6 and out[-1][2:] == sg[2:]:
            out[-1][1] = sg[1]
        elif out and sg[1] - sg[0] <= win + 1e-6 and len(out) and segs.index(sg) + 1 < len(segs) and segs[segs.index(sg) + 1][2:] == out[-1][2:]:
            out[-1][1] = sg[1]
        else:
            out.append(list(sg))
    # back-to-back chords on the same root and of the same kind (Fm9 then Fm7) are one chord: keep the longer label
    merged = []
    for sg in out:
        if merged and merged[-1][2] == sg[2] and _family(merged[-1][3]) == _family(sg[3]):
            if sg[1] - sg[0] > merged[-1][1] - merged[-1][0]:
                merged[-1][3] = sg[3]
            merged[-1][1] = sg[1]
        else:
            merged.append(sg)
    return merged, (sure / active if active else 0.0)


FAMILY = {"min": ["m9", "m11", "m7", "madd9", "m"], "maj": ["maj9", "maj7", "add9", ""], "dom": ["9", "13", "7"],
          "sus": ["sus2", "sus4"], "dim": ["m7b5", "dim"]}


def _family(q):
    if q in ("7",):
        return "dom"
    if q.startswith("sus"):
        return "sus"
    if q in ("dim", "m7b5"):
        return "dim"
    if q.startswith("m") and not q.startswith("maj"):
        return "min"
    return "maj"


def _follow_vocab(root, q, style, P):
    """Chords for one of the sample's own chords: the same chord in this style's colours, plus substitutes that share
    at least three of its notes (relative / mediant chords) — the ones whose tones the sample's sound actually fits."""
    fam = _family(q)
    own = {(root + i) % 12 for i in (QUAL.get(q) or QUAL["m" if fam == "min" else ""])}
    pref = STYLE_QUALS[style]["min" if fam == "min" else "dom" if fam == "dom" else "maj"]
    same = [dict(root=root, q=qq, own=True) for qq in dict.fromkeys(pref + FAMILY.get(fam, [])) if qq in QUAL][:4]
    subs = []
    for r2 in range(12):
        if r2 == root:
            continue
        for f2 in ("min", "maj"):
            for qq in STYLE_QUALS[style][f2][:2]:
                t2 = {(r2 + i) % 12 for i in QUAL[qq]}
                if len(t2 & own) >= 3:
                    subs.append(dict(root=r2, q=qq, own=False))
    subs = sorted(subs, key=lambda c: -_fit(c, P))[:6]
    return same + subs


def _suggest_following(row, segs, style, notes, tonic, mode, n_options):
    """Options for a sample with its own chord changes: chords change where the sample's do."""
    rel = row["path"]
    total = float(row["dur"] or segs[-1][1])
    import librosa
    from .edit import _load
    y = _load(rel).mean(0)
    chroma = librosa.feature.chroma_cqt(y=y, sr=C.SR, hop_length=2048)
    fr = librosa.frames_to_time(np.arange(chroma.shape[1]), sr=C.SR, hop_length=2048)
    P = []
    for a, b, *_ in segs:
        m = (fr >= a) & (fr < b)
        c = chroma[:, m].mean(1) if m.any() else np.zeros(12)
        c = np.where(c > np.percentile(c, 50), c, 0)
        P.append(c / (c.sum() + 1e-9))
    V = [_follow_vocab(r, q, style, P[k]) for k, (a, b, r, q) in enumerate(segs)]
    E = [[_fit(c, P[k]) for c in V[k]] for k in range(len(segs))]

    def common(a, b):
        return len({(a["root"] + i) % 12 for i in QUAL[a["q"]]} & {(b["root"] + i) % 12 for i in QUAL[b["q"]]})

    def run(only_own=None):
        beam = [(E[0][j], [j]) for j in range(len(V[0])) if only_own is None or V[0][j]["own"] == only_own]
        for k in range(1, len(segs)):
            nb = []
            for sc, path in beam:
                for j, c in enumerate(V[k]):
                    if only_own is not None and c["own"] != only_own:
                        continue
                    prev = V[k - 1][path[-1]]
                    tr = 0.05 * common(prev, c) - (0.15 if (prev["root"], prev["q"]) == (c["root"], c["q"]) else 0)
                    nb.append((sc + E[k][j] + tr, path + [j]))
            beam = sorted(nb, key=lambda x: -x[0])[:200]
        return beam
    picks = []
    fol = run(True)
    if fol:
        picks.append(("follows its chords", fol[0]))
    roots = lambda path: [V[k][j]["root"] for k, j in enumerate(path)]
    for sc, path in run(None):
        rp = roots(path)
        # different enough: from "follows" in at least half the chords, and from every other option somewhere
        if picks and sum(a != b for a, b in zip(rp, roots(picks[0][1][1]))) < max(1, (len(segs) + 1) // 2):
            continue
        if any(rp == roots(q) for _, (s2, q) in picks[1:]):
            continue
        picks.append(("reharmonised", (sc, path)))
        if len(picks) >= n_options:
            break
    mid = float(np.median([p for _, _, p, _ in notes])) if notes else 64.0
    low, high = (48, 67) if mid >= 62 else (57, 76)
    best = max((p[1][0] for p in picks), default=1)
    options = []
    for label, (sc, path) in picks:
        prev, chords = None, []
        for k, j in enumerate(path):
            c = V[k][j]
            ch = dict(root=c["root"], q=c["q"])
            v = _voicing(ch, prev, low, high)
            prev = v[1:]
            # the sample changes key as it goes, so say which of its chords this sits on rather than a Roman numeral
            chords.append(dict(name=_spell(c["root"], tonic, mode) + c["q"], roman="on " + _spell(segs[k][2], tonic, mode) + segs[k][3],
                               notes=v, fit=round(float(E[k][j]), 2), t=round(segs[k][0], 3),
                               d=round(segs[k][1] - segs[k][0], 3)))
        options.append(dict(label=label, chords=chords, score=round(float(sc / (best + 1e-9)), 3),
                            fit=round(float(np.mean([c["fit"] for c in chords])), 2)))
    own = [_spell(r, tonic, mode) + q for a, b, r, q in segs]
    return options, own, total, (low, high)


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
    # a sample with chords of its own (keys, pads): follow *its* changes and harmony, not a fixed key on a grid
    if row["category"] in ("Chords & Keys", "Pads & Atmospheres", "Vocal Atmospheres"):
        segs, sure = own_chords(rel)
        if segs and sure >= 0.6:
            options, own, total, reg = _suggest_following(row, segs, style, notes, tonic, mode, n_options)
            if options:
                return dict(key=_spell(tonic, tonic, mode) + ("m" if mode == "minor" else ""), mode=mode, style=style,
                            moods=top_moods, timbre=_timbre(row, style), pads=PADS, tempo=round(tempo, 2), step=0,
                            steps=len(segs), bars_per_chord=bars_per_chord, loop=bool(loop), register=list(reg),
                            follows=True, own=own, total=round(total, 3), options=options)
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


def write_midi(name, chords, step, tempo, reveal=True, times=None, bass=None):
    """chords: [[midi notes]] one per step (or at times=[[start, length]]) -> a .mid in the User Library (Chords/).
    bass: [[pitch, start, length, velocity]] for a second track (the bassline from the chords panel)."""
    import re
    import subprocess
    import pretty_midi
    pm = pretty_midi.PrettyMIDI(initial_tempo=float(tempo))
    inst = pretty_midi.Instrument(0, name="chords")
    for k, notes in enumerate(chords):
        for n in notes:
            a, d = times[k] if times else (k * step, step)
            inst.notes.append(pretty_midi.Note(velocity=80, pitch=int(n), start=float(a), end=float(a) + float(d)))
    pm.instruments.append(inst)
    if bass:
        b = pretty_midi.Instrument(33, name="bass")
        for n, a, d, *v in bass:
            b.notes.append(pretty_midi.Note(velocity=int(v[0]) if v else 90, pitch=int(n), start=float(a), end=float(a) + float(d)))
        pm.instruments.append(b)
    dest = C.ABLETON_SAMPLES / "Chords"
    dest.mkdir(parents=True, exist_ok=True)
    f = dest / (re.sub(r'[/:\\*?"<>|]+', "-", name)[:80] + ".mid")
    pm.write(str(f))
    if reveal:
        subprocess.run(["open", "-R", str(f)])
    return dict(path=str(f))
