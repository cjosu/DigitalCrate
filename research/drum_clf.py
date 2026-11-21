"""Experiment A: learn the drum pieces from your labels, using only the hit's own audio.

Features: CLAP embedding (PCA) + band energies / decay / brightness from the WAV. One logistic model per piece
(multi-label), so combos come out naturally. Leave-one-out cross-validation."""
import numpy as np, soundfile as sf, librosa
from sklearn.linear_model import LogisticRegression
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
from drum_eval import load, true_subtype
from digitalcrate import config as C

data = load()
PIECES = ["kick", "snare", "rim_clap", "hat_closed", "hat_open", "tom", "wood_metal", "shaker", "ride", "crash", "hand_drum", "orchestral"]


def spectral(path):
    y, sr = sf.read(str(C.LIB_ROOT / path), dtype="float32", always_2d=True)
    m = y.mean(1)[: int(sr * 0.8)]
    S = np.abs(librosa.stft(m, n_fft=2048, hop_length=256)) + 1e-9
    f = librosa.fft_frequencies(sr=sr, n_fft=2048)
    bands = [(20, 80), (80, 200), (200, 500), (500, 1500), (1500, 5000), (5000, 10000), (10000, 20000)]
    E = np.array([S[(f >= a) & (f < b)].sum(0) for a, b in bands])  # bands x frames
    tot = E.sum(0)
    pk = int(np.argmax(tot))
    early = E[:, pk:pk + 6].sum(1); late = E[:, pk + 12:pk + 40].sum(1) + 1e-9
    share = early / early.sum()
    decay = np.log(early + 1e-9) - np.log(late)  # per band: how fast each band dies away
    cen = librosa.feature.spectral_centroid(S=S, sr=sr)[0][pk:pk + 6].mean()
    flat = librosa.feature.spectral_flatness(S=S)[0][pk:pk + 6].mean()
    dur = len(m) / sr
    return np.r_[np.log(share + 1e-6), decay, np.log(cen), flat, dur]


emb = np.stack([np.frombuffer(r["clap"], np.float16).astype(np.float32) for r, _, _ in data])
spec = np.stack([spectral(r["path"]) for r, _, _ in data])
Y = np.array([[p in ps for p in PIECES] for _, ps, _ in data])
truth = [t for *_, t in data]


def loo(make_X, C_=1.0):
    pred_sets = []
    for k in range(len(data)):
        tr = np.arange(len(data)) != k
        Xtr, Xte = make_X(tr, k)
        probs = {}
        for j, p in enumerate(PIECES):
            yj = Y[tr, j]
            if yj.sum() < 2:
                probs[p] = 0.0; continue
            m = LogisticRegression(C=C_, max_iter=2000, class_weight="balanced").fit(Xtr, yj)
            probs[p] = m.predict_proba(Xte)[0, 1]
        # the strongest piece always; a second only if clearly present
        ranked = sorted(probs, key=lambda p: -probs[p])
        s = {ranked[0]} | ({ranked[1]} if probs[ranked[1]] > 0.75 else set())
        pred_sets.append(s)
    return pred_sets


def score(name, sets):
    st = [true_subtype(s) for s in sets]
    acc = np.mean([a == b for a, b in zip(st, truth)])
    main = np.mean([bool(s & ps) for s, (_, ps, _) in zip(sets, data)])  # got at least the main piece
    print(f"{name:45s} subtype exactly right {acc:.0%} · main drum right {main:.0%}")


def X_spec(tr, k):
    sc = StandardScaler().fit(spec[tr]); return sc.transform(spec[tr]), sc.transform(spec[k:k + 1])


def X_clap(tr, k, n=16):
    p = PCA(n).fit(emb[tr]); return p.transform(emb[tr]), p.transform(emb[k:k + 1])


def X_both(tr, k):
    a, b = X_spec(tr, k); c, d = X_clap(tr, k)
    return np.hstack([a, c]), np.hstack([b, d])


print(f"{len(data)} labelled hits")
score("spectral features", loo(X_spec, .5))
score("CLAP embedding", loo(X_clap, .5))
score("spectral + CLAP", loo(X_both, .5))

# ---- experiment B results: DrumSep run on the clip itself
import os
if os.path.exists("drumsep_feats.npy"):
    DS = np.load("drumsep_feats.npy")
    KEYS = ["kick", "snare", "toms", "hh", "ride", "crash"]
    MAP = {"kick": "kick", "snare": "snare", "toms": "tom", "hh": "hat_closed", "ride": "ride", "crash": "crash"}
    for gap in (6, 10, 15):
        sets = []
        for lev in DS:
            top = lev.max()
            sets.append({MAP[k] for k, l in zip(KEYS, lev) if l > top - gap})
        # hats: open vs closed is not something DrumSep tells apart; count either as right for this check
        norm = lambda s: {("hat_closed" if p in ("hat_open", "hat_closed") else p) for p in s}
        acc = np.mean([norm(s) == norm(ps) for s, (_, ps, _) in zip(sets, data)])
        main = np.mean([bool(norm(s) & norm(ps)) for s, (_, ps, _) in zip(sets, data)])
        print(f"DrumSep on the clip, pieces within {gap:2d} dB of loudest: piece set right {acc:.0%} · main drum right {main:.0%}")
    rel = DS - DS.max(1, keepdims=True)
    def X_all(tr, k):
        a, b = X_both(tr, k); sc = StandardScaler().fit(rel[tr])
        return np.hstack([a, sc.transform(rel[tr])]), np.hstack([b, sc.transform(rel[k:k + 1])])
    def X_sc(tr, k):
        a, b = X_clap(tr, k); sc = StandardScaler().fit(rel[tr])
        return np.hstack([a, sc.transform(rel[tr])]), np.hstack([b, sc.transform(rel[k:k + 1])])
    score("CLAP + DrumSep-on-clip", loo(X_sc, .5))
    score("spectral + CLAP + DrumSep-on-clip", loo(X_all, .5))
