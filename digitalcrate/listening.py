"""Listening tests that give the recommendation and drum models real ground truth.

/pairtest   blind test of Goes-well-with: for a set of samples, the current ("clap") and the learned partner
            picks are mixed together and shuffled; you rate how well each pair sits together, 1-5.
/drumlabel  label a stratified handful of drum one-shots by the pieces you hear, to measure and retrain the
            drum classifier.
"""
import json
import random
import time

import numpy as np

from . import config as C
from .db import connect

PAIR_FILE = C.DATA_DIR / "pairtest.json"
DRUM_FILE = C.DATA_DIR / "drumlabel.json"
PIECES = ["kick", "snare", "rim_clap", "hat_closed", "hat_open", "shaker", "ride", "crash", "tom", "hand_drum",
          "wood_metal", "orchestral", "not_drum", "unsure"]


def _db():
    con = connect()
    con.execute("CREATE TABLE IF NOT EXISTS pair_votes (trial TEXT PRIMARY KEY, rating INTEGER, ts REAL)")
    con.execute("CREATE TABLE IF NOT EXISTS drum_labels (sample_id TEXT PRIMARY KEY, pieces TEXT, ts REAL)")
    return con


# ------------------------------------------------------------------ pair test

ROUNDS = {1: ("clap", "learned"), 2: ("clap", "blend")}
ROUND = 2


def _make_pairs(excl=(), n_src=24, per=3, seed=None):
    from . import build as B
    from .genre import assign
    con = _db()
    d = B.load(con)
    if d.get("Fa") is None:
        raise RuntimeError("no learned pairing model yet: run `digitalcrate build` first")
    genre = np.array(assign(d["rows"], d["emb"]))
    rows, n = d["rows"], d["n"]
    ok = np.array([r["category"] != "Percussion" and not r["parent_id"] and r["quality"] >= .5 for r in rows])
    ok &= ~np.isin(genre, list(excl))
    rng = random.Random(seed)
    # fresh samples each round: skip sources already used in earlier rounds
    used = set()
    for f in C.DATA_DIR.glob("pairtest*.json"):
        used |= {t["src"] for t in json.loads(f.read_text())["trials"]}
    ok &= np.array([r["path"] not in used for r in rows])
    fav = {r["path"] for r in con.execute("SELECT path FROM favorites")}
    favs = [i for i in range(n) if ok[i] and rows[i]["path"] in fav]
    rest = [i for i in range(n) if ok[i] and rows[i]["path"] not in fav]
    rng.shuffle(favs); rng.shuffle(rest)
    # spread across categories: round-robin, favourites first (you know you like these)
    by = {}
    for i in favs + rest:
        by.setdefault(rows[i]["category"], []).append(i)
    src = []
    while len(src) < n_src and any(by.values()):
        for c in list(by):
            if by[c] and len(src) < n_src:
                src.append(by[c].pop(0))
    idx = np.array(src)
    keep = ~np.isin(genre, list(excl))
    picks = {}
    modes = ROUNDS[ROUND]
    for mode in modes:
        comp = B.compat_block(d, idx, mode=mode)
        sc = comp["score"].copy()
        sc[np.arange(len(idx)), idx] = -1
        for k, gi in enumerate(idx):
            js = [p[0] for p in B._picks(d, gi, comp, sc, k) if keep[p[0]]][:per]
            picks[(int(gi), mode)] = js
    trials = []
    for gi in src:
        both = {}
        for mode in modes:
            for j in picks[(gi, mode)]:
                both.setdefault(j, []).append(mode)
        items = [dict(trial=f"{rows[gi]['id']}-{rows[j]['id']}", path=rows[j]["path"], methods=m,
                      label=f"{rows[j]['category']} · {rows[j]['artist']} — {rows[j]['title']}",
                      kind=rows[j]["kind"]) for j, m in both.items()]
        rng.shuffle(items)
        trials.append(dict(src=rows[gi]["path"], kind=rows[gi]["kind"],
                           label=f"{rows[gi]['category']} · {rows[gi]['artist']} — {rows[gi]['title']}",
                           items=items))
    m = dict(created=time.time(), round=ROUND, modes=list(modes), trials=trials)
    PAIR_FILE.write_text(json.dumps(m))
    return m


def pair_manifest(excl=(), new=False):
    if new or not PAIR_FILE.exists():
        return _make_pairs(excl)
    return json.loads(PAIR_FILE.read_text())


def pair_vote(trial, rating):
    con = _db()
    if rating:
        con.execute("INSERT OR REPLACE INTO pair_votes VALUES (?,?,?)", (trial, int(rating), time.time()))
    else:
        con.execute("DELETE FROM pair_votes WHERE trial=?", (trial,))
    con.commit()
    return True


def pair_results():
    """Mean rating per method, and per source sample which method's picks you rated higher."""
    if not PAIR_FILE.exists():
        return {}
    m = json.loads(PAIR_FILE.read_text())
    A, Bm = m.get("modes", ["clap", "learned"])
    v = {r["trial"]: r["rating"] for r in _db().execute("SELECT * FROM pair_votes")}
    out = {A: [], Bm: []}
    wins = {"current": 0, "new": 0, "tie": 0}
    for t in m["trials"]:
        per = {A: [], Bm: []}
        for it in t["items"]:
            if it["trial"] in v:
                for mm in it["methods"]:
                    per[mm].append(v[it["trial"]]); out[mm].append(v[it["trial"]])
        if per[A] and per[Bm]:
            a, b = np.mean(per[A]), np.mean(per[Bm])
            wins["new" if b > a else "current" if a > b else "tie"] += 1
    rng = np.random.default_rng(0)
    res = {}
    for k, x in out.items():
        if x:
            boot = [np.mean(rng.choice(x, len(x))) for _ in range(2000)]
            res[k] = dict(n=len(x), mean=round(float(np.mean(x)), 2),
                          ci=[round(float(np.percentile(boot, 2.5)), 2), round(float(np.percentile(boot, 97.5)), 2)])
    return dict(methods=res, wins=wins, rated=sum(it["trial"] in v for t in m["trials"] for it in t["items"]),
                round=m.get("round", 1))


# ------------------------------------------------------------------ drum labels

def drum_manifest(per=8, new=False):
    if DRUM_FILE.exists() and not new:
        return json.loads(DRUM_FILE.read_text())
    con = _db()
    rows = con.execute("""SELECT id, path, subtype FROM samples WHERE category='Percussion' AND kind='oneshot'
                          AND parent_id IS NULL""").fetchall()
    rng = random.Random(1)
    by = {}
    for r in rows:
        by.setdefault(r["subtype"], []).append(r)
    items = []
    for sub, rs in by.items():
        rng.shuffle(rs)
        items += [dict(id=r["id"], path=r["path"], subtype=sub) for r in rs[:per]]
    rng.shuffle(items)
    m = dict(created=time.time(), pieces=PIECES, items=items)
    DRUM_FILE.write_text(json.dumps(m))
    return m


def drum_round2(n_repeat=20, n_uncertain=40, seed=2):
    """Round 2: some hits you already labelled (shuffled in, to measure how consistent labels are), plus the hits
    the classifier trained on your labels is least sure about (they teach it the most)."""
    from .drumclass import Model, training_set
    con = _db()
    ids, E, Y, W = training_set(con)
    model = Model(E, Y, W)
    rows = con.execute("""SELECT id, path, subtype, clap FROM samples WHERE category='Percussion' AND kind='oneshot'
                          AND parent_id IS NULL""").fetchall()
    done = {r["sample_id"].split("#")[0] for r in con.execute("SELECT sample_id FROM drum_labels")}
    cand = [r for r in rows if r["id"] not in done]
    P = model.probs(np.stack([np.frombuffer(r["clap"], np.float16).astype(np.float32) for r in cand]))
    top2 = np.sort(P, 1)[:, -2:]
    margin = top2[:, 1] - top2[:, 0]  # small gap between the two likeliest pieces = unsure
    rng = random.Random(seed)
    unsure = [cand[k] for k in np.argsort(margin)[: n_uncertain * 3]]
    rng.shuffle(unsure)
    pick = unsure[:n_uncertain]
    lab = [r for r in rows if r["id"] in done]
    rng.shuffle(lab)
    items = [dict(id=r["id"], path=r["path"], subtype=r["subtype"]) for r in pick] + \
            [dict(id=r["id"] + "#r2", path=r["path"], subtype=r["subtype"]) for r in lab[:n_repeat]]
    rng.shuffle(items)
    if DRUM_FILE.exists():
        DRUM_FILE.rename(DRUM_FILE.with_name("drumlabel-round1.json"))
    m = dict(created=time.time(), round=2, pieces=PIECES, items=items)
    DRUM_FILE.write_text(json.dumps(m))
    return m


def drum_vote(sample_id, pieces):
    con = _db()
    if pieces is None:
        con.execute("DELETE FROM drum_labels WHERE sample_id=?", (sample_id,))
    else:
        con.execute("INSERT OR REPLACE INTO drum_labels VALUES (?,?,?)", (sample_id, json.dumps(pieces), time.time()))
    con.commit()
    return True


def drum_labels():
    return {r["sample_id"]: json.loads(r["pieces"]) for r in _db().execute("SELECT * FROM drum_labels")}
