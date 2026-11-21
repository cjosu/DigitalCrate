"""Drum one-shot classifier learned from your labels (the /drumlabel page).

Which pieces strike in a hit (kick, snare, hats…) is predicted from the CLAP embedding with one logistic model per
piece, so combos come out naturally. On your first 108 labels it got the subtype right about half the time, against
under a fifth for the pipeline's separation-based labels (research/drum_eval.py, drum_clf.py). Labels marked
"not sure" count for less; repeat labels of the same hit are averaged.
"""
import numpy as np

PIECES = ["kick", "snare", "rim_clap", "hat_closed", "hat_open", "tom", "wood_metal", "shaker", "ride", "crash",
          "hand_drum", "orchestral"]
SINGLE = dict(kick="Kick", snare="Snare", rim_clap="Rim & Clap", hat_closed="Hat Closed", hat_open="Hat Open",
              shaker="Shaker & Tamb", ride="Ride", crash="Crash", tom="Tom", hand_drum="Hand Drum",
              wood_metal="Wood & Metal", orchestral="Orchestral")
HAT, CYM, PERC = {"hat_closed", "hat_open"}, {"ride", "crash"}, {"tom", "hand_drum", "wood_metal", "shaker"}


def subtype(pieces):
    """A set of pieces -> the app's subtype name."""
    p = set(pieces) - {"unsure"}
    if "not_drum" in p:
        return "Not a drum"
    if len(p) == 1:
        return SINGLE[next(iter(p))]
    sn = p & {"snare", "rim_clap"}
    if "kick" in p and sn: return "Kick + Snare"
    if "kick" in p and p & CYM: return "Kick + Cymbal"
    if sn and p & CYM: return "Snare + Cymbal"
    if "kick" in p and p - {"kick"} <= HAT: return "Kick + Hat"
    if sn and p - sn <= HAT and p & HAT: return "Snare + Hat"
    if p & PERC and p - PERC <= HAT and p & HAT: return "Perc + Hat"
    return "Other Combos"


def training_set(con):
    """(sample ids, embeddings, Y pieces matrix, weights) from drum_labels; 'id#r2' repeats fold into their hit."""
    lab = {}
    for r in con.execute("SELECT * FROM drum_labels"):
        sid = r["sample_id"].split("#")[0]
        import json
        ps = set(json.loads(r["pieces"]))
        lab.setdefault(sid, []).append(ps)
    rows = {r["id"]: r for r in con.execute(
        f"SELECT id, clap FROM samples WHERE id IN ({','.join('?' * len(lab))})", list(lab))} if lab else {}
    ids, E, Y, W = [], [], [], []
    for sid, sets in lab.items():
        if sid not in rows or any("not_drum" in s for s in sets):
            continue
        y = np.mean([[p in s for p in PIECES] for s in sets], 0)  # repeats that disagree -> soft label
        w = np.mean([0.5 if "unsure" in s else 1.0 for s in sets])
        ids.append(sid); E.append(np.frombuffer(rows[sid]["clap"], np.float16).astype(np.float32))
        Y.append(y); W.append(w)
    return ids, np.array(E), np.array(Y), np.array(W)


class Model:
    def __init__(self, E, Y, W, npca=16, C=0.5):
        from sklearn.decomposition import PCA
        from sklearn.linear_model import LogisticRegression
        self.pca = PCA(min(npca, len(E) - 1)).fit(E)
        X = self.pca.transform(E)
        self.models = {}
        for j, p in enumerate(PIECES):
            # soft labels: duplicate each hit as a positive and a negative, weighted by how often it was marked
            yj = np.r_[np.ones(len(X)), np.zeros(len(X))]
            wj = np.r_[W * Y[:, j], W * (1 - Y[:, j])]
            keep = wj > 0
            if (yj[keep] == 1).sum() >= 2 and (yj[keep] == 0).sum() >= 2:
                self.models[p] = LogisticRegression(C=C, max_iter=3000, class_weight="balanced").fit(
                    np.vstack([X, X])[keep], yj[keep], sample_weight=wj[keep])

    def probs(self, E):
        X = self.pca.transform(E)
        return np.stack([self.models[p].predict_proba(X)[:, 1] if p in self.models else np.zeros(len(X))
                         for p in PIECES], 1)

    @staticmethod
    def pieces(pr, combo=0.75):
        o = np.argsort(-pr)
        return {PIECES[o[0]]} | ({PIECES[o[1]]} if pr[o[1]] > combo else set())
