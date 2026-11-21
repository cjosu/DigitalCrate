"""Pitch / time engines, chosen by your blind shootout (digitalcrate/shootout.py, Nov 2026):

  not stretched (phrases, chops, one-shots, free pads) -> Re-Pitch: plain resampling, tape-style. Pitch and length
                                                          move together; zero processing artifacts. Best on vocals + keys.
  stretched (loops, editor stretch)                   -> Signalsmith Stretch. Tied Rubber Band R3 on drums / loops /
                                                          keys, clearly better on vocals.
  Rubber Band R3 with formant preservation scored worst on vocals (1.9 / 5), so it's only used when explicitly asked.
"""
from fractions import Fraction

import numpy as np

from . import config as C

SR = C.SR


def repitch(y, semis):
    """Varispeed: semis up = shorter, like speeding up tape."""
    if not semis:
        return y
    from scipy.signal import resample_poly
    f = Fraction(2 ** (-semis / 12)).limit_denominator(1000)
    return resample_poly(y, f.numerator, f.denominator, axis=1).astype(np.float32)


def signalsmith(y, semis=0.0, time=1.0):
    """time = output length / input length."""
    import python_stretch as ps
    s = ps.Signalsmith.Stretch(7)
    s.preset(y.shape[0], float(SR))
    s.setTransposeSemitones(float(semis))
    s.setTimeFactor(float(1 / time))
    return s.process(np.ascontiguousarray(y, dtype=np.float32))


def shift(y, semis=0.0, time=1.0, engine="auto", formant=False):
    """-> (audio, engine used). auto: Re-Pitch when no stretch is needed, else Signalsmith."""
    if engine == "auto":
        engine = "rubberband" if formant else "repitch" if abs(time - 1) < 1e-3 else "signalsmith"
    if engine == "repitch":
        return repitch(y, semis), engine
    if engine == "rubberband":
        from .mangle import _rb
        return _rb(y, time=time, semis=semis, formant=formant), engine
    return signalsmith(y, semis, time), engine
