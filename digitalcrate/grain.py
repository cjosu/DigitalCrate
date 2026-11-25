"""Separation grain: the watery, flickering "musical noise" a stem gets where the separator pulled loud vocals or
drums out of the same frequencies. The cleanliness score can't hear it (the stem *is* clean of drums), so a sample cut
from a stem can score 1.0 and still sound grainy.

How: compare the stem with the original mix at the same spot. Their ratio, per frequency, is the separator's mask; a
mask that flickers from frame to frame between 1 and 8 kHz (weighted by where the stem has energy) is what the grain
sounds like. 0 = the stem is the mix (no grain). Checked by ear on 12 samples: under 0.01 clean, 0.06 there if you
listen for it, 0.075 noticeable, 0.09 obvious, 0.15 bad. About 40% of instrument-stem cuts are 0.07 or more.

    score(stem, mix)   -> 0..~0.5 (mono or (channels, n) arrays of the same stretch, at C.SR)
    run()              the library pass: every sample cut from the instrument stem; grainy ones rank lower (quality)
                       and are tagged (vocal stems: not yet, the line was set by ear on instrument stems)
"""
import numpy as np

from . import config as C
from .db import connect

GRAINY = 0.07   # at or above: audibly grainy (checked by ear)
GRAINY_FT = 0.085  # the same for htdemucs_ft cuts: by ear 0.063 "very good", 0.080 "much better", 0.089 still grainy


def score(stem, mix):
    import librosa
    s = np.asarray(stem, np.float32)
    m = np.asarray(mix, np.float32)
    s = s.mean(0) if s.ndim > 1 else s
    m = m.mean(0) if m.ndim > 1 else m
    n = min(len(s), len(m))
    if n < 4096:
        return 0.0
    S = np.abs(librosa.stft(s[:n], n_fft=2048, hop_length=512))
    M = np.abs(librosa.stft(m[:n], n_fft=2048, hop_length=512))
    f = librosa.fft_frequencies(sr=C.SR, n_fft=2048)
    band = (f > 1000) & (f < 8000)
    R = np.clip(S[band] / (M[band] + 1e-6), 0, 1.5)
    w = S[band][:, 1:]
    return round(float((np.abs(np.diff(R, axis=1)) * w).sum() / (w.sum() + 1e-9)), 3)


def penalty(g):
    """Quality multiplier: none up to 0.05, then down to 0.6 by 0.15 (a grainy sample sinks, it isn't hidden)."""
    return float(1 - np.clip((g - 0.05) / 0.10, 0, 1) * 0.4)


def _db():
    con = connect()
    cols = {r[1] for r in con.execute("PRAGMA table_info(samples)")}
    for c in ("grain", "quality_raw"):
        if c not in cols:
            con.execute(f"ALTER TABLE samples ADD COLUMN {c} REAL")
    return con


def line(model):
    """The grain at which a cut sounds grainy: htdemucs_ft's grain reads higher for what sounds cleaner."""
    return GRAINY_FT if model == "htdemucs_ft" else GRAINY


def apply(con, sid, g, model=None):
    """Store the grain, and scale the quality by it (from the original quality, so it can be redone)."""
    r = con.execute("SELECT quality, quality_raw FROM samples WHERE id=?", (sid,)).fetchone()
    raw = r["quality_raw"] if r["quality_raw"] is not None else r["quality"]
    shift = line(model) - GRAINY  # the penalty starts later for a cut whose grain reads high
    con.execute("UPDATE samples SET grain=?, quality_raw=?, quality=? WHERE id=?",
                (g, raw, round(raw * penalty(g - shift), 3), sid))


def run(redo=False):
    from .audio import decode
    from .memguard import breathe
    con = _db()
    rows = con.execute(f"""SELECT s.id, s.path, s.start, s.kind, t.id tid, t.path tpath FROM samples s
                           JOIN tracks t ON t.id = s.track_id
                           WHERE s.rendered_from = 'other' AND s.parent_id IS NULL AND s.category != 'Percussion'
                           {'' if redo else 'AND s.grain IS NULL'} ORDER BY t.id""").fetchall()
    print(f"TASK checking {len(rows)} stem samples for separation grain", flush=True)
    by = {}
    for r in rows:
        by.setdefault(r["tid"], []).append(r)
    done, grainy = 0, 0
    for k, (tid, rs) in enumerate(by.items(), 1):
        if k % 10 == 1:
            breathe()
        try:
            mix = decode(rs[0]["tpath"]).mean(0)
        except Exception as e:
            print(f"    {rs[0]['tpath']}: {str(e)[:80]}", flush=True)
            continue
        for r in rs:
            f = C.LIB_ROOT / r["path"]
            if not f.exists() or r["start"] is None:
                continue
            try:
                st = decode(f).mean(0)
                a = max(0, int((r["start"] - (0 if r["kind"] == "loop" else 0.03)) * C.SR))  # as mining cut it
                g = score(st, mix[a:a + len(st)])
            except Exception as e:
                print(f"    {r['path']}: {str(e)[:80]}", flush=True)
                continue
            apply(con, r["id"], g)
            con.commit()  # right away: a write lock held across the next item's audio work blocks the app (saving, ratings) for minutes
            done += 1
            grainy += g >= GRAINY
        con.commit()
        print(f"grain: {done}/{len(rows)} [{grainy} grainy]", flush=True)
    print(f"TASK DONE {grainy} of {done} stem samples are grainy (ranked lower, tagged)", flush=True)


def reapply():
    """Scale every scored sample's quality again (after the line moved): from its original quality."""
    con = _db()
    cols = {r[1] for r in con.execute("PRAGMA table_info(samples)")}
    rows = con.execute(f"SELECT id, grain, {'recut' if 'recut' in cols else 'NULL'} recut FROM samples "
                       "WHERE grain IS NOT NULL").fetchall()
    for r in rows:
        apply(con, r["id"], r["grain"], r["recut"])
    con.commit()
    return len(rows)


def recut(min_grain=GRAINY, model=None, limit=None):
    """Cut the grainy samples again from a better separation (htdemucs_ft: blind listening found it far less grainy),
    in place: same file, same id, so favorites, sketches and collections still point at them. Kept only if it's
    clearly less grainy; the old file is backed up to _data/recut_backup/. Its sound embedding and sustain loop are
    redone too."""
    import shutil
    from . import models
    from .audio import decode, write_wav, to_mono48
    from .memguard import breathe
    model = model or C.DEMUCS_MODEL
    con = _db()
    cols = {r[1] for r in con.execute("PRAGMA table_info(samples)")}
    if "recut" not in cols:
        con.execute("ALTER TABLE samples ADD COLUMN recut TEXT")
    rows = con.execute("""SELECT s.*, t.path tpath FROM samples s JOIN tracks t ON t.id = s.track_id
                          WHERE s.rendered_from = 'other' AND s.grain >= ? AND s.parent_id IS NULL
                          AND (s.recut IS NULL OR s.recut != ?) ORDER BY t.id""", (min_grain, model)).fetchall()
    rows = rows[:limit] if limit else rows
    print(f"TASK cutting {len(rows)} grainy samples again with {model}", flush=True)
    backup = C.DATA_DIR / "recut_backup"
    backup.mkdir(parents=True, exist_ok=True)
    cl = models.clap()
    better, cur_t, full = 0, None, None
    for k, r in enumerate(rows, 1):
        if k % 10 == 1:
            breathe()
        f = C.LIB_ROOT / r["path"]
        try:
            if not f.exists():
                continue
            if r["track_id"] != cur_t:
                full, cur_t = decode(r["tpath"]), r["track_id"]
            old = decode(f)
            n = old.shape[1]
            a0 = max(0, int((r["start"] - (0 if r["kind"] == "loop" else 0.03)) * C.SR))
            lo, hi = max(0, a0 - 10 * C.SR), min(full.shape[1], a0 + n + 10 * C.SR)  # 10 s of context either side
            y = np.ascontiguousarray(full[:, lo:hi])
            new = models.separate(y, model)["other"][:, a0 - lo:a0 - lo + n]
            if new.shape[1] < n:
                continue
            mix = full[:, a0:a0 + n]
            g = score(new, mix)
            if g < (r["grain"] or 0) - 0.005:
                shutil.copy2(f, backup / f.name)
                write_wav(f, new, fade_in=0.003, fade_out=0.003 if r["kind"] == "loop" else 0.12)
                m = decode(f).mean(0)
                if len(m) > C.SR * 10:
                    m = m[len(m) // 2 - C.SR * 5: len(m) // 2 + C.SR * 5]
                e = cl.embed_audio([to_mono48(m)])[0]
                con.execute("UPDATE samples SET clap=?, recut=?, loop_q=NULL, loop_start=NULL, loop_end=NULL, "
                            "loop_xf=NULL WHERE id=?", (e.astype(np.float16).tobytes(), model, r["id"]))
                apply(con, r["id"], g, model)
                better += 1
            else:
                con.execute("UPDATE samples SET recut=? WHERE id=?", (model, r["id"]))  # tried: no better
            con.commit()  # right away: a write lock held across the next item's audio work blocks the app (saving, ratings) for minutes
        except Exception as ex:
            con.rollback()
            print(f"    {r['path']}: {str(ex)[:100]}", flush=True)
        if k % 10 == 0 or k == len(rows):
            print(f"recut: {k}/{len(rows)} [{better} cleaner]", flush=True)
    con.commit()
    if better:  # the page's grain tags and quality follow
        try:
            from .build import build
            print("BUILDING", flush=True)
            build()
            print("BUILD DONE", flush=True)
        except Exception as e:
            print(f"    build failed: {str(e)[:100]}", flush=True)
    print(f"TASK DONE {better} of {len(rows)} grainy samples are cleaner now (old files in _data/recut_backup)", flush=True)
