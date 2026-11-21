import numpy as np, collections
import drum_clf as D
from drum_curve import fit_predict, sets
from drum_eval import true_subtype
COARSE = {"Kick": "Kick", "Snare": "Snare & Clap", "Rim & Clap": "Snare & Clap", "Hat Closed": "Hats & Shakers",
          "Hat Open": "Hats & Shakers", "Shaker & Tamb": "Hats & Shakers", "Tom": "Toms & Hand", "Hand Drum": "Toms & Hand",
          "Orchestral": "Toms & Hand", "Wood & Metal": "Wood & Metal", "Ride": "Cymbals", "Crash": "Cymbals"}
co = lambda s: COARSE.get(s, "Combos" if (" + " in s or s == "Other Combos") else s)
N = len(D.data)
pred = []
for k in range(N):
    P = fit_predict(np.flatnonzero(np.arange(N) != k), np.array([k])); pred.append(true_subtype(sets(P)[0]))
cur = [r["subtype"] for r, _, _ in D.data]
tc = [co(t) for t in D.truth]
print(f"coarse groups (Kick · Snare & Clap · Hats & Shakers · Toms & Hand · Cymbals · Wood & Metal · Combos):")
print(f"  current labels {np.mean([co(c) == t for c, t in zip(cur, tc)]):.0%} · learned {np.mean([co(p) == t for p, t in zip(pred, tc)]):.0%}")
print("  learned mistakes (truth → predicted):", collections.Counter((t, co(p)) for p, t in zip(pred, tc) if co(p) != t).most_common(8))
print(f"  fine subtype: learned {np.mean([p == t for p, t in zip(pred, D.truth)]):.0%}")
