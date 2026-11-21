"""Experiment B: run DrumSep on each labelled hit's own audio and read which pieces carry energy at the hit.
Saves the per-piece levels (dB) to drumsep_feats.npy for use as classifier features."""
import time, numpy as np, soundfile as sf
from drum_eval import load
from digitalcrate import config as C
from digitalcrate.percussion import drumsep
from scipy.signal import resample_poly

data = load()
KEYS = ["kick", "snare", "toms", "hh", "ride", "crash"]
F = []
t = time.time()
for r, _, _ in data:
    y, sr = sf.read(str(C.LIB_ROOT / r["path"]), dtype="float32", always_2d=True)
    y = y.T
    if sr != C.SR:
        y = resample_poly(y, C.SR, sr, axis=1).astype(np.float32)
    pad = np.zeros((2, int(C.SR * 0.5)), np.float32)  # context so the separator isn't fed a bare click
    st = drumsep(np.concatenate([pad, y, pad], 1))
    a, b = pad.shape[1], pad.shape[1] + int(C.SR * 0.15)
    lev = [10 * np.log10(np.mean(st[k][:, a:b] ** 2) + 1e-12) if k in st else -120 for k in KEYS]
    F.append(lev)
F = np.array(F)
np.save("drumsep_feats.npy", F)
print(f"{len(F)} clips in {time.time() - t:.0f}s · stems: {KEYS}")
