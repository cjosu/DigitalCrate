import numpy as np
import drum_clf as D
from drum_eval import true_subtype
from sklearn.linear_model import LogisticRegression
from sklearn.decomposition import PCA
rng = np.random.default_rng(0)
N = len(D.data)


def fit_predict(tr, te):
    p = PCA(16).fit(D.emb[tr]); Xtr, Xte = p.transform(D.emb[tr]), p.transform(D.emb[te])
    P = np.zeros((len(te), len(D.PIECES)))
    for j in range(len(D.PIECES)):
        yj = D.Y[tr, j]
        if yj.sum() >= 2 and (~yj).sum() >= 2:
            P[:, j] = LogisticRegression(C=.5, max_iter=2000, class_weight="balanced").fit(Xtr, yj).predict_proba(Xte)[:, 1]
    return P


def sets(P):
    out = []
    for pr in P:
        o = np.argsort(-pr); s = {D.PIECES[o[0]]} | ({D.PIECES[o[1]]} if pr[o[1]] > .75 else set()); out.append(s)
    return out


print("learning curve (accuracy on held-out hits):")
for n in (30, 50, 70, 90):
    acc = []
    for rep in range(30):
        perm = rng.permutation(N); tr, te = perm[:n], perm[n:]
        st = [true_subtype(s) for s in sets(fit_predict(tr, te))]
        acc.append(np.mean([a == D.truth[k] for a, k in zip(st, te)]))
    print(f"  {n:3d} labels → {np.mean(acc):.0%}")
# confidence vs precision (LOO)
conf, right = [], []
for k in range(N):
    tr = np.arange(N) != k
    P = fit_predict(np.flatnonzero(tr), np.array([k]))
    conf.append(P[0].max()); right.append(true_subtype(sets(P)[0]) == D.truth[k])
conf, right = np.array(conf), np.array(right)
for t in (0, .6, .75, .85):
    m = conf >= t
    print(f"  confidence ≥ {t:.2f}: covers {m.mean():.0%} of hits, right {right[m].mean():.0%}")
