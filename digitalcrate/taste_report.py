"""The taste model explained, for the Taste page (/taste): how well it predicts you, what it has learned, what it is
learning from, where it's unsure, and how all that changes over time.

Accuracy is measured honestly: every sample you've heard is put in one of five groups; for each group, everything
you told the model about those samples (stars, ✕, skips, listening) is hidden, the model is fitted on the rest, and it
must rank the group's favourites above the group's heard-but-not-starred samples (AUC: 0.5 is guessing, 1.0 is
perfect). Hiding every label of the group, not just the stars, keeps a rule from being graded on samples it labelled
itself. Five folds, two shuffles. Two simple rankings are measured the same way for context: sample quality alone,
and random. Each result is kept in `taste_history`, so the page can show the trend as you rate more.

"What it has learned" reads the fitted model:
  - the category, kind and sound-feature weights directly (log-odds: + means more likely to be one you'd star);
  - words: descriptions like "warm analog synth pad" are embedded with CLAP (the same space the samples live in)
    and scored by the model, so its taste can be read in plain language. Approximate: text and audio embeddings
    aren't identical, so treat the order as a hint, not a measurement.
"""
import time

import numpy as np

from .taste import CATS, KINDS, N_PCA, _db, _library, fit, item_labels, scores_payload

ENG = ["longer", "brighter", "noisier / breathier", "more pitched", "minor key", "a variation (reworked)"]
WORDS = [
    "a woman singing softly", "a man singing softly", "a choir", "soulful r&b vocals", "a breathy whispered voice",
    "a vocal chop", "operatic singing", "spoken words", "humming", "a gospel choir",
    "a warm analog synth pad", "a bright digital synth", "an ambient drone", "slow sustained strings",
    "a solo piano", "a rhodes electric piano", "an acoustic guitar", "a distorted electric guitar", "a church organ",
    "a jazz saxophone", "a muted trumpet", "a harp", "a music box", "a flute", "a bass line", "a deep sub bass",
    "a drum loop", "a crisp snare", "a kick drum", "hi-hats", "vinyl crackle", "tape hiss", "field recording of rain",
    "dark, ominous music", "sad, melancholic music", "ethereal, angelic sound", "warm, nostalgic, lo-fi sound",
    "happy, uplifting music", "aggressive, intense music", "dreamy, hazy, reverb-drenched", "dry and close",
    "romantic, sensual", "tense, suspenseful", "playful, quirky", "cinematic and epic", "minimal and sparse",
    "busy and dense", "medieval chant", "bossa nova", "1970s soul", "1990s r&b", "classical orchestra", "jazz trio",
]


def _auc(y, s):
    from scipy.stats import rankdata
    r = rankdata(s)
    n1 = y.sum(); n0 = len(y) - n1
    return float((r[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)) if n1 and n0 else None


def accuracy(con=None, folds=5, seeds=2):
    con = con or _db()
    L = _library(con)
    labels = item_labels(con, None, L["durs"])
    pos = L["pos"]
    fav = [r[0] for r in con.execute("SELECT path FROM favorites") if r[0] in pos]
    heard = {r[0] for r in con.execute("SELECT DISTINCT path FROM events WHERE type='listen'") if r[0] in pos}
    if len(fav) < 10:
        return dict(auc=None, note=f"needs about 10 favourites to measure (you have {len(fav)})", n_fav=len(fav))
    q = np.array([0.0] * len(L["paths"]))
    for r in con.execute("SELECT path, quality FROM samples"):
        if r[0] in pos:
            q[pos[r[0]]] = r[1] or 0
    res, base = [], []
    allh = sorted(heard | set(fav))
    favs = set(fav)
    for seed in range(seeds):
        f = np.array(allh); np.random.default_rng(seed).shuffle(f)
        for k in range(folds):
            hide = set(f[k::folds].tolist())
            lab = {p: v for p, v in labels.items() if p not in hide}
            r = fit(None, labels=lab)
            cand = sorted(hide)  # this group's favourites vs this group's heard, never starred
            y = np.array([p in favs for p in cand])
            idx = [pos[p] for p in cand]
            a = _auc(y, np.asarray(r["score"])[idx])
            b = _auc(y, q[idx])
            if a is not None:
                res.append(a); base.append(b)
    return dict(auc=round(float(np.mean(res)), 3), se=round(float(np.std(res) / np.sqrt(len(res))), 3),
                quality_auc=round(float(np.mean(base)), 3), n_fav=len(fav), n_heard=len(heard))


def _history(con):
    con.execute("""CREATE TABLE IF NOT EXISTS taste_history (ts REAL, n_labels INTEGER, n_pos INTEGER, n_fav INTEGER,
                   n_dislike INTEGER, auc REAL, quality_auc REAL)""")
    return con


_CACHE = {}
import threading
_MEASURING = threading.Event()


def measure_soon(sig):
    """Measure accuracy in a background thread (10-15 s) and add it to the history."""
    if _MEASURING.is_set():
        return
    _MEASURING.set()

    def go():
        try:
            con = _history(_db())
            acc = accuracy(con)
            if acc.get("auc") is not None:
                con.execute("INSERT INTO taste_history VALUES (?,?,?,?,?,?,?)",
                            (time.time(), *sig, acc["auc"], acc["quality_auc"]))
                con.commit()
            _CACHE.clear()
        finally:
            _MEASURING.clear()
    threading.Thread(target=go, daemon=True).start()


def explain():
    con = _history(_db())
    L = _library(con)
    if L is None:
        return dict(ready=False)
    labels = item_labels(con, None, L["durs"])
    payload = scores_payload(None)  # also fits (or reuses) the model
    from .taste import _FIT
    res = _FIT.get(None) or {}
    key = res.get("_key")
    if _CACHE.get("key") == key and not _MEASURING.is_set():
        return _CACHE["value"]

    # what it learns from
    fav = {r[0] for r in con.execute("SELECT path FROM favorites")}
    kinds = dict(favourites=0, dislikes=0, liked_by_listening=0, skipped=0)
    for p, (y, w) in labels.items():
        if p in fav:
            kinds["favourites"] += 1
        elif y == 1:
            kinds["liked_by_listening"] += 1
        elif w >= 1.5:
            kinds["dislikes"] += 1
        else:
            kinds["skipped"] += 1
    n_listen = con.execute("SELECT COUNT(*) FROM events WHERE type='listen'").fetchone()[0]

    # accuracy: the last measurement; a new one runs in the background when your ratings changed since
    last = con.execute("SELECT * FROM taste_history ORDER BY ts DESC LIMIT 1").fetchone()
    sig = (res.get("n_labels"), res.get("n_pos"), len(fav), kinds["dislikes"])
    stale = not last or (last["n_labels"], last["n_pos"], last["n_fav"], last["n_dislike"]) != sig
    if stale:
        measure_soon(sig)
    acc = dict(auc=last["auc"], quality_auc=last["quality_auc"], when=last["ts"]) if last else dict(auc=None)
    acc.update(measuring=_MEASURING.is_set(), n_fav=len(fav))
    hist = [dict(r) for r in con.execute("SELECT * FROM taste_history ORDER BY ts")]

    learned = {}
    if "beta" in res:
        beta, fz = res["beta"], L["fz"]
        b_eng = beta[N_PCA + len(CATS) + len(KINDS):]
        # these weights are "with the sound held equal": e.g. among samples that sound alike, the longer one
        learned["features"] = sorted([[e, round(float(b), 2)] for e, b in zip(ENG, b_eng)], key=lambda x: -x[1])
        from .models import clap
        T = clap().embed_text(tuple(WORDS))
        Z = ((T / np.linalg.norm(T, axis=1, keepdims=True)) * np.linalg.norm(L["E"], axis=1).mean() - fz.mu) @ fz.P / fz.sd
        sw = Z @ beta[:N_PCA]
        sw = (sw - sw.mean()) / (sw.std() + 1e-9)
        o = np.argsort(-sw)
        learned["words_up"] = [[WORDS[i], round(float(sw[i]), 2)] for i in o[:10]]
        learned["words_down"] = [[WORDS[i], round(float(sw[i]), 2)] for i in o[::-1][:10]]

    # examples
    paths = L["paths"]
    score = np.asarray(res.get("score", np.zeros(len(paths))))
    unc = np.asarray(res.get("unc", np.zeros(len(paths))))
    heard = {r[0] for r in con.execute("SELECT DISTINCT path FROM events")}
    info = {r["path"]: dict(path=r["path"], id=r["id"], cat=r["category"], sub=r["subtype"], artist=r["artist"],
                            title=r["title"])
            for r in con.execute("""SELECT s.path, s.id, s.category, s.subtype, t.artist, t.title
                                    FROM samples s JOIN tracks t ON t.id=s.track_id""")}
    pct = np.argsort(np.argsort(score)) / max(1, len(score) - 1)  # percentile of each sample's score
    def ex(i, why=None):
        d = dict(info.get(paths[i], dict(path=paths[i])), pct=round(float(pct[i]) * 100))
        if why:
            d["why"] = why
        return d
    order = np.argsort(-score)
    unheard, seen_song = [], set()
    for i in order:  # one sample per song, so the lists show variety
        if paths[i] in heard or paths[i] in labels:
            continue
        song = (info.get(paths[i], {}).get("artist"), info.get(paths[i], {}).get("title"))
        if song in seen_song:
            continue
        seen_song.add(song); unheard.append(i)
        if len(unheard) >= 3000:
            break
    examples = dict(
        top=[ex(i) for i in unheard[:8]],
        unsure=[ex(i) for i in sorted(unheard[:2000], key=lambda i: -unc[i])[:8]],
        missed=[ex(i, "you starred it") for i in
                sorted([L["pos"][p] for p in fav if p in L["pos"]], key=lambda i: score[i])[:6]],
        wrong=[ex(i, "you said not for me") for i in
               sorted([L["pos"][p] for p, (y, w) in labels.items() if y == 0 and w >= 1.5 and p in L["pos"]],
                      key=lambda i: -score[i])[:6]],
    )
    by_cat, by_kind = {}, {}
    meta = L["meta"]
    for i, p in enumerate(paths):
        m = meta.get(p, {})
        if m.get("category"):
            by_cat.setdefault(m["category"], []).append(pct[i] * 100)
        if m.get("kind"):
            by_kind.setdefault(m["kind"], []).append(pct[i] * 100)
    value = dict(ready=True, accuracy=acc, history=hist, signals=dict(kinds, listens=n_listen,
                 labelled=res.get("n_labels"), positive=res.get("n_pos")), learned=learned, examples=examples,
                 by_category=sorted([[c, round(float(np.mean(v))), len(v)] for c, v in by_cat.items()],
                                    key=lambda x: -x[1]),
                 by_kind=sorted([[c, round(float(np.mean(v))), len(v)] for c, v in by_kind.items()], key=lambda x: -x[1]),
                 model="Bayesian logistic regression on CLAP sound features (64 dimensions) plus category, kind and "
                       "six sound measurements, blended 55/45 with similarity to your favourites")
    _CACHE.update(key=key, value=value)
    return value
