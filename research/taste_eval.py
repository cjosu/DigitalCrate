"""Honest offline test of the "for you" model.

Held-out stars: hide 1/5 of your favourites, fit on everything else, then ask: among the samples you actually
listened to, are the hidden favourites ranked above the ones you heard and didn't star? (AUC; 0.5 = guessing.)
Comparing only against heard samples controls for exposure: you can't star what you never played.
"""
import sys
import numpy as np
from scipy.stats import rankdata

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
from digitalcrate import taste
from digitalcrate.db import connect


def auc(y, p):
    r = rankdata(p); n1 = y.sum(); n0 = len(y) - n1
    return (r[y == 1].sum() - n1 * (n1 + 1) / 2) / max(1, n1 * n0)


def setup():
    con = connect()
    rows = con.execute("""SELECT s.*, t.artist FROM samples s JOIN tracks t ON t.id=s.track_id
                          WHERE s.path NOT LIKE '_Reference/%'""").fetchall()
    E = np.stack([np.frombuffer(r["clap"], np.float16).astype(np.float32) for r in rows])
    paths = [r["path"] for r in rows]
    pos = {p: i for i, p in enumerate(paths)}
    fav = [pos[r["path"]] for r in con.execute("SELECT path FROM favorites") if r["path"] in pos]
    heard = sorted({pos[r["path"]] for r in con.execute("SELECT path FROM events WHERE type='listen'") if r["path"] in pos})
    dis = sorted({pos[r["path"]] for r in con.execute("SELECT path FROM events WHERE type='dislike' AND value=1") if r["path"] in pos})
    ev = [(pos[r["path"]], r["value"] or 0) for r in con.execute("SELECT path, value FROM events WHERE type='listen'") if r["path"] in pos]
    return con, rows, E, fav, heard, dis, ev


def evaluate(score_fn, name, folds=5, seeds=4):
    con, rows, E, fav, heard, dis, ev = DATA
    res = []
    for seed in range(seeds):
        rng = np.random.default_rng(seed)
        f = np.array(fav); rng.shuffle(f)
        for k in range(folds):
            test = set(f[k::folds].tolist())
            train_fav = [i for i in fav if i not in test]
            s = score_fn(train_fav, test)
            cand = [i for i in heard if i not in train_fav]
            y = np.array([i in test for i in cand])
            if y.sum() and (~y).sum():
                res.append(auc(y, s[cand]))
    print(f"{name:45s} AUC {np.mean(res):.3f} ± {np.std(res) / np.sqrt(len(res)):.3f}")
    return np.mean(res)


DATA = setup()
