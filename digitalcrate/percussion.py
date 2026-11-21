"""Percussion mining: drum one-shots (including clean combined strikes like snare+hat) and drum loops.

Pipeline per track:
  decode -> Demucs drums stem -> MDX23C DrumSep (kick/snare/toms/hh/ride/crash) used for LABELLING only
  -> onsets on the full drum stem; each hit = onset .. next onset; label = pieces striking together
  -> CLAP refines (tom vs hand drum vs wood/metal, snare vs rim/clap, closed/open hat vs shaker)
  -> one-shots rendered from the drum stem (or the original mix when drums are alone)
  -> loops (1/2/4 bars): Breaks (drums alone in the mix), Full Kit, Tops (kick removed), Percussion; swing %.
"""
import hashlib
import json
import logging
import os
import tempfile
import time
import traceback

import numpy as np
import librosa
import soundfile as sf
from tqdm import tqdm

from . import config as C
from .audio import decode, write_wav, to_mono48, PITCHES
from .analyze import track_tempo_key, SourceFeat, bar_starts
from .db import connect
from . import models

SR = C.SR
HOP = 256
DRUMSEP = "MDX23C-DrumSep-aufr33-jarredou.ckpt"

PERC_PROMPTS = {
    "kick": "a kick drum hit", "snare": "a snare drum hit", "rim": "a rimshot or side stick click",
    "clap": "a hand clap", "hat_closed": "a closed hi-hat tick", "hat_open": "an open hi-hat",
    "shaker": "a shaker or tambourine", "ride": "a ride cymbal ping", "crash": "a crash cymbal",
    "tom": "a tom drum hit", "hand_drum": "a conga, bongo or djembe hand drum hit",
    "woodmetal": "a cowbell, woodblock, clave or bell", "orchestral": "a timpani or orchestral bass drum",
    "hand_loop": "hand percussion groove, congas and bongos", "kit_loop": "a drum kit beat",
}
PK = list(PERC_PROMPTS)

ONE_SHOT_SUBTYPES = ["Kick", "Snare", "Rim & Clap", "Hat Closed", "Hat Open", "Ride", "Crash", "Tom", "Hand Drum",
                     "Shaker & Tamb", "Wood & Metal", "Orchestral", "Kick + Hat", "Kick + Snare", "Snare + Hat",
                     "Kick + Cymbal", "Snare + Cymbal", "Perc + Hat", "Other Combos"]
LOOP_SUBTYPES = ["Breaks", "Full Kit", "Tops", "Percussion Loops"]
SUBTYPES = ONE_SHOT_SUBTYPES + LOOP_SUBTYPES
PREFIX = {s: s.replace(" + ", "").replace(" & ", "").replace(" ", "") for s in SUBTYPES}
CAP = dict(pure=3, combo=2, Breaks=3, **{"Full Kit": 3, "Tops": 2, "Percussion Loops": 2})

_sep = None


def drumsep(drums):
    """Split a drum stem into kick/snare/toms/hh/ride/crash (mono arrays)."""
    global _sep
    from audio_separator.separator import Separator
    tmp = tempfile.mkdtemp(dir=str(C.DATA_DIR))
    if _sep is None:
        _sep = Separator(model_file_dir=str(C.MODELS_DIR), output_dir=tmp, output_format="WAV",
                         log_level=logging.WARNING)
        _sep.load_model(DRUMSEP)
    _sep.output_dir = tmp
    if getattr(_sep, "model_instance", None) is not None:
        _sep.model_instance.output_dir = tmp
    src = os.path.join(tmp, "drums.wav")
    sf.write(src, drums.T, SR, subtype="FLOAT")
    files = _sep.separate(src)
    out = {}
    for f in files:
        k = f.split("(")[1].split(")")[0].lower()
        a, _ = sf.read(os.path.join(tmp, os.path.basename(f)), dtype="float32", always_2d=True)
        out[k] = a.T
        os.unlink(os.path.join(tmp, os.path.basename(f)))
    os.unlink(src)
    os.rmdir(tmp)
    n = drums.shape[1]
    return {k: np.pad(v, ((0, 0), (0, max(0, n - v.shape[1]))))[:, :n] for k, v in out.items()}


def _rmsdb(v):
    return 20 * np.log10(librosa.feature.rms(y=v, frame_length=1024, hop_length=HOP)[0] + 1e-9)


def _label(pieces):
    """pieces: set of drumsep pieces striking together -> (subtype-ish family, is_combo)."""
    p = set(pieces)
    cym = p & {"crash", "ride"}
    if p == {"kick"}: return "kick", False
    if p == {"snare"}: return "snare", False
    if p == {"toms"}: return "toms", False
    if p == {"hh"}: return "hh", False
    if p == {"ride"}: return "Ride", False
    if p == {"crash"}: return "Crash", False
    if {"kick", "snare"} <= p: return "Kick + Snare", True
    if "kick" in p and cym: return "Kick + Cymbal", True
    if "snare" in p and cym: return "Snare + Cymbal", True
    if p == {"kick", "hh"}: return "Kick + Hat", True
    if p == {"snare", "hh"}: return "Snare + Hat", True
    if p == {"toms", "hh"}: return "Perc + Hat", True
    if "kick" in p: return ("Kick" if len(p - {"kick", "toms"}) == 0 else "Other Combos"), len(p) > 1
    return "Other Combos", True


def _refine(fam, probs, dur):
    q = dict(zip(PK, probs))
    best = lambda ks: max(ks, key=lambda k: q[k])
    if fam == "kick":
        return "Orchestral" if q["orchestral"] > q["kick"] * 3 and dur > 0.4 else "Kick"
    if fam == "snare":
        return {"snare": "Snare", "rim": "Rim & Clap", "clap": "Rim & Clap"}[best(["snare", "rim", "clap"])]
    if fam == "toms":
        b = best(["tom", "hand_drum", "woodmetal", "orchestral"])
        if b == "orchestral" and not (q["orchestral"] > 3 * max(q["tom"], q["hand_drum"]) and dur > 0.4):
            b = best(["tom", "hand_drum", "woodmetal"])
        return {"tom": "Tom", "hand_drum": "Hand Drum", "woodmetal": "Wood & Metal", "orchestral": "Orchestral"}[b]
    if fam == "hh":
        b = best(["hat_closed", "hat_open", "shaker"])
        if b == "shaker":
            return "Shaker & Tamb"
        return "Hat Open" if (b == "hat_open" or dur > 0.28) else "Hat Closed"
    return fam


def _tuning(y, fam):
    """Rough pitch for tuned drums: strongest low-frequency spectral peak."""
    m = y.mean(0)[: int(0.25 * SR)]
    if len(m) < 2048:
        return None
    spec = np.abs(np.fft.rfft(m * np.hanning(len(m))))
    freqs = np.fft.rfftfreq(len(m), 1 / SR)
    lo, hi = (30, 200) if fam in ("Kick", "Orchestral") else (60, 900)
    band = (freqs >= lo) & (freqs <= hi)
    if not band.any():
        return None
    f = freqs[band][np.argmax(spec[band])]
    return PITCHES[int(round(librosa.hz_to_midi(f))) % 12]


def _swing(y, bpm):
    """Swing % from onset positions of off-beat 16ths (50 = straight, ~66 = triplet swing)."""
    on = librosa.onset.onset_detect(y=y.mean(0), sr=SR, hop_length=HOP, units="time")
    if len(on) < 6 or not bpm:
        return None
    s16 = on / (60 / bpm / 4)
    off = (s16 % 2)
    off = off[(off > 0.6) & (off < 1.6)]
    if len(off) < 3:
        return None
    return float(np.clip(50 * np.median(off), 45, 75))


def _loop_windows(bar_times, bpm, s, e):
    out = []
    bar = 240 / bpm
    for L in (4, 2, 1):
        idx = np.flatnonzero((bar_times >= s - 0.05) & (bar_times + L * bar <= e + 0.1))
        last = -1e9
        for i in idx:
            t0 = bar_times[i]
            t1 = bar_times[i + L] if i + L < len(bar_times) else t0 + L * bar
            if t0 >= last and abs((t1 - t0) - L * bar) < 0.25 * bar:
                out.append((t0, t1, L))
                last = t1
    return out


def process_track(con, row, verbose=True):
    t0 = time.time()
    y = decode(row["path"])
    tk = track_tempo_key(y)
    stems = models.separate(y)
    drums = stems["drums"]
    mixdb = _rmsdb(y.mean(0))
    rel = {k: _rmsdb(v.mean(0)) - mixdb for k, v in stems.items()}
    n = len(mixdb)
    rel = {k: v[:n] for k, v in rel.items()}
    if np.mean(rel["drums"] > -15) < 0.05:
        con.execute("UPDATE tracks SET drums_done=1 WHERE id=?", (row["id"],))
        con.commit()
        return 0  # no meaningful drums
    pieces = drumsep(drums)
    pdb = {k: _rmsdb(v.mean(0))[:n] for k, v in pieces.items()}
    D = _rmsdb(drums.mean(0))[:n]
    peak = {k: np.percentile(v, 99.5) for k, v in pdb.items()}
    loud = np.percentile(D, 99)
    alone = lambda f0, f1: all(np.percentile(rel[k][f0:f1], 90) < C.NEGLIGIBLE_REL_DB for k in ("bass", "other", "vocals"))

    # ---------- one-shots
    on = librosa.onset.onset_detect(y=drums.mean(0), sr=SR, hop_length=HOP, backtrack=True, units="frames", delta=0.08)
    hits = []
    for i, f0 in enumerate(on):
        f1 = on[i + 1] if i + 1 < len(on) else n
        if D[min(n - 1, f0 + 3)] < loud - 30:
            continue
        a, b = max(0, f0 - 3), min(n - 1, f0 + 4)
        jump = {k: pdb[k][b] - pdb[k][a] for k in pdb if pdb[k][b] > peak[k] - 22 and pdb[k][b] - pdb[k][a] > 5}
        if not jump:
            continue
        top = max(pdb[k][b] for k in jump)
        struck = sorted(k for k in jump if pdb[k][b] > top - 15)  # drop bleed
        fam, combo = _label(struck)
        dur = (f1 - f0) * HOP / SR
        hp = D[f0:f1].max()
        decay = hp - D[max(f0, f1 - 3):f1].mean()
        if dur < 0.08 or decay < 12:
            continue
        cap_s = 1.2 if fam in ("Crash", "Ride", "hh") else 0.8
        score = (hp - loud + 30) / 30 + min(decay, 30) / 30 + min(dur, 0.6)
        hits.append(dict(f0=f0, f1=min(f1, f0 + int(cap_s * SR / HOP)), fam=fam, combo=combo, pieces=struck,
                         dur=min(dur, cap_s), score=score, decay=decay))
    # keep the best few per family before CLAP
    hits.sort(key=lambda h: -h["score"])
    pre, cnt = [], {}
    for h in hits:
        if cnt.get(h["fam"], 0) < 6:
            pre.append(h); cnt[h["fam"]] = cnt.get(h["fam"], 0) + 1

    # ---------- loops
    loops = []
    if tk["tempo_ok"]:
        mixfeat = SourceFeat(y, hpss=False)
        bars = bar_starts(tk["beats"], mixfeat)
        active = rel["drums"] > -15
        from .analyze import runs
        fps = SR / HOP
        for r0, r1 in runs(active, min_len=int(2 * fps), max_gap=int(0.5 * fps)):
            for a_, b_, L in _loop_windows(bars, tk["bpm"], r0 / fps, r1 / fps):
                f0, f1 = int(a_ * fps), int(b_ * fps)
                loops.append(dict(start=a_, end=b_, bars=L, alone=alone(f0, f1),
                                  dom=float(np.median(rel["drums"][f0:f1]))))
        loops.sort(key=lambda l: (-l["alone"], -l["dom"], -l["bars"]))
        loops = loops[:12]

    # ---------- CLAP: refine one-shot classes, classify loops, embed everything
    cl = models.clap()
    T = cl.embed_text(tuple(PERC_PROMPTS.values()))
    from .process import MOOD_PROMPTS
    M = cl.embed_text(tuple(MOOD_PROMPTS.values()))
    scale = float(cl.model.logit_scale_a.exp().clamp(max=100))

    def audio_hit(h):
        a = max(0, h["f0"] * HOP - int(0.005 * SR)); b = h["f1"] * HOP
        src = y if alone(h["f0"], max(h["f0"] + 1, h["f1"])) else drums
        return src[:, a:b], ("mix" if src is y else "drums")

    def audio_loop(l, sub):
        a, b = int(l["start"] * SR), int(l["end"] * SR)
        if sub == "Breaks":
            return y[:, a:b], "mix"
        if sub == "Tops":
            return (drums - pieces["kick"])[:, a:b], "drums-kick"
        return drums[:, a:b], "drums"

    items = []
    for h in pre:
        clip, src = audio_hit(h)
        items.append(dict(kind="oneshot", h=h, clip=clip, src=src, start=h["f0"] * HOP / SR))
    for l in loops:
        sub = "Breaks" if l["alone"] else "Full Kit"
        clip, src = audio_loop(l, sub)
        items.append(dict(kind="loop", l=l, sub=sub, clip=clip, src=src, start=l["start"]))
        if not l["alone"] and "kick" in pieces:
            clip2, src2 = audio_loop(l, "Tops")
            items.append(dict(kind="loop", l=l, sub="Tops", clip=clip2, src=src2, start=l["start"] + 0.001))
    if not items:
        con.execute("UPDATE tracks SET drums_done=1 WHERE id=?", (row["id"],)); con.commit()
        return 0
    clips = []
    for it in items:
        m = it["clip"].mean(0)
        if len(m) > SR * 10:
            m = m[:SR * 10]
        if len(m) < SR // 2:
            m = np.pad(m, (0, SR // 2 - len(m)))
        clips.append(to_mono48(m))
    E = cl.embed_audio(clips)
    lg = scale * E @ T.T
    PR = np.exp(lg - lg.max(1, keepdims=True)); PR /= PR.sum(1, keepdims=True)

    for it, e, pr in zip(items, E, PR):
        it["emb"], it["probs"], it["moods"] = e, pr, e @ M.T
        if it["kind"] == "oneshot":
            h = it["h"]
            it["sub"] = _refine(h["fam"], pr, h["dur"]) if not h["combo"] else h["fam"]
            it["quality"] = float(np.clip(h["score"] / 2.6, 0, 1))
            it["group"] = "combo" if h["combo"] else "pure"
        else:
            if it["sub"] == "Full Kit" and pr[PK.index("hand_loop")] > pr[PK.index("kit_loop")]:
                it["sub"] = "Percussion Loops"
            it["quality"] = float(np.clip(0.6 + 0.4 * it["l"]["alone"] + it["l"]["dom"] / 60, 0, 1))
            it["group"] = it["sub"]

    # dedupe + caps
    kept, cnt = [], {}
    for it in sorted(items, key=lambda x: -x["quality"]):
        key = it["sub"] if it["kind"] == "oneshot" else it["group"]
        cap = CAP["combo" if it.get("group") == "combo" else "pure"] if it["kind"] == "oneshot" else CAP[it["group"]]
        if cnt.get(key, 0) >= cap:
            continue
        if any(k["sub"] == it["sub"] and float(k["emb"] @ it["emb"]) > 0.97 for k in kept):
            continue
        kept.append(it); cnt[key] = cnt.get(key, 0) + 1

    # ---------- write
    con.execute("DELETE FROM samples WHERE track_id=? AND category='Percussion' AND parent_id IS NULL", (row["id"],))
    from .process import _safe
    from .policy import sample_dir
    bpm = tk["bpm"] if tk["tempo_ok"] else None
    for it in kept:
        clip = it["clip"]
        sub = it["sub"]
        note = _tuning(clip, sub) if sub in ("Kick", "Tom", "Hand Drum", "Orchestral") else None
        swing = _swing(clip, bpm) if it["kind"] == "loop" else None
        sid = hashlib.sha1(f"{row['path']}|perc|{it['start']:.3f}|{sub}".encode()).hexdigest()[:6]
        pref = PREFIX[sub] + (f"-Loop{it['l']['bars']}" if it["kind"] == "loop" else "")
        mm, ss = divmod(int(it["start"]), 60)
        extra = f"{note}" if note else (f"swing{swing:.0f}" if swing else "")
        fname = (f"{pref}_{extra + '_' if extra else ''}{f'{bpm:.0f}bpm' if bpm else 'free'}_"
                 f"{_safe(row['artist'], 24)}-{_safe(row['title'], 30)}_{mm}m{ss:02d}s_{sid}.wav")
        path = sample_dir(row["policy"]) / "Percussion" / sub / fname
        fo = 0.003 if it["kind"] == "loop" else min(0.03, clip.shape[1] / SR / 4)
        write_wav(path, clip, fade_in=0.001 if it["kind"] == "oneshot" else 0.003, fade_out=fo)
        a = np.abs(clip).max(0)
        env = (np.array([float(x.max()) for x in np.array_split(a, 64)]) / (a.max() + 1e-9) * 99).astype(int).tolist() \
            if len(a) >= 64 else [0] * 64
        tags = ([f"swing {swing:.0f}%"] if swing and swing > 54 else []) + (["break"] if sub == "Breaks" else [])
        con.execute(
            """INSERT OR REPLACE INTO samples(id, track_id, source, rendered_from, category, subtype, kind, start, dur,
               bpm, bars, key, scale, camelot, key_strength, key_from, note, chroma, centroid, flatness, pratio,
               dominance, drum_leak, loudness, quality, clap, type_probs, mood_sims, instrument, path, env, tags)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (sid, row["id"], "drums", it["src"], "Percussion", sub, "loop" if it["kind"] == "loop" else "oneshot",
             it["start"], clip.shape[1] / SR, bpm, it["l"]["bars"] if it["kind"] == "loop" else None,
             PITCHES[tk["pc"]], tk["scale"], tk["camelot"], 0.0, "none", note, json.dumps([0.0] * 12),
             None, None, None, None, None, None, round(it["quality"], 3), it["emb"].astype(np.float16).tobytes(),
             json.dumps(dict(zip(PK, np.round(it["probs"], 3).tolist()))),
             json.dumps(dict(zip(MOOD_PROMPTS, np.round(it["moods"], 4).tolist()))),
             "+".join(it["h"]["pieces"]) if it["kind"] == "oneshot" else it["sub"].lower(),
             str(path.relative_to(C.LIB_ROOT)), json.dumps(env), json.dumps(tags)))
    con.execute("UPDATE tracks SET drums_done=1 WHERE id=?", (row["id"],))
    con.commit()
    if verbose:
        from collections import Counter
        c = Counter(it["sub"] for it in kept)
        tqdm.write(f"  {row['artist']} - {row['title']}: {len(kept)} percussion ({dict(c)}) {time.time() - t0:.0f}s")
    return len(kept)


# genre families with live drummers (electronic, ambient, hip-hop drums are machines or samples)
DRUM_FAMILIES = {"Soul & R&B", "Jazz", "Rock & Indie", "World", "Folk", "Pop"}


def run(where="1=1", params=(), top=None, limit=None, redo=False):
    con = connect()
    cols = {r[1] for r in con.execute("PRAGMA table_info(tracks)")}
    if "drums_done" not in cols:
        con.execute("ALTER TABLE tracks ADD COLUMN drums_done INTEGER")
    q = f"""SELECT * FROM tracks WHERE ({where}) AND COALESCE(policy,'source')='source'
            {'' if redo else 'AND drums_done IS NULL'}"""
    if top:
        q += " AND scout_done=1 ORDER BY (1 - scout_sparse) DESC, RANDOM()"
    rows = con.execute(q, params).fetchall()
    if top:
        if not rows and not con.execute("SELECT 1 FROM tracks WHERE scout_done=1 LIMIT 1").fetchone():
            print("--top ranks tracks by the scout pass, and nothing is scouted yet: run `python -m digitalcrate scout` "
                  "first, or pick tracks with --artist / --match instead.")
        from .genre import family, overrides, artist_consensus
        ov, cons = overrides(), artist_consensus()
        rows = [r for r in rows if family(r["artist"], r["genre"], ov, cons) in DRUM_FAMILIES]  # live drummers only
        per_album, per_artist, kept = {}, {}, []
        for r in rows:
            a, al = r["artist"] or "?", f"{r['artist']}|{r['album']}"
            if per_album.get(al, 0) < 2 and per_artist.get(a, 0) < 4:
                kept.append(r); per_album[al] = per_album.get(al, 0) + 1; per_artist[a] = per_artist.get(a, 0) + 1
        rows = kept[:top]
    if limit:
        rows = rows[:limit]
    print(f"{len(rows)} tracks for percussion mining")
    total = 0
    for r in tqdm(rows, desc="drums"):
        try:
            total += process_track(con, r)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            tqdm.write(f"  ERROR {r['path']}: {e}\n{traceback.format_exc()[-600:]}")
    print(f"done: {total} percussion samples")
