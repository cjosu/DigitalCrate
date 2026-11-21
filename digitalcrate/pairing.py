"""Learned "vibe" for Goes-well-with, trained on the arrangements already in your library.

Samples cut from the same song in different categories (its vocal, its pad, its keys) really were played
together, so they're examples of things that fit. A small two-tower network learns, from CLAP embeddings, to
score a candidate partner highly when it would sit in the same arrangement, with partners from other songs in the
batch as negatives. Embeddings are centred per category first so "both are vocals" isn't what it matches on.

On held-out songs (research/vibe_eval.py) it ranks a song's real partner above other songs' samples with AUC 0.82,
against 0.70 for the plain CLAP similarity used before.
"""
import numpy as np

from . import config as C

WEIGHTS = C.DATA_DIR / "pairing.pt"
CATS = ["Vocals", "Vocal Atmospheres", "Pads & Atmospheres", "Chords & Keys", "Melodies & Leads",
        "Textures & Field", "Bass & Sub", "Percussion"]


def _inputs(emb, cat_idx, mu=None):
    nc = len(CATS)
    if mu is None:
        mu = np.stack([emb[cat_idx == k].mean(0) if (cat_idx == k).any() else np.zeros(emb.shape[1])
                       for k in range(nc)])
    ec = emb - mu[cat_idx]
    ec /= np.linalg.norm(ec, axis=1, keepdims=True) + 1e-9
    return np.hstack([ec, np.eye(nc)[cat_idx]]).astype(np.float32), mu


def _towers(d_in):
    import torch

    class Tower(torch.nn.Module):
        def __init__(s):
            super().__init__()
            s.n = torch.nn.Sequential(torch.nn.Linear(d_in, 256), torch.nn.GELU(), torch.nn.Dropout(.2),
                                      torch.nn.Linear(256, 128))

        def forward(s, x):
            return torch.nn.functional.normalize(s.n(x), dim=-1)
    return Tower(), Tower()


def arrangement_pairs(cat_idx, track, ok):
    by = {}
    for i in np.flatnonzero(ok):
        by.setdefault(track[i], []).append(i)
    return [(a, b) for ids in by.values() for a in ids for b in ids if cat_idx[a] != cat_idx[b]]


def train(emb, cat_idx, track, ok, epochs=8, temp=.07, seed=0, verbose=True):
    """Fit both towers on every same-song cross-category pair; returns a state dict (also saved)."""
    import torch
    torch.manual_seed(seed)
    X, mu = _inputs(emb, cat_idx)
    Xt = torch.tensor(X)
    P = torch.tensor(np.array(arrangement_pairs(cat_idx, track, ok)))
    if len(P) < 500:
        if verbose:
            print(f"pairing: only {len(P)} arrangement pairs; keeping the plain similarity")
        return None
    f, g = _towers(X.shape[1])
    opt = torch.optim.AdamW(list(f.parameters()) + list(g.parameters()), lr=1e-3, weight_decay=1e-3)
    tr = torch.tensor(track)
    for ep in range(epochs):
        perm = P[torch.randperm(len(P))]
        for k in range(0, len(perm), 512):
            bt = perm[k:k + 512]
            lg = f(Xt[bt[:, 0]]) @ g(Xt[bt[:, 1]]).T / temp
            same = tr[bt[:, 0]][:, None] == tr[bt[:, 1]][None, :]  # other pairs from the same song aren't negatives
            lg = lg.masked_fill(same & ~torch.eye(len(bt), dtype=torch.bool), -1e4)
            loss = torch.nn.functional.cross_entropy(lg, torch.arange(len(bt)))
            opt.zero_grad(); loss.backward(); opt.step()
    state = dict(f=f.state_dict(), g=g.state_dict(), mu=mu, d_in=X.shape[1], n_pairs=len(P))
    torch.save(state, WEIGHTS)
    if verbose:
        print(f"pairing: trained on {len(P):,} arrangement pairs")
    return state


def vectors(emb, cat_idx, state=None):
    """(Fa, Gb): a sample's 'what I want' and 'what I offer' vectors; vibe(a, b) = Fa[a] @ Gb[b]. None if untrained."""
    import torch
    if state is None:
        if not WEIGHTS.exists():
            return None
        state = torch.load(WEIGHTS, weights_only=False)
    X, _ = _inputs(emb, cat_idx, state["mu"])
    f, g = _towers(state["d_in"])
    f.load_state_dict(state["f"]); g.load_state_dict(state["g"]); f.eval(); g.eval()
    with torch.no_grad():
        Xt = torch.tensor(X)
        return f(Xt).numpy(), g(Xt).numpy()
