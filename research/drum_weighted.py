import numpy as np, collections
import drum_clf as D
from drum_curve import fit_predict, sets
from drum_eval import true_subtype
from digitalcrate.db import connect
N = len(D.data)
pred, conf = [], []
for k in range(N):
    P = fit_predict(np.flatnonzero(np.arange(N) != k), np.array([k])); pred.append(true_subtype(sets(P)[0])); conf.append(P[0].max())
cur = np.array([r["subtype"] for r, _, _ in D.data]); truth = np.array(D.truth); pred = np.array(pred); conf = np.array(conf)
lib = {r[0]: r[1] for r in connect().execute("SELECT subtype, COUNT(*) FROM samples WHERE category='Percussion' AND kind='oneshot' AND parent_id IS NULL GROUP BY 1")}
def weighted(right):
    num = den = 0
    for s, n in lib.items():
        m = cur == s
        if m.sum(): num += n * right[m].mean(); den += n
    return num / den
KEEP = {"Snare", "Kick"}
hyb = np.where(np.isin(cur, list(KEEP)), cur, pred)
print(f"library-weighted accuracy  current {weighted(cur == truth):.0%} · learned {weighted(pred == truth):.0%} · hybrid (keep Snare/Kick) {weighted(hyb == truth):.0%}")
for s in ("Snare", "Kick", "Hat Open"):
    m = cur == s; print(f"  among current '{s}': current right {np.mean(cur[m]==truth[m]):.0%}, learned right {np.mean(pred[m]==truth[m]):.0%} (n={m.sum()})")
