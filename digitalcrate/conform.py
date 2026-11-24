"""Project mode: render any library sample conformed to a target key + tempo, cached (engines: stretch.py).

Pitch: the smallest shift (-6..+5 st) that puts the sample's tonic on the project's, matching relative
major/minor (a C-major pad in an A-minor project is left alone). Atonal samples and percussion are not pitched.
Tempo: only loops are stretched (to the nearest of ×½ / ×1 / ×2 of the project tempo); phrases, one-shots and
free-time pads keep their natural timing. Unstretched samples are Re-Pitched (tape-style: a sample pitched up gets
a little shorter); loops use Signalsmith Stretch so they stay bar-exact.
"""
import hashlib
import json
import re

import numpy as np
import soundfile as sf

from . import config as C
from .audio import PITCHES, camelot, key_label, pc_of
from .db import connect

CACHE = C.DATA_DIR / "conform"


def parse_key(k):
    """'Fm', 'F minor', 'F#', '8A' -> (pc, 'major'|'minor')"""
    k = k.strip()
    m = re.match(r"^(\d{1,2})([AB])$", k, re.I)
    if m:  # Camelot
        n, l = int(m.group(1)), m.group(2).upper()
        for pc in range(12):
            for sc in ("major", "minor"):
                if camelot(pc, sc) == f"{n}{l}":
                    return pc, sc
    m = re.match(r"^([A-Ga-g][#b]?)\s*(m|min|minor|maj|major)?$", k)
    if not m:
        raise ValueError(f"can't read key '{k}'")
    return pc_of(m.group(1).capitalize()), ("minor" if (m.group(2) or "").startswith("m") and m.group(2) not in ("maj", "major") else "major")


def lookup(rel):
    con = connect()
    tq = "SELECT s.*, t.bpm AS track_bpm, t.tempo_ok FROM samples s JOIN tracks t ON t.id=s.track_id"
    r = con.execute(f"{tq} WHERE s.path=?", (rel,)).fetchone()
    shift = 0
    if r is None:  # a variation: inherit from its source, shifted by the variation's own pitch
        r = con.execute(f"{tq} JOIN variants v ON v.sample_id=s.id WHERE v.path=?", (rel,)).fetchone()
        ch = con.execute("SELECT chain FROM variants WHERE path=?", (rel,)).fetchone()
        mm = re.search(r"(?:pitch|tape|vari)([+-]\d+)", ch["chain"] if ch else "")
        shift = int(mm.group(1)) if mm else 0
        if r is not None:
            r = dict(r, kind="free" if r["kind"] == "loop" else r["kind"])  # variations aren't bar-exact any more
    return (dict(r), shift) if r is not None else (None, 0)


def plan(row, shift, key=None, bpm=None, src=None):
    """-> (semitones, time_ratio, info) for conforming this sample."""
    semis, time, info = 0, 1.0, {}
    if key and row and row["key_from"] != "none" and row["category"] != "Percussion":
        tpc, tsc = parse_key(key)
        spc = (PITCHES.index(row["key"]) + shift) % 12
        if row["scale"] != tsc:  # compare against the relative key of the same mode
            tpc = (tpc + 9) % 12 if row["scale"] == "minor" else (tpc + 3) % 12
        semis = ((tpc - spc + 6) % 12) - 6
        info["key"] = key_label((spc + semis) % 12, row["scale"])
    if bpm and src and row and row["category"] != "Percussion":
        # the clip's own pulse, measured in the sketchpad ("fit to tempo"): stretch it onto the project tempo
        mult = min((0.5, 1, 2), key=lambda m: abs(np.log(bpm / (src * m))))
        r_ = (src * mult) / bpm
        if 0.6 <= r_ <= 1.6:
            time = r_
            info["bpm"] = bpm
    elif bpm and row and row["kind"] == "loop" and row["bpm"]:
        src = float(row["bpm"])
        mult = min((0.5, 1, 2), key=lambda m: abs(np.log(bpm / (src * m))))
        time = (src * mult) / bpm
        info["bpm"] = bpm
    elif bpm and row and row["kind"] in ("phrase", "free") and row["category"] != "Percussion" \
            and row.get("tempo_ok") and row.get("track_bpm"):
        # phrases and free clips keep their song's pulse: stretch them to the project tempo too, when the
        # song's tempo was detected reliably and the stretch is gentle enough to sound clean
        src = float(row["track_bpm"])
        mult = min((0.5, 1, 2), key=lambda m: abs(np.log(bpm / (src * m))))
        r_ = (src * mult) / bpm
        if 0.7 <= r_ <= 1.4:
            time = r_
            info["bpm"] = bpm
    return semis, time, info


def render(rel, key=None, bpm=None, src=None):
    """Conformed copy of a library file -> absolute cache path (rendered once)."""
    row, shift = lookup(rel)
    semis, time, info = plan(row, shift, key, bpm, src)
    if semis == 0 and abs(time - 1) < 1e-3:
        return C.LIB_ROOT / rel, dict(info, semis=0, time=1, length=1)
    CACHE.mkdir(parents=True, exist_ok=True)
    mt = (C.LIB_ROOT / rel).stat().st_mtime if (C.LIB_ROOT / rel).exists() else 0  # a re-cut file renders anew
    h = hashlib.sha1(f"{rel}|{mt}|{semis}|{time:.5f}|v3".encode()).hexdigest()[:14]
    out = CACHE / f"{h}.wav"
    if not out.exists():
        from .edit import _load
        from .stretch import shift as engine
        y = _load(rel)
        # loops, and anything being moved to the project tempo, need an exact length -> Signalsmith;
        # a key change alone -> Re-Pitch (tape-style: pitch and length move together; won the blind test)
        loop = row["kind"] == "loop" or abs(time - 1) > 1e-3
        z, _ = engine(y, semis, time if loop else 1.0, engine="signalsmith" if loop else "repitch")
        if row["kind"] == "loop":  # keep loops bar-exact after the stretch
            n = int(round(y.shape[1] * time))
            z = z[:, :n] if z.shape[1] >= n else np.pad(z, ((0, 0), (0, n - z.shape[1])))
        z *= min(1.0, 0.891 / (np.abs(z).max() + 1e-9))
        tmp = out.with_suffix(".tmp.wav")
        sf.write(str(tmp), z.T, C.SR, subtype="PCM_24")
        tmp.rename(out)
    loop = row["kind"] == "loop" or abs(time - 1) > 1e-3
    eng = "signalsmith" if loop else "repitch"
    length = time if loop else 2 ** (-semis / 12)  # Re-Pitch changes the length with the pitch
    return out, dict(info, semis=semis, time=round(time, 4), length=round(length, 5), engine=eng)


def conformed_name(rel, info):
    """File name for an exported conformed copy: swap the key/bpm tokens, mark it."""
    name = re.sub(r"\.wav$", "", rel.split("/")[-1])
    tag = []
    if info.get("semis"):
        tag.append(f"{info['semis']:+d}st")
    if info.get("bpm"):
        tag.append(f"{info['bpm']:g}bpm")
    if info.get("key"):
        tag.append(info["key"].replace(" ", ""))
    return f"{name}__{'_'.join(tag) or 'asis'}.wav"


PULSE_CACHE = C.DATA_DIR / "pulse_cache.json"
PULSE_CONF = 2.75


def pulse(rel):
    """Does this clip have a steady pulse, and at what tempo? Essentia's RhythmExtractor2013 (multifeature): a pulse
    needs confidence >= 2.5 (its scale runs 0-5.3) and steady beats. Clips without one are pads/textures with
    nothing to line up. Cached per file (the yes/no is re-decided on every call, so the cutoff can be tuned).
    2.75: clear pulses (plucked keys, bossa guitar) pass; loose fingerpicking and swells (2.2-2.6) don't."""
    import json
    cache = json.loads(PULSE_CACHE.read_text()) if PULSE_CACHE.exists() else {}
    if rel in cache:
        c = cache[rel]
        return dict(c, ok=bool(c["conf"] >= PULSE_CONF and c["steady"] <= 0.06))
    import essentia.standard as es
    from scipy.signal import resample_poly
    from .edit import _load
    m = _load(rel).mean(0).astype(np.float32)
    if C.SR != 44100:
        m = resample_poly(m, 44100, C.SR).astype(np.float32)
    out = dict(bpm=0.0, conf=0.0, steady=9.0, ok=False)
    if len(m) > 44100 * 2:
        bpm, beats, conf, _, _ = es.RhythmExtractor2013(method="multifeature")(m)
        ibi = np.diff(beats)
        steady = float(np.std(ibi) / np.mean(ibi)) if len(ibi) > 3 else 9.0
        out = dict(bpm=round(float(bpm), 1), conf=round(float(conf), 2), steady=round(steady, 3),
                   ok=bool(conf >= PULSE_CONF and steady <= 0.06))
    cache[rel] = out
    PULSE_CACHE.write_text(json.dumps(cache))
    return out
