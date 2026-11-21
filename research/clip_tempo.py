"""Can a clip's own pulse be found when its song's tempo was unreliable? For each clip: beat-track it, stretch it
to the project tempo, line its first beat up with the bar, and measure how far its attacks fall from the grid
(ms to the nearest 8th note). Random placement scores ~1/4 of an 8th; tight is under ~25 ms."""
import sys, pathlib, numpy as np, librosa, soundfile as sf
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from digitalcrate import config as C
from digitalcrate.db import connect

BPM = float(sys.argv[1]) if len(sys.argv) > 1 else 109
EIGHTH = 60 / BPM / 2


def off_grid(on):
    ph = (on / EIGHTH) % 1
    return np.median(np.minimum(ph, 1 - ph) * EIGHTH * 1000)


def clip_tempo(m, sr):
    env = librosa.onset.onset_strength(y=m, sr=sr, hop_length=512)
    tempo, beats = librosa.beat.beat_track(onset_envelope=env, sr=sr, hop_length=512, units="frames")
    tempo = float(np.atleast_1d(tempo)[0])
    if len(beats) < 4:
        return None, 0, None
    # confidence: how much stronger the onset envelope is on the tracked beats than elsewhere
    conf = float(env[beats].mean() / (env.mean() + 1e-9))
    # steadiness: spread of inter-beat intervals
    ibi = np.diff(beats) * 512 / sr
    steady = float(np.std(ibi) / np.mean(ibi))
    return tempo, conf, (beats[0] * 512 / sr, steady)


con = connect()
rows = con.execute("""SELECT s.path, s.kind, s.category, t.artist FROM samples s JOIN tracks t ON t.id=s.track_id
                      WHERE s.kind IN ('free','phrase') AND s.category NOT IN ('Percussion') AND COALESCE(t.tempo_ok,0)=0
                      AND s.parent_id IS NULL ORDER BY RANDOM() LIMIT 60""").fetchall()
res = []
for r in rows:
    m, sr = sf.read(str(C.LIB_ROOT / r["path"]), dtype="float32", always_2d=True); m = m.mean(1)
    if len(m) > sr * 12: m = m[: sr * 12]
    t, conf, extra = clip_tempo(m, sr)
    if t is None: continue
    first, steady = extra
    mult = min((0.5, 1, 2), key=lambda k: abs(np.log(BPM / (t * k))))
    ratio = BPM / (t * mult)  # playback speed factor needed
    on = librosa.onset.onset_detect(y=m, sr=sr, units="time")
    before = off_grid(on - on[0]) if len(on) else np.nan             # today: attack on the beat, no stretch
    after = off_grid((on - first) / ratio) if len(on) else np.nan     # stretched + first beat on the grid
    res.append((r["category"][:10], r["artist"][:14], t, conf, steady, ratio, before, after))
R = np.array([(x[3], x[4], x[5], x[6], x[7]) for x in res])
print(f"{len(res)} clips from songs with unreliable tempo · random ≈ {EIGHTH * 250:.0f} ms")
print(f"all:                         today {np.nanmedian(R[:, 3]):.0f} ms → stretched {np.nanmedian(R[:, 4]):.0f} ms")
for thr in (1.5, 2.0, 2.5):
    ok = (R[:, 0] >= thr) & (R[:, 1] < 0.08) & (R[:, 2] > 0.7) & (R[:, 2] < 1.4)
    print(f"confident pulse (conf≥{thr}, steady): {ok.sum():2d} clips · today {np.nanmedian(R[ok, 3]):.0f} ms → stretched {np.nanmedian(R[ok, 4]):.0f} ms")
