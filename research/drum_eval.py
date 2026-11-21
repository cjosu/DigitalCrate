"""How right are the drum subtypes? Compares each sample's current subtype with the pieces you labelled.

Your label (a set of pieces) is mapped to the subtype the app should have given it, using the same naming as the
app (one piece -> its type; two -> the combo name)."""
import sys, pathlib, collections, json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from digitalcrate.listening import drum_labels, DRUM_FILE
from digitalcrate.db import connect

SINGLE = dict(kick="Kick", snare="Snare", rim_clap="Rim & Clap", hat_closed="Hat Closed", hat_open="Hat Open",
              shaker="Shaker & Tamb", ride="Ride", crash="Crash", tom="Tom", hand_drum="Hand Drum",
              wood_metal="Wood & Metal", orchestral="Orchestral")
HAT, CYM, PERC = {"hat_closed", "hat_open"}, {"ride", "crash"}, {"tom", "hand_drum", "wood_metal", "shaker"}


def true_subtype(p):
    p = set(p)
    if "not_drum" in p: return "Not a drum"
    if len(p) == 1: return SINGLE[next(iter(p))]
    sn = p & {"snare", "rim_clap"}
    if "kick" in p and sn: return "Kick + Snare"
    if "kick" in p and p & CYM: return "Kick + Cymbal"
    if sn and p & CYM: return "Snare + Cymbal"
    if p == {"kick"} | (p & HAT) and p & HAT: return "Kick + Hat"
    if sn and p - sn <= HAT and p & HAT: return "Snare + Hat"
    if p & PERC and p - PERC <= HAT and p & HAT: return "Perc + Hat"
    return "Other Combos"


def load():
    L = drum_labels()
    con = connect()
    rows = {r["id"]: r for r in con.execute(f"SELECT * FROM samples WHERE id IN ({','.join('?' * len(L))})", list(L))}
    return [(rows[i], set(p), true_subtype(p)) for i, p in L.items() if i in rows]


if __name__ == "__main__":
    data = load()
    n = len(data)
    ok = sum(r["subtype"] == t for r, _, t in data)
    combo_pred = lambda s: " + " in s or s == "Other Combos"
    combo_true = lambda t: " + " in t or t == "Other Combos"
    print(f"{n} labelled hits · current subtype exactly right: {ok}/{n} = {ok / n:.0%}")
    cm = sum(combo_pred(r["subtype"]) == combo_true(t) for r, _, t in data if t != "Not a drum")
    print(f"single-vs-combo right: {cm}/{sum(t != 'Not a drum' for *_, t in data)}")
    print("true labels:", collections.Counter(t for *_, t in data).most_common())
    print("\nper current subtype: right / labelled  → what they really were")
    by = collections.defaultdict(list)
    for r, _, t in data:
        by[r["subtype"]].append(t)
    for s, ts in sorted(by.items(), key=lambda x: -len(x[1])):
        c = collections.Counter(ts)
        print(f"  {s:16s} {c[s]}/{len(ts)}   " + ", ".join(f"{k} {v}" for k, v in c.most_common() if k != s))
