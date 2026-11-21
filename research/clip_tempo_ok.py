import numpy as np, librosa, soundfile as sf
from clip_tempo import off_grid, BPM, EIGHTH
from digitalcrate import config as C
from digitalcrate.db import connect
rows = connect().execute("""SELECT s.path, t.bpm tb FROM samples s JOIN tracks t ON t.id=s.track_id WHERE s.kind='phrase'
   AND s.category!='Percussion' AND t.tempo_ok=1 AND s.parent_id IS NULL ORDER BY RANDOM() LIMIT 40""").fetchall()
a, b = [], []
for r in rows:
    m, sr = sf.read(str(C.LIB_ROOT / r["path"]), dtype="float32", always_2d=True); m = m.mean(1)[: sr * 12]
    on = librosa.onset.onset_detect(y=m, sr=sr, units="time")
    if len(on) < 3: continue
    mult = min((0.5, 1, 2), key=lambda k: abs(np.log(BPM / (r["tb"] * k)))); ratio = BPM / (r["tb"] * mult)
    if not 0.7 <= 1 / ratio <= 1.4: continue
    a.append(off_grid(on - on[0])); b.append(off_grid((on - on[0]) / ratio))
print(f"phrases from songs with a reliable tempo ({len(a)}): unstretched {np.median(a):.0f} ms → stretched to {BPM:g} bpm {np.median(b):.0f} ms (random ≈ {EIGHTH*250:.0f})")
