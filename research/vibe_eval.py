"""Proxy test for the "vibe" part of Goes-well-with, using real arrangements as ground truth.

Samples cut from the same song in different categories (its vocal and its pad, say) really were played together.
For a sample from a held-out song, rank every sample of the partner's category from *other* songs plus the true
partner, and see how high the true partner lands (AUC: 0.5 = chance, 1 = always first). Same-artist candidates are
dropped so "same record" can't be the shortcut.
"""
import sys, pathlib
import numpy as np
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from digitalcrate.db import connect
from digitalcrate import build as B

d = B.load(connect()); rows = d["rows"]
E = d["emb"]; cat = d["cat"]; track = d["track"]; artist = np.array([r["artist"] or "" for r in rows])
src_ok = np.array([r["source"] != "edit" and not r["parent_id"] for r in rows])
NC = len(B.CATS)
rng = np.random.default_rng(0)
tracks = np.unique(track[src_ok]); rng.shuffle(tracks)
test_tracks = set(tracks[: len(tracks) // 3].tolist())
is_test = np.array([t in test_tracks for t in track])


def pairs(mask):
    out = []
    by = {}
    for i in np.flatnonzero(mask & src_ok):
        by.setdefault(track[i], []).append(i)
    for t, ids in by.items():
        for a in ids:
            for b in ids:
                if cat[a] != cat[b]:
                    out.append((a, b))
    return out


test_pairs = pairs(is_test)
sub = rng.choice(len(test_pairs), min(4000, len(test_pairs)), replace=False)
test_pairs = [test_pairs[k] for k in sub]
train_pairs = pairs(~is_test)
print(f"{len(test_pairs)} test pairs from {len(test_tracks)} held-out songs, {len(train_pairs)} training pairs")


def evaluate(name, sim):
    """sim(a, cand_idx) -> scores"""
    A = []
    for a, b in test_pairs:
        cand = np.flatnonzero((cat == cat[b]) & (artist != artist[a]) & src_ok)
        cand = np.r_[cand[track[cand] != track[a]], b]
        s = sim(a, cand)
        A.append((s[:-1] < s[-1]).mean() + .5 * (s[:-1] == s[-1]).mean())
    A = np.array(A)
    print(f"{name:50s} AUC {A.mean():.3f}  (±{A.std() / np.sqrt(len(A)):.3f})")
    return A.mean()


norm = lambda X: X / (np.linalg.norm(X, axis=1, keepdims=True) + 1e-9)
evaluate("raw CLAP cosine (current vibe)", lambda a, c: E[c] @ E[a])
mu = np.stack([E[cat == k].mean(0) for k in range(NC)])
Ec = norm(E - mu[cat])
evaluate("category-centred CLAP", lambda a, c: Ec[c] @ Ec[a])
# whitened (centred) – equalises dominant directions
U, S_, Vt = np.linalg.svd(Ec[~is_test], full_matrices=False)
for k in (64, 128):
    W = Vt[:k].T / (S_[:k] / np.sqrt((~is_test).sum()))
    Ew = norm(Ec @ W)
    evaluate(f"centred + whitened ({k} dims)", lambda a, c, Ew=Ew: Ew[c] @ Ew[a])
# learned: a bilinear map trained on real arrangements in training songs (one shared map, ridge)
P = Vt[:128].T; Z = Ec @ P
ta = np.array([p[0] for p in train_pairs]); tb = np.array([p[1] for p in train_pairs])
for lam in (10., 100.):
    M = np.linalg.solve(Z[ta].T @ Z[ta] + lam * np.eye(128), Z[ta].T @ Z[tb])  # predict partner's embedding
    Zp = Z @ M
    evaluate(f"learned arrangement map (ridge λ={lam:g})", lambda a, c, Zp=Zp: norm(Z[c]) @ (Zp[a] / np.linalg.norm(Zp[a])))

# ---- contrastive two-tower model: f(a)·g(b) high for real arrangement partners, in-batch negatives
import torch
torch.manual_seed(0)
oh = np.eye(NC)[cat].astype(np.float32)
Xin = torch.tensor(np.hstack([Ec, oh]).astype(np.float32))


class Tower(torch.nn.Module):
    def __init__(s, d_in, h=256, out=128):
        super().__init__(); s.n = torch.nn.Sequential(torch.nn.Linear(d_in, h), torch.nn.GELU(), torch.nn.Dropout(.2), torch.nn.Linear(h, out))
    def forward(s, x): return torch.nn.functional.normalize(s.n(x), dim=-1)


def train_tower(epochs=8, temp=.07, shared=True):
    f = Tower(Xin.shape[1]); g = f if shared else Tower(Xin.shape[1])
    opt = torch.optim.AdamW(list(f.parameters()) + ([] if shared else list(g.parameters())), lr=1e-3, weight_decay=1e-3)
    P_ = torch.tensor(np.array(train_pairs))
    for ep in range(epochs):
        perm = P_[torch.randperm(len(P_))]
        for k in range(0, len(perm), 512):
            bt = perm[k:k + 512]
            fa, gb = f(Xin[bt[:, 0]]), g(Xin[bt[:, 1]])
            lg = fa @ gb.T / temp
            # pairs from the same song in a batch are not negatives of each other
            same = torch.tensor(track[bt[:, 0].numpy()][:, None] == track[bt[:, 1].numpy()][None, :])
            lg = lg.masked_fill(same & ~torch.eye(len(bt), dtype=bool), -1e4)
            loss = torch.nn.functional.cross_entropy(lg, torch.arange(len(bt)))
            opt.zero_grad(); loss.backward(); opt.step()
    f.eval(); g.eval()
    with torch.no_grad():
        return f(Xin).numpy(), g(Xin).numpy()


for shared in (True, False):
    Fa, Gb = train_tower(shared=shared)
    evaluate(f"contrastive two-tower ({'shared' if shared else 'separate'} towers)", lambda a, c, Fa=Fa, Gb=Gb: Gb[c] @ Fa[a])
