import numpy as np
import pytest

SR = 44100


def pytest_addoption(parser):
    parser.addoption("--slow", action="store_true", help="also run the end-to-end pipeline test (loads models)")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--slow"):
        return
    skip = pytest.mark.skip(reason="end-to-end: run with --slow")
    for it in items:
        if "slow" in it.keywords:
            it.add_marker(skip)


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: end-to-end test that loads the separation and CLAP models")


def tone(freqs, secs=4.0, sr=SR):
    """A soft stereo chord: sum of sines with a gentle attack and release."""
    t = np.arange(int(secs * sr)) / sr
    y = sum(np.sin(2 * np.pi * f * t) for f in np.atleast_1d(freqs)) / len(np.atleast_1d(freqs))
    env = np.minimum(1, t / 0.05) * np.minimum(1, (secs - t) / 0.2)
    y = (0.3 * y * env).astype(np.float32)
    return np.stack([y, y])
