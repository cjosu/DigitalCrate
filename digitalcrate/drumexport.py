"""The drum lane for Live: a Drum Rack of its pads plus a MIDI clip of its pattern (⇩ MIDI + rack).

The rack is built by export(): each pad trimmed to the hit or as edited in the lane, with its choke group. Pad k sits
on MIDI note 36 + k (C1 up), so the clip plays the rack as it is. The clip is one pass of the pattern (1 or 2 bars):
16ths, velocities, swing (every other 16th late, as in the lane), and flams as a soft grace note 20 ms before. In Live,
drop the rack on a MIDI track, then the clip onto it (or into a clip slot).
"""
from pathlib import Path

from .ableton import BASE_NOTE
from .export import _safe


def drum_export(name, bpm, bars, swing, pads, reveal=True):
    import pretty_midi
    import soundfile as sf
    from . import config as C
    from .ableton import drum_rack
    from .edit import render
    live = [p for p in pads if not p.get("mute")]
    dest = C.ABLETON_SAMPLES / _safe(name)
    (dest / "Pads").mkdir(parents=True, exist_ok=True)
    rack_pads = []
    for k, p in enumerate(live):  # each pad as the lane plays it (slices of one loop each get their own file)
        y, _ = render(p["path"], dict(start=p.get("start") or 0, end=p.get("end"), semis=p.get("tune") or 0, tape=True,
                                      decay=p.get("decay") or 0, fade_in=1, fade_out=5, normalize=False))
        f = dest / "Pads" / f"{k + 1:02d} {_safe(p.get('label') or Path(p['path']).stem)[:50]}.wav"
        sf.write(str(f), y.T, C.SR, subtype="PCM_24")
        rack_pads.append((f, f"{k + 1:02d} {p.get('label') or ''}".strip(), int(p.get("choke") or 0)))
    rack = dest / f"{_safe(name)}.adg"
    drum_rack(rack_pads, name, rack)
    r = dict(extra=[rack.name])
    step = 60.0 / bpm / 4
    pm = pretty_midi.PrettyMIDI(initial_tempo=float(bpm))
    inst = pretty_midi.Instrument(program=0, name=_safe(name))
    for k, p in enumerate(live):
        note = BASE_NOTE + k
        steps, flams = p.get("steps") or [], p.get("flams") or []
        for j in range(16 * int(bars)):
            v = steps[j] if j < len(steps) else 0
            if not v:
                continue
            t = j * step + (swing * step if j % 2 else 0)
            vel = max(1, min(127, round(v * 127)))
            if j < len(flams) and flams[j]:
                g = max(0.0, t - 0.02)
                inst.notes.append(pretty_midi.Note(velocity=max(1, round(vel * 0.45)), pitch=note, start=g, end=g + 0.015))
            inst.notes.append(pretty_midi.Note(velocity=vel, pitch=note, start=t, end=t + step * 0.9))
    pm.instruments.append(inst)
    mid = dest / f"{_safe(name)} pattern.mid"
    pm.write(str(mid))
    if reveal:
        import subprocess
        subprocess.run(["open", str(dest)])
    return dict(dest=str(dest), rack=r["extra"], midi=mid.name, pads=len(live), notes=len(inst.notes))
