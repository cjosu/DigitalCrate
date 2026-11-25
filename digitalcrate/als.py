"""A sketch as an Ableton Live set: one audio track per lane, an arrangement clip wherever that lane plays, at the
sketch's tempo, with muted lanes kept as muted tracks.

The set starts from Live's own empty template (DefaultLiveSet.als inside the installed Live app), so it has your
version's structure; nothing from Ableton is stored in this repo. Each lane's audio is the exact stem the sketchpad
renders (trimmed, tempo- and key-matched, faded, with your levels baked in), written next to the set; the clips
point into it, warped at the set's tempo so changing the tempo in Live still keeps them in time.
"""
import copy
import gzip
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import soundfile as sf

COLORS = {"Vocals": 26, "Vocal Atmospheres": 25, "Pads & Atmospheres": 16, "Strings & Orchestral": 14, "Chords & Keys": 13, "Bass & Sub": 2,
          "Percussion": 4, "Leads & Melodic": 9, "FX & Textures": 21}
WARP = {"beats": 0, "complex": 4}


def template():
    apps = sorted(Path("/Applications").glob("Ableton Live*.app"), reverse=True)
    for a in apps:
        f = a / "Contents/App-Resources/Builtin/Templates/DefaultLiveSet.als"
        if f.exists():
            return f
    raise FileNotFoundError("Ableton Live isn't installed in /Applications (its empty set is the starting point)")


def spans(y, sr, bpm, total_beats, floor_db=-60.0):
    """Where a stem is sounding, in beats: [start, end) pairs snapped out to 16th notes; gaps under a beat bridged."""
    beat = 60.0 / bpm
    hop = int(sr * 0.01)
    m = np.abs(y).max(1) if y.ndim > 1 else np.abs(y)
    n = len(m) // hop
    if not n:
        return []
    env = m[: n * hop].reshape(n, hop).max(1)
    on = env > max(10 ** (floor_db / 20), env.max() * 10 ** (-50 / 20))
    out, k = [], 0
    while k < n:
        if not on[k]:
            k += 1
            continue
        j = k
        while j < n and on[j]:
            j += 1
        a, b = k * 0.01 / beat, j * 0.01 / beat
        if out and a - out[-1][1] < 1.0:
            out[-1][1] = b
        else:
            out.append([a, b])
        k = j
    q = 0.25
    return [[max(0.0, np.floor(a / q) * q), min(total_beats, np.ceil(b / q) * q)] for a, b in out]


def _set(el, path, value):
    node = el.find(path)
    if node is None:
        raise KeyError(path)
    node.set("Value", str(value))


CLIP = """<AudioClip Id="{id}" Time="{a}"><LomId Value="0" /><LomIdView Value="0" /><CurrentStart Value="{a}" /><CurrentEnd Value="{b}" />
<Loop><LoopStart Value="{ls}" /><LoopEnd Value="{le}" /><StartRelative Value="0" /><LoopOn Value="{loop}" /><OutMarker Value="{le}" /><HiddenLoopStart Value="{ls}" /><HiddenLoopEnd Value="{le}" /></Loop>
<Name Value="" /><Annotation Value="" /><Color Value="{color}" /><LaunchMode Value="0" /><LaunchQuantisation Value="0" />
<TimeSignature><TimeSignatures><RemoteableTimeSignature Id="0"><Numerator Value="4" /><Denominator Value="4" /><Time Value="0" /></RemoteableTimeSignature></TimeSignatures></TimeSignature>
<Envelopes><Envelopes /></Envelopes><ScrollerTimePreserver><LeftTime Value="0" /><RightTime Value="0" /></ScrollerTimePreserver>
<TimeSelection><AnchorTime Value="0" /><OtherTime Value="0" /></TimeSelection><Legato Value="false" /><Ram Value="false" />
<GrooveSettings><GrooveId Value="-1" /></GrooveSettings><Disabled Value="false" /><VelocityAmount Value="0" />
<FollowAction><FollowTime Value="4" /><IsLinked Value="true" /><LoopIterations Value="1" /><FollowActionA Value="4" /><FollowActionB Value="0" /><FollowChanceA Value="100" /><FollowChanceB Value="0" /><JumpIndexA Value="0" /><JumpIndexB Value="0" /><FollowActionEnabled Value="false" /></FollowAction>
<Grid><FixedNumerator Value="1" /><FixedDenominator Value="16" /><GridIntervalPixel Value="20" /><Ntoles Value="2" /><SnapToGrid Value="true" /><Fixed Value="false" /></Grid>
<FreezeStart Value="0" /><FreezeEnd Value="0" /><IsWarped Value="true" /><TakeId Value="0" /><IsInKey Value="false" /><ScaleInformation><Root Value="0" /><Name Value="0" /></ScaleInformation>
<SampleRef><FileRef><RelativePathType Value="1" /><RelativePath Value="" /><Path Value="" /><Type Value="2" /><LivePackName Value="" /><LivePackId Value="" /><OriginalFileSize Value="0" /><OriginalCrc Value="0" /></FileRef>
<LastModDate Value="0" /><SourceContext /><SampleUsageHint Value="0" /><DefaultDuration Value="{frames}" /><DefaultSampleRate Value="{sr}" /><SamplesToAutoWarp Value="0" /></SampleRef>
<Onsets><UserOnsets /><HasUserOnsets Value="false" /></Onsets><WarpMode Value="{warp}" /><GranularityTones Value="30" /><GranularityTexture Value="65" /><FluctuationTexture Value="25" />
<TransientResolution Value="6" /><TransientLoopMode Value="2" /><TransientEnvelope Value="100" /><ComplexProFormants Value="100" /><ComplexProEnvelope Value="128" />
<Sync Value="true" /><HiQ Value="true" /><Fade Value="true" />
<Fades><FadeInLength Value="0" /><FadeOutLength Value="0" /><ClipFadesAreInitialized Value="true" /><CrossfadeInState Value="0" /><FadeInCurveSkew Value="0" /><FadeInCurveSlope Value="0" /><FadeOutCurveSkew Value="0" /><FadeOutCurveSlope Value="0" /><IsDefaultFadeIn Value="true" /><IsDefaultFadeOut Value="true" /></Fades>
<PitchCoarse Value="0" /><PitchFine Value="0" /><SampleVolume Value="{gain}" />
<WarpMarkers><WarpMarker Id="0" SecTime="0" BeatTime="0" /><WarpMarker Id="1" SecTime="{sec1}" BeatTime="{beat1}" /></WarpMarkers>
<SavedWarpMarkersForStretched /><MarkersGenerated Value="false" /><IsSongTempoLeader Value="false" /><AutoWarpPending Value="false" /><WasMuted Value="false" /></AudioClip>"""


def write_set(dest, name, lanes, bpm, bars):
    """lanes: [{file (Path to a WAV in dest), label, category, mute, drums}] -> dest/<name>.als"""
    root = ET.parse(gzip.open(template())).getroot()
    ls = root.find("LiveSet")
    tracks = ls.find("Tracks")
    proto = tracks.find("AudioTrack")
    for t in list(tracks):
        if t.tag in ("AudioTrack", "MidiTrack", "GroupTrack"):
            tracks.remove(t)
    nxt = int(ls.find("NextPointeeId").get("Value"))
    total = bars * 4.0
    returns = [i for i, t in enumerate(list(tracks)) if t.tag == "ReturnTrack"]
    for k, lane in enumerate(lanes):
        t = copy.deepcopy(proto)
        t.set("Id", str(1000 + k))
        for el in t.iter():  # automation/modulation targets must be unique across the set
            if "Id" in el.attrib and (el.tag.endswith("Target") or el.tag == "Pointee"):
                el.set("Id", str(nxt)); nxt += 1
        _set(t, "Name/EffectiveName", lane["label"])
        _set(t, "Name/UserName", lane["label"])
        color = COLORS.get(lane.get("category"), 0)
        _set(t, "Color", color)
        dc = t.find("DeviceChain")
        _set(dc, "Mixer/Speaker/Manual", "false" if lane.get("mute") else "true")
        y, sr = sf.read(str(lane["file"]), dtype="float32", always_2d=True)
        events = dc.find("MainSequencer/Sample/ArrangerAutomation/Events")
        secs = len(y) / sr
        for j, (a, b) in enumerate(spans(y, sr, bpm, total)):
            if b - a < 0.25:
                continue
            clip = ET.fromstring(CLIP.format(id=j, a=f"{a:g}", b=f"{b:g}", ls=f"{a:g}", le=f"{b:g}", loop="false", gain="1",
                                             color=color, frames=len(y), sr=sr,
                                             warp=WARP["beats" if lane.get("drums") else "complex"],
                                             sec1=f"{secs:.6f}", beat1=f"{secs * bpm / 60:.6f}"))
            _set(clip, "Name", lane["label"])
            _set(clip, "SampleRef/FileRef/RelativePath", lane["file"].name)
            _set(clip, "SampleRef/FileRef/Path", str(lane["file"]))
            _set(clip, "SampleRef/FileRef/OriginalFileSize", lane["file"].stat().st_size)
            _set(clip, "SampleRef/LastModDate", int(lane["file"].stat().st_mtime))
            events.append(clip)
        tracks.insert(len(tracks) - len(returns), t)
    ls.find("NextPointeeId").set("Value", str(nxt))
    # tempo: the dial and the tempo envelope's starting value
    main = ls.find("MainTrack") if ls.find("MainTrack") is not None else ls.find("MasterTrack")
    tempo = main.find("DeviceChain/Mixer/Tempo")
    _set(tempo, "Manual", f"{bpm:g}")
    tid = tempo.find("AutomationTarget").get("Id")
    for env in main.iter("AutomationEnvelope"):
        if env.find("EnvelopeTarget/PointeeId").get("Value") == tid:
            for ev in env.iter("FloatEvent"):
                ev.set("Value", f"{bpm:g}")
    tr = ls.find("Transport")
    _set(tr, "LoopStart", 0); _set(tr, "LoopLength", f"{total:g}"); _set(tr, "LoopOn", "true")
    out = Path(dest) / f"{name}.als"
    xml = ET.tostring(root, encoding="unicode")
    with gzip.open(out, "wb") as f:
        f.write(('<?xml version="1.0" encoding="UTF-8"?>\n' + xml).encode("utf-8"))
    return out


def write_arrangement(dest, name, tracks, bpm, total_beats, locators=()):
    """An arrangement of looping clips, for the Mashup export (stems.export).

    tracks: [{label, category, volume (linear, 1 = 0 dB), mute, drums,
              clips: [{file (a WAV exactly `beats` long at bpm), start, end (beats in the arrangement), beats, gain,
                       label}]}]
    locators: [(beat, name)]. Each clip loops its file from its start to its end, warped 1:1 at the set's tempo.
    -> dest/<name>.als"""
    root = ET.parse(gzip.open(template())).getroot()
    ls = root.find("LiveSet")
    tr_el = ls.find("Tracks")
    proto = tr_el.find("AudioTrack")
    for t in list(tr_el):
        if t.tag in ("AudioTrack", "MidiTrack", "GroupTrack"):
            tr_el.remove(t)
    nxt = int(ls.find("NextPointeeId").get("Value"))
    returns = [i for i, t in enumerate(list(tr_el)) if t.tag == "ReturnTrack"]
    cid = 0
    for k, tr in enumerate(tracks):
        t = copy.deepcopy(proto)
        t.set("Id", str(1000 + k))
        for el in t.iter():
            if "Id" in el.attrib and (el.tag.endswith("Target") or el.tag == "Pointee"):
                el.set("Id", str(nxt)); nxt += 1
        _set(t, "Name/EffectiveName", tr["label"])
        _set(t, "Name/UserName", tr["label"])
        color = COLORS.get(tr.get("category"), 0)
        _set(t, "Color", color)
        dc = t.find("DeviceChain")
        _set(dc, "Mixer/Speaker/Manual", "false" if tr.get("mute") else "true")
        _set(dc, "Mixer/Volume/Manual", f"{min(1.99, max(0.0004, float(tr.get('volume', 1)))):.6f}")
        events = dc.find("MainSequencer/Sample/ArrangerAutomation/Events")
        for c in sorted(tr["clips"], key=lambda c: c["start"]):
            info = sf.info(str(c["file"]))
            secs = info.frames / info.samplerate
            clip = ET.fromstring(CLIP.format(id=cid, a=f"{c['start']:g}", b=f"{c['end']:g}", ls="0", le=f"{c['beats']:g}",
                                             loop="true", gain=f"{float(c.get('gain', 1)):.6f}", color=color,
                                             frames=info.frames, sr=info.samplerate,
                                             warp=WARP["beats" if tr.get("drums") else "complex"],
                                             sec1=f"{secs:.6f}", beat1=f"{c['beats']:g}"))
            cid += 1
            _set(clip, "Name", c.get("label") or tr["label"])
            _set(clip, "SampleRef/FileRef/RelativePath", str(Path(c["file"]).relative_to(dest)))
            _set(clip, "SampleRef/FileRef/Path", str(c["file"]))
            _set(clip, "SampleRef/FileRef/OriginalFileSize", Path(c["file"]).stat().st_size)
            _set(clip, "SampleRef/LastModDate", int(Path(c["file"]).stat().st_mtime))
            events.append(clip)
        tr_el.insert(len(tr_el) - len(returns), t)
    lo = ls.find("Locators/Locators")
    if lo is not None:
        for k, (beat, nm) in enumerate(locators):
            e = ET.SubElement(lo, "Locator", Id=str(k))
            for tag, v in (("LomId", "0"), ("Time", f"{beat:g}"), ("Name", nm), ("Annotation", ""), ("IsSongStart", "false")):
                ET.SubElement(e, tag, Value=v)
    ls.find("NextPointeeId").set("Value", str(nxt))
    main = ls.find("MainTrack") if ls.find("MainTrack") is not None else ls.find("MasterTrack")
    tempo = main.find("DeviceChain/Mixer/Tempo")
    _set(tempo, "Manual", f"{bpm:g}")
    tid = tempo.find("AutomationTarget").get("Id")
    for env in main.iter("AutomationEnvelope"):
        if env.find("EnvelopeTarget/PointeeId").get("Value") == tid:
            for ev in env.iter("FloatEvent"):
                ev.set("Value", f"{bpm:g}")
    tp = ls.find("Transport")
    _set(tp, "LoopStart", 0); _set(tp, "LoopLength", f"{total_beats:g}"); _set(tp, "LoopOn", "true")
    out = Path(dest) / f"{name}.als"
    with gzip.open(out, "wb") as fh:
        fh.write(('<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")).encode("utf-8"))
    return out
