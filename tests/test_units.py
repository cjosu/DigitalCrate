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


def test_stems_are_aligned(tmp_path, monkeypatch):
    """Stems of different lengths come out trimmed to one length, with one shared gain, plus a reference mix."""
    import base64, io
    import soundfile as sf
    from digitalcrate import combos
    monkeypatch.setattr(combos.C, "ABLETON_SAMPLES", tmp_path)

    def wav(n, amp):
        b = io.BytesIO()
        sf.write(b, np.full((n, 2), amp, np.float32), 44100, format="WAV", subtype="FLOAT")
        return base64.b64encode(b.getvalue()).decode()
    r = combos.write_stems("Test", [dict(label="MEL a", wav=wav(44100, .9)), dict(label="KEYS b", wav=wav(44000, .6))],
                           key="Fm", bpm=80, reveal=False)
    files = sorted((tmp_path / "Sketches" / "Test (Fm, 80 bpm)").glob("*.wav"))
    assert [f.name for f in files] == ["00 mix (reference).wav", "01 MEL a.wav", "02 KEYS b.wav"]
    a, b = (sf.read(str(f))[0] for f in files[1:])
    assert len(a) == len(b) == 44000
    assert abs(a.max() / b.max() - 1.5) < 1e-3  # balance kept
    assert sf.read(str(files[0]))[0].max() <= 0.891


def test_harmony_theory():
    """Chord names are spelled for the key, Roman numerals are right, and fit prefers chords whose tones sound."""
    from digitalcrate.harmony import _vocab, _fit
    v = _vocab(5, "minor", "soulful")  # F minor
    names = {c["name"]: c["roman"] for c in v}
    assert names.get("Dbmaj9") == "bVImaj9" and names.get("Fm9") == "i9" and "C#maj9" not in names
    w = np.zeros(12); w[[0, 4, 7]] = 1 / 3  # C E G sounding
    plain = _vocab(0, "major", "plain")
    best = max(plain, key=lambda c: _fit(c, w))
    assert best["root"] == 0 and best["q"] in ("", "add9")
    clash = next(c for c in plain if c["root"] == 4)  # E minor over C E G: C is a semitone above B -> penalised
    assert _fit(clash, w) < _fit(best, w)


def test_voicings_use_only_chord_tones():
    """Every voiced note belongs to its chord (a 5-note voicing once fell back to wrong notes), root in the bass."""
    from digitalcrate.harmony import _vocab, _voicing, QUAL
    for tonic, mode in ((5, "minor"), (8, "major"), (2, "minor")):
        for style in ("soulful", "dark", "ethereal", "plain"):
            prev = None
            for ch in _vocab(tonic, mode, style):
                v = _voicing(ch, prev, 57, 76)
                assert {n % 12 for n in v} <= {(ch["root"] + i) % 12 for i in QUAL[ch["q"]]}, ch["name"]
                assert v[0] % 12 == ch["root"] and v[0] < min(v[1:])
                prev = v[1:]


def test_whisper_hallucinations_are_dropped():
    from digitalcrate.lyrics import _clean
    seg = lambda t, **k: dict(dict(text=t, no_speech_prob=0.0, avg_logprob=-0.3, compression_ratio=1.2,
                                   words=[dict(word=w, start=i * 0.4, end=i * 0.4 + 0.3, probability=0.9)
                                          for i, w in enumerate(t.split())]), **k)
    assert _clean(dict(segments=[seg(" Thank you.")]))[0] == ""
    assert _clean(dict(segments=[seg(" Ba-a-a-a-a-a-a-a-a")]))[0] == ""
    assert _clean(dict(segments=[seg(" oh love", avg_logprob=-1.4)]))[0] == ""
    text, words, _ = _clean(dict(segments=[seg(" How can I even try")], language="en"))
    assert text == "How can I even try" and words[1][0] == "can"


def test_style_families_and_search_phrases():
    from digitalcrate.styles import family_of
    from digitalcrate.related import phrase, _style_ok
    assert family_of([["Jazz---Hard Bop", 0.4], ["Jazz---Post Bop", 0.3]]) == "Jazz"
    assert family_of([["Electronic---Ambient", 0.5], ["Electronic---Drone", 0.4]]) == "Ambient"
    assert family_of([["Funk / Soul---Neo Soul", 0.05]]) is None  # nothing confident
    assert phrase("Classical---Modern") == "modern classical" and phrase("Funk / Soul---Neo Soul") == "neo soul"
    assert not _style_ok("Hip Hop---Boom Bap") and _style_ok("Electronic---Ambient") and not _style_ok("Rock---Punk")


def test_beat_this_bars_fall_back_without_a_grid(monkeypatch):
    import numpy as np
    from digitalcrate import analyze
    beats = np.arange(0, 60, 0.5)  # a steady 120 bpm, downbeat every 4th beat
    monkeypatch.setattr(analyze, "beat_this", lambda y: (beats, beats[::4]))
    tk = dict(beats=np.array([]), tempo_ok=False, bpm=0)
    bars, how = analyze.bars(tk, None, None)
    assert how == "beat_this" and tk["tempo_ok"] and abs(tk["bpm"] - 120) < 0.01 and len(bars) == 30
    rng = np.random.default_rng(0)  # rubato: no grid, and Essentia didn't trust its tempo either
    loose = np.cumsum(rng.uniform(0.3, 0.9, 80))
    monkeypatch.setattr(analyze, "beat_this", lambda y: (loose, loose[::4]))
    tk = dict(beats=np.array([]), tempo_ok=False, bpm=0)
    assert analyze.bars(tk, None, None)[1] == "none"


def test_setup_saves_folders(tmp_path, monkeypatch):
    """The setup page writes the two folders into the config in use, keeps other settings, and refuses bad choices."""
    from digitalcrate import app, config as C
    cfg = tmp_path / "digitalcrate.toml"
    cfg.write_text('reference_artists = ["X"]\nmusic = "/old"\n')
    monkeypatch.setattr(C, "CONFIG_FILE", cfg)
    music = tmp_path / "Music"; music.mkdir()
    (music / "a.mp3").write_bytes(b""); (music / "._a.mp3").write_bytes(b"")
    assert app.count_audio(music) == {"n": 1, "more": False}
    app.save_config(music, tmp_path / "Lib")
    import tomllib
    d = tomllib.loads(cfg.read_text())
    assert d["music"] == str(music) and d["library"] == str(tmp_path / "Lib") and d["reference_artists"] == ["X"]
    import pytest
    with pytest.raises(ValueError):
        app.save_config(tmp_path / "nope", tmp_path / "Lib")
    with pytest.raises(ValueError):
        app.save_config(music, music / "Lib")


def test_drum_hits_are_trimmed_to_the_impact():
    """Exported drum one-shots start on the hit (most mined hits open with 20-40 ms before it)."""
    import numpy as np
    from digitalcrate.export import trim_to_hit
    sr = 44100
    t = np.arange(int(0.3 * sr)) / sr
    hit = np.sin(2 * np.pi * 80 * t) * np.exp(-t * 20)
    y = np.stack([np.r_[np.zeros(int(0.03 * sr)), hit]] * 2).astype(np.float32)  # 30 ms before the impact
    z = trim_to_hit(y, sr)
    first = int(np.argmax(np.abs(z[0]) >= 0.25 * np.abs(z[0]).max())) / sr
    assert first < 0.004 and z.shape[1] < y.shape[1]
    assert trim_to_hit(z, sr).shape == z.shape  # already on the hit: left alone


def test_suggestions_are_precomputed_and_go_stale_on_a_rating(monkeypatch):
    """The editor's background precompute is used by ✨ (shown only then), the next press is precomputed, and a
    rating makes a precomputed run stale."""
    import time
    from digitalcrate import suggest as sg
    calls = []

    def fake(rel, pk=None, start=None, end=None, n=3, seed=None, log=True, commit=True):
        calls.append(rel)
        time.sleep(0.2)
        return dict(suggestions=[], _shown=dict(ids={len(calls)}, types=set(), families=set()), _rel=rel, _sid="x")
    monkeypatch.setattr(sg, "suggest", fake)
    monkeypatch.setattr(sg, "_PRE", {})
    monkeypatch.setattr(sg, "_SHOWN", {})
    sg.prefetch("a.wav", None, 0, 2)
    assert "a.wav" not in sg._SHOWN  # not shown yet
    r = sg.suggest_now("a.wav", None, 0, 2, log=False)
    assert r["precomputed"] and len(calls) == 2 and sg._SHOWN["a.wav"][-1]["ids"] == {1}  # the next is on its way
    time.sleep(0.3)
    t = time.time()
    assert sg.suggest_now("a.wav", None, 0, 2, log=False)["precomputed"] and time.time() - t < 0.1
    time.sleep(0.3)
    sg.stale("a.wav")
    assert not sg.suggest_now("a.wav", None, 0, 2, log=False)["precomputed"]
