"""Decoding, writing and small DSP helpers."""
import subprocess
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

from .config import SR

PITCHES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
_ALIASES = {"Db": "C#", "D#": "Eb", "Gb": "F#", "G#": "Ab", "A#": "Bb", "Cb": "B", "Fb": "E", "E#": "F", "B#": "C"}


def decode(path, sr=SR):
    """Decode any file ffmpeg understands to float32 stereo (2, n)."""
    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-i", str(path), "-map", "0:a:0",
           "-f", "f32le", "-acodec", "pcm_f32le", "-ac", "2", "-ar", str(sr), "-"]
    out = subprocess.run(cmd, capture_output=True, check=True).stdout
    y = np.frombuffer(out, np.float32).reshape(-1, 2).T.copy()
    return y


def to_mono22(y):
    return resample_poly(y.mean(0), 1, 2).astype(np.float32)


def to_mono48(y_mono44):
    return resample_poly(y_mono44, 160, 147).astype(np.float32)


def write_wav(path, y, fade_in=0.005, fade_out=0.03, sr=SR):
    y = y.copy()
    n = y.shape[1]
    fi, fo = int(fade_in * sr), int(fade_out * sr)
    if fi > 0:
        y[:, :fi] *= np.linspace(0, 1, fi, dtype=np.float32)
    if fo > 0 and fo < n:
        y[:, -fo:] *= np.linspace(1, 0, fo, dtype=np.float32)
    peak = np.abs(y).max()
    if peak > 1e-6:
        y *= 0.891 / peak  # normalise to -1 dBFS
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), y.T, sr, subtype="PCM_24")


def pc_of(name):
    name = _ALIASES.get(name, name)
    return PITCHES.index(name)


def camelot(pc, scale):
    """Camelot code like '8A' (A minor) / '8B' (C major)."""
    if scale == "major":
        n = (pc * 7 + 8) % 12
        return f"{n or 12}B"
    n = (pc * 7 + 5) % 12
    return f"{n or 12}A"


def camelot_parts(code):
    return int(code[:-1]), code[-1]


def key_label(pc, scale):
    return PITCHES[pc] + ("m" if scale == "minor" else "")
