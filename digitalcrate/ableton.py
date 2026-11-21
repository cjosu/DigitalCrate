"""Ableton Live presets: Drum Racks (.adg) whose pads are your samples or a sample's syllable chops.

Built from a factory Live 12 Drum Rack as a template (so the XML is exactly what this Live version expects):
every pad is a clone of the template's first pad with the sample, name and note swapped and the Drum Sampler set
to play the whole sample (trigger mode, no effect, full filter, 0 dB).

    drum_rack([(abs_wav_path, "pad name"), ...], "Rack name", out_path)     -> .adg
    chops(rel, n=16) -> [(y, start_s)]                                        syllable/onset slices of a sample
"""
import gzip
import re
from pathlib import Path

import numpy as np
import soundfile as sf

from . import config as C

TEMPLATE = Path("/Applications/Ableton Live 12 Suite.app/Contents/App-Resources/Core Library/Racks/Drum Racks/"
                "Sampled/Rattle Kit.adg")
BASE_NOTE = 36  # C1 = first pad


def _template():
    cands = [TEMPLATE] + sorted(Path("/Applications").glob("Ableton Live*/Contents/App-Resources/Core Library/"
                                                            "Racks/Drum Racks/*/*.adg"))
    for t in cands:
        if t.exists():
            x = gzip.open(t).read().decode("utf-8")
            if "<DrumBranchPreset" in x and "<DrumCell " in x:
                return x
    raise FileNotFoundError("no Ableton Live Drum Rack found to use as a template")


def _set(block, tag, value):
    """Set <Tag><Manual Value=...> (automatable param) or <Tag Value=...> (plain) inside the first occurrence."""
    m = re.search(rf"(<{tag}>\s*<LomId Value=\"0\" />\s*<Manual Value=\")([^\"]*)(\")", block)
    if m:
        return block[:m.start(2)] + str(value) + block[m.end(2):]
    return re.sub(rf"(<{tag} Value=\")[^\"]*(\")", lambda mm: mm.group(1) + str(value) + mm.group(2), block, count=1)


def _esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _pad(tpl, k, path, label):
    info = sf.info(str(path))
    b = re.sub(r'<DrumBranchPreset Id="\d+">', f'<DrumBranchPreset Id="{k}">', tpl, count=1)
    b = re.sub(r'(<DrumBranchPreset Id="\d+">\s*<Name Value=")[^"]*', lambda m: m.group(1) + _esc(label), b, count=1)
    fr = (f'<FileRef>\n<RelativePathType Value="0" />\n<RelativePath Value="" />\n<Path Value="{_esc(str(path))}" />\n'
          f'<Type Value="2" />\n<LivePackName Value="" />\n<LivePackId Value="" />\n'
          f'<OriginalFileSize Value="{path.stat().st_size}" />\n<OriginalCrc Value="0" />\n</FileRef>')
    b = re.sub(r"<UserSample>.*?<FileRef>.*?</FileRef>", lambda m: m.group(0)[:m.group(0).index("<FileRef>")] + fr, b,
               count=1, flags=re.S)
    b = _set(b, "DefaultDuration", info.frames)
    b = _set(b, "DefaultSampleRate", info.samplerate)
    b = _set(b, "LastModDate", int(path.stat().st_mtime))
    for tag, v in [("Voice_Envelope_Mode", 0), ("Voice_Envelope_Attack", 0.0001),
                   ("Voice_Envelope_Hold", round(min(60.0, info.duration + 0.05), 4)), ("Voice_Envelope_Decay", 0.25),
                   ("Voice_PlaybackStart", 0), ("Voice_PlaybackLength", 1), ("Voice_Transpose", 0),
                   ("Voice_Filter_Frequency", 21999.9902), ("Voice_Filter_On", "false"), ("Effect_On", "false"),
                   ("Volume", 0), ("Pan", 0)]:
        b = _set(b, tag, v)
    b = re.sub(r'(<BrowserContentPath Value=")[^"]*', r"\1", b)
    b = re.sub(r'(<ReceivingNote Value=")\d+', lambda m: m.group(1) + str(128 - (BASE_NOTE + k)), b)
    b = re.sub(r'(<ChokeGroup Value=")\d+', r"\g<1>0", b)
    return b


def drum_rack(pads, name, out):
    """pads: [(Path to wav, label)] (max 128). Writes a gzipped .adg; returns its path."""
    x = _template()
    spans = [m.span() for m in re.finditer(r"<DrumBranchPreset Id=\"\d+\">.*?</DrumBranchPreset>", x, re.S)]
    first, last = spans[0][0], spans[-1][1]
    tpl = x[spans[0][0]:spans[0][1]]
    body = "\n".join(_pad(tpl, k, Path(p), lbl) for k, (p, lbl) in enumerate(pads[:128]))
    x = x[:first] + body + x[last:]
    # rack names: every UserName that carried the factory kit's name
    kit = re.search(r'<UserName Value="([^"]+)"', x)
    if kit:
        x = x.replace(f'<UserName Value="{kit.group(1)}"', f'<UserName Value="{_esc(name)}"')
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out, "wb") as fh:
        fh.write(x.encode("utf-8"))
    return out


def chops(rel, n=16, min_len=0.08):
    """Slice a sample at onsets (syllables / notes) into at most n chops, merging the shortest neighbours."""
    import librosa
    from .edit import _load
    y = _load(rel)
    sr = C.SR
    on = librosa.onset.onset_detect(y=y.mean(0), sr=sr, hop_length=256, backtrack=True, units="samples").tolist()
    b = sorted(set([0] + [o for o in on if o > 0] + [y.shape[1]]))
    segs = [[a, e] for a, e in zip(b[:-1], b[1:])]
    segs = [s for s in segs if s[1] - s[0] > 0] or [[0, y.shape[1]]]
    while len(segs) > n or any(s[1] - s[0] < min_len * sr for s in segs) and len(segs) > 1:
        k = int(np.argmin([s[1] - s[0] for s in segs]))
        j = k - 1 if k == len(segs) - 1 or (k > 0 and segs[k - 1][1] - segs[k - 1][0] < segs[k + 1][1] - segs[k + 1][0]) else k + 1
        a, c = min(k, j), max(k, j)
        segs[a:c + 1] = [[segs[a][0], segs[c][1]]]
    out = []
    for a, e in segs:
        z = y[:, a:e].copy()
        f = min(int(0.004 * sr), z.shape[1] // 4)
        if f:
            z[:, :f] *= np.linspace(0, 1, f, dtype=np.float32)
            z[:, -f:] *= np.linspace(1, 0, f, dtype=np.float32)
        out.append((z, a / sr))
    return out
