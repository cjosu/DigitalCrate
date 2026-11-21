"""End to end on synthetic audio: scan -> process -> build -> serve, in a throwaway library.

    pytest --slow tests/test_pipeline.py      (first run downloads the separation and CLAP models)
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

import numpy as np
import pytest
import soundfile as sf

from conftest import SR, tone

pytestmark = pytest.mark.slow


def _track():
    """~40 s: a slow chord progression with a sung-ish melody on top, so there are pads and phrases to find."""
    chords = [(220, 261.6, 329.6), (174.6, 220, 261.6), (196, 246.9, 293.7), (164.8, 207.7, 246.9)] * 2
    pad = np.concatenate([tone(c, 5.0) for c in chords], axis=1)
    t = np.arange(pad.shape[1]) / SR
    f = 440 * 2 ** (np.round(4 * np.sin(2 * np.pi * t / 7)) / 12)
    mel = 0.15 * np.sin(2 * np.pi * np.cumsum(f) / SR) * (0.5 + 0.5 * np.sin(2 * np.pi * t / 2.5) ** 2)
    return (pad + mel[None]).astype(np.float32)


def test_pipeline(tmp_path):
    music, lib = tmp_path / "music" / "Test Artist" / "Test Album", tmp_path / "lib"
    music.mkdir(parents=True)
    sf.write(music / "01 Test Track.wav", _track().T, SR)
    env = dict(os.environ, DIGITALCRATE_MUSIC=str(tmp_path / "music"), DIGITALCRATE_LIBRARY=str(lib),
               DIGITALCRATE_FOUND=str(tmp_path / "found"), DIGITALCRATE_ABLETON_SAMPLES=str(tmp_path / "ableton"),
               DIGITALCRATE_CONFIG=str(tmp_path / "none.toml"))
    run = lambda *a: subprocess.run([sys.executable, "-m", "digitalcrate", *a], env=env, check=True,
                                    capture_output=True, text=True).stdout
    assert "1 new" in run("scan")
    run("policy")
    out = run("process", "--all", "--separate", "never")
    assert "ERROR" not in out, out
    n = int(out.rsplit("done:", 1)[1].split()[0])
    assert n > 0, out
    run("build")
    assert (lib / "Browser.html").exists()

    srv = subprocess.Popen([sys.executable, "-c", "from digitalcrate.serve import serve; serve(8799, open_browser=False)"],
                           env=env)
    try:
        for _ in range(60):
            try:
                assert urllib.request.urlopen("http://localhost:8799/").status == 200
                break
            except OSError:
                time.sleep(1)
        else:
            pytest.fail("server did not start")
        r = json.load(urllib.request.urlopen("http://localhost:8799/api/shootout"))
        assert "items" in r
        # saving a pitch-shifted edit returns its own "goes well with" picks, scored in the new key
        src = json.loads(lib.joinpath("Browser.html").read_text().split('type="application/json">', 1)[1]
                         .split("</script>", 1)[0])["samples"]
        keyed = next(x for x in src if x[5])  # a sample with a key
        req = urllib.request.Request("http://localhost:8799/api/edit/save", method="POST",
                                     data=json.dumps({"path": keyed[1], "params": {"semis": 3}}).encode())
        row = json.load(urllib.request.urlopen(req, timeout=300))["row"]
        assert row["cam"] != keyed[5]
        assert "partners" in row and all(len(p) == 4 for p in row["partners"])
    finally:
        srv.terminate()
