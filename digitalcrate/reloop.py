"""Re-cut existing loops on Beat This! downbeats, in place.

Loops mined before Beat This were cut on bar starts from Essentia's beats with the bar phase guessed from bass-band
onsets, which disagreed with Beat This's downbeats in about half the songs tested: those loops start on beat 2, 3 or
4. This finds each loop's nearest Beat This downbeat and, where the loop starts more than 70 ms away from one,
re-cuts it from the same source (re-separating the song when the loop came from a stem) to start on the downbeat
and run the same number of bars.

It is careful with what you've touched:
  - a loop keeps its ID and file name, so favourites, ratings and history still point at it;
  - loops you starred, rated, edited or made variations of are left exactly as they are (and listed);
  - the old file is kept under _data/loop_backup/ (delete that folder once you're happy);
  - songs where Beat This finds no steady 4/4 grid are left alone.

    digitalcrate reloop            dry run: how many loops are off the downbeat
    digitalcrate reloop --fix      re-cut them
"""
import json
import shutil
import time

import numpy as np

from . import config as C
from .db import connect

TOL = 0.07  # s: a loop starting this close to a downbeat is fine


def _protected(con):
    """sample ids you've touched: starred, rated (not just played), edited or varied."""
    p = {r[0] for r in con.execute("SELECT s.id FROM favorites f JOIN samples s ON s.path=f.path")}
    p |= {r[0] for r in con.execute("""SELECT DISTINCT s.id FROM events e JOIN samples s ON s.path=e.path
                                       WHERE e.type != 'listen'""")}
    p |= {r[0] for r in con.execute("SELECT DISTINCT parent_id FROM samples WHERE parent_id IS NOT NULL")}
    try:
        p |= {r[0] for r in con.execute("SELECT DISTINCT sample_id FROM variants")}
    except Exception:
        pass
    return p


def _grid(beats, downs):
    if len(beats) < 17 or len(downs) < 5:
        return None
    ibi = np.diff(beats)
    if ibi.std() / ibi.mean() >= 0.12:
        return None
    per_bar = np.median([((beats >= a - 0.03) & (beats < b - 0.03)).sum() for a, b in zip(downs[:-1], downs[1:])])
    if per_bar != 4:
        return None
    return float(np.polyfit(np.arange(len(beats)), beats, 1)[0])


def run(fix=False, limit=None):
    from tqdm import tqdm
    from .analyze import beat_this, _fold
    from .audio import decode, write_wav, to_mono48
    con = connect()
    prot = _protected(con)
    tracks = con.execute("""SELECT DISTINCT t.id, t.path, t.artist, t.title FROM tracks t JOIN samples s ON s.track_id=t.id
                            WHERE s.kind='loop' AND s.parent_id IS NULL AND s.category != 'Percussion'
                            AND s.path NOT LIKE '_Reference/%' ORDER BY t.id""").fetchall()[:limit]
    st = dict(tracks=len(tracks), loops=0, on_beat=0, off_beat=0, fixed=0, kept_yours=0, no_grid=0, failed=0)
    backup = C.DATA_DIR / "loop_backup"
    cl = None
    for t in tqdm(tracks, desc="reloop", mininterval=5):
        loops = con.execute("""SELECT * FROM samples WHERE track_id=? AND kind='loop' AND parent_id IS NULL
                               AND category != 'Percussion'""", (t["id"],)).fetchall()
        st["loops"] += len(loops)
        try:
            y = decode(t["path"])
            beats, downs = beat_this(y)
        except Exception as e:
            print(f"  {t['artist']} - {t['title']}: {e}")
            st["failed"] += len(loops)
            continue
        period = _grid(beats, downs)
        if period is None:
            st["no_grid"] += len(loops)
            continue
        bar = 4 * period
        todo = []
        for s in loops:
            k = int(np.argmin(np.abs(downs - s["start"])))
            if abs(downs[k] - s["start"]) <= TOL:
                st["on_beat"] += 1
                continue
            st["off_beat"] += 1
            if s["id"] in prot:
                st["kept_yours"] += 1
                continue
            L = int(s["bars"] or round(s["dur"] / bar))
            a = float(downs[k])
            b = float(downs[k + L]) if k + L < len(downs) else a + L * bar
            todo.append((s, a, b))
        if not fix or not todo:
            continue
        print(f"NOW {t['artist']} - {t['title']}", flush=True)
        stems = None
        if any(s["rendered_from"] != "mix" for s, _, _ in todo):
            from . import models
            stems = models.separate(y)
        if cl is None:
            from .models import clap
            cl = clap()
        for s, a, b in todo:
            sig = y if s["rendered_from"] == "mix" else stems.get(s["rendered_from"])
            if sig is None:
                st["failed"] += 1
                continue
            clip = sig[:, int(a * C.SR):min(sig.shape[1], int(b * C.SR))]
            if clip.shape[1] < C.SR:
                st["failed"] += 1
                continue
            f = C.LIB_ROOT / s["path"]
            if f.exists():
                (backup / s["path"]).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, backup / s["path"])
            write_wav(f, clip, fade_in=0.003, fade_out=0.003)
            m = clip.mean(0)
            if len(m) > C.SR * 10:
                mid = len(m) // 2
                m = m[mid - C.SR * 5: mid + C.SR * 5]
            emb = cl.embed_audio([to_mono48(m)])[0]
            amp = np.abs(clip).max(0)
            env = [float(x.max()) for x in np.array_split(amp, 64)]
            env = (np.array(env) / (max(env) + 1e-9) * 99).astype(int).tolist()
            con.execute("""UPDATE samples SET start=?, dur=?, bpm=?, clap=?, env=?,
                           ops=json_set(COALESCE(ops,'{}'), '$.recut', ?) WHERE id=?""",
                        (a, b - a, round(_fold(60.0 / period), 2), emb.astype(np.float16).tobytes(), json.dumps(env),
                         f"moved {a - s['start']:+.2f}s onto the downbeat", s["id"]))
            con.commit()
            st["fixed"] += 1
    print("SUMMARY " + json.dumps(st))
    verb = "re-cut" if fix else "would re-cut"
    print(f"{st['loops']} loops in {st['tracks']} songs: {st['on_beat']} already on the downbeat, {st['off_beat']} off it "
          f"({st['kept_yours']} of those are ones you starred, rated or edited: left alone); "
          f"{st['fixed'] if fix else st['off_beat'] - st['kept_yours']} {verb}; "
          f"{st['no_grid']} in songs without a steady 4/4 grid left alone.")
    if fix and st["fixed"]:
        print(f"old files: {backup}  (rebuild the page to see the new waveforms: digitalcrate build)")
    return st
