"""Fixed key + bar grid vs following the sample's own changes, on random keys/pad samples that have chords.
Clash = share of the sample's sound a semitone from the pad's core chord tones (lower is better)."""
import sys, pathlib, subprocess, re
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import numpy as np
from digitalcrate.db import connect
from digitalcrate import harmony as H
rows = connect().execute("""SELECT id, path FROM samples WHERE category IN ('Chords & Keys','Pads & Atmospheres') AND key_from!='none'
    AND path NOT LIKE '_Reference%' AND parent_id IS NULL AND dur BETWEEN 4 AND 20 ORDER BY RANDOM() LIMIT 40""").fetchall()
import runpy
res = []
for r in rows:
    segs, sure = H.own_chords(r["path"])
    if not segs or sure < 0.6 or len(segs) < 2:
        continue
    out = {}
    for mode in ("grid", "follow"):
        orig = H.own_chords
        if mode == "grid":
            H.own_chords = lambda rel: ([], 0)
        try:
            sys.argv = ["x", r["id"], "100", "1"]
            import io, contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                runpy.run_path(str(pathlib.Path(__file__).with_name("chord_eval.py")), run_name="__main__")
            lines = [l for l in buf.getvalue().splitlines() if re.match(r"^(option|follows|reharmonised)", l)]
            vals = [list(map(int, re.findall(r"(\d+)%", l)))[:2] for l in lines]
            out[mode] = (np.mean([v[0] for v in vals]), np.mean([v[1] for v in vals]), min(v[1] for v in vals))
        finally:
            H.own_chords = orig
    res.append(out)
    if len(res) >= 10:
        break
g = np.array([x["grid"] for x in res]); f = np.array([x["follow"] for x in res])
print(f"{len(res)} samples with their own chord changes")
print(f"fixed key + grid:      on-chord {g[:, 0].mean():.0f}%  clash {g[:, 1].mean():.0f}% (best option {g[:, 2].mean():.0f}%)")
print(f"follows its changes:   on-chord {f[:, 0].mean():.0f}%  clash {f[:, 1].mean():.0f}% (best option {f[:, 2].mean():.0f}%)")
print("clash per sample (grid → follow):", ", ".join(f"{a:.0f}→{b:.0f}" for a, b in zip(g[:, 1], f[:, 1])))
