"""Fast checks of the pure parts: genre mapping, key parsing, the stretch and tuning engines."""
import numpy as np
import pytest

from conftest import SR, tone
from digitalcrate import genre
from digitalcrate.conform import parse_key
from digitalcrate.stretch import repitch, shift


@pytest.mark.parametrize("tag, fam", [
    ("Techno", "Electronic"),
    ("Disco/Deep House/Funk", "Electronic"),      # compound tag: Electronic beats Soul
    ("Ambient/Dark Ambient/Drone", "Ambient"),
    ("Broken Beat / Nu-Jazz, Classic House", "Electronic"),
    ("R&B", "Soul & R&B"),
    ("Folk Rock", "Folk"),
    ("Classical", "Classical"),
    ("Lo-Fi", "Other"),
    ("", None),
    (None, None),
])
def test_from_tag(tag, fam):
    assert genre.from_tag(tag) == fam


def test_family_order_of_evidence():
    ov = {"vladislav delay": "Electronic"}
    cons = {"gas": "Ambient"}
    assert genre.family("Vladislav  Delay", "Blues", ov, cons) == "Electronic"   # override beats a wrong tag
    assert genre.family("Gas", None, ov, cons) == "Ambient"                      # untagged: artist consensus
    assert genre.family("Gas", "Minimal", ov, cons) == "Electronic"              # a real tag beats consensus
    assert genre.family("Nobody", None, ov, cons) is None                        # left to the audio


@pytest.mark.parametrize("k, out", [("Fm", (5, "minor")), ("Ab", (8, "major")), ("C#m", (1, "minor"))])
def test_parse_key(k, out):
    assert parse_key(k) == out


def test_repitch_changes_length_like_tape():
    y = tone(440, 2.0)
    up = repitch(y, 12)                                  # an octave up = half as long
    assert abs(up.shape[1] / y.shape[1] - 0.5) < 0.01


def test_signalsmith_keeps_length_on_pitch_and_stretches_on_time():
    y = tone(440, 2.0)
    z, eng = shift(y, 3, 1.0, engine="signalsmith")
    assert eng == "signalsmith" and abs(z.shape[1] - y.shape[1]) < SR * 0.05
    z, _ = shift(y, 0, 1.25, engine="signalsmith")
    assert abs(z.shape[1] / y.shape[1] - 1.25) < 0.02


def test_auto_engine():
    y = tone(440, 1.0)
    assert shift(y, 2, 1.0)[1] == "repitch"
    assert shift(y, 0, 1.1)[1] == "signalsmith"


def _f0(y):
    import librosa
    f, v, _ = librosa.pyin(y[0], fmin=150, fmax=1000, sr=SR)
    return np.nanmedian(f[v])


def test_tune_pulls_a_flat_note_into_key():
    from digitalcrate.retune import tune
    flat = 440 * 2 ** (-0.4 / 12)                         # A, 40 cents flat
    y = tone(flat, 2.0)
    z = tune(y, "A", strength=1.0, speed_ms=0)
    before, after = abs(1200 * np.log2(_f0(y) / 440)), abs(1200 * np.log2(_f0(z) / 440))
    assert after < before / 2
