"""Candidate sample detection: find clean regions in the mix and in stems, cut them
into loops / phrases / chops / one-shots, and measure how 'clean' each one is."""
import numpy as np
import librosa

from . import config as C
from .analyze import runs, frames_to_sec, sec_to_frames
from .config import FPS, SR_F


def _clamp(x):
    return float(min(1.0, max(0.0, x)))


# ---------------------------------------------------------------- cutting helpers

def loops_in(s, e, bar_times, bpm):
    """Greedy, non-overlapping bar-aligned loops (8, then 4, then 2 bars) inside [s, e]."""
    out, free = [], [(s, e)]
    bar_len = 240.0 / bpm
    for L in (8, 4, 2):
        if L * bar_len > C.LOOP_MAX_SECONDS:
            continue
        nxt = []
        for a, b in free:
            idx = np.flatnonzero((bar_times >= a - 0.05) & (bar_times <= b))
            i, last_end = 0, a
            while i < len(idx):
                bi = idx[i]
                t0 = bar_times[bi]
                t1 = bar_times[bi + L] if bi + L < len(bar_times) else t0 + L * bar_len
                if t1 <= b + 0.1 and abs((t1 - t0) - L * bar_len) < 0.25 * bar_len:
                    out.append((t0, t1, L))
                    if t0 - last_end > 2 * bar_len:
                        nxt.append((last_end, t0))
                    last_end = t1
                    while i < len(idx) and bar_times[idx[i]] < t1 - 0.05:
                        i += 1
                else:
                    i += 1
            if b - last_end > 2 * bar_len:
                nxt.append((last_end, b))
        free = nxt
    return out


def free_windows(s, e):
    d = e - s
    if d < 4:
        return []
    if d <= 2 * C.FREE_WINDOW_SECONDS:
        return [(s, e)]
    n = int(d // C.FREE_WINDOW_SECONDS)
    w = d / n
    return [(s + i * w, s + (i + 1) * w) for i in range(n)]


def split_long_phrase(feat, s, e, target=8.0, max_len=20.0):
    """Split a long vocal region at its quietest points."""
    if e - s <= max_len:
        return [(s, e)]
    pieces, cur = [], s
    while e - cur > max_len:
        lo, hi = sec_to_frames(cur + target * 0.6), sec_to_frames(min(cur + target * 1.6, e - 1.5))
        if hi <= lo:
            break
        cut = frames_to_sec(lo + int(np.argmin(feat.db[lo:hi])))
        pieces.append((cur, cut))
        cur = cut
    pieces.append((cur, e))
    return pieces


def vocal_chops(feat, s, e, max_len=1.5):
    seg = feat.mono[int(s * SR_F):int(e * SR_F)]
    if len(seg) < SR_F * 0.3:
        return []
    on = librosa.onset.onset_detect(y=seg, sr=SR_F, hop_length=256, backtrack=True, units="time")
    on = list(on) + [e - s]
    out = []
    for a, b in zip(on[:-1], on[1:]):
        b = min(b, a + max_len)
        if b - a >= 0.25:
            out.append((s + a, s + b))
    return out


# ---------------------------------------------------------------- main detection

def find_candidates(tk, mix, feats, bar_times):
    """Return list of candidate dicts with times in seconds.

    tk: track tempo/key dict; mix: SourceFeat of mix; feats: dict of stem SourceFeats or None.
    """
    cands = []
    tempo_ok = tk["tempo_ok"] and len(bar_times) > 4
    bpm = tk["bpm"]

    def add(source, group, kind, s, e, bars=None):
        cands.append(dict(source=source, group=group, kind=kind, start=float(s), end=float(e), bars=bars))

    def long_cuts(source, group, s, e):
        if tempo_ok:
            for a, b, L in loops_in(s, e, bar_times, bpm):
                add(source, group, "loop", a, b, L)
        else:
            for a, b in free_windows(s, e):
                add(source, group, "free", a, b)

    if feats is not None:
        rel = {k: feats[k].db - mix.db for k in feats}
        drums_on = (rel["drums"] > C.DRUMS_REL_DB) & feats["drums"].active(40)
        bass_on = (rel["bass"] > C.BASS_REL_DB) & feats["bass"].active(40)
        voc_on = feats["vocals"].active(C.ACTIVE_BELOW_P95_DB, C.ABS_FLOOR_DB) & (rel["vocals"] > -20)
        oth_on = (feats["other"].active(C.ACTIVE_BELOW_P95_DB, C.ABS_FLOOR_DB) & (rel["other"] > -20)
                  & (feats["other"].pratio < C.OTHER_PRATIO_MAX))

        # A) vocals stem: phrases + chops
        for f0, f1 in runs(voc_on, min_len=sec_to_frames(0.2), max_gap=sec_to_frames(0.35)):
            s, e = frames_to_sec(f0), frames_to_sec(f1)
            if e - s >= 1.5:
                for a, b in split_long_phrase(feats["vocals"], s, e):
                    if b - a >= 1.5:
                        add("vocals", "vocal_phrase", "phrase", a, b)
            for a, b in vocal_chops(feats["vocals"], s, e):
                add("vocals", "vocal_chop", "oneshot", a, b)

        # B) 'other' stem: pads, chords, melodies, textures
        for f0, f1 in runs(oth_on, min_len=sec_to_frames(0.4), max_gap=sec_to_frames(1.0)):
            s, e = frames_to_sec(f0), frames_to_sec(f1)
            if e - s >= 4:
                long_cuts("other", "long", s, e)
            elif e - s <= 4:
                add("other", "oneshot", "oneshot", s, e)

        # C) clean mix with voice over atmosphere (the Burial blend)
        clean = mix.active() & ~drums_on & ~bass_on
        for f0, f1 in runs(clean, min_len=sec_to_frames(4), max_gap=sec_to_frames(0.5)):
            if voc_on[f0:f1].mean() > 0.4 and oth_on[f0:f1].mean() > 0.4:
                long_cuts("mix", "vocal_atmos", frames_to_sec(f0), frames_to_sec(f1))
        masks = dict(drums=drums_on, bass=bass_on, vocals=voc_on, other=oth_on, rel=rel)
    else:
        drums_on = mix.pratio > C.MIX_PRATIO_DRUMS
        clean = mix.active() & ~drums_on
        for f0, f1 in runs(clean, min_len=sec_to_frames(0.4), max_gap=sec_to_frames(1.0)):
            s, e = frames_to_sec(f0), frames_to_sec(f1)
            if e - s >= 4:
                long_cuts("mix", "long", s, e)
            else:
                add("mix", "oneshot", "oneshot", s, e)
        masks = dict(drums=drums_on, rel=None)
    return cands, masks


def measure(c, mix, feats, masks):
    """Cleanliness metrics + quality score (before CLAP adjustments)."""
    f0, f1 = sec_to_frames(c["start"]), max(sec_to_frames(c["end"]), sec_to_frames(c["start"]) + 1)
    src = c["source"]
    rendered = src
    dominance, drum_leak = 0.0, None
    if feats is not None:
        rel = masks["rel"]
        drum_leak = float(np.percentile(rel["drums"][f0:f1], 90))
        if src != "mix":
            dominance = float(np.median(rel[src][f0:f1]))
            others = [k for k in ("drums", "bass", "vocals", "other") if k != src]
            if all(np.percentile(rel[k][f0:f1], 90) < C.NEGLIGIBLE_REL_DB for k in others):
                rendered = "mix"  # stem is effectively solo in the mix: use the untouched original
    else:
        drum_leak = float(-40 * (1 - mix.pratio[f0:f1].mean() / C.MIX_PRATIO_DRUMS))

    feat = feats[src] if (src != "mix" and feats is not None) else mix
    q = 1.0
    if rendered == "mix":
        q *= _clamp((-drum_leak - 10) / 12) if feats is not None else _clamp(-drum_leak / 25)
    else:
        q *= 1 - 0.5 * _clamp((drum_leak + 20) / 20)
        q *= _clamp((dominance + 22) / 14)
    pr = float(feat.pratio[f0:f1].mean()) if feat.pratio is not None else 0.0
    pr_max = 0.45 if src == "vocals" else 0.35
    q *= _clamp((pr_max + 0.15 - pr) / 0.3)
    loud = float(np.percentile(feat.db[f0:f1], 90))
    q *= _clamp((loud - (feat.p95 - 24)) / 12)
    c.update(rendered_from=rendered, dominance=dominance, drum_leak=drum_leak, pratio_c=pr, quality=q)
    c["feat_src"] = "mix" if rendered == "mix" else src
    return c
