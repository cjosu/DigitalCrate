"""Real pads: sounds that hold one or two chords and keep still, so they loop and can be played from MIDI.

The category "Pads & Atmospheres" used to collect anything long and sustained, which in practice meant mostly
orchestral string passages (three or more chords, moving lines). Those are good samples, just not pads: they now live
in "Strings & Orchestral". A pad here:

  - holds at most 2 distinct chords (a pad rocking between two chords counts),
  - keeps its harmony still (every moment's chroma close to the sample's overall chroma),
  - keeps a steady level (no big swells or decays across it).

Chords come from madmom's deep-chroma chord recognizer (Korzeniowski & Widmer 2016; madmom is BSD, the model CC
BY-NC-SA, the same as the rest of madmom's models): major / minor triads, robust to timbre, about 30 ms a sample.

    analyze(y)            -> dict(chords=[(start, end, "Fm")...], n, still, steady)
    is_pad(a)             -> bool
    where(row, a)         -> (category, subtype) the sample belongs in
    find(y, bar_times)    mining: [(start, end, bars)] stretches of a stem that hold 1-2 chords for 2+ bars
    run()                 the library pass: label every long sustained sample, move the non-pads
"""
import json
from pathlib import Path

import numpy as np

from . import config as C
from .db import connect

STRINGS = "Strings & Orchestral"
PADS = "Pads & Atmospheres"
MAX_CHORDS = 2
MIN_STILL = 0.9    # chroma steadiness (1 = the harmony never moves)
MAX_SWELL = 0.45   # spread of the level (log RMS) over the sounding part
ORCHESTRAL = ("strings", "vocal_choir", "vocal_female", "vocal_male", "vocal_spoken", "brass")

_proc = None


def _procs():
    global _proc
    if _proc is None:
        from madmom.audio.chroma import DeepChromaProcessor
        from madmom.features.chords import DeepChromaChordRecognitionProcessor
        _proc = (DeepChromaProcessor(), DeepChromaChordRecognitionProcessor())
    return _proc


def _name(lab):
    """madmom 'A#:min' -> 'B♭m' style names (flats, as most keys spell them)."""
    if lab == "N":
        return None
    root, q = lab.split(":")
    flat = {"A#": "B♭", "C#": "D♭", "D#": "E♭", "F#": "F♯", "G#": "A♭"}.get(root, root)
    return flat + ("m" if q == "min" else "")


def chords(y, sr=C.SR):
    """[(start, end, name)] for a mono or (channels, n) signal; 'no chord' stretches are left out."""
    from madmom.audio.signal import Signal
    y = np.asarray(y, np.float32)
    if y.ndim > 1:
        y = y.mean(0)
    if sr != 44100:
        import librosa
        y = librosa.resample(y, orig_sr=sr, target_sr=44100)
    dcp, rec = _procs()
    out = []
    for a, b, lab in rec(dcp(Signal(y, sample_rate=44100))):
        n = _name(lab)
        if n is None:
            continue
        if out and out[-1][2] == n and a - out[-1][1] < 0.3:
            out[-1][1] = float(b)
        else:
            out.append([float(a), float(b), n])
    return [(round(a, 2), round(b, 2), n) for a, b, n in out]


def analyze(y, sr=C.SR):
    import librosa
    y = np.asarray(y, np.float32)
    m = y.mean(0) if y.ndim > 1 else y
    ch = chords(m, sr)
    long = {}
    for a, b, n in ch:
        long[n] = long.get(n, 0) + (b - a)
    main = [n for n, d in sorted(long.items(), key=lambda kv: -kv[1]) if d >= 1.0]
    cq = librosa.feature.chroma_cqt(y=m, sr=sr, hop_length=4096)
    rms = librosa.feature.rms(y=m, hop_length=2048)[0]
    on = rms[rms > 0.1 * (rms.max() + 1e-9)]
    w = rms[::2][:cq.shape[1]] if len(rms) >= 2 * cq.shape[1] else np.ones(cq.shape[1])
    cs = cq / (np.linalg.norm(cq, axis=0) + 1e-9)
    act = w > 0.1 * (w.max() + 1e-9)
    if act.sum() < 2:
        act = np.ones_like(act)
    mean = cs[:, act].mean(1)
    mean /= np.linalg.norm(mean) + 1e-9
    pk = int(rms.argmax())
    tail = rms[pk:]
    hold = float(np.median(tail[len(tail) // 2:int(len(tail) * 0.8) + 1]) / (rms.max() + 1e-9)) if len(tail) > 4 else 0.0
    return dict(chords=ch, names=main, n=len(main), still=round(float((mean @ cs[:, act]).mean()), 3),
                steady=round(float(np.std(np.log(on + 1e-6))) if len(on) > 1 else 0.0, 3), hold=round(hold, 3))


MIN_HOLD = 0.5  # a pad one-shot still has half its level well after the peak; a struck key or pluck has died away


def is_pad(a, oneshot=False):
    if oneshot:  # a short sound: what matters is that it sustains
        return a.get("hold", 1.0) >= MIN_HOLD and a["n"] <= MAX_CHORDS
    return a["n"] <= MAX_CHORDS and a["still"] >= MIN_STILL and a["steady"] <= MAX_SWELL


def where(row, a):
    """Pads stay; moving orchestral passages go to Strings & Orchestral; moving synth chords to Chords & Keys; struck
    one-shots (a key, a pluck: they die away) to Chords & Keys."""
    oneshot = row.get("kind") == "oneshot" if hasattr(row, "get") else row["kind"] == "oneshot"
    if is_pad(a, oneshot):
        return PADS, row["subtype"]
    if oneshot:
        return "Chords & Keys", row["subtype"]
    if (row["instrument"] or "") in ORCHESTRAL:
        return STRINGS, row["subtype"]
    return "Chords & Keys", row["subtype"]


# ---------------------------------------------------------------- mining

def _still(m, sr):
    """Chroma steadiness of a mono stretch (as in analyze)."""
    import librosa
    cq = librosa.feature.chroma_cqt(y=m, sr=sr, hop_length=4096)
    cs = cq / (np.linalg.norm(cq, axis=0) + 1e-9)
    mean = cs.mean(1)
    mean /= np.linalg.norm(mean) + 1e-9
    return float((mean @ cs).mean())


def find(y, sr, bar_times=None, min_bars=2, max_bars=8, free_min=6.0, free_max=12.0):
    """Stretches of y (a stem, or the mix) that hold 1-2 chords and keep still. With a reliable tempo: bar-aligned
    (start, end, bars) loops of 2, 4 or 8 bars that start on a chord change (so the jump back is natural); without
    one (much ambient music): (start, end, None) cuts of 6-12 s along the hold."""
    y = np.asarray(y, np.float32)
    m = y.mean(0) if y.ndim > 1 else y
    ch = chords(m, sr)
    bt = np.asarray(bar_times if bar_times is not None else [], float)
    timed = len(bt) >= min_bars + 1
    out = []
    i = 0
    while i < len(ch):
        names, j = {ch[i][2]}, i
        while j + 1 < len(ch) and len(names | {ch[j + 1][2]}) <= MAX_CHORDS and ch[j + 1][0] - ch[j][1] < 1.0:
            j += 1
            names.add(ch[j][2])
        s, e = ch[i][0], ch[j][1]
        i = j + 1
        cut = None
        if timed:
            b0 = int(np.searchsorted(bt, s - 0.15))  # the first bar line at or just after the chord change
            for L in (max_bars, 4, min_bars):
                if b0 + L < len(bt) and bt[b0 + L] <= e + 0.15:
                    cut = (float(bt[b0]), float(bt[b0 + L]), L)
                    break
        elif e - s >= free_min:
            cut = (float(s), float(min(e, s + free_max)), None)
        if cut and _still(m[int(cut[0] * sr):int(cut[1] * sr)], sr) >= MIN_STILL:
            out.append(cut)
    return out


# ---------------------------------------------------------------- library pass

def _db():
    con = connect()
    cols = {r[1] for r in con.execute("PRAGMA table_info(samples)")}
    for c, t in (("chords", "TEXT"), ("pad_still", "REAL"), ("pad_steady", "REAL")):
        if c not in cols:
            con.execute(f"ALTER TABLE samples ADD COLUMN {c} {t}")
    return con


def run(redo=False, move=True):
    """Label the chords of every long sustained sample, and move the ones that aren't pads (unless you moved them
    yourself: manual recategorisations always win)."""
    from .audio import decode
    from .recat import move_sample, overrides
    con = _db()
    q = f"""SELECT * FROM samples WHERE (category IN (?,?) AND kind != 'oneshot' OR category=? AND kind='oneshot')
            {'' if redo else 'AND chords IS NULL'}"""
    rows = con.execute(q, (PADS, STRINGS, PADS)).fetchall()
    keep = overrides()
    print(f"TASK sorting real pads from {len(rows)} sustained samples", flush=True)
    moved = {PADS: 0, STRINGS: 0, "Chords & Keys": 0}
    for k, r in enumerate(rows, 1):
        f = C.LIB_ROOT / r["path"]
        try:
            a = analyze(decode(f)) if f.exists() else None
        except Exception as e:
            print(f"    {r['path']}: {str(e)[:80]}", flush=True)
            a = None
        if a:
            con.execute("UPDATE samples SET chords=?, pad_still=?, pad_steady=? WHERE id=?",
                        (json.dumps(a["chords"]), a["still"], a["steady"], r["id"]))
            cat, sub = where(dict(r), a)
            moved[cat] += 1
            if move and cat != r["category"] and r["id"] not in keep:
                try:
                    move_sample(con, con.execute("SELECT * FROM samples WHERE id=?", (r["id"],)).fetchone(), cat, sub)
                except Exception as e:
                    print(f"    couldn't move {r['path']}: {str(e)[:80]}", flush=True)
        if k % 50 == 0:
            con.commit()
            print(f"pads: {k}/{len(rows)} [{moved[PADS]} pads]", flush=True)
    con.commit()
    print(f"TASK DONE {moved[PADS]} pads · {moved[STRINGS]} strings & orchestral · {moved['Chords & Keys']} chords & keys",
          flush=True)


# ---------------------------------------------------------------- playable + MIDI

PC = {"C": 0, "D♭": 1, "D": 2, "E♭": 3, "E": 4, "F": 5, "F♯": 6, "G": 7, "A♭": 8, "A": 9, "B♭": 10, "B": 11}


def _pc(name):
    return PC[name[:-1] if name.endswith("m") else name]


def root_note(chs):
    """The MIDI note that plays the pad as recorded: its longest chord's root, near middle C (60)."""
    if not chs:
        return 60
    long = {}
    for a, b, n in chs:
        long[n] = long.get(n, 0) + b - a
    pc = _pc(max(long, key=long.get))
    return 60 + pc if pc < 6 else 48 + pc


def chord_midi(chs, out, bpm=None, dur=None):
    """The pad's own chords as a MIDI clip: close triads around middle C, one per chord, as long as it holds."""
    import pretty_midi
    pm = pretty_midi.PrettyMIDI(initial_tempo=float(bpm or 120))
    inst = pretty_midi.Instrument(program=89, name="pad chords")
    for a, b, n in chs:
        r = _pc(n)
        notes = [48 + r, 48 + r + (3 if n.endswith("m") else 4), 48 + r + 7]
        notes = [p + 12 if p < 52 else p for p in notes]  # keep it close, between E3 and B4
        for p in sorted(notes):
            inst.notes.append(pretty_midi.Note(velocity=80, pitch=p, start=float(a), end=float(b)))
    pm.instruments.append(inst)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    pm.write(str(out))
    return out


def playable(rel, reveal=True):
    """A pad as an instrument for Live: the WAV (its sustain loop baked in and in a smpl chunk, or looping whole if
    it's a bar loop), a Simpler preset tuned to its chord so each key plays it from that note, and its chords as
    MIDI. Into the Ableton samples folder, under Playable pads/."""
    import shutil
    import soundfile as sf
    from .ableton import simpler
    from .loopfind import export_loop, write_smpl
    con = _db()
    r = con.execute("SELECT * FROM samples WHERE path=?", (rel,)).fetchone()
    if r is None:
        raise ValueError("no such sample")
    chs = json.loads(r["chords"]) if r["chords"] else None
    if chs is None:
        from .audio import decode
        chs = analyze(decode(C.LIB_ROOT / rel))["chords"]
    root = root_note(chs)
    dest = C.ABLETON_SAMPLES / "Playable pads"
    dest.mkdir(parents=True, exist_ok=True)
    wav = dest / Path(rel).name
    shutil.copy2(C.LIB_ROOT / rel, wav)
    n = sf.info(str(wav)).frames
    try:
        if r["kind"] == "loop":  # a bar loop: the whole file repeats
            write_smpl(wav, 0, n - 1)
            adv = simpler(wav, wav.stem[:60], wav.with_suffix(".adv"), loop=(0, n - 1), root=root)
        elif r["loop_q"]:
            adv = export_loop(wav, r, n, root=root)
        else:
            adv = simpler(wav, wav.stem[:60], wav.with_suffix(".adv"), root=root)
    except FileNotFoundError:  # no Live installed: the WAV (with its loop) and the chords still help
        adv = None
    mid = chord_midi(chs, wav.with_name(wav.stem + " chords.mid"), r["bpm"])
    if reveal:
        import subprocess
        subprocess.run(["open", "-R", str(adv or wav)])
    names = [n for _, _, n in chs]
    return dict(dest=str(dest), wav=wav.name, adv=adv.name if adv else None, midi=mid.name, root=root,
                chords=[n for k, n in enumerate(names) if k == 0 or n != names[k - 1]])
