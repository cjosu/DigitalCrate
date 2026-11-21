"""How well do suggested progressions sit with a sample that has its own chords?

Every 100 ms: which pitch classes the sample is sounding (CQT chroma, strongest bins), and which chord the pad plays
then. Scores, weighted by how loud the sample is:
  on      share of the sample's sound on the pad's chord tones (higher = consonant)
  clash   share a semitone above or below a pad chord tone's core (root/3rd/5th) (lower = better)
  agree   how often the pad's chord is the sample's own chord at that moment (same root and quality family)
Compared with: the pad doubling the sample's own detected chords at their real times (an upper bound), a static
tonic pad, and the average random in-key progression (a floor).

    python research/chord_eval.py <sample id> [bpm] [bars_per_chord]
"""
import sys, pathlib, json
import numpy as np
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import librosa
from digitalcrate import config as C
from digitalcrate.db import connect
from digitalcrate.edit import _load
from digitalcrate.harmony import suggest, QUAL, _vocab, NAMES
from digitalcrate.midi import chord_of, CHORDS, NAMES as MN

sid = sys.argv[1]; bpm = float(sys.argv[2]) if len(sys.argv) > 2 else 113; bpc = int(sys.argv[3]) if len(sys.argv) > 3 else 1
row = connect().execute("SELECT * FROM samples WHERE id=?", (sid,)).fetchone()
y = _load(row["path"]).mean(0); sr = C.SR; hop = int(0.1 * sr)
ch = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop)          # 12 x frames
rms = librosa.feature.rms(y=y, frame_length=hop * 2, hop_length=hop)[0][: ch.shape[1]]
T = np.arange(ch.shape[1]) * 0.1
w = rms / (rms.max() + 1e-9); w[w < 0.05] = 0                        # ignore near-silence
P = np.where(ch >= np.sort(ch, 0)[-4], ch, 0); P /= P.sum(0, keepdims=True) + 1e-9   # top-4 pitch classes per frame

# the sample's own chords, 0.5 s windows
own = []
for t0 in np.arange(0, T[-1], 0.5):
    m = (T >= t0) & (T < t0 + 0.5)
    own.append((t0, chord_of((ch[:, m] * w[m]).sum(1))))
segs = []
for t0, c in own:
    if c and (not segs or segs[-1][2] != c): segs.append([t0, t0 + 0.5, c])
    elif c and segs: segs[-1][1] = t0 + 0.5
print(f"{row['path'].split('/')[-1]}\n{row['dur']:.2f}s, file key {row['key']}{'m' if row['scale'] == 'minor' else ''}")
print("the sample's own chords:", "  ".join(f"{c} {a:.1f}–{b:.1f}s" for a, b, c in segs))

def parse(name):
    for L in (NAMES, ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]):
        for k in range(12):
            if name.startswith(L[k]) and name[len(L[k]):] in QUAL: return k, name[len(L[k]):]
    for k in range(12):
        if name.startswith(MN[k]) and name[len(MN[k]):] in CHORDS: return k, name[len(MN[k]):]
    return None

def tones(name, core=False):
    r, q = parse(name); iv = (QUAL.get(q) or CHORDS[q])
    return {(r + i) % 12 for i in (iv[:3] if core else iv)}

def score(chord_at):
    on = cl = ag = tot = 0.0
    for f in range(len(T)):
        if not w[f]: continue
        c = chord_at(T[f])
        if not c: continue
        tn, co = tones(c), tones(c, core=True)
        on += w[f] * sum(P[p, f] for p in tn)
        cl += w[f] * sum(P[p, f] for p in range(12) if p not in tn and ((p - 1) % 12 in co or (p + 1) % 12 in co))
        oc = next((s[2] for s in segs if s[0] <= T[f] < s[1]), None)
        if oc:
            (r1, q1), (r2, q2) = parse(c), parse(oc)
            ag += w[f] * (r1 == r2 and q1.startswith("m") == q2.startswith("m"))
        tot += w[f]
    return on / tot, cl / tot, ag / tot

res = suggest(row["path"], bpm=bpm, bars_per_chord=bpc)
step = res["step"]
print(f"panel: key {res['key']}, " + (f"follows the sample's own changes {res['own']}" if res.get("follows") else f"{res['steps']} chords × {step:.2f}s ({bpm:g} bpm, {bpc} bar each)") + "\n")
print(f"{'':44s}  on-chord  clash  same as sample")
rows = []
def at(o):
    cs = o["chords"]
    if "t" in cs[0]:  # chords that change where the sample's own chords do
        return lambda t: next((c["name"] for c in reversed(cs) if c["t"] <= t), cs[0]["name"])
    return lambda t: cs[min(len(cs) - 1, int(t // step))]["name"]
for k, o in enumerate(res["options"]):
    names = [c["name"] for c in o["chords"]]
    s = score(at(o))
    rows.append((f"{o.get('label', 'option')} {k + 1}: " + " ".join(names), s))
s_own = score(lambda t: next((c for a, b, c in segs if a <= t < b), None))
tonic = res["key"]; tq = "m" if tonic.endswith("m") else ""
s_ton = score(lambda t: tonic[:-1] + "m" if tq else tonic)
rng = np.random.default_rng(0)
V = [c["name"] for c in _vocab(*((NAMES.index(tonic.rstrip("m")) if tonic.rstrip("m") in NAMES else ["C","Db","D","Eb","E","F","Gb","G","Ab","A","Bb","B"].index(tonic.rstrip("m"))), "minor" if tq else "major"), res["style"])]
st_ = step or (T[-1] / res["steps"])
rand = np.mean([score(lambda t, p=list(rng.choice(V, res["steps"])): p[min(len(p) - 1, int(t // st_))]) for _ in range(30)], 0)
for name, s in rows + [("doubling the sample's own chords", s_own), (f"static {tonic} pad", s_ton), ("random in-key progression (avg)", rand)]:
    print(f"{name[:44]:44s}  {s[0]:6.0%}  {s[1]:6.0%}  {s[2]:8.0%}")
# where do the grid steps sit against the sample's own changes?
print("\nsample chord changes at:", ", ".join(f"{a:.1f}s" for a, b, c in segs[1:]), "| panel chord changes at:",
      ", ".join(f"{c['t']:.1f}s" for c in res["options"][0]["chords"][1:]) if res.get("follows") else ", ".join(f"{k * step:.1f}s" for k in range(1, res["steps"])))

# clash by section: where do the suggestions go wrong?
if len(sys.argv) > 4:
    cut = float(sys.argv[4]); w0 = w.copy()
    for lab, keep in (("before", T < cut), ("after", T >= cut)):
        w[:] = np.where(keep, w0, 0)
        print(f"\n{lab} {cut:g}s:", "   ".join(f"opt{k + 1} clash {score(at(o))[1]:.0%}" for k, o in enumerate(res["options"])))
    w[:] = w0
