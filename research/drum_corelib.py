"""Experiment C: train the drum classifier on Ableton's Core Library one-shots (labelled by folder), plus
synthetic combos mixed from them, roughened to sound more like hits cut from records. Tested on your labels.

Embeddings are cached in corelib_emb.npz (local only; the audio itself is never copied)."""
import os, re, glob, numpy as np, soundfile as sf, librosa
from scipy.signal import resample_poly, butter, sosfilt
from sklearn.linear_model import LogisticRegression
from sklearn.decomposition import PCA
from drum_eval import load, true_subtype
from digitalcrate import models

ROOT = "/Applications/Ableton Live 12 Suite.app/Contents/App-Resources/Core Library/Samples/One Shots/Drums"
PIECES = ["kick", "snare", "rim_clap", "hat_closed", "hat_open", "tom", "wood_metal", "shaker", "ride", "crash", "hand_drum", "orchestral"]
FOLDER = {"Kick": "kick", "Snare": "snare", "Clap": "rim_clap", "Rim": "rim_clap", "Tom": "tom", "Ride": "ride",
          "Cymbal": "crash", "Shaker": "shaker", "Tambourine": "shaker", "Wood": "wood_metal", "Bell": "wood_metal",
          "Conga": "hand_drum", "Bongo": "hand_drum", "Timbales": "hand_drum"}
SR = 48000
rng = np.random.default_rng(0)


def read(path, secs=0.8):
    y, sr = sf.read(path, dtype="float32", always_2d=True)
    m = y.mean(1)
    if sr != SR:
        m = resample_poly(m, SR, sr).astype(np.float32)
    m = m[: int(SR * secs)]
    return m / (np.abs(m).max() + 1e-9)


def files():
    out = []
    for f in glob.glob(f"{ROOT}/*/*"):
        if not re.search(r"\.(wav|aif|aiff)$", f, re.I):
            continue
        folder = f.split("/")[-2]
        if folder == "Hihat":
            p = "hat_open" if re.search(r"open", f, re.I) else "hat_closed"
        elif folder in FOLDER:
            p = FOLDER[folder]
        else:
            continue
        out.append((f, p))
    return out


def roughen(m):
    """Make a clean studio hit sound a bit more like one cut from a record: band-limit, noise, saturation, bleed tail."""
    if rng.random() < .7:
        lo, hi = rng.uniform(20, 120), rng.uniform(6000, 16000)
        m = sosfilt(butter(2, [lo, hi], "band", fs=SR, output="sos"), m)
    if rng.random() < .5:
        m = np.tanh(m * rng.uniform(1, 3))
    m = m + rng.normal(0, rng.uniform(.002, .02), len(m))
    if rng.random() < .4:  # faint room/reverb-ish tail
        tail = np.convolve(m, np.exp(-np.arange(int(SR * .25)) / (SR * .06)) * rng.normal(0, 1, int(SR * .25)))[: len(m)]
        m = m + .03 * tail / (np.abs(tail).max() + 1e-9)
    return (m / (np.abs(m).max() + 1e-9)).astype(np.float32)


def build():
    if os.path.exists("corelib_emb.npz"):
        z = np.load("corelib_emb.npz", allow_pickle=True)
        return z["E"], z["Y"]
    fs = files()
    by = {}
    for f, p in fs:
        by.setdefault(p, []).append(f)
    clips, labels = [], []
    for f, p in fs:  # singles, half of them roughened
        m = read(f)
        clips.append(roughen(m) if rng.random() < .5 else m); labels.append({p})
    combos = [("kick", "hat_closed"), ("kick", "hat_open"), ("snare", "hat_closed"), ("snare", "hat_open"),
              ("kick", "snare"), ("kick", "crash"), ("snare", "crash"), ("tom", "hat_closed"), ("hand_drum", "hat_closed"),
              ("kick", "ride"), ("snare", "ride")]
    for _ in range(1200):
        a, b = combos[rng.integers(len(combos))]
        x, y = read(rng.choice(by[a])), read(rng.choice(by[b]))
        n = max(len(x), len(y)); x = np.pad(x, (0, n - len(x))); y = np.pad(y, (0, n - len(y)))
        g = rng.uniform(.35, 1.0)
        clips.append(roughen(x + g * y)); labels.append({a, b})
    print(f"embedding {len(clips)} clips ({len(fs)} singles + {len(clips) - len(fs)} synthetic combos)…")
    clips = [np.pad(c, (0, max(0, SR // 2 - len(c)))) for c in clips]  # same padding as the pipeline
    E = models.clap().embed_audio(clips)
    Y = np.array([[p in s for p in PIECES] for s in labels])
    np.savez("corelib_emb.npz", E=E, Y=Y)
    return E, Y


if __name__ == "__main__":
    E, Y = build()
    data = load()
    Eu = np.stack([np.frombuffer(r["clap"], np.float16).astype(np.float32) for r, _, _ in data])
    Yu = np.array([[p in ps for p in PIECES] for _, ps, _ in data])
    truth = [t for *_, t in data]
    N = len(data)

    def run(name, use_lib=True, use_user=True, w_user=5.0, npca=48, C_=1.0, thr=.6):
        preds = []
        for k in range(N):
            tr = np.arange(N) != k
            Xs, Ys, Ws = [], [], []
            if use_lib: Xs.append(E); Ys.append(Y); Ws.append(np.ones(len(E)))
            if use_user: Xs.append(Eu[tr]); Ys.append(Yu[tr]); Ws.append(np.full(tr.sum(), w_user))
            X, Yt, W = np.vstack(Xs), np.vstack(Ys), np.concatenate(Ws)
            pca = PCA(npca).fit(X)
            Xt, xq = pca.transform(X), pca.transform(Eu[k:k + 1])
            pr = np.zeros(len(PIECES))
            for j in range(len(PIECES)):
                if Yt[:, j].sum() >= 2:
                    pr[j] = LogisticRegression(C=C_, max_iter=3000, class_weight="balanced").fit(Xt, Yt[:, j], sample_weight=W).predict_proba(xq)[0, 1]
            o = np.argsort(-pr)
            preds.append({PIECES[o[0]]} | ({PIECES[o[1]]} if pr[o[1]] > thr else set()))
        st = [true_subtype(s) for s in preds]
        acc = np.mean([a == b for a, b in zip(st, truth)])
        main = np.mean([bool(s & ps) for s, (_, ps, _) in zip(preds, data)])
        print(f"{name:52s} subtype right {acc:.0%} · main drum right {main:.0%}")
        return st

    for t in (.85, .9, .95, 1.01):
        run(f"Core Library + yours ×15, second piece only if p>{t:.2f}" if t <= 1 else "Core Library + yours ×15, never call a combo", w_user=15, thr=t)
