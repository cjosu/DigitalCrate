"""Taste model: learns what you like from stars, dislikes and listening behaviour.

Two parts:
 1. Sound taste — Bayesian logistic regression (Laplace approximation) on PCA-reduced CLAP embeddings +
    engineered features, giving a mean *and* an uncertainty per sample (used for exploration), blended with
    a multi-mood nearest-favourite similarity (your taste is several moods, not one average).
 2. Technique taste — Beta posteriors per manipulation technique / amount, from stars & dislikes on
    variations. mangle.py draws variation families from these instead of hand-set weights.

Unrated library samples act as weak negatives (positive-unlabelled learning). Recent events can be up-weighted
for a "today's vibe" ranking.
"""
import json
import re
import time
from pathlib import Path

import numpy as np

from . import config as C
from .db import connect

CATS = ["Vocals", "Vocal Atmospheres", "Pads & Atmospheres", "Chords & Keys", "Melodies & Leads",
        "Textures & Field", "Bass & Sub", "Percussion"]
KINDS = ["loop", "free", "phrase", "oneshot"]
TECH_FILE = C.DATA_DIR / "technique_taste.json"
N_PCA = 32


def _db():
    con = connect()
    con.execute("""CREATE TABLE IF NOT EXISTS events (ts REAL, path TEXT, sample_id TEXT, type TEXT,
                   value REAL, context TEXT)""")
    con.execute("CREATE INDEX IF NOT EXISTS events_path ON events(path)")
    con.execute("CREATE TABLE IF NOT EXISTS embeddings (path TEXT PRIMARY KEY, clap BLOB)")
    con.execute("""CREATE TABLE IF NOT EXISTS favorites (path TEXT PRIMARY KEY, sample_id TEXT,
                   label TEXT, added_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    return con


def log_event(path, type_, value=None, sample_id=None, context=None):
    con = _db()
    con.execute("INSERT INTO events VALUES (?,?,?,?,?,?)",
                (time.time(), path, sample_id, type_, value, json.dumps(context) if context else None))
    con.commit()


# ---------------------------------------------------------------- labels from events

def item_labels(con, recent_hours=None):
    """Aggregate events into (path -> (y, weight)). Explicit signals dominate implicit ones."""
    now = time.time()
    lab = {}
    fav = {r["path"] for r in con.execute("SELECT path FROM favorites")}
    for r in con.execute("SELECT * FROM events ORDER BY ts"):
        age_d = (now - r["ts"]) / 86400
        w_time = np.exp(-age_d / 60)  # slow decay: taste drifts over months
        if recent_hours and (now - r["ts"]) < recent_hours * 3600:
            w_time *= 4
        d = lab.setdefault(r["path"], {"pos": 0.0, "neg": 0.0, "dislike": None})
        t, v = r["type"], r["value"]
        if t == "dislike":
            d["dislike"] = bool(v)
        elif t == "unstar":
            d["neg"] += 0.5 * w_time
        elif t == "listen":
            frac = v or 0
            if frac >= 0.7:
                d["pos"] += 0.25 * w_time
            elif frac < 0.15:
                d["neg"] += 0.25 * w_time
    out = {}
    for p, d in lab.items():
        if d["dislike"]:
            out[p] = (0, 1.5)
        elif p in fav:
            continue
        else:
            net = d["pos"] - d["neg"]
            if abs(net) > 0.05:
                out[p] = (1 if net > 0 else 0, min(1.0, abs(net)))
    for p in fav:
        out[p] = (1, 1.5)
    return out


# ---------------------------------------------------------------- features

def _variation_meta(path):
    """Technique + amount from a variation file's sidecar."""
    j = (C.LIB_ROOT / path).with_suffix(".json")
    if not j.exists():
        return None
    info = json.loads(j.read_text())
    return info


def embed_paths(con, paths):
    """CLAP embeddings for arbitrary library files (variations), cached in the DB."""
    have = {r["path"]: np.frombuffer(r["clap"], np.float16).astype(np.float32)
            for r in con.execute(f"SELECT * FROM embeddings WHERE path IN ({','.join('?' * len(paths))})", paths)} \
        if paths else {}
    todo = [p for p in paths if p not in have and (C.LIB_ROOT / p).exists()]
    if todo:
        import soundfile as sf
        from scipy.signal import resample_poly
        from . import models
        cl = models.clap()
        clips = []
        for p in todo:
            y, sr = sf.read(str(C.LIB_ROOT / p), dtype="float32", always_2d=True)
            m = y.mean(1)
            if len(m) > sr * 10:
                mid = len(m) // 2
                m = m[mid - sr * 5: mid + sr * 5]
            clips.append(resample_poly(m, 48000, sr).astype(np.float32))
        E = cl.embed_audio(clips)
        for p, e in zip(todo, E):
            con.execute("INSERT OR REPLACE INTO embeddings VALUES (?,?)", (p, e.astype(np.float16).tobytes()))
            have[p] = e
        con.commit()
    return have


class Featurizer:
    def __init__(self, E_all):
        mu = E_all.mean(0)
        U, S, Vt = np.linalg.svd(E_all - mu, full_matrices=False)
        self.mu, self.P = mu, Vt[:N_PCA].T
        self.scale = (E_all - mu) @ self.P
        self.sd = self.scale.std(0) + 1e-6

    def __call__(self, emb, meta):
        z = ((emb - self.mu) @ self.P) / self.sd
        cat = np.zeros(len(CATS)); kind = np.zeros(len(KINDS))
        if meta.get("category") in CATS:
            cat[CATS.index(meta["category"])] = 1
        if meta.get("kind") in KINDS:
            kind[KINDS.index(meta["kind"])] = 1
        eng = np.array([np.log1p(meta.get("dur") or 5) - 1.6, (meta.get("centroid") or 1500) / 3000 - 0.5,
                        (meta.get("flatness") or 0.02) * 10, meta.get("pratio") or 0.1,
                        1.0 if meta.get("scale") == "minor" else 0.0, 1.0 if meta.get("variation") else 0.0])
        return np.concatenate([z, cat, kind, eng])


# ---------------------------------------------------------------- Bayesian logistic regression

def _sig(x):
    return 1 / (1 + np.exp(-np.clip(x, -30, 30)))


def fit_blr(X, y, w, prior_var=1.0, iters=30):
    d = X.shape[1]
    beta = np.zeros(d)
    A0 = np.eye(d) / prior_var
    for _ in range(iters):
        p = _sig(X @ beta)
        g = X.T @ (w * (p - y)) + A0 @ beta
        H = (X * (w * p * (1 - p))[:, None]).T @ X + A0
        step = np.linalg.solve(H, g)
        beta -= step
        if np.abs(step).max() < 1e-6:
            break
    p = _sig(X @ beta)
    H = (X * (w * p * (1 - p))[:, None]).T @ X + A0
    return beta, np.linalg.inv(H)


def predict(X, beta, cov):
    m = X @ beta
    s = np.einsum("ij,jk,ik->i", X, cov, X)
    return _sig(m / np.sqrt(1 + np.pi * s / 8)), np.sqrt(s)


# ---------------------------------------------------------------- full fit

def fit(recent_hours=None, verbose=False):
    con = _db()
    rows = con.execute("""SELECT s.*, t.artist FROM samples s JOIN tracks t ON t.id=s.track_id
                          WHERE s.path NOT LIKE '_Reference/%'""").fetchall()
    if not rows:
        return None
    E = np.stack([np.frombuffer(r["clap"], np.float16).astype(np.float32) for r in rows])
    fz = Featurizer(E)
    meta = {r["path"]: dict(category=r["category"], kind=r["kind"], dur=r["dur"], centroid=r["centroid"],
                            flatness=r["flatness"], pratio=r["pratio"], scale=r["scale"]) for r in rows}
    emb = {r["path"]: e for r, e in zip(rows, E)}
    labels = item_labels(con, recent_hours)

    # variation files: embed + inherit metadata from their source sample
    var_paths = [p for p in labels if p.startswith("Variations/")]
    vrows = {r["path"]: r for r in con.execute("SELECT * FROM variants")} if var_paths else {}
    if var_paths:
        emb.update(embed_paths(con, var_paths))
        for p in var_paths:
            src = con.execute("SELECT s.* FROM samples s JOIN variants v ON v.sample_id=s.id WHERE v.path=?",
                              (p,)).fetchone()
            meta[p] = dict(meta.get(src["path"], {}) if src else {}, variation=True)
    lp = [p for p in labels if p in emb]
    n_pos = sum(labels[p][0] for p in lp)
    X_all = np.stack([fz(emb[r["path"]], meta[r["path"]]) for r in rows])
    result = dict(n_labels=len(lp), n_pos=int(n_pos), paths=[r["path"] for r in rows])

    # multi-mood similarity: best match among liked items minus best match among disliked
    pos = [emb[p] for p in lp if labels[p][0] == 1]
    neg = [emb[p] for p in lp if labels[p][0] == 0 and labels[p][1] >= 1]
    knn = np.zeros(len(rows))
    if pos:
        S = E @ np.stack(pos).T
        k = min(3, S.shape[1])
        knn = np.sort(S, 1)[:, -k:].mean(1)
        if neg:
            knn -= 0.5 * np.sort(E @ np.stack(neg).T, 1)[:, -1:].mean(1)
    result["knn"] = knn

    if len(lp) >= 8 and n_pos >= 3:
        # PU learning: random unlabelled samples as weak negatives
        rng = np.random.default_rng(0)
        unl = [i for i, r in enumerate(rows) if r["path"] not in labels]
        bg = rng.choice(unl, size=min(len(unl), 20 * max(1, n_pos)), replace=False) if unl else []
        X = np.vstack([np.stack([fz(emb[p], meta[p]) for p in lp]), X_all[bg]])
        y = np.r_[[labels[p][0] for p in lp], np.zeros(len(bg))]
        w = np.r_[[labels[p][1] for p in lp], np.full(len(bg), 0.05)]
        beta, cov = fit_blr(X, y, w)
        prob, unc = predict(X_all, beta, cov)
        result.update(prob=prob, unc=unc, beta=beta, cov=cov)
        kz = (knn - knn.mean()) / (knn.std() + 1e-9)
        pz = (prob - prob.mean()) / (prob.std() + 1e-9)
        result["score"] = 0.55 * pz + 0.45 * kz
        rng2 = np.random.default_rng()
        bt = rng2.multivariate_normal(beta, cov)
        result["discover"] = X_all @ bt  # Thompson sample: optimistic where uncertain
    else:
        result["score"] = knn
        result["unc"] = np.ones(len(rows))
        result["discover"] = knn + np.random.default_rng().normal(0, 0.15, len(rows))
    if verbose:
        report(result, labels, lp, emb, fz, meta)
    return result


def report(res, labels, lp, emb, fz, meta):
    print(f"labels: {res['n_labels']} ({res['n_pos']} positive)")
    if res["n_labels"] < 30:
        print("held-out evaluation needs ~30+ rated items; keep starring / dismissing.")
        return
    def roc_auc_score(y, p):
        from scipy.stats import rankdata
        r = rankdata(p); n1 = y.sum(); n0 = len(y) - n1
        return (r[y == 1].sum() - n1 * (n1 + 1) / 2) / max(1, n1 * n0)
    X = np.stack([fz(emb[p], meta[p]) for p in lp])
    y = np.array([labels[p][0] for p in lp])
    w = np.array([labels[p][1] for p in lp])
    pred = np.zeros(len(lp))
    for f in range(5):
        te = np.arange(len(lp)) % 5 == f
        b, c = fit_blr(X[~te], y[~te], w[~te])
        pred[te] = predict(X[te], b, c)[0]
    print(f"5-fold AUC of the sound-taste model: {roc_auc_score(y, pred):.2f} (0.5 = guessing)")


# ---------------------------------------------------------------- technique taste

def technique_posteriors(prior):
    """Beta posterior per technique and per 'technique:amount' from events on variation files."""
    con = _db()
    labels = item_labels(con)
    post = {t: [1 + 2 * v, 3.0] if v > 0 else [0.5, 6.0] for t, v in prior.items()}
    for path, (y, w) in labels.items():
        if not path.startswith("Variations/"):
            continue
        info = _variation_meta(path)
        if not info or not info.get("technique"):
            continue
        keys = [info["technique"]]
        amt = next((re.findall(r"[+-]\d+", s)[0] for s in info.get("chain", []) if re.search(r"[+-]\d+", s)), None)
        if amt:
            keys.append(f"{info['technique']}:{amt}")
        for k in keys:
            a, b = post.setdefault(k, [1.0, 1.0])
            post[k] = [a + w * y, b + w * (1 - y)]
    TECH_FILE.parent.mkdir(parents=True, exist_ok=True)
    TECH_FILE.write_text(json.dumps(post, indent=1))
    return post


def scores_payload(recent_hours=None):
    res = fit(recent_hours)
    if res is None:
        return {}
    disliked = {p for p, (y, w) in item_labels(_db()).items() if y == 0 and w >= 1.5}
    return dict(n_labels=res["n_labels"], n_pos=res["n_pos"],
                score={p: round(float(s), 4) for p, s in zip(res["paths"], res["score"])},
                discover={p: round(float(s), 4) for p, s in zip(res["paths"], res["discover"])},
                disliked=sorted(disliked))
