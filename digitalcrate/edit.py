"""Non-destructive sample editing with provenance.

render() applies an edit (trim / reverse / stretch / pitch / fades / normalize) to a library file.
save() writes the result as a *new* first-class sample under SampleLibrary/Edits/, recording
parent_id (what was edited), root_id (the original mined sample) and the exact ops.
"""
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import soundfile as sf

from . import config as C
from .audio import PITCHES, camelot, key_label

SR = C.SR
PREVIEW_DIR = C.DATA_DIR / "previews"


def _load(rel):
    y, sr = sf.read(str(C.LIB_ROOT / rel), dtype="float32", always_2d=True)
    y = y.T
    if y.shape[0] == 1:
        y = np.repeat(y, 2, 0)
    if sr != SR:
        from scipy.signal import resample_poly
        y = resample_poly(y, SR, sr, axis=1).astype(np.float32)
    return y


def onsets(rel):
    import librosa
    y = _load(rel)
    m = y.mean(0)
    on = librosa.onset.onset_detect(y=m, sr=SR, hop_length=256, backtrack=True, units="time")
    return dict(onsets=[round(float(t), 3) for t in on], dur=round(y.shape[1] / SR, 3))


def clean_params(p):
    return dict(start=float(p.get("start") or 0), end=float(p["end"]) if p.get("end") not in (None, "") else None,
                stretch=float(p.get("stretch") or 1), semis=float(p.get("semis") or 0),
                formant=bool(p.get("formant")), reverse=bool(p.get("reverse")),
                fade_in=float(p.get("fade_in") or 5) / 1000, fade_out=float(p.get("fade_out") or 30) / 1000,
                normalize=bool(p.get("normalize", True)), loop_xfade=float(p.get("loop_xfade") or 0) / 1000,
                tune_key=(p.get("tune_key") or None), tune_strength=float(p.get("tune_strength") if p.get("tune_strength") is not None else 0.8),
                tune_speed=float(p.get("tune_speed") if p.get("tune_speed") is not None else 60),
                tune_detune=float(p.get("tune_detune") or 0), tune_drift=float(p.get("tune_drift") or 0),
                tune_engine=p.get("tune_engine") or "vari")


def render(rel, p):
    p = clean_params(p)
    y = _load(rel)
    a = int(max(0, p["start"]) * SR)
    b = int(p["end"] * SR) if p["end"] else y.shape[1]
    y = y[:, a:max(b, a + 64)].copy()
    if p["reverse"]:
        y = y[:, ::-1].copy()
    if abs(p["stretch"] - 1) > 1e-3 or abs(p["semis"]) > 1e-3:
        from .stretch import shift
        y, _ = shift(y, p["semis"], p["stretch"], engine="rubberband" if p["formant"] else "signalsmith",
                     formant=p["formant"])
    if p.get("tune_key") or p.get("tune_detune") or p.get("tune_drift"):
        from .retune import tune
        y = tune(y, p.get("tune_key") or "C", strength=p["tune_strength"] if p.get("tune_key") else 0,
                 speed_ms=p["tune_speed"], detune_cents=p["tune_detune"], drift_cents=p["tune_drift"],
                 engine=p["tune_engine"])
    n = y.shape[1]
    xf = min(int(p["loop_xfade"] * SR), n // 3)
    if xf > 32:  # seamless loop: crossfade the tail into the head (equal-power), drop separate fades
        t = np.linspace(0, np.pi / 2, xf, dtype=np.float32)
        body = y[:, :-xf].copy()
        body[:, :xf] = body[:, :xf] * np.sin(t) + y[:, -xf:] * np.cos(t)
        y = body
        p = dict(p, fade_in=0, fade_out=0)
    n = y.shape[1]
    fi, fo = min(int(p["fade_in"] * SR), n // 3), min(int(p["fade_out"] * SR), n // 3)
    if fi:
        y[:, :fi] *= np.linspace(0, 1, fi, dtype=np.float32)
    if fo:
        y[:, -fo:] *= np.linspace(1, 0, fo, dtype=np.float32)
    if p["normalize"]:
        y *= 0.891 / (np.abs(y).max() + 1e-9)
    return y, p


def preview(rel, params):
    y, p = render(rel, params)
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha1((rel + json.dumps(p, sort_keys=True)).encode()).hexdigest()[:10]
    out = PREVIEW_DIR / f"{h}.wav"
    sf.write(str(out), y.T, SR, subtype="PCM_24")
    return str(out.relative_to(C.LIB_ROOT))


def clear_previews():
    if PREVIEW_DIR.exists():
        for f in PREVIEW_DIR.glob("*.wav"):
            f.unlink(missing_ok=True)


def _ops_tag(p):
    t = []
    if p["start"] > 0 or p["end"]:
        t.append("cut")
    if p["reverse"]:
        t.append("rev")
    if abs(p["stretch"] - 1) > 1e-3:
        t.append(f"x{p['stretch']:g}")
    if abs(p["semis"]) > 1e-3:
        t.append(f"{p['semis']:+g}st" + ("F" if p["formant"] else ""))
    if p.get("loop_xfade", 0) > 0.001:
        t.append(f"xf{int(p['loop_xfade'] * 1000)}")
    if p.get("tune_key"):
        t.append(f"tuned{p['tune_key']}{int(p.get('tune_strength', 1) * 100)}")
    if p.get("tune_detune"):
        t.append(f"{p['tune_detune']:+g}c")
    if p.get("tune_drift"):
        t.append(f"drift{p['tune_drift']:g}")
    return "-".join(t) or "copy"


def save(rel, params, name=None):
    """Write the edit as a new sample with provenance; returns the new DB row as a dict."""
    from .db import connect
    from .process import MOOD_PROMPTS, _safe
    con = connect()
    parent = con.execute("SELECT s.*, t.artist, t.title FROM samples s JOIN tracks t ON t.id=s.track_id WHERE s.path=?",
                         (rel,)).fetchone()
    if parent is None:
        raise ValueError("edits start from a library sample")
    y, p = render(rel, params)
    return store(parent, rel, y, p, name)


def store(parent, rel, y, p, name=None, override=None, prefix="Edit", folder="Edits"):
    """Write audio derived from `parent` as a new sample with provenance. `override` can set kind/bpm/bars/tag."""
    from .db import connect
    from .process import MOOD_PROMPTS, _safe
    con = connect()
    override = override or {}
    p = dict(dict(start=0.0, end=None, stretch=1.0, semis=0.0, formant=False, reverse=False, fade_in=0, fade_out=0,
                  normalize=True, loop_xfade=0), **p)
    dur = y.shape[1] / SR
    # musical metadata, adjusted for the ops
    pc = (PITCHES.index(parent["key"]) + int(round(p["semis"]))) % 12
    scale = parent["scale"]
    if p.get("tune_key"):
        from .conform import parse_key
        tpc, tsc = parse_key(p["tune_key"])
        if tsc == scale:
            pc = tpc
    cam = camelot(pc, scale)
    chroma = np.roll(np.array(json.loads(parent["chroma"])), int(round(p["semis"])))
    note = parent["note"]
    if note and p["semis"]:
        note = PITCHES[(PITCHES.index(note) + int(round(p["semis"]))) % 12]
    bpm = parent["bpm"] / p["stretch"] if parent["bpm"] else None
    whole = p["start"] <= 0.01 and (p["end"] is None or p["end"] >= parent["dur"] - 0.05)
    if parent["kind"] == "loop" and whole and not p["reverse"]:
        kind, bars = "loop", parent["bars"]
    else:
        kind, bars = ("oneshot" if dur < 1.5 else ("phrase" if parent["category"] == "Vocals" else "free")), None
    subtype = parent["subtype"]
    if parent["category"] == "Vocals" and kind == "oneshot":
        subtype = "Chops"
    kind = override.get("kind", kind)
    bars = override.get("bars", bars)
    bpm = override.get("bpm", bpm)
    if kind == "loop" and parent["category"] not in ("Vocals", "Percussion"):
        subtype = "Loops"
    sid = hashlib.sha1(f"{rel}{json.dumps(p, sort_keys=True)}{time.time()}".encode()).hexdigest()[:6]
    tag = _safe(name, 30) if name else override.get("tag") or _ops_tag(p)
    keystr = "nokey" if parent["key_from"] == "none" else f"{int(cam[:-1]):02d}{cam[-1]}-{key_label(pc, scale)}"
    bpmstr = f"{bpm:.0f}bpm" if bpm else "free"
    fname = f"{prefix}_{keystr}_{bpmstr}_{_safe(parent['artist'], 20)}-{_safe(parent['title'], 24)}_{tag}_{sid}.wav"
    out = C.LIB_ROOT / folder / parent["category"] / fname
    out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out), y.T, SR, subtype="PCM_24")
    # embedding + mood similarities for related-sample matching and the taste model
    from scipy.signal import resample_poly
    from . import models
    cl = models.clap()
    m = y.mean(0)
    if len(m) > SR * 10:
        mid = len(m) // 2
        m = m[mid - SR * 5: mid + SR * 5]
    e = cl.embed_audio([resample_poly(m, 160, 147).astype(np.float32)])[0]
    moods = e @ cl.embed_text(tuple(MOOD_PROMPTS.values())).T
    a = np.abs(y).max(0)
    env = (np.array([float(x.max()) for x in np.array_split(a, 64)]) / (a.max() + 1e-9) * 99).astype(int).tolist()
    root = parent["root_id"] or parent["id"]
    ops = dict(p, name=name, parent_path=rel, **override.get("ops", {}))
    if override.get("tag"):
        ops["tag"] = override["tag"]
    con.execute(
        """INSERT INTO samples(id, track_id, source, rendered_from, category, subtype, kind, start, dur, bpm, bars,
           key, scale, camelot, key_strength, key_from, note, chroma, centroid, flatness, pratio, dominance, drum_leak,
           loudness, quality, clap, type_probs, mood_sims, instrument, path, env, tags, parent_id, root_id, ops)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (sid, parent["track_id"], "edit", parent["rendered_from"], parent["category"], subtype, kind,
         parent["start"] + p["start"], dur, bpm, bars, PITCHES[pc], scale, cam, parent["key_strength"],
         parent["key_from"], note, json.dumps(np.round(chroma, 3).tolist()), parent["centroid"], parent["flatness"],
         parent["pratio"], parent["dominance"], parent["drum_leak"], parent["loudness"], parent["quality"],
         e.astype(np.float16).tobytes(), parent["type_probs"],
         json.dumps(dict(zip(MOOD_PROMPTS, np.round(moods, 4).tolist()))), parent["instrument"],
         str(out.relative_to(C.LIB_ROOT)), json.dumps(env), parent["tags"], parent["id"], root, json.dumps(ops)))
    con.commit()
    return dict(id=sid, path=str(out.relative_to(C.LIB_ROOT)), category=parent["category"], subtype=subtype,
                kind=kind, cam=cam if parent["key_from"] != "none" else "",
                key=(PITCHES[pc] + ("m" if scale == "minor" else "")) if parent["key_from"] != "none" else "",
                bpm=round(bpm) if bpm else 0, dur=round(dur, 1), note=note or "", bars=bars or 0,
                start=round(parent["start"] + p["start"]), env=env, parent=parent["id"], root=root,
                ops=(override.get("tag") or _ops_tag(p)) + (f" · {name}" if name else ""))
