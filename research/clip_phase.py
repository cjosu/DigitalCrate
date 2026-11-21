"""If we knew where the song's beats fall, how well would a phrase line up? Beat-track the whole song, find the
first song beat inside the clip, stretch the clip by song tempo -> project tempo, and put that beat on the grid."""
import sys, time, numpy as np, librosa, soundfile as sf
from clip_tempo import off_grid, BPM, EIGHTH
from digitalcrate import config as C
from digitalcrate.db import connect
from digitalcrate.audio import decode
from digitalcrate.analyze import track_tempo_key
tok = sys.argv[2] if len(sys.argv) > 2 else "1"
rows = connect().execute(f"""SELECT s.path, s.start, t.path tpath, t.bpm tb FROM samples s JOIN tracks t ON t.id=s.track_id
   WHERE s.kind IN ('phrase','free') AND s.category!='Percussion' AND COALESCE(t.tempo_ok,0)={tok} AND s.parent_id IS NULL
   AND t.path NOT LIKE '%YouTube%' GROUP BY t.id ORDER BY RANDOM() LIMIT 14""").fetchall()
a, b, c = [], [], []; t0 = time.time()
for r in rows:
    try:
        y = decode(r["tpath"]); tk = track_tempo_key(y)
    except Exception as e:
        continue
    beats = np.asarray(tk["beats"], float); bpm = float(tk["bpm"])
    m, sr = sf.read(str(C.LIB_ROOT / r["path"]), dtype="float32", always_2d=True); m = m.mean(1)[: sr * 12]
    on = librosa.onset.onset_detect(y=m, sr=sr, units="time")
    inside = beats[(beats >= r["start"]) & (beats < r["start"] + len(m) / sr)] - r["start"]
    if len(on) < 3 or not len(inside): continue
    mult = min((0.5, 1, 2), key=lambda k: abs(np.log(BPM / (bpm * k)))); ratio = BPM / (bpm * mult)
    if not 0.7 <= 1 / ratio <= 1.4: continue
    a.append(off_grid(on - on[0])); b.append(off_grid((on - on[0]) / ratio)); c.append(off_grid((on - inside[0]) / ratio))
print(f"tempo_ok={tok}: {len(a)} clips ({time.time() - t0:.0f}s) · random ≈ {EIGHTH * 250:.0f} ms")
print(f"  today (first attack on beat, no stretch) {np.median(a):.0f} ms · + stretch {np.median(b):.0f} ms · song's beat grid {np.median(c):.0f} ms")
