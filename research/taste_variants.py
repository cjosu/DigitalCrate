"""Compare "for you" model variants with held-out *heard* samples: hide 1/5 of what you've played (all its
events), train on the rest, and score whether the hidden favourites outrank the hidden heard-but-not-starred.
Also reports AUC within category (the list is now browsed one category tab at a time)."""
import numpy as np
from collections import defaultdict
from taste_eval import DATA, auc
from digitalcrate import taste

con, rows, E, fav, heard, dis, ev = DATA
N = len(rows)
favs, diss = set(fav), set(dis)
cat = np.array([r["category"] for r in rows])
dur = np.array([r["dur"] for r in rows])
meta = [dict(category=r["category"], kind=r["kind"], dur=r["dur"], centroid=r["centroid"], flatness=r["flatness"],
             pratio=r["pratio"], scale=r["scale"]) for r in rows]
fz = taste.Featurizer(E)
X_full = np.stack([fz(E[i], meta[i]) for i in range(N)])
X_nodur = X_full.copy(); X_nodur[:, -6] = 0  # zero the duration feature
listens = defaultdict(list)
for i, v in ev:
    listens[i].append(v)


def labels(train_items, implicit):
    """train_items: heard items whose events we may use; favourites/dislikes among them are explicit labels."""
    lab = {}
    for i in train_items:
        if i in diss: lab[i] = (0, 1.5); continue
        if i in favs: lab[i] = (1, 1.5); continue
        if implicit == "none": continue
        fr = listens.get(i, [])
        if implicit == "fraction":  # the current rule
            net = sum(.25 for f in fr if f >= .7) - sum(.25 for f in fr if f < .15)
            if abs(net) > .05: lab[i] = (int(net > 0), min(1, abs(net)))
        elif implicit == "seconds":  # debiased: real listening time and replays, not % of a tiny clip
            secs = sum(f * dur[i] for f in fr)
            if len(fr) >= 3 or secs >= 12: lab[i] = (1, .5)
            elif dur[i] > 3 and max(fr) < .15: lab[i] = (0, .5)
    for i in fav:  # favourites you made outside the held-out set count even if never "listened"
        if i in train_items or i not in heard_set: lab[i] = (1, 1.5)
    return lab


heard_set = set(heard)


def fit_score(lab, X, mode, bg_w=.05):
    idx = np.array(list(lab)); y = np.array([lab[i][0] for i in idx]); w = np.array([lab[i][1] for i in idx])
    pos = idx[y == 1]; neg = idx[(y == 0) & (w >= 1)]
    knn = np.zeros(N)
    if len(pos):
        S = E @ E[pos].T; knn = np.sort(S, 1)[:, -min(3, S.shape[1]):].mean(1)
        if len(neg): knn -= .5 * np.sort(E @ E[neg].T, 1)[:, -1:].mean(1)
    if mode == "knn": return knn
    rng = np.random.default_rng(0)
    unl = np.setdiff1d(np.arange(N), idx)
    bg = rng.choice(unl, size=min(len(unl), 20 * max(1, len(pos))), replace=False)
    Xt = np.vstack([X[idx], X[bg]]); yt = np.r_[y, np.zeros(len(bg))]; wt = np.r_[w, np.full(len(bg), bg_w)]
    beta, cov = taste.fit_blr(Xt, yt, wt)
    prob, _ = taste.predict(X, beta, cov)
    if mode == "blr": return prob
    z = lambda a: (a - a.mean()) / (a.std() + 1e-9)
    return .55 * z(prob) + .45 * z(knn)


def run(name, implicit, X, mode, folds=5, seeds=3):
    A, Ac = [], []
    H = np.array(heard)
    for seed in range(seeds):
        rng = np.random.default_rng(seed); h = H.copy(); rng.shuffle(h)
        for k in range(folds):
            test = h[k::folds]; train = np.setdiff1d(H, test)
            s = fit_score(labels(set(train.tolist()), implicit), X, mode)
            y = np.array([i in favs for i in test])
            A.append(auc(y, s[test]))
            per = [auc(y[cat[test] == c], s[test][cat[test] == c]) for c in set(cat[test])
                   if 0 < y[cat[test] == c].sum() < (cat[test] == c).sum()]
            Ac.append(np.mean(per) if per else np.nan)
    print(f"{name:52s} overall {np.mean(A):.3f}   within category {np.nanmean(Ac):.3f}")


print(f"{N} samples · {len(heard)} heard · {len(fav)} favourites · {len(dis)} dislikes\n")
run("current: fraction-listened labels, BLR+kNN blend", "fraction", X_full, "blend")
run("explicit only (stars, dislikes)", "none", X_full, "blend")
run("listening time & replays instead of fraction", "seconds", X_full, "blend")
run("seconds, no duration feature", "seconds", X_nodur, "blend")
run("explicit only, kNN only", "none", X_full, "knn")
run("explicit only, BLR only", "none", X_full, "blr")
run("seconds, kNN only", "seconds", X_full, "knn")
run("seconds, BLR only", "seconds", X_full, "blr")
