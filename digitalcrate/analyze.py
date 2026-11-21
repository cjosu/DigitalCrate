"""Track-level analysis (tempo, key) and frame-level features per source."""
import numpy as np
import librosa
from scipy.ndimage import uniform_filter1d
import essentia
import essentia.standard as es

from .config import SR, SR_F, N_FFT, HOP, FPS
from .audio import pc_of, camelot, to_mono22

essentia.log.warningActive = False
essentia.log.infoActive = False

# Krumhansl-Kessler key profiles
_MAJ = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MIN = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def track_tempo_key(y):
    mono = y.mean(0).astype(np.float32)
    bpm, beats, conf, _, _ = es.RhythmExtractor2013(method="multifeature")(mono)
    key, scale, strength = es.KeyExtractor(profileType="edma", sampleRate=SR)(mono)
    bpm = float(bpm)
    # fold silly tempi into a producer-friendly range
    while bpm and bpm < 70:
        bpm *= 2
    while bpm > 180:
        bpm /= 2
    pc = pc_of(key)
    return dict(bpm=round(bpm, 2), bpm_conf=float(conf), beats=np.asarray(beats, float),
                tempo_ok=bool(conf >= 1.0 and len(beats) > 16),
                pc=pc, scale=scale, key_strength=float(strength), camelot=camelot(pc, scale))


def bar_starts(beats, mix_feat):
    """Pick a 4/4 bar phase using low-band onset strength at each beat."""
    if len(beats) < 8:
        return np.array([])
    low = mix_feat.S[:24]  # < ~250 Hz
    flux = np.maximum(0, np.diff(low, axis=1, prepend=low[:, :1])).sum(0)
    idx = np.clip((beats * FPS).astype(int), 0, len(flux) - 1)
    strength = [flux[idx[p::4]].mean() for p in range(4)]
    return beats[int(np.argmax(strength))::4]


class SourceFeat:
    """STFT-based frame features for one source signal (mix or a stem)."""

    def __init__(self, y44, hpss=True):
        self.mono = to_mono22(y44)
        S = np.abs(librosa.stft(self.mono, n_fft=N_FFT, hop_length=HOP)).astype(np.float32)
        self.S = S
        pw = (S ** 2).mean(0)
        self.db = 10 * np.log10(uniform_filter1d(pw, 5) + 1e-12)
        self.db_raw = 10 * np.log10(pw + 1e-12)
        if hpss:
            H, P = librosa.decompose.hpss(S, kernel_size=(17, 31))
            h, p = (H ** 2).sum(0), (P ** 2).sum(0)
            self.pratio = uniform_filter1d(p / (h + p + 1e-12), 21)  # ~1 s smoothing
        else:
            self.pratio = None
        self.p95 = np.percentile(self.db, 95)
        self.n = S.shape[1]

    def active(self, below=28, floor=-62):
        return self.db > max(self.p95 - below, floor)


def frames_to_sec(f):
    return f / FPS


def sec_to_frames(s):
    return int(round(s * FPS))


def runs(mask, min_len=1, max_gap=0):
    """Contiguous True runs as (start, end) frame pairs, merging gaps <= max_gap."""
    m = np.asarray(mask, bool)
    if not m.any():
        return []
    d = np.diff(np.concatenate([[0], m.astype(int), [0]]))
    starts, ends = np.flatnonzero(d == 1), np.flatnonzero(d == -1)
    out = []
    for s, e in zip(starts, ends):
        if out and s - out[-1][1] <= max_gap:
            out[-1][1] = e
        else:
            out.append([s, e])
    return [(s, e) for s, e in out if e - s >= min_len]


def sample_key(chroma, track_pc, track_scale):
    """Key from a 12-bin chroma using K-K profiles, nudged toward the track key."""
    c = chroma - chroma.mean()
    if np.allclose(c, 0):
        return track_pc, track_scale, 0.0, "track"
    best = (-2, 0, "minor")
    for pc in range(12):
        for scale, prof in (("major", _MAJ), ("minor", _MIN)):
            r = np.corrcoef(c, np.roll(prof, pc))[0, 1]
            if pc == track_pc and scale == track_scale:
                r += 0.05
            if r > best[0]:
                best = (r, pc, scale)
    r, pc, scale = best
    if r < 0.45:
        return track_pc, track_scale, float(r), "track"
    return pc, scale, float(r), "sample"


def segment_stats(feat, f0, f1):
    """Spectral stats for frames [f0, f1) of a SourceFeat."""
    S = feat.S[:, f0:f1]
    pw = S ** 2
    chroma = librosa.feature.chroma_stft(S=pw, sr=SR_F, n_fft=N_FFT).mean(1)
    chroma = chroma / (chroma.max() + 1e-9)
    freqs = librosa.fft_frequencies(sr=SR_F, n_fft=N_FFT)
    spec = pw.mean(1)
    centroid = float((freqs * spec).sum() / (spec.sum() + 1e-12))
    flat = float(librosa.feature.spectral_flatness(S=S).mean())
    pr = float(feat.pratio[f0:f1].mean()) if feat.pratio is not None else 0.0
    loud = float(np.percentile(feat.db_raw[f0:f1], 90))
    return dict(chroma=chroma, centroid=centroid, flatness=flat, pratio=pr, loudness=loud)
