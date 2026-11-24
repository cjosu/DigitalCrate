"""The drum lane for Live: a Drum Rack of its pads plus a MIDI clip of its pattern (⇩ MIDI + rack).

The rack is built by export(): each pad trimmed to the hit or as edited in the lane, with its choke group. Pad k sits
on MIDI note 36 + k (C1 up), so the clip plays the rack as it is. The clip is one pass of the pattern (1 or 2 bars):
16ths, velocities, swing (every other 16th late, as in the lane), and flams as a soft grace note 20 ms before. A pad
with alternate takes (round robin) puts each take on its own pad and the clip cycles through them hit by hit, made
long enough that the cycle lines up when Live loops it. In Live,
drop the rack on a MIDI track, then the clip onto it (or into a clip slot).
"""
from pathlib import Path

from math import gcd

from .ableton import BASE_NOTE
from .export import _safe, trim_to_hit



M32 = 0xFFFFFFFF


def _hash(x):
    x &= M32
    x = ((x ^ (x >> 16)) * 0x45D9F3B) & M32
    x = ((x ^ (x >> 16)) * 0x45D9F3B) & M32
    return x ^ (x >> 16)


def _perm(b, n, s):
    P = list(range(n))
    for k in range(n - 1, 0, -1):  # Fisher-Yates, seeded by the block and the pad's seed
        j = _hash(b * 131 + k + s) % (k + 1)
        P[k], P[j] = P[j], P[k]
    return P


def take_idx(p, h, j, n):
    """Which take plays hit h (step j) of pad p: pinned, in turn or shuffled (a shuffle bag: every take once in a
    random order, then a new order, never the same take twice running). Same as takeIdx in studio.js."""
    pins = p.get("pins") or []
    if j < len(pins) and pins[j]:
        return min(int(pins[j]) - 1, n - 1)
    if p.get("order") != "shuffle" or n < 2:
        return h % n
    s = int(p.get("seed") or 1) * 7919
    if n == 2:  # two takes can't avoid repeats and still be random
        return _hash(h + s) % 2
    b, i = divmod(h, n)
    P = _perm(b, n, s)
    if b > 0 and P[0] == _perm(b - 1, n, s)[-1]:
        P[0], P[1] = P[1], P[0]
    return P[i]



def drum_export(name, bpm, bars, swing, pads, reveal=True):
    import pretty_midi
    import soundfile as sf
    from . import config as C
    from .ableton import drum_rack
    from .edit import render
    live = [p for p in pads if not p.get("mute")]
    dest = C.ABLETON_SAMPLES / _safe(name)
    (dest / "Pads").mkdir(parents=True, exist_ok=True)
    rack_pads, notes = [], []  # notes[k]: the rack notes pad k cycles through (its main hit, then its takes)
    for k, p in enumerate(live):  # each pad as the lane plays it (slices of one loop each get their own file)
        y, _ = render(p["path"], dict(start=p.get("start") or 0, end=p.get("end"), semis=p.get("tune") or 0, tape=True,
                                      decay=p.get("decay") or 0, fade_in=1, fade_out=5, normalize=False))
        label = p.get("label") or Path(p["path"]).stem
        ns = [BASE_NOTE + len(rack_pads)]
        f = dest / "Pads" / f"{len(rack_pads) + 1:02d} {_safe(label)[:50]}.wav"
        sf.write(str(f), y.T, C.SR, subtype="PCM_24")
        rack_pads.append((f, f"{len(rack_pads) + 1:02d} {p.get('label') or ''}".strip(), int(p.get("choke") or 0)))
        span = (p["end"] - (p.get("start") or 0)) if p.get("end") else None
        for j, tp in enumerate(p.get("takes") or []):  # round robin: each take its own pad, the clip alternates
            z, _ = render(tp, dict(start=0, semis=p.get("tune") or 0, tape=True, decay=p.get("decay") or 0,
                                   fade_in=1, fade_out=5, normalize=False))
            z = trim_to_hit(z, C.SR)
            if span:
                z = z[:, :int(span / 2 ** ((p.get("tune") or 0) / 12) * C.SR)]
            ns.append(BASE_NOTE + len(rack_pads))
            f = dest / "Pads" / f"{len(rack_pads) + 1:02d} {_safe(label)[:44]} take {j + 2}.wav"
            sf.write(str(f), z.T, C.SR, subtype="PCM_24")
            rack_pads.append((f, f"{len(rack_pads) + 1:02d} {p.get('label') or ''} take {j + 2}".strip(),
                              int(p.get("choke") or 0)))
        notes.append(ns)
    rack = dest / f"{_safe(name)}.adg"
    drum_rack(rack_pads, name, rack)
    r = dict(extra=[rack.name])
    step = 60.0 / bpm / 4
    n = 16 * int(bars)
    # with takes the clip runs until the alternation lines up again, so it loops exactly as the lane plays
    passes = 1
    for k, p in enumerate(live):
        act = sum(1 for j in range(n) if j < len(p.get("steps") or []) and p["steps"][j])
        if act and len(notes[k]) > 1:
            m = len(notes[k]) // gcd(act, len(notes[k]))
            passes = passes * m // gcd(passes, m)
        if act and len(notes[k]) > 1 and p.get("order") == "shuffle":  # never lines up: four passes of it
            passes = passes * 4 // gcd(passes, 4)
    passes = min(passes, 6)
    pm = pretty_midi.PrettyMIDI(initial_tempo=float(bpm))
    inst = pretty_midi.Instrument(program=0, name=_safe(name))
    for k, p in enumerate(live):
        steps, flams = p.get("steps") or [], p.get("flams") or []
        hit = 0
        for ps in range(passes):
            for j in range(n):
                v = steps[j] if j < len(steps) else 0
                if not v:
                    continue
                note = notes[k][take_idx(p, hit, j, len(notes[k]))]
                hit += 1
                t = (ps * n + j) * step + (swing * step if j % 2 else 0)
                vel = max(1, min(127, round(v * 127)))
                if j < len(flams) and flams[j]:
                    g = max(0.0, t - 0.02)
                    inst.notes.append(pretty_midi.Note(velocity=max(1, round(vel * 0.45)), pitch=note, start=g,
                                                       end=g + 0.015))
                inst.notes.append(pretty_midi.Note(velocity=vel, pitch=note, start=t, end=t + step * 0.9))
    pm.instruments.append(inst)
    mid = dest / f"{_safe(name)} pattern.mid"
    pm.write(str(mid))
    if reveal:
        import subprocess
        subprocess.run(["open", str(dest)])
    return dict(dest=str(dest), rack=r["extra"], midi=mid.name, pads=len(rack_pads), notes=len(inst.notes),
                bars=passes * int(bars))
