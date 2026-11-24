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


def test_fits_my_track_key_and_tempo():
    import numpy as np
    from digitalcrate.mytrack import key_fit, tempo_fit
    # track in C major (pc 0). Samples: C major, A minor (relative), D major (+2 away), F# major, unkeyed
    fit, shift = key_fit(np.array([0, 9, 2, 6, 0]), np.array([False, True, False, False, False]),
                         np.array([True, True, True, True, False]), 0, False)
    assert shift[0] == 0 and shift[1] == 0 and shift[2] == -2 and abs(shift[3]) == 6
    assert fit[0] > fit[1] > fit[2] > fit[3] and fit[4] == 0.75
    tf, pct = tempo_fit(np.array([True, True, True, False]), np.array([90.0, 45.0, 100.0, 0.0]), 90.0)
    assert tf[0] == tf[1] == 1.0 and pct[2] > 10 and tf[2] < 0.2 and tf[3] == 1.0  # half time is on tempo


def _pad(sr=SR, secs=6.0, seed=1):
    """A synthetic pad: a soft attack, a steady chord with slow vibrato and some air, and a fade."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(secs * sr)) / sr
    y = sum(np.sin(2 * np.pi * f * t + 0.3 * np.sin(2 * np.pi * 0.25 * t)) for f in (220.0, 277.18, 329.63)) / 3
    y = y + 0.02 * rng.standard_normal(len(t))
    env = np.minimum(1, t / 0.3) * np.minimum(1, (secs - t) / 0.8)
    return (0.5 * y * env).astype(np.float32)


def test_sustain_loop_is_seamless_and_survives_export(tmp_path):
    import soundfile as sf
    import struct
    from digitalcrate.loopfind import find_loop, seam, bake, write_smpl, MAX_SEAM
    y = _pad()
    lp = find_loop(y, SR)
    assert lp and 0.3 <= lp["start"] < lp["end"] <= 5.3 and lp["end"] - lp["start"] >= 0.5
    assert seam(y, SR, lp) <= MAX_SEAM
    assert find_loop(np.zeros(SR * 4, np.float32), SR) is None  # silence: nothing to loop
    b = bake(y, SR, dict(lp, xf=0.05))
    a, e, n = int(lp["start"] * SR), int(lp["end"] * SR), int(0.05 * SR)
    assert np.allclose(b[:e - n], y[:e - n]) and np.allclose(b[e:], y[e:])  # only the loop's last 50 ms change
    f = tmp_path / "pad.wav"
    sf.write(str(f), y, SR, subtype="PCM_24")
    write_smpl(f, a, e - 1)
    raw = f.read_bytes()
    assert struct.unpack("<I", raw[4:8])[0] == len(raw) - 8
    k = raw.index(b"smpl")
    assert struct.unpack("<6I", raw[k + 8 + 36:k + 8 + 60])[2:4] == (a, e - 1)
    assert sf.read(str(f))[0].shape[0] == len(y)  # still an ordinary WAV


def test_neighborhood_attention_matches_a_direct_reference():
    """The plain-PyTorch NATTEN functions (for All-In-One's song sections), against a slow obvious version."""
    import torch
    from digitalcrate import _natten as N

    def ref_1d(q, k, rpb, K, d):
        n = q.shape[2]
        out = torch.zeros(*q.shape[:3], K)
        for i in range(n):
            g, ig = i % d, i // d
            members = list(range(g, n, d))
            s = min(max(ig - K // 2, 0), len(members) - K)
            for j in range(K):
                nb = members[s + j]
                out[:, :, i, j] = (q[:, :, i] * k[:, :, nb]).sum(-1) + rpb[:, s + j - ig + K - 1]
        return out
    torch.manual_seed(0)
    for n, K, d in [(20, 5, 1), (23, 3, 4), (30, 7, 2)]:
        q, k, v = (torch.randn(1, 2, n, 4) for _ in range(3))
        rpb = torch.randn(2, 2 * K - 1)
        a = N.natten1dqkrpb(q, k, rpb, K, d)
        assert torch.allclose(a, ref_1d(q, k, rpb, K, d), atol=1e-5)
        p = a.softmax(-1)
        nb, _ = N._idx(n, K, d, "cpu")
        direct = torch.stack([(p[:, :, i, :, None] * v[:, :, nb[i]]).sum(2) for i in range(n)], 2)
        assert torch.allclose(N.natten1dav(p, v, K, d), direct, atol=1e-5)
    q, k = torch.randn(1, 2, 4, 9, 4), torch.randn(1, 2, 4, 9, 4)
    rpb = torch.zeros(2, 5, 5)
    a = N.natten2dqkrpb(q, k, rpb, 3, 1)
    assert a.shape == (1, 2, 4, 9, 9)
    # 2D with no bias is the product of the two 1D neighbourhoods: corner (0, 0) sees rows 0-2, columns 0-2
    assert torch.allclose(a[0, 0, 0, 0, 4], (q[0, 0, 0, 0] * k[0, 0, 1, 1]).sum(), atol=1e-5)


def test_song_sections_label_samples_and_steer_mining():
    from digitalcrate.sections import of_sample, adjust
    secs = [(0.0, 20.0, "intro"), (20.0, 50.0, "verse"), (50.0, 70.0, "chorus"), (70.0, 80.0, "outro")]
    assert of_sample(secs, 18.0, 30.0) == "verse" and of_sample(secs, 72.0, 75.0) == "outro"
    assert of_sample([], 1, 2) is None
    c = adjust([dict(start=2.0, end=6.0, quality=0.5, kind="free"),       # in the intro: a little bonus
                dict(start=30.0, end=34.0, quality=0.5, kind="free"),     # in a verse: unchanged
                dict(start=46.0, end=54.0, quality=0.5, kind="loop"),     # a loop across verse -> chorus
                dict(start=52.0, end=60.0, quality=0.5, kind="loop")], secs)
    assert c[0]["quality"] > 0.5 and c[1]["quality"] == 0.5 and c[2]["quality"] < 0.5 and c[3]["quality"] == 0.5
    assert [x["section"] for x in c] == ["intro", "verse", "verse", "chorus"]


def _chords(seq, secs_each, sr=SR):
    """Held triads with a little air, one after another: seq like [(57, 'm'), (53, '')] (root MIDI note, quality)."""
    out = []
    rng = np.random.default_rng(3)
    for root, q in seq:
        t = np.arange(int(secs_each * sr)) / sr
        notes = [root, root + (3 if q == "m" else 4), root + 7, root + 12]
        y = sum(np.sin(2 * np.pi * 440 * 2 ** ((n - 69) / 12) * t) for n in notes) / len(notes)
        out.append(y + 0.01 * rng.standard_normal(len(t)))
    y = np.concatenate(out)
    return (0.4 * y).astype(np.float32)


def test_pads_hold_their_chords_and_moving_passages_dont(tmp_path):
    pytest.importorskip("madmom")
    import pretty_midi
    from digitalcrate import pads
    a = pads.analyze(_chords([(57, "m")], 10.0))  # A minor, held
    assert a["names"] == ["Am"] and pads.is_pad(a)
    b = pads.analyze(_chords([(57, "m"), (53, ""), (48, ""), (55, "")], 3.0))  # Am F C G: a progression
    assert b["n"] >= 3 and not pads.is_pad(b)
    assert pads.where(dict(subtype="Free", instrument="strings"), b) == (pads.STRINGS, "Free")
    assert pads.where(dict(subtype="Free", instrument="pad"), a) == (pads.PADS, "Free")
    # two chords rocking back and forth is still a pad
    c = pads.analyze(_chords([(57, "m"), (53, ""), (57, "m"), (53, "")], 3.0))
    assert set(c["names"]) == {"Am", "F"} and c["n"] == 2
    # mining: a held stretch then a moving one; with bar lines the cut is whole bars from the chord change
    y = np.concatenate([_chords([(57, "m")], 8.0), _chords([(48, ""), (55, ""), (50, "m"), (52, "")], 1.0)])
    found = pads.find(y, SR, bar_times=np.arange(0, 12.1, 2.0))
    assert found and found[0][0] == 0.0 and found[0][2] in (2, 4) and found[0][1] <= 8.2
    assert pads.find(y, SR)[0][2] is None  # no tempo: a free cut along the hold
    # the chords as MIDI, and the note that plays the pad as recorded
    mid = pads.chord_midi([(0, 4, "Am"), (4, 8, "F")], tmp_path / "c.mid", bpm=90)
    pm = pretty_midi.PrettyMIDI(str(mid))
    first = sorted(n.pitch % 12 for n in pm.instruments[0].notes if n.start == 0)
    assert first == [0, 4, 9] and len(pm.instruments[0].notes) == 6
    assert pads.root_note([(0, 6, "Am"), (6, 8, "F")]) == 57 and pads.root_note([(0, 6, "D")]) == 62


MOVE_SCRIPT = r'''
import json, soundfile as sf, numpy as np
from digitalcrate import config as C
from digitalcrate.db import connect
from digitalcrate.recat import move_sample
con = connect()
old = "Pads & Atmospheres/Free/Pad_08A-Am_free_X-Y_0m10s_abc123.wav"
(C.LIB_ROOT / old).parent.mkdir(parents=True, exist_ok=True)
sf.write(str(C.LIB_ROOT / old), np.zeros((4410, 2), np.float32), 44100)
con.execute("INSERT INTO tracks (id, path, status) VALUES (1, 'x.wav', 'done')")
con.execute("INSERT INTO samples (id, track_id, category, subtype, kind, path) VALUES ('abc123', 1, 'Pads & Atmospheres', 'Free', 'free', ?)", (old,))
con.execute("CREATE TABLE IF NOT EXISTS sketches (name TEXT, state TEXT)")
con.execute("INSERT INTO sketches (name, state) VALUES ('s', ?)", (json.dumps({"lanes": [{"path": old}]}),))
con.execute("INSERT INTO events (ts, path, sample_id, type) VALUES (0, ?, 'abc123', 'play')", (old,))
new = move_sample(con, con.execute("SELECT * FROM samples WHERE id='abc123'").fetchone(), "Strings & Orchestral", "Free")
con.commit()
assert new.startswith("Strings & Orchestral/Free/Strings_"), new
assert (C.LIB_ROOT / new).exists() and not (C.LIB_ROOT / old).exists()
assert json.loads(con.execute("SELECT state FROM sketches").fetchone()[0])["lanes"][0]["path"] == new
assert con.execute("SELECT path FROM events").fetchone()[0] == new
assert con.execute("SELECT new FROM moved WHERE old=?", (old,)).fetchone()[0] == new
print("MOVED OK")
'''


def test_moving_a_sample_keeps_every_reference(tmp_path):
    import os, subprocess, sys
    env = dict(os.environ, DIGITALCRATE_LIBRARY=str(tmp_path / "lib"), DIGITALCRATE_MUSIC=str(tmp_path / "m"),
               DIGITALCRATE_CONFIG=str(tmp_path / "cfg.toml"))
    (tmp_path / "cfg.toml").write_text(f'library = "{tmp_path / "lib"}"\nmusic = "{tmp_path / "m"}"\n')
    r = subprocess.run([sys.executable, "-c", MOVE_SCRIPT], env=env, capture_output=True, text=True)
    assert "MOVED OK" in r.stdout, r.stderr[-2000:]
