"""Loudness and peak conditioning for a rendered bass loop."""

import numpy as np
from scipy.fft import rfft, rfftfreq
from scipy.ndimage import maximum_filter1d, uniform_filter1d
from scipy.signal import hilbert, sosfiltfilt


VERSION = 1
P = dict(sub_over=3.0, sub_share=0.5, sub_max=6.0, sub_fc=70, thr=5.0, knee=6.0, ratio=3.0,
         att=0.005, rel=0.15, peak_over=12.0, peak_win=0.003, weigh=0.5, offset=6.4, swing=4.0,
         ceil=0.9, target=0.08, max_gain=60.0)


def _db(value):
    return 20 * np.log10(np.maximum(value, 1e-12))


def _spectrum(x, sr):
    power = np.abs(rfft(x)) ** 2
    if x.ndim == 2:
        power = power.mean(axis=0)
    # The real FFT stores the DC and Nyquist bins once and the other frequencies in pairs.
    power[1:] *= 2
    if x.shape[-1] % 2 == 0:
        power[-1] *= 0.5
    return rfftfreq(x.shape[-1], 1 / sr), power


def _weighted_rms(freq, power, length):
    f2 = freq ** 2
    weight = (12194**2 * freq ** 3 * 10**(0.17 / 20)
              / ((f2 + 20.6**2) * np.sqrt(f2 + 158.5**2) * (f2 + 12194**2)))
    return float(np.sqrt(np.dot(power, weight ** 2)) / length)


def heard(x, sr):
    """B-weighted RMS of a mono signal."""
    if not len(x):
        return 0.0
    return _weighted_rms(*_spectrum(x, sr), len(x))


def _low_shelf(fc, gain_db, sr):
    # RBJ low shelf with a slope of 1.
    a = 10 ** (gain_db / 40)
    w = 2 * np.pi * fc / sr
    c, s = np.cos(w), np.sin(w)
    beta = np.sqrt(2 * a) * s
    b0 = a * ((a + 1) - (a - 1) * c + beta)
    b1 = 2 * a * ((a - 1) - (a + 1) * c)
    b2 = a * ((a + 1) - (a - 1) * c - beta)
    a0 = (a + 1) + (a - 1) * c + beta
    a1 = -2 * ((a - 1) + (a + 1) * c)
    a2 = (a + 1) + (a - 1) * c - beta
    return np.array([[b0 / a0, b1 / a0, b2 / a0, 1, a1 / a0, a2 / a0]], np.float32)


def _rms(y):
    return float(np.sqrt(np.mean(y ** 2)))


def _interpolate(curve, edges):
    return np.interp(np.arange(edges[-1]), edges, np.r_[curve, curve[0]]).astype(np.float32)


def _compress(y, rms, edges, rate):
    # The analytic envelope of one periodic loop matches that of three copies.
    envelope = np.sqrt(np.mean(np.abs(hilbert(y, axis=1)) ** 2, axis=0))
    control = np.add.reduceat(envelope, edges[:-1]) / np.diff(edges)
    control = uniform_filter1d(control, max(1, round(0.010 * rate)), mode="wrap")
    over = _db(control) - (_db(rms) + P["thr"])
    knee = P["knee"]
    reduction = np.where(over > knee / 2, over, np.maximum(over + knee / 2, 0) ** 2 / (2 * knee))
    target = -reduction * (1 - 1 / P["ratio"])
    down, up = (1 - np.exp(-1 / (P[k] * rate)) for k in ("att", "rel"))
    needed = np.tile(target, 3)
    smooth = np.empty_like(needed)
    gain = 0.0
    for i, desired in enumerate(needed):
        gain += (desired - gain) * (down if desired < gain else up)
        smooth[i] = gain
    n = len(target)
    ahead = min(n, round(P["att"] * rate))
    return y * _interpolate(10 ** (smooth[n + ahead:2 * n + ahead] / 20), edges)


def _hold_peaks(y, ceiling, edges, rate):
    peaks = np.maximum.reduceat(np.max(np.abs(y), axis=0), edges[:-1])
    if peaks.max() <= ceiling:
        return y
    radius = max(1, round(P["peak_win"] * rate))
    held = maximum_filter1d(peaks, 2 * radius + 1, mode="wrap")
    gain = np.minimum(1, ceiling / np.maximum(held, 1e-12))
    if radius >= 2:
        gain = uniform_filter1d(gain, 3, mode="wrap")
    # Both ends of each interval see its peak, even after smoothing.
    return y * _interpolate(gain, edges)


def condition(y, sr):
    """Condition a stereo float32 loop and keep its shape, timing and dtype."""
    length = y.shape[-1]
    if not length:
        return y.copy()
    source = y
    input_rms = rms = _rms(y)
    if rms * P["max_gain"] <= P["target"]:
        peak = float(np.abs(y).max())
        gain = min(P["max_gain"], P["ceil"] / max(peak, 1e-12))
        return np.clip(y * gain, -P["ceil"], P["ceil"])

    freq, power = _spectrum(y, sr)
    sub = float(power[(freq >= 30) & (freq < 60)].sum())
    mid = float(power[(freq >= 60) & (freq < 300)].sum())
    # Leave a pure sub alone. Note attacks can put a little of its energy in the next band.
    if sub and mid > 0.01 * sub:
        cut = np.clip((10 * np.log10(sub / mid) - P["sub_over"]) * P["sub_share"], 0, P["sub_max"])
        if cut > 0.1:
            shelf = _low_shelf(P["sub_fc"], -cut / 2, sr)
            loop = sosfiltfilt(shelf, np.tile(y, (1, 3)), axis=1, padlen=0)
            y = loop[:, length:2 * length].copy()
            rms = _rms(y)

    # Wrap the control points and retain the middle pass of the compressor.
    count = max(1, min(length, round(length * 1000 / sr)))
    edges = np.linspace(0, length, count + 1, dtype=np.int64)
    rate = count * sr / length
    y = _compress(y, rms, edges, rate)
    y = _hold_peaks(y, _rms(y) * 10 ** (P["peak_over"] / 20), edges, rate)
    rms_db = _db(_rms(y))
    weighted_db = _db(_weighted_rms(*_spectrum(y, sr), length))
    energy_gain = _db(P["target"]) - rms_db
    correction = np.clip(P["weigh"] * (rms_db - weighted_db - P["offset"]), -P["swing"], P["swing"])
    gain = min(10 ** ((energy_gain + correction) / 20), P["max_gain"])
    # A click can mask near-silence until it is limited. Fade in the gain above the plain render
    # over 12 dB so a small difference in the remaining signal cannot lift a quiet bed abruptly.
    quiet_edge = _db(P["target"] / P["max_gain"])
    above_quiet = np.clip((rms_db - quiet_edge) / 12, 0, 1)
    if above_quiet < 1:
        input_peak = float(np.abs(source).max())
        plain_gain = min(P["target"] / input_rms, P["ceil"] / input_peak, P["max_gain"])
        gain = min(gain, plain_gain * (gain / plain_gain) ** above_quiet)
    y *= np.float32(gain)
    return np.clip(_hold_peaks(y, P["ceil"], edges, rate), -P["ceil"], P["ceil"])
