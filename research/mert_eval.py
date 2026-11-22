"""Does MERT (a music-understanding model) predict what you star better than CLAP, the embedding everything uses now?

Same honest test as taste_eval.py: hide 1/5 of your favourites, train on the rest, and check whether the hidden ones
rank above the samples you listened to and didn't star (AUC; 0.5 = guessing). Two scorers, so the result isn't about
one model: nearest-favourite similarity, and a logistic regression. Also Discogs-EffNet (styles.py) on the samples.

    python research/mert_eval.py      (embeds only the samples you've heard or starred; cached in research/)
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from taste_eval import DATA, auc  # noqa: E402  (loads the library)
from digitalcrate import config as C  # noqa: E402
from digitalcrate.mert import embed_files  # noqa: E402

con, rows, E_clap, fav, heard, dis, ev = DATA
need = sorted(set(heard) | set(fav))
cache = Path(__file__).with_name("mert_eval_emb.npz")
if cache.exists() and set(np.load(cache)["idx"].tolist()) >= set(need):
    z = np.load(cache)
    pos = {int(i): k for k, i in enumerate(z["idx"])}
    M, D = z["mert"][[pos[i] for i in need]], z["effnet"][[pos[i] for i in need]]
else:
    files = [C.LIB_ROOT / rows[i]["path"] for i in need]
    M = embed_files(files, layers="all")  # (n, 13, 768)
    from digitalcrate.styles import predict
    import soundfile as sf
    from scipy.signal import resample_poly
    D = []
    for f in files:
        y, sr = sf.read(str(f), dtype="float32", always_2d=True)
        y = resample_poly(y.mean(1), 16000, sr).astype(np.float32)
        if len(y) < 16000 * 2.1:
            y = np.pad(y, (0, int(16000 * 2.1) - len(y)))
        r = predict([y])
        D.append(r[1] if r else np.zeros(1280, np.float32))
    D = np.array(D)
    np.savez(cache, idx=np.array(need), mert=M, effnet=D)
print(f"{len(need)} samples ({len(fav)} favourites)")

loc = {i: k for k, i in enumerate(need)}


def unit(X):
    X = X - X.mean(0)
    X = X / (X.std(0) + 1e-6)
    return X / (np.linalg.norm(X, axis=1, keepdims=True) + 1e-9)


def knn(X):
    X = unit(X)
    def score(train_fav, test):
        F = X[[loc[i] for i in train_fav]]
        S = X @ F.T
        s = np.sort(S, 1)[:, -3:].mean(1)
        out = np.full(len(rows), -9.0); out[need] = s
        return out
    return score


def logreg(X, dim=48):
    from sklearn.decomposition import PCA
    from sklearn.linear_model import LogisticRegression
    Z = PCA(min(dim, X.shape[1]), random_state=0).fit_transform(unit(X))
    def score(train_fav, test):
        tf = set(train_fav)
        tr = [i for i in need if i in tf or (i in set(heard) and i not in test)]
        y = np.array([i in tf for i in tr])
        clf = LogisticRegression(C=0.3, class_weight="balanced", max_iter=2000).fit(Z[[loc[i] for i in tr]], y)
        out = np.full(len(rows), -9.0); out[need] = clf.decision_function(Z)
        return out
    return score


def evaluate(fn, name, folds=5, seeds=6):
    res = []
    for seed in range(seeds):
        rng = np.random.default_rng(seed)
        f = np.array(fav); rng.shuffle(f)
        for k in range(folds):
            test = set(f[k::folds].tolist())
            train = [i for i in fav if i not in test]
            s = fn(train, test)
            cand = [i for i in heard if i not in train]
            y = np.array([i in test for i in cand])
            if y.sum() and (~y).sum():
                res.append(auc(y, s[cand]))
    print(f"{name:34s} AUC {np.mean(res):.3f} ± {np.std(res) / np.sqrt(len(res)):.3f}")
    return np.mean(res)


Ec = E_clap[need]
feats = {"CLAP (now)": Ec, "Discogs-EffNet": D, "MERT mean of layers": M.mean(1)}
for L in (3, 6, 9, 12):
    feats[f"MERT layer {L}"] = M[:, L]
feats["CLAP + MERT mean"] = np.hstack([unit(Ec), unit(M.mean(1))])
for name, X in feats.items():
    evaluate(knn(X), "nearest favourites · " + name)
for name, X in feats.items():
    evaluate(logreg(X), "logistic · " + name)
